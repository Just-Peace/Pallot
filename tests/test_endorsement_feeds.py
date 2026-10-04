"""The live endorsement feeds: each organization's adapter, the cards they give like a frozen
list's, the copy kept a week (a second lookup asks no one), a refusal's pause, and the row in
Settings with Refresh and Clear (tests/fixtures/endorsement_feeds holds each recorded list)."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from pallot.admin import SOURCES
from pallot.models import Candidate, Race
from pallot.sources.endorsement_feeds import FEEDS, muslims_united
from pallot.sources.endorsements import ENDORSEMENTS_DIR, FLAG, EndorsementList, read_entry

from .conftest import get_ballot, last_use, load

MUPAC = "mupac"
FEED_HOST = "muslimsunitedpac.com"


def row(client: TestClient, source: str = MUPAC) -> dict:
    return next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == source)


def cards_from(ballot: dict, source: str = MUPAC) -> dict[str, dict]:
    return {p["name"]: c for r in ballot["races"] for p in r["candidates"] for c in p["cards"] if c["source"] == source}


def test_feed_ids_are_their_own():
    ids = [feed.source for feed in FEEDS]
    files = {path.stem for path in ENDORSEMENTS_DIR.glob("*.json")}
    assert len(set(ids)) == len(ids) and not set(ids) & ({info.id for info in SOURCES} | files)


def test_muslims_united_entries():
    found = {entry["name"]: entry for entry in muslims_united(load(f"endorsement_feeds/{MUPAC}.json"))}
    assert len(found) == 26  # incumbents and challengers; "total" is a count, skipped
    assert found["Al Green"] == {
        "name": "Al Green", "state": "TX", "office": "U.S. House", "district": "18", "party": "Democratic", "note": None,
        "url": "https://muslimsunitedpac.com/endorsements/al-green-tx"}
    assert found["Rashida Tlaib"]["note"].startswith("The only Palestinian-American in Congress")  # its "ourTake"
    assert (found["Bernie Sanders"]["office"], found["Bernie Sanders"]["district"]) == ("U.S. Senate", None)
    assert found["Ruwa Romman"]["office"] == "Governor of Georgia"  # its officeName, which names a seat too
    assert found["Zohran Mamdani"]["office"] == "Mayor of New York City"
    assert [read_entry(raw, n, MUPAC)["name"] for n, raw in enumerate(found.values())] == list(found)


def test_muslims_united_leaves_out_what_it_cant_read():
    with pytest.raises(ValueError):
        muslims_united([])
    answer = {"incumbents": [
        {"id": "1", "name": "Al Green", "officeType": "US House", "state": "TX", "district": "18", "slug": "../x"},
        {"id": "1", "name": "Al Green", "officeType": "US House", "state": "TX", "district": "18"},
        "not a candidate",
    ], "total": 2}
    assert muslims_united(answer) == [{"name": "Al Green", "state": "TX", "office": "U.S. House", "district": "18",
                                       "party": None, "note": None, "url": None}]


def race(name, *candidates, key, seat):
    return Race(key=key, name=name, group="federal", source="sos", seat=seat,
                candidates=[Candidate(key=f"{key}:{i}", name=n, party=p) for i, (n, p) in enumerate(candidates)])


def test_entries_match_as_a_frozen_lists_do():
    entries = [read_entry(raw, n, MUPAC) for n, raw in enumerate(muslims_united(load(f"endorsement_feeds/{MUPAC}.json")))]
    found = EndorsementList(source=MUPAC, label="Muslims United PAC", organization="Muslims United PAC",
                            url="https://muslimsunitedpac.com/endorsements", captured="2026-10-04",
                            description="", entries=entries, live=True)
    races = [race("U.S. Representative District 18", ("Al Green", "D"), ("Ronald Whitfield", "R"), key="sos:1:18", seat="TX-18"),
             race("U.S. Representative District 9", ("Al Green", "D"), key="sos:1:9", seat="TX-09"),
             race("U.S. Representative District 12", ("Rashida Tlaib", "D"), key="sos:1:12", seat="TX-12")]
    cards = found.cards(races, {}, "Harris").candidates
    assert {key: card.match.confidence for key, card in cards.items()} == {"sos:1:18:0": "exact", "sos:1:9:0": "likely"}
    # Rashida Tlaib is on the list for Michigan's 12th, never Texas's.
    green = cards["sos:1:18:0"]
    assert {f.label: f.value for f in green.facts}["List fetched"] == "Oct 4, 2026"
    assert green.url == "https://muslimsunitedpac.com/endorsements/al-green-tx" and green.flags == [FLAG]


def test_the_ballot_fetches_it_once_and_keeps_it(client, upstream):
    assert row(client)["notice"].startswith("Not fetched yet: the first lookup with it on fetches")
    ballot = get_ballot(client, "ut")
    casar = cards_from(ballot)["Greg Casar"]
    today = dt.date.today()
    assert (casar["label"], casar["as_of"], casar["match"]["confidence"], casar["flags"]) == (
        "Muslims United PAC", today.isoformat(), "exact", [FLAG])
    assert [(b["text"], b["url"]) for b in casar["badges"]] == [
        ("Endorsed by Muslims United PAC", "https://muslimsunitedpac.com/endorsements/greg-casar-tx")]
    assert {f["label"]: f["value"] for f in casar["facts"]}["Office on the list"] == "U.S. House, District 37"
    assert casar["quotes"][0].startswith("As Chair of the Congressional Progressive Caucus")
    assert upstream.count(FEED_HOST) == 1
    assert last_use(client, MUPAC)["status"] == "used" and last_use(client, MUPAC)["calls"] == 1

    again = get_ballot(client, "ut")
    assert again["meta"]["external_calls"] == 0 and upstream.count(FEED_HOST) == 1
    get_ballot(client)  # another address, another state's ballot races: the same copy
    assert upstream.count(FEED_HOST) == 1

    endorsements = {found["source"]: found for found in client.get("/api/endorsements").json()}
    assert endorsements[MUPAC] == {
        "source": MUPAC, "label": "Muslims United PAC", "organization": "Muslims United PAC",
        "url": "https://muslimsunitedpac.com/endorsements", "captured": today.isoformat(),
        "description": FEEDS[0].description, "live": True, "enabled": True}


def test_its_settings_row_refreshes_and_clears(client, upstream):
    get_ballot(client, "ut")
    found = row(client)
    assert (found["label"], found["toggleable"], found["enabled"], found["frozen"], found["refreshable"],
            found["resettable"], found["cache"]["entries"]) == (
        "Muslims United PAC endorsements", True, True, False, True, False, 1)
    assert found["notice"].startswith("Fetched from [Muslims United PAC's website](https://muslimsunitedpac.com/endorsements) on ")
    assert found["notice"].endswith("; a lookup fetches it again once it's 7 days old.")
    assert [(f["label"], f["value"]) for f in found["details"]] == [
        ("Texas candidates", "3"), ("All candidates", "26 in 18 states")]
    assert found["clear_confirm"] == "Clear everything cached from Muslims United PAC endorsements? The next lookup will fetch it again."

    refreshed = client.post(f"/api/sources/{MUPAC}/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["message"] == "Refreshed 1 cached response. 3 of its 26 candidates are in Texas."
    assert upstream.count(FEED_HOST) == 2

    cleared = client.post(f"/api/sources/{MUPAC}/clear").json()["message"]
    assert cleared == "Cleared 1 cached response. The next lookup fetches the list again."
    assert row(client)["details"] == []
    assert "Greg Casar" in cards_from(get_ballot(client, "ut")) and upstream.count(FEED_HOST) == 3


def test_refresh_fetches_a_list_never_fetched(client, upstream):
    message = client.post(f"/api/sources/{MUPAC}/refresh").json()["message"]
    assert message == "Refreshed 0 cached responses. 3 of its 26 candidates are in Texas."
    assert upstream.count(FEED_HOST) == 1


def test_a_refusal_pauses_it_and_the_ballot_goes_on(client, upstream):
    upstream.feed_status = 429
    ballot = get_ballot(client, "ut")
    assert not cards_from(ballot) and ballot["races"]
    assert [w for w in ballot["warnings"] if w.startswith("Couldn't load Muslims United PAC's endorsements (")]
    assert last_use(client, MUPAC)["status"] == "error"
    assert upstream.count(FEED_HOST) == 1

    again = get_ballot(client, "ut")
    assert upstream.count(FEED_HOST) == 1  # paused: not asked again
    assert any("paused until" in w and "Muslims United PAC's website refused a request" in w for w in again["warnings"])
    notice = row(client)["notice"]
    assert notice.startswith("Paused until ") and notice.endswith(
        "after Muslims United PAC's website refused a request; the list already fetched still shows.")
    assert row(client)["notice_tone"] == "warn"


def test_an_answer_it_cant_read_is_refused(client, upstream):
    upstream.feed_answers[MUPAC] = {"incumbents": [{"title": "renamed fields"}], "total": 1}
    ballot = get_ballot(client, "ut")
    assert not cards_from(ballot)
    assert "Couldn't load Muslims United PAC's endorsements (a list with no candidate Pallot can read)." in ballot["warnings"]
    assert row(client)["details"] == []


def test_turned_off_it_isnt_asked(make_app, upstream):
    with TestClient(make_app()) as client:
        assert client.put(f"/api/sources/{MUPAC}", json={"enabled": False}).status_code == 200
        ballot = get_ballot(client, "ut")
        assert not cards_from(ballot) and upstream.count(FEED_HOST) == 0
        assert row(client)["enabled"] is False and last_use(client, MUPAC)["status"] == "off"
    with TestClient(make_app()) as client:  # the switch is kept
        assert next(f for f in client.get("/api/endorsements").json() if f["source"] == MUPAC)["enabled"] is False
