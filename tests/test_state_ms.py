"""Mississippi's ballot (states/ms.py), from the Secretary of State's Candidate Qualifying List, one
HTML page of every office on file, and its key dates worked out from Title 23 of its code.
tests/fixtures/state_ms.html is the page as served, without its scripts (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot import counties
from pallot.models import Districts
from pallot.states import key_dates as state_key_dates
from pallot.states import ms
from pallot.states.ms import MsList
from pallot.states.place import where

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch

HOST = "www.sos.ms.gov"
LISTED = (FIXTURES / "state_ms.html").read_text(encoding="utf-8")


def test_mississippis_list_has_congress_the_court_of_appeals_and_the_specials():
    filings = MsList.parse(LISTED.encode())
    assert {f.day for f in filings} == {"2026-11-03"} and not any(f.write_in or f.incumbent for f in filings)
    races = {f.office_id: f for f in filings}
    assert Counter(f.reach for f in races.values()) == {"state": 1, "cd": 4, "counties": 6, "hd": 2, "sd": 1}
    senate = {f.name: (f.party, f.party_name) for f in filings if f.office_id == "US SENATE"}
    assert senate == {"Scott Colom": ("D", None), "Ty Pinkins": (None, "Independent"), "Cindy Hyde-Smith": ("R", None)}
    appeals = races["COURT OF APPEALS 1 1"]
    assert (appeals.office, appeals.group, appeals.district) == ("Court of Appeals Judge, District 1, Place 1",
                                                                 "judicial", "1")
    assert "DESOTO" in appeals.counties and "PANOLA*" in appeals.counties and appeals.party is None
    assert sorted(f.name for f in filings if f.office_id == "COURT OF APPEALS 1 1") == ["Derek Dewayne Hopson Jr.",
                                                                                     "John Weddle"]
    assert all(races[key].unexpired for key in ("STATE HOUSE 70", "STATE HOUSE 77", "STATE SENATE 34",
                                                "DISTRICT ATTORNEY 7"))
    assert races["DISTRICT ATTORNEY 7"].counties == ("HINDS",)
    assert 'Anthony "Tony" Lawrence' in {f.name for f in filings}
    assert not any(word in f.family for f in filings for word in ("CHANCERY", "CIRCUIT", "SUPREME"))


def test_the_court_of_appeals_districts_cover_every_county_once_or_in_part():
    listed = Counter(county.rstrip("*") for district in ms.APPEALS for county in ms.appeals_counties(district))
    assert set(listed) == {county.name.upper() for county in counties.counties("MS")}
    split = {county for county, times in listed.items() if times > 1}
    assert split == {"GRENADA", "MONTGOMERY", "PANOLA", "TALLAHATCHIE", "ATTALA", "LEAKE", "MADISON", "HINDS", "JONES",
                     "WAYNE"}
    assert all(f"{county}*" in ms.appeals_counties(district) for district in ms.APPEALS
               for county in ms.APPEALS[district][1])


def test_a_judicial_district_reaching_part_of_a_county_is_only_maybe_there():
    appeals = next(f for f in MsList.parse(LISTED.encode()) if f.office_id == "COURT OF APPEALS 4 2")
    districts = Districts(cd=3)
    assert where(appeals, districts, "LINCOLN", None, set()) == "include"
    assert where(appeals, districts, "JONES", None, set()) == "unconfirmed"
    assert where(appeals, districts, "RANKIN", None, set()) == "skip"


def test_a_page_short_of_races_or_with_an_office_it_doesnt_know_is_refused():
    one_house = LISTED.replace("<td>2</td></tr>", "<td>1</td></tr>").replace("<td>3</td></tr>", "<td>1</td></tr>")
    with pytest.raises(ValueError, match="2 U.S. House races, not 4"):
        MsList.parse(one_house)
    with pytest.raises(ValueError, match="an office it doesn't know: Candidates for Dogcatcher"):
        MsList.parse(LISTED.replace("Candidates for State Senate 34", "Candidates for Dogcatcher"))
    with pytest.raises(ValueError, match="no general election on it"):
        MsList.parse(LISTED.replace("General Election:", "Runoff:"))
    with pytest.raises(ValueError, match="no general election on it"):
        MsList.parse(b"<html><body>Service Unavailable</body></html>")


def test_a_jackson_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "jackson")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (2, 29, 67)
    assert [race["name"] for race in ballot["races"]] == [
        "U.S. Senator", "U.S. Representative District 2", "District Attorney, District 7"]
    assert all(race["source"] == "state_ms" for race in ballot["races"])
    assert "Bennie G. Thompson" in candidate_names(find_race(ballot, "U.S. Representative District 2"))
    assert find_race(ballot, "District Attorney, District 7")["unexpired"]
    assert ballot["left_out"]["races"] == 2  # the Court of Appeals' districts 2 and 4 each reach part of Hinds
    assert any("Supreme Court" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-05",
        "mail_apply_by": None, "early_voting_start": "2026-09-21", "early_voting_end": "2026-10-31",
        "source": "Mississippi Secretary of State", "source_url": "https://www.sos.ms.gov/elections-voting",
        "computed": True,
    }
    assert upstream.count(HOST) == 1
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_ms'")]
    assert [sorted(value) for value in kept] == [["filings"]]
    assert "__VIEWSTATE" not in json.dumps(kept)
    get_ballot(client, "jackson")
    assert logged_calls() == 0 and upstream.count(HOST) == 1


def test_a_mississippi_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "jackson")
    upstream.state_lists[HOST] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_ms")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "jackson")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "District Attorney, District 7")


def test_with_mississippis_list_off_or_unreadable_its_ballot_has_congress_from_the_fec(client, upstream):
    switch(client, "state_ms", False)
    ballot = get_ballot(client, "jackson")
    assert ballot["coverage"]["ballot"] == "fec"
    assert upstream.count(HOST) == 0
    switch(client, "state_ms", True)
    upstream.state_lists[HOST] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "jackson")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Mississippi Secretary of State" in w
               for w in ballot["warnings"])


def test_mississippis_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_ms")
    assert outcome.status == "updated" and outcome.answers == 1
    assert outcome.counts == {"races": 14, "candidates": 39}
    assert upstream.count(HOST) == 1
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "jackson")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == 1


def test_mississippis_2026_key_dates_are_worked_out_from_title_23():
    found = state_key_dates.computed("MS", dt.date(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        dt.date(2026, 10, 5), None, dt.date(2026, 9, 21), dt.date(2026, 10, 31), "MS")


def test_mississippis_calendar_file_and_when_to_vote_say_absentee_needs_an_excuse(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "MS"})
    assert response.status_code == 200 and "mississippi-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "voting early means voting absentee in person\\, which needs a reason" in text
    assert all(day in text for day in ("20261005", "20261031", "20261103"))  # from the tests' today, Sep 27
    info = state_key_dates.GUIDES["MS"].voter_info()
    assert info.poll_hours == "7 a.m. – 7 p.m." and info.late_registration is None
    assert info.mail_eligibility.startswith("Only if you're 65 or older")
    assert "within five business days" in info.mail_eligibility
