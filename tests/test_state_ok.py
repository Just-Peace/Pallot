"""Oklahoma's ballot (states/ok.py), from the State Election Board's list of elections, one static
page county by county, and its key dates worked out from Oklahoma's election law.
tests/fixtures/state_ok.html is the page as served for the November 3, 2026 general election, cut
down to a few counties' sections (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import key_dates as state_key_dates
from pallot.states import ok
from pallot.states.ok import OkList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch

HOST = "hosting.okelections.gov"
PAGE = (FIXTURES / "state_ok.html").read_text(encoding="utf-8")
DAY = dt.date(2026, 11, 3)
OFFICE = ('<font size="3" ><TABLE CELLSPACING=3 BORDER=0 WIDTH=1000><TR><TD WIDTH=10></TD><TD WIDTH=10></TD>'
          '<TD WIDTH=980> <B>{}</B></TD></TR></TABLE></font>\n')
LINE = ('<TABLE CELLSPACING=3 BORDER=0 WIDTH=1000><TR><TD WIDTH=10></TD><TD WIDTH=10></TD><TD WIDTH=10></TD>'
        '<TD WIDTH=970> {}</TD></TR></TABLE> \n')
SECTION = ('<font size="4" ><B><TABLE CELLSPACING=3 BORDER=0 WIDTH=1000><TR><TD WIDTH=10></TD><TD WIDTH=990> {}</TD>'
           '</TR></TABLE></B></font>\n')
COUNTY = '<font size="5" ><B><U> <A NAME=40>{}</A></U></B></font>\n'


def county(name: str, *parts: str) -> str:
    """The page with a county's section of ``parts`` (SECTION, OFFICE and LINE filled in) added at its end."""
    footer = PAGE.rindex('<font size="2" >')
    return PAGE[:footer] + COUNTY.format(name) + "".join(parts) + PAGE[footer:]


def test_the_page_names_its_general_election_and_is_the_list_too():
    kept = OkList.read_index(PAGE.encode())
    assert kept["elections"] == ["2026-11-03"] and len(kept["filings"]) == 174
    lists = OkList.__new__(OkList)
    lists._read = None
    spec = lists.spec(DAY)
    assert (spec.method, spec.url) == ("GET", f"https://{HOST}/electionlist.html")
    assert lists.follow(kept, DAY) == []
    assert {f.day for f in lists.on(kept, DAY)} == {"2026-11-03"} and not lists.on(kept, dt.date(2028, 11, 7))
    for other in ("FEBRUARY / 2027", "NOVEMBER / 2027"):  # a school's or a city's election day
        assert OkList.read_index(PAGE.replace("NOVEMBER / 2026", other).encode()) == {"elections": [], "filings": []}
    with pytest.raises(ValueError, match="not the State Election Board's list of elections"):
        OkList.read_index(b"<html><body>Service Unavailable</body></html>")


def test_oklahomas_list_has_each_race_once_with_the_counties_it_comes_under():
    filings = OkList.parse(PAGE.encode())
    assert len(filings) == 174 and {f.day for f in filings} == {"2026-11-03"}
    races = {f.office_id: f for f in filings}
    assert Counter(f.reach for f in races.values()) == {"state": 9, "cd": 5, "sd": 12, "hd": 43, "county": 5,
                                                         "counties": 4, "part_county": 2}
    assert {int(f.district) % 2 for f in races.values() if f.reach == "sd" and not f.unexpired} == {0}
    assert races["STATE SENATE 17 UNEXPIRED"].unexpired
    senate = [(f.name, f.party, f.party_name) for f in filings if f.office_id == "US SENATE"]
    assert senate == [("Kevin Hern", "R", None), ("N'kiyla Jasmine Thomas", "D", None), ("Sevier White", "L", None),
                      ("Ron Meinhardt", None, "Independent"), ("Curtis Stinnett", None, "Independent")]
    assert races["LIEUTENANT GOVERNOR"].office == "Lieutenant Governor"  # elected apart from the Governor
    judge = races["DISTRICT JUDGE 14 1"]
    assert (judge.office, judge.family, judge.group, judge.reach, judge.district, judge.counties) == (
        "District Judge, District 14, Office 1", "DISTRICT JUDGE", "judicial", "counties", "14", ("PAWNEE", "TULSA"))
    assert races["DISTRICT JUDGE 14 4"].counties == ("TULSA",)  # an office Tulsa County alone elects
    assert [f.name for f in filings if f.office_id == "DISTRICT JUDGE 14 1"] == ["Tom Sawyer", "Caroline Wall"]
    assert all(f.party is None and f.party_name is None for f in filings if f.group == "judicial")
    assert (races["ASSOCIATE DISTRICT JUDGE ALFALFA"].office, races["ASSOCIATE DISTRICT JUDGE ALFALFA"].reach) == (
        "Alfalfa County Associate District Judge", "county")
    sheriff = races["COUNTY SHERIFF PITTSBURG UNEXPIRED"]
    assert (sheriff.office, sheriff.counties, sheriff.unexpired) == ("Pittsburg County Sheriff", ("PITTSBURG",), True)
    commissioner = races["COUNTY COMMISSIONER OKLAHOMA 3"]
    assert (commissioner.office, commissioner.reach) == ("Oklahoma County Commissioner, District 3", "part_county")
    names = {f.name for f in filings}
    assert {"Michelle LaFleur", "Frankie McClendon", "T. W. Shannon"} <= names
    assert not names & {"Vanessa Hall-Harper", "Corinice Wilson"}  # the City of Tulsa's council
    assert not any("QUESTION" in f.office_id or "SUPREME" in f.office_id for f in filings)
    assert not any(f.incumbent or f.write_in for f in filings)


def test_a_county_is_named_as_the_census_names_it():
    page = county("LEFLORE", SECTION.format("JUDICIAL OFFICERS"), OFFICE.format("ASSOCIATE DISTRICT JUDGE - LEFLORE COUNTY"),
                  LINE.format("SOME JUDGE"), LINE.format("OTHER JUDGE"), SECTION.format("LEGISLATIVE, DISTRICT AND COUNTY OFFICERS"),
                  OFFICE.format("COUNTY COMMISSIONER DISTRICT NO. 2"), LINE.format("ANN ROE, REPUBLICAN"),
                  LINE.format("BOB DOE, DEMOCRAT"), OFFICE.format("COUNTY CLERK"), LINE.format("CAL POE, REPUBLICAN"),
                  LINE.format("DEE LOE, DEMOCRAT"), OFFICE.format("DISTRICT ATTORNEY - DISTRICT 16"),
                  LINE.format("EVE KOE, REPUBLICAN"), LINE.format("FAY MOE, DEMOCRAT"))
    races = {f.office_id: f for f in OkList.parse(page.encode())}
    assert races["ASSOCIATE DISTRICT JUDGE LE FLORE"].office == "Le Flore County Associate District Judge"
    assert races["ASSOCIATE DISTRICT JUDGE LE FLORE"].counties == ("LE FLORE",)
    assert races["COUNTY COMMISSIONER LE FLORE 2"].office == "Le Flore County Commissioner, District 2"
    assert (races["COUNTY CLERK LE FLORE"].office, races["COUNTY CLERK LE FLORE"].reach) == ("Le Flore County Clerk", "county")
    attorney = races["DISTRICT ATTORNEY 16"]
    assert (attorney.office, attorney.reach, attorney.counties) == ("District Attorney, District 16", "counties", ("LE FLORE",))


def test_a_list_short_of_districts_or_that_it_cant_read_is_refused():
    with pytest.raises(ValueError, match="a federal office it doesn't know"):
        OkList.parse(PAGE.replace("UNITED STATES REPRESENTATIVE - DISTRICT 03", "UNITED STATES DELEGATE").encode())
    dropped = PAGE.replace("CONGRESSIONAL OFFICERS", "CITY OF NOWHERE")  # its races read as a city's, left out
    with pytest.raises(ValueError, match="0 U.S. House races, not 3"):
        OkList.parse(dropped.encode())
    stray = county("ADAIR", SECTION.format("STATE OFFICERS"), LINE.format("SOME ONE, REPUBLICAN"))
    with pytest.raises(ValueError, match="a candidate outside an office"):
        OkList.parse(stray.encode())
    unknown = county("ADAIR", SECTION.format("JUDICIAL OFFICERS"), OFFICE.format("SPECIAL MASTER"), LINE.format("SOME ONE"))
    assert next(f for f in OkList.parse(unknown.encode()) if f.name == "Some One").reach == "unplaced"


def test_a_tulsa_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "tulsa")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (1, 11, 73)
    names = [race["name"] for race in ballot["races"]]
    assert names == ["U.S. Senator", "U.S. Representative District 1", "Governor", "Lieutenant Governor",
                     "Attorney General", "State Treasurer", "Superintendent of Public Instruction",
                     "Commissioner of Labor", "Insurance Commissioner", "Corporation Commissioner",
                     "District Judge, District 14, Office 1", "District Judge, District 14, Office 12",
                     "District Judge, District 14, Office 4"]  # House District 73 is unopposed: not on the ballot
    assert all(race["source"] == "state_ok" for race in ballot["races"])
    house = find_race(ballot, "U.S. Representative District 1")
    assert house["seat"] == "OK-01" and candidate_names(house) == ["Mark Tedford", "John Croisant"]
    assert any(card["source"] == "fec" and card["kind"] == "money" for c in house["candidates"] for card in c["cards"])
    assert candidate_names(find_race(ballot, "District Judge, District 14, Office 4")) == ["Loretta Radford",
                                                                                           "Dustin Allen"]
    assert any("a candidate with no opponent is elected without a vote" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-09",
        "mail_apply_by": "2026-10-19", "early_voting_start": "2026-10-28", "early_voting_end": "2026-10-31",
        "source": "Oklahoma State Election Board", "source_url": "https://oklahoma.gov/elections.html", "computed": True,
    }
    assert upstream.count(HOST) == 1
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_ok'")]
    assert [sorted(value) for value in kept] == [["elections", "filings"]]
    assert "<TABLE" not in json.dumps(kept)
    get_ballot(client, "tulsa")
    assert logged_calls() == 0 and upstream.count(HOST) == 1


def test_an_oklahoma_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "tulsa")
    upstream.state_lists[HOST] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_ok")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "tulsa")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "District Judge, District 14, Office 1")


def test_with_oklahomas_list_off_or_unreadable_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_ok", False)
    ballot = get_ballot(client, "tulsa")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 1")
    assert upstream.count(HOST) == 0
    switch(client, "state_ok", True)
    upstream.state_lists[HOST] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "tulsa")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Oklahoma State Election Board" in w
               for w in ballot["warnings"])


def test_a_page_for_another_election_leaves_the_fecs_races(make_app, upstream):
    upstream.state_lists[HOST] = PAGE.replace("NOVEMBER / 2026", "FEBRUARY / 2027")
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "tulsa")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("The Oklahoma State Election Board hasn't published its list of candidates" in n for n in ballot["notes"])
    assert upstream.count(HOST) == 1


def test_oklahomas_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_ok")
    assert outcome.status == "updated" and outcome.answers == 1
    assert outcome.counts == {"races": 80, "candidates": 174}
    asked = upstream.count(HOST)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "tulsa")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == asked


@pytest.mark.parametrize("day, register, apply, start, end", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 9), dt.date(2026, 10, 19), dt.date(2026, 10, 28), dt.date(2026, 10, 31)),
    (dt.date(2028, 11, 7), dt.date(2028, 10, 13), dt.date(2028, 10, 23), dt.date(2028, 11, 1), dt.date(2028, 11, 4)),
])
def test_oklahomas_key_dates_are_worked_out_from_its_election_law(day, register, apply, start, end):
    """2026's against the State Election Board's 2026 Voter Information Calendar: registration
    Oct 9, absentee requests by 5 p.m. Oct 19, early voting Wed Oct 28 - Fri Oct 30 (8 a.m. - 6 p.m.)
    and Sat Oct 31 (8 a.m. - 2 p.m.), polls 7 a.m. - 7 p.m."""
    found = state_key_dates.computed("OK", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, apply, start, end, "OK")
    assert found.register_by.weekday() == 4 and found.mail_apply_by.weekday() == 0
    assert found.early_start.weekday() == 2 and found.early_end.weekday() == 5
    assert state_key_dates.computed("OK", dt.date(2027, 11, 2)) is None  # no general election in an odd year
    assert state_key_dates.computed("OK", dt.date(2026, 11, 10)) is None


def test_oklahomas_calendar_file_and_when_to_vote_say_anyone_can_vote_absentee_and_the_poll_hours(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "OK"})
    assert response.status_code == 200
    assert "oklahoma-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls are open 7 a.m. to 7 p.m.\\; if you're in line at 7\\, you can vote." in text
    assert all(day in text for day in ("20261009", "20261028", "20261031", "20261103"))
    assert "online on the OK Voter Portal" in text and "8 a.m. to 2 p.m. on the Saturday" in text
    info = state_key_dates.GUIDES["OK"].voter_info()
    assert info.poll_hours == "7 a.m. – 7 p.m." and info.late_registration is None
    assert info.mail_eligibility.startswith("Any registered voter can vote absentee, no reason needed.")
    assert "notary" in info.mail_eligibility
    assert info.mail_deadline == "Your request must reach your county election board by 5 p.m. on "
    assert ok.GUIDE.local_office == "Your county election board"
