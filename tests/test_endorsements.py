"""The frozen endorsement lists: every file that comes with Pallot is valid, a list's cards and
how its entries meet the ballot's races, and its row in Settings (tests/fixtures/endorsements
holds a made-up one)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pallot.admin import SOURCES
from pallot.models import Candidate, Race
from pallot.offices import classify
from pallot.settings import Settings
from pallot.sources.endorsements import ENDORSEMENTS_DIR, FLAG, BadList, load_all, parse

from .conftest import FIXTURES, get_ballot

EXAMPLE = FIXTURES / "endorsements" / "examplepac.json"
BUILT_IN = {info.id for info in SOURCES}


def test_every_list_that_comes_with_pallot_is_valid():
    lists = load_all(ENDORSEMENTS_DIR, reserved=BUILT_IN)  # none yet: each organization's pull request adds its file
    assert len({found.source for found in lists}) == len(lists)
    assert all(found.entries for found in lists)


def write(tmp_path: Path, change=None, name: str = "examplepac.json") -> Path:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    if change:
        change(data)
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("change, message", [
    (lambda d: d.pop("captured"), "is missing captured"),
    (lambda d: d.update(capture="2026-09-20"), "unknown fields: capture"),
    (lambda d: d.update(captured="Sept 20"), "captured must be a date"),
    (lambda d: d.update(source="other"), "source must be the file's name"),
    (lambda d: d.update(url="example.org"), "url must be an http(s) link"),
    (lambda d: d.update(label=" "), "label must be non-empty text"),
    (lambda d: d.update(candidates=[]), "at least one candidate"),
    (lambda d: d["candidates"][1].pop("office"), "candidates[1].office must be non-empty text"),
    (lambda d: d["candidates"][0].update(state="Texas"), "candidates[0].state must be a two-letter postal code"),
    (lambda d: d["candidates"][0].update(seat="TX-SEN"), "candidates[0] has unknown fields: seat"),
    (lambda d: d["candidates"][0].update(district=["1"]), "candidates[0].district must be text"),
    (lambda d: d["candidates"][0].update(url="javascript:alert(1)"), "candidates[0].url must be an http(s) link"),
])
def test_a_malformed_list_is_refused_with_where(tmp_path, change, message):
    with pytest.raises(BadList, match=r"examplepac\.json") as refused:
        parse(write(tmp_path, change))
    assert message in str(refused.value)


def test_a_list_cant_take_another_sources_id(tmp_path):
    write(tmp_path, lambda d: d.update(source="fec"), name="fec.json")
    with pytest.raises(BadList, match="already another source's id"):
        load_all(tmp_path, reserved=BUILT_IN)
    assert load_all(tmp_path / "none") == []


def test_lists_are_found_in_the_folder_by_label(tmp_path):
    write(tmp_path)
    write(tmp_path, lambda d: d.update(source="another", label="Another PAC"), name="another.json")
    assert [found.source for found in load_all(tmp_path, reserved=BUILT_IN)] == ["another", "examplepac"]


def race(name, *candidates, key="sos:1:1", group="state", seat=None):
    return Race(key=key, name=name, group=group, source="sos", seat=seat,
                candidates=[Candidate(key=f"{key}:{i}", name=n, party=p) for i, (n, p) in enumerate(candidates)])


def test_cards_match_texas_entries_by_seat_and_name():
    example = parse(EXAMPLE)
    races = [
        race("U.S. Senator", ("Ken Paxton", "R"), ("James Talarico", "D"), key="sos:1:2", group="federal", seat="TX-SEN"),
        race("U.S. Representative District 10", ("Chris Gober", "R"), key="sos:1:10", group="federal", seat="TX-10"),
        race("State Representative District 49", ("Montserrat Garibay", "D"), key="sos:1:49", group="legislature"),
        race("Justice, Supreme Court, Place 8", ("Gisela D. Triana", "D"), key="sos:1:8"),
        race("Justice, Supreme Court, Place 7", ("Kyle Hawkins", "R"), ("Kristen Hawkins", "D"), key="sos:1:7"),
        race("County Commissioner Precinct 2", ("Brigid Shea", "D"), key="sos:1:3", group="precinct"),
    ]
    scopes = {"sos:1:49": classify("STATE REPRESENTATIVE, DISTRICT 49", "SR", set()),
              "sos:1:8": classify("JUSTICE, SUPREME COURT, PLACE 8", "SW", set())}
    found = example.cards(races, scopes, "Travis").candidates
    assert sorted(found) == ["sos:1:2:1", "sos:1:3:0", "sos:1:49:0", "sos:1:8:0"]
    assert {key: card.match.confidence for key, card in found.items()} == {
        "sos:1:2:1": "exact", "sos:1:3:0": "exact", "sos:1:49:0": "exact", "sos:1:8:0": "exact"}
    # Chris Gober is on the list for California's 10th, never Texas's; "K. Hawkins" is both Kyle and Kristen.

    talarico = found["sos:1:2:1"]
    assert (talarico.source, talarico.label, talarico.as_of, talarico.flags) == ("examplepac", "Example PAC", "2026-09-20", [FLAG])
    assert [(b.text, b.tone, b.url) for b in talarico.badges] == [
        ("Endorsed by Example PAC", "good", "https://example.org/endorsements/talarico")]
    assert {f.label: f.value for f in talarico.facts} == {
        "Endorsed by": "Example Peace Action Committee", "Office on the list": "U.S. Senate",
        "Party on the list": "Democrat", "List captured": "Sep 20, 2026"}
    assert talarico.quotes == ["Endorsed for the general election."]
    assert [(link.label, link.url) for link in talarico.links] == [
        ("Example PAC's endorsement list", "https://example.org/endorsements")]
    shea = found["sos:1:3:0"]
    assert shea.url == "https://example.org/endorsements" and shea.links == [] and shea.quotes == []
    assert {f.label: f.value for f in shea.facts}["Office on the list"] == "County Commissioner, District 2"


def test_the_file_keeps_every_state_and_the_ballots_state_is_matched():
    example = parse(EXAMPLE)
    assert (example.count(), example.count("TX"), example.count("CA"), example.states()) == (7, 5, 1, 3)
    races = [race("U.S. Representative District 10", ("Chris Gober", "R"), key="ca:1:10", group="federal", seat="CA-10"),
             race("U.S. Senator", ("James Talarico", "D"), key="ca:1:2", group="federal", seat="CA-SEN")]
    found = example.cards(races, {}, None, state="CA").candidates
    assert list(found) == ["ca:1:10:0"] and found["ca:1:10:0"].match.confidence == "exact"


def test_another_seat_is_only_likely():
    found = parse(EXAMPLE).cards([race("State Representative District 50", ("Montserrat Garibay", "D"),
                                       key="sos:1:50", group="legislature")],
                                 {"sos:1:50": classify("STATE REPRESENTATIVE, DISTRICT 50", "SR", set())}, None)
    match = found.candidates["sos:1:50:0"].match
    assert (match.confidence, match.note) == ("likely", "Example PAC lists them for State House, District 49")


@pytest.mark.parametrize("listed", ["Rev. Frederick D. Haynes III", "Rev. Dr. Frederick D. Haynes III",
                                    "Honorable Frederick D. Haynes III", "Judge Frederick D. Haynes III"])
def test_a_title_before_the_name_still_matches_exactly(tmp_path, listed):
    entry = {"name": listed, "state": "TX", "office": "U.S. House", "district": "30"}
    found = parse(write(tmp_path, lambda d: d["candidates"].append(entry))).cards(
        [race("U.S. Representative District 30", ("FREDERICK HAYNES", "D"), key="sos:1:30", group="federal", seat="TX-30")],
        {}, None).candidates
    assert found["sos:1:30:0"].match.confidence == "exact"


def test_the_ballot_settings_and_the_pages_list(client, upstream):
    ballot = get_ballot(client)
    senate = next(r for r in ballot["races"] if r["name"] == "U.S. Senator")
    card = next(c for c in senate["candidates"][1]["cards"] if c["source"] == "examplepac")
    assert card["badges"][0]["text"] == "Endorsed by Example PAC" and card["flags"] == [FLAG]
    calls = len(upstream.calls)
    assert get_ballot(client)["meta"]["external_calls"] == 0 and len(upstream.calls) == calls

    row = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "examplepac")
    assert (row["label"], row["toggleable"], row["enabled"], row["frozen"], row["refreshable"], row["resettable"]) == (
        "Example PAC endorsements", True, True, True, False, False)
    assert row["notice"] == ("A frozen list from [Example Peace Action Committee](https://example.org/endorsements), "
                             "captured on Sep 20, 2026. It came with Pallot, and Pallot never fetches it.")
    assert [(f["label"], f["value"]) for f in row["details"]] == [
        ("Captured", "Sep 20, 2026"), ("Texas candidates", "5"), ("All candidates", "7 in 3 states")]
    assert row["last_use"] == {"id": "examplepac", "label": "Example PAC", "status": "used", "as_of": "2026-09-20",
                               "calls": 0, "message": None}
    assert client.post("/api/sources/examplepac/refresh").status_code == 400
    assert client.post("/api/sources/examplepac/clear").status_code == 400
    assert client.post("/api/cache/clear").status_code == 200  # Clear all leaves it be

    assert [found for found in client.get("/api/endorsements").json() if not found["live"]] == [{
        "source": "examplepac", "label": "Example PAC", "organization": "Example Peace Action Committee",
        "url": "https://example.org/endorsements", "captured": "2026-09-20",
        "description": "A made-up organization's endorsements, for the tests.", "live": False, "enabled": True,
    }]


def test_turned_off_it_adds_no_cards_and_stays_off(make_app, tmp_path):
    with TestClient(make_app()) as client:
        assert client.put("/api/sources/examplepac", json={"enabled": False}).status_code == 200
        ballot = get_ballot(client)
        assert not [c for r in ballot["races"] for p in r["candidates"] for c in p["cards"] if c["source"] == "examplepac"]
        row = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "examplepac")
        assert row["enabled"] is False and row["last_use"]["status"] == "off"
    with TestClient(make_app()) as client:
        assert next(found for found in client.get("/api/endorsements").json() if found["source"] == "examplepac")[
            "enabled"] is False
    with TestClient(make_app(endorsements_dir=tmp_path / "none")) as client:  # its file gone: its switch is ignored
        assert "examplepac" not in [s["id"] for s in client.get("/api/sources").json()["sources"]]
        assert [found["source"] for found in client.get("/api/endorsements").json() if not found["live"]] == []


def test_settings_only_keep_switches_for_known_sources(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"sources": {"examplepac": False, "gone": False}}), encoding="utf-8")
    assert Settings(path, ["examplepac"]).enabled("examplepac") is False
    assert Settings(path).enabled("examplepac") is True  # a list that's no longer there
    with pytest.raises(KeyError):
        Settings(path).set_enabled("examplepac", True)
