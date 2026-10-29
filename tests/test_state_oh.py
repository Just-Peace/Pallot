"""Ohio's statewide races (states/oh.py), transcribed by hand from the SOS's sample ballot and
imported (bundles/manual.py), with the U.S. House race from the FEC, and its key dates worked out
from the Ohio Revised Code, without ever asking ohiosos.gov. tests/fixtures/state_oh.json is a
copy of manual/state_oh/ohio.json."""

from __future__ import annotations

import copy
import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from bundles import store
from bundles.entry import BundleError
from bundles.manual import import_list
from pallot.states import key_dates as state_key_dates
from pallot.states.oh import OhList

from .bundling import build
from .conftest import FIXTURES, TODAY, candidate_names, find_race, get_ballot, switch

LIST = FIXTURES / "state_oh.json"


def imported(tmp_path) -> dict:
    outcome = import_list("oh", LIST, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert outcome.status == "updated"
    return outcome.counts


def ohio_calls(upstream) -> int:
    return upstream.count("ohiosos")


def test_ohios_list_has_its_statewide_races_with_the_governors_ticket():
    filings = OhList.parse(LIST.read_text(encoding="utf-8"))
    assert {(f.day, f.reach, f.district) for f in filings} == {("2026-11-03", "state", None)}
    governor = [f for f in filings if f.office_id == "GOVERNOR"]
    assert [(f.name, f.party, f.office, f.group) for f in governor] == [
        ("Amy Acton and David Pepper", "D", "Governor and Lieutenant Governor", "state"),
        ("Don Kissick and James L. Mills", "L", "Governor and Lieutenant Governor", "state"),
        ("Vivek Ramaswamy and Robert A. McColley", "R", "Governor and Lieutenant Governor", "state")]
    senate = [f for f in filings if f.office_id == "US SENATE"]
    assert {(f.office, f.group, f.unexpired) for f in senate} == {("U.S. Senator", "federal", True)}
    assert [(f.name, f.party, f.party_name) for f in senate] == [
        ("Sherrod Brown", "D", None), ("Jon Husted", "R", None), ("Greg Levy", None, "Other party"),
        ("William B. Redpath", "L", None)]
    assert not any(f.unexpired for f in filings if f.office_id != "US SENATE")
    courts = sorted({(f.office_id, f.office, f.family, f.group) for f in filings if f.family == "SUPREME COURT"})
    assert courts == [
        ("SUPREME COURT JANUARY 1, 2027", "Justice of the Supreme Court (term beginning January 1, 2027)",
         "SUPREME COURT", "judicial"),
        ("SUPREME COURT JANUARY 2, 2027", "Justice of the Supreme Court (term beginning January 2, 2027)",
         "SUPREME COURT", "judicial")]
    assert [f.name for f in filings if f.office_id == "SUPREME COURT JANUARY 2, 2027"] == [
        "Jennifer Brunner", "Colleen O’Donnell"]
    assert [f.office_id for f in filings if f.name in ("Keith Faber", "Frank LaRose", "Allison Russo", "Seth Walsh")] == [
        "ATTORNEY GENERAL", "AUDITOR OF STATE", "SECRETARY OF STATE", "TREASURER OF STATE"]
    assert len(filings) == 20 and not any(f.write_in for f in filings)


def test_two_races_for_one_office_without_a_term_are_numbered():
    court = {"office": "Justice of the Supreme Court", "candidates": [{"name": "A B", "party": "Republican"}]}
    filings = OhList.parse(_changed(contests=[court, court]))
    assert [(f.office_id, f.office) for f in filings] == [
        ("SUPREME COURT 1", "Justice of the Supreme Court (1)"), ("SUPREME COURT 2", "Justice of the Supreme Court (2)")]


def _changed(**changes) -> str:
    data = copy.deepcopy(json.loads(LIST.read_text(encoding="utf-8")))
    for key, value in changes.items():
        data[key] = value
    return json.dumps(data)


@pytest.mark.parametrize("raw", [
    "", "<html><title>Just a moment...</title></html>", "[]",
    _changed(scope={"type": "full_ballot"}),
    _changed(scope=None),
    _changed(contests=[]),
    _changed(contests=[{"office": "Governor and Lieutenant Governor", "candidates": []}]),
    _changed(election={"name": "General Election"}),
    _changed(contests=[{"office": "Attorney General", "candidates": [{"party": "Republican"}]}]),
])
def test_a_file_that_isnt_ohios_statewide_list_is_refused(raw):
    with pytest.raises(ValueError):
        OhList.parse(raw)


def test_the_import_bundles_the_statewide_races(tmp_path):
    assert imported(tmp_path) == {"races": 8, "candidates": 20}
    [answer] = store.load("state_oh", tmp_path / "bundles").answers
    assert answer["request"]["url"] == "manual:state_oh" and set(answer["value"]) == {"filings"}
    again = import_list("oh", LIST, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert again.status == "no_changes"


def test_the_import_refuses_another_scope_and_writes_nothing(tmp_path):
    saved = tmp_path / "ohio.json"
    saved.write_text(_changed(scope={"type": "county_ballot"}), encoding="utf-8")
    with pytest.raises(BundleError, match="scope is 'county_ballot'"):
        import_list("oh", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    saved.write_text("<html><title>Just a moment...</title></html>", encoding="utf-8")
    with pytest.raises(BundleError, match="the site's bot check"):
        import_list("oh", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert not (tmp_path / "bundles" / "state_oh.json").exists()


def test_refreshing_the_bundles_never_fetches_ohios_list(tmp_path, upstream):
    outcome = build(tmp_path, "state_oh")
    assert outcome.status == "skipped" and "imported by hand" in outcome.detail
    assert ohio_calls(upstream) == 0


def test_a_columbus_ballot_has_the_statewide_races_and_the_fecs_house_race(tmp_path, upstream, make_app, logged_calls):
    imported(tmp_path)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "columbus")
        assert ballot["coverage"]["ballot"] == "list" and ballot["coverage"]["districts"] == ["cd", "sd", "hd"]
        assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (15, 15, 1)
        assert [race["name"] for race in ballot["races"]] == [
            "U.S. Senator", "U.S. Representative District 15", "Governor and Lieutenant Governor", "Attorney General",
            "Auditor of State", "Secretary of State", "Treasurer of State",
            "Justice of the Supreme Court (term beginning January 1, 2027)",
            "Justice of the Supreme Court (term beginning January 2, 2027)"]
        senate = find_race(ballot, "U.S. Senator")
        assert senate["unexpired"] and senate["source"] == "state_oh"
        assert not any(c["unverified"] for c in senate["candidates"])
        house = find_race(ballot, "U.S. Representative District 15")
        assert house["source"] == "fec" and all(c["unverified"] for c in house["candidates"])
        assert candidate_names(house)[0] == "Mike Carey"
        assert candidate_names(find_race(ballot, "Governor and Lieutenant Governor"))[0] == "Amy Acton and David Pepper"
        assert any("isn't covered: your county board of elections' sample ballot has it" in n for n in ballot["notes"])
        assert ballot["key_dates"] == {
            "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-05",
            "mail_apply_by": "2026-10-27", "early_voting_start": "2026-10-06", "early_voting_end": "2026-11-01",
            "source": "Ohio Secretary of State", "source_url": "https://www.ohiosos.gov/elections/", "computed": True,
        }
        get_ballot(client, "columbus")
        assert logged_calls() == 0
        rows = {row["id"]: row for row in client.get("/api/sources").json()["sources"]}
        assert rows["state_oh"]["notice"].startswith("Imported by hand on ")
    assert ohio_calls(upstream) == 0


def test_with_the_fec_off_ohio_keeps_its_statewide_races(tmp_path, upstream, make_app):
    imported(tmp_path)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        switch(client, "fec", False)
        ballot = get_ballot(client, "columbus")
        names = [race["name"] for race in ballot["races"]]
        assert "U.S. Senator" in names and not any(name.startswith("U.S. Representative") for name in names)
        assert any("The FEC is turned off, so the U.S. House race isn't shown" in n for n in ballot["notes"])
    assert ohio_calls(upstream) == 0


def test_when_the_fec_cant_be_had_ohio_keeps_its_statewide_races(tmp_path, upstream, make_app):
    imported(tmp_path)
    upstream.fec_status = 500
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "columbus")
        assert find_race(ballot, "Governor and Lieutenant Governor")
        assert not any(race["name"].startswith("U.S. Representative") for race in ballot["races"])
        assert any("Couldn't load the FEC's filers for the U.S. House race" in w for w in ballot["warnings"])


def test_without_an_imported_list_ohio_has_the_fecs_races_for_congress(client, upstream):
    ballot = get_ballot(client, "columbus")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("doesn't have the Ohio Secretary of State's list of candidates" in n for n in ballot["notes"])
    assert find_race(ballot, "U.S. Representative District 15")
    assert ohio_calls(upstream) == 0


@pytest.mark.parametrize("day, register, apply, early, end", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 5), dt.date(2026, 10, 27), dt.date(2026, 10, 6), dt.date(2026, 11, 1)),
    (dt.date(2028, 11, 7), dt.date(2028, 10, 10), dt.date(2028, 10, 31), dt.date(2028, 10, 11), dt.date(2028, 11, 5)),
    (dt.date(2030, 11, 5), dt.date(2030, 10, 7), dt.date(2030, 10, 29), dt.date(2030, 10, 8), dt.date(2030, 11, 3)),
])
def test_ohios_key_dates_are_worked_out_from_its_statutes(day, register, apply, early, end):
    found = state_key_dates.computed("OH", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, apply, early, end, "OH")
    assert state_key_dates.computed("OH", dt.date(2026, 11, 10)) is None


def test_ohios_calendar_file_has_its_dates(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "OH"})
    assert response.status_code == 200 and "ohio-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls are open 6:30 a.m. to 7:30 p.m." in text and "20261005" in text
