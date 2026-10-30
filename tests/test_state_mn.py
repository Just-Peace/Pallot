"""Minnesota's ballot (states/mn.py), from the Secretary of State's election results files for the
general election, posted with every candidate before Election Day, and its key dates worked out from
Minnesota's election law. tests/fixtures/state_mn_*.txt are the files as served (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import key_dates as state_key_dates
from pallot.states import mn
from pallot.states.mn import MnList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch

HOST = "electionresultsfiles.sos.mn.gov"
FILES = (mn.INDEX, *mn.FILES)


def raw(file: str) -> bytes:
    return (FIXTURES / f"state_mn_{file.removesuffix('.txt').lower()}.txt").read_bytes()


def every_filing() -> list:
    return [f for file in FILES for f in MnList.parse(raw(file))]


def test_minnesotas_files_have_congress_the_statewide_offices_and_both_chambers():
    filings = every_filing()
    assert len(filings) == 420 and {f.day for f in filings} == {""} and not any(f.write_in for f in filings)
    races = {f.office_id: f for f in filings}
    assert Counter(f.reach for f in races.values()) == {"state": 5, "cd": 8, "sd": 67, "hd": 134}
    senate = {f.name: (f.party, f.party_name) for f in filings if f.office_id == "US SENATE"}
    assert senate == {"Peggy Flanagan": ("D", None), "Michele Tafoya": ("R", None), "Rebecca Whiting": ("L", None),
                      "Marisa Simonetti": (None, "Independent")}
    governor = sorted((f.name, f.party) for f in filings if f.office_id == "GOVERNOR")
    assert governor == [("Amy Klobuchar and Ben Schierer", "D"), ("Lisa Demuth and Ryan Wilson", "R"),
                        ("Steven Young and Jane Kirby", "G")]
    assert races["GOVERNOR"].office == "Governor and Lieutenant Governor"
    house = races["STATE HOUSE 65B"]
    assert (house.office, house.district, house.reach, house.group) == (
        "State Representative District 65B", "65B", "hd", "legislature")
    assert races["STATE SENATE 65"].district == "65"
    assert {f.party_name for f in filings if f.party is None} == {
        "Independent", "Forward Independence", "United New Independence"}
    one_each = Counter((f.office_id, f.party) for f in filings if f.party)  # the primaries' losers aren't on it
    assert max(one_each.values()) == 1


def test_a_races_candidates_come_by_party_and_its_kinds_in_ballot_order():
    filings = every_filing()
    first = {}
    for f in sorted(filings, key=lambda f: f.order):
        first.setdefault(f.family, f.order)
    assert sorted(first, key=first.get) == ["US SENATE", "US HOUSE", "GOVERNOR", "SECRETARY OF STATE", "STATE AUDITOR",
                                            "ATTORNEY GENERAL", "STATE SENATE", "STATE HOUSE"]
    senate = [f.name for f in sorted(filings, key=lambda f: f.order) if f.office_id == "US SENATE"]
    assert senate == ["Peggy Flanagan", "Michele Tafoya", "Rebecca Whiting", "Marisa Simonetti"]


def test_a_file_that_isnt_one_or_has_an_office_it_doesnt_know_is_refused():
    with pytest.raises(ValueError, match="not one of the Secretary of State's results files"):
        MnList.parse(b"<html><body>Service Unavailable</body></html>")
    with pytest.raises(ValueError, match="not one of the Secretary of State's results files"):
        MnList.parse(b"")
    with pytest.raises(ValueError, match="an office it doesn't know: Dogcatcher"):
        MnList.parse(raw("auditor.txt").replace(b"State Auditor", b"Dogcatcher"))
    assert MnList.read_index(raw("ushouse.txt"))["files"] == list(mn.FILES)
    assert MnList.read_index(raw("governor.txt")) is None


def test_a_saint_paul_ballot_has_its_races_from_the_files(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "stpaul")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (4, 65, "65B")
    assert [race["name"] for race in ballot["races"]] == [
        "U.S. Senator", "U.S. Representative District 4", "Governor and Lieutenant Governor", "Secretary of State",
        "State Auditor", "Attorney General", "State Senator District 65", "State Representative District 65B"]
    assert all(race["source"] == "state_mn" for race in ballot["races"])
    assert "Betty McCollum" in candidate_names(find_race(ballot, "U.S. Representative District 4"))
    assert candidate_names(find_race(ballot, "State Representative District 65B")) == ["Sebastian Ellefson"]
    assert any("judges" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-13",
        "mail_apply_by": "2026-11-02", "early_voting_start": "2026-09-18", "early_voting_end": "2026-11-02",
        "source": "Minnesota Secretary of State", "source_url": "https://www.sos.mn.gov/elections-voting/",
        "computed": True,
    }
    assert upstream.count(HOST) == len(FILES)
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_mn'")]
    assert sorted(sorted(value) for value in kept) == [["files", "filings"]] + [["filings"]] * len(mn.FILES)
    assert "WRITE-IN" not in json.dumps(kept)
    get_ballot(client, "stpaul")
    assert logged_calls() == 0 and upstream.count(HOST) == len(FILES)


def test_files_short_of_the_legislature_arent_served(client, upstream):
    upstream.state_lists[f"{HOST}/20261103/LegislativeByDistrict.txt"] = raw("legislativebydistrict.txt").decode(
        "cp1252").splitlines()[0]
    ballot = get_ballot(client, "stpaul")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Minnesota Secretary of State" in w
               for w in ballot["warnings"])


def test_a_minnesota_file_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "stpaul")
    upstream.state_lists[f"{HOST}/20261103/governor.txt"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_mn")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "stpaul")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "Governor and Lieutenant Governor")


def test_with_minnesotas_list_off_its_ballot_has_congress_from_the_fec(client, upstream):
    switch(client, "state_mn", False)
    ballot = get_ballot(client, "stpaul")
    assert ballot["coverage"]["ballot"] == "fec"
    assert upstream.count(HOST) == 0


def test_minnesotas_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_mn")
    assert outcome.status == "updated" and outcome.answers == len(FILES)
    assert outcome.counts == {"races": 214, "candidates": 420}
    assert upstream.count(HOST) == len(FILES)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "stpaul")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == len(FILES)


def test_minnesotas_2026_key_dates_are_worked_out_from_its_election_law():
    found = state_key_dates.computed("MN", dt.date(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        dt.date(2026, 10, 13), dt.date(2026, 11, 2), dt.date(2026, 9, 18), dt.date(2026, 11, 2), "MN")
    assert state_key_dates.computed("MN", dt.date(2027, 11, 2)) is None


def test_minnesotas_calendar_file_and_when_to_vote_say_you_can_register_on_election_day(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "MN"})
    assert response.status_code == 200 and "minnesota-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "register at your polling place on Election Day" in text
    assert all(day in text for day in ("20261013", "20261102", "20261103"))
    info = state_key_dates.GUIDES["MN"].voter_info()
    assert info.poll_hours == "7 a.m. – 8 p.m." and info.late_registration is not None
    assert info.mail_eligibility.startswith("Any registered voter can vote absentee")
