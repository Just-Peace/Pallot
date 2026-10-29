"""Indiana's ballot (states/in_.py), from the Election Division's candidate spreadsheet, found by its
link on the division's home page, and its key dates worked out from the Indiana Code.
tests/fixtures/state_in.html is that page cut down to its link; state_in.xlsx is the spreadsheet
as served (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import in_, sheet_rows
from pallot.states import key_dates as state_key_dates
from pallot.states.in_ import InList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch

HOST = "www.in.gov"
PAGE = (FIXTURES / "state_in.html").read_text(encoding="utf-8")
LISTED = (FIXTURES / "state_in.xlsx").read_bytes()
LIST_PATH = "/sos/elections/files/Candidate_List_Abbreviated_20260922_011251PM.xlsx"
HEADING = [["Candidate List - Abbreviated"], ["ALL COUNTIES"], ["2027 MUNICIPAL GENERAL ELECTION - 11/2/2027 11:59:00 PM"],
           [], ["OFFICE CATEGORY:", "MAYOR"], ["BALLOT NAME", "PARTY", "OFFICE TITLE", "FILED DATE", ""]]


def rows() -> list[list[str]]:
    return sheet_rows(LISTED)[1]


def test_the_page_links_the_years_general_election_list():
    found = in_.links(PAGE)
    assert found == {"links": {"2026": f"https://www.in.gov{LIST_PATH}"}}
    lists = InList.__new__(InList)
    assert [spec.url for spec in lists.follow(found, dt.date(2026, 11, 3))] == [found["links"]["2026"]]
    assert lists.follow(found, dt.date(2028, 11, 7)) is None
    primary = '<a href="/dA/1/Primary-Candidate-List-3.25.26.xlsx"><strong>2026 Primary Candidate List</strong></a>'
    assert in_.links(PAGE.replace("<body>", f"<body>{primary}"))["links"] == found["links"]
    assert InList.read_index(PAGE.encode()) == found and InList.read_index(LISTED) is None
    with pytest.raises(ValueError, match="not the Election Division's home page"):
        in_.links("<html><head><title>Maintenance</title></head></html>")


def test_indianas_list_has_congress_the_state_the_legislature_and_the_counties_but_not_the_towns():
    filings = InList.parse(LISTED)
    assert len(filings) == 1696 and {f.day for f in filings} == {"2026-11-03"}
    races = {f.office_id: f for f in filings}
    assert Counter(f.reach for f in races.values()) == {"state": 3, "cd": 9, "sd": 25, "hd": 100, "county": 640,
                                                       "part_county": 462}
    assert sorted({f.office for f in filings if f.reach == "state"}) == [
        "Secretary of State", "State Comptroller (Auditor of State)", "Treasurer of State"]
    secretary = [(f.name, f.party, f.party_name, f.write_in) for f in filings if f.office == "Secretary of State"]
    assert secretary == [("Beau Bayh", "D", None, False), ("Lauri A. Shillings", "L", None, False),
                         ("Greg Ballard", None, "Lincoln Party", False), ("Max Engling", "R", None, False),
                         ("Andrew Delano", None, "National Socialist American Workers'", True)]
    house = {(f.district, f.name) for f in filings if f.reach == "cd"}
    assert ("8", "Mark Messmer") in house and ("7", "André Carson") in house and len(house) == 26
    degman = next(f for f in filings if f.name == "Alexander R (Alex) Degman")
    assert (degman.office, degman.party_name, degman.write_in) == ("U.S. Representative District 1", "Independent", True)
    assert next(f for f in filings if f.name == "Prescription Dope Deaths Johnson, Jr").party_name is None
    senator = next(f for f in filings if f.office_id == "STATE SENATOR, DISTRICT 01" and f.party == "R")
    assert (senator.name, senator.office, senator.district) == ("Trevor G. De Vries", "State Senator District 1", "1")
    sheriff = next(f for f in filings if f.office == "Allen County Sheriff")
    assert (sheriff.group, sheriff.reach, sheriff.counties, sheriff.family) == (
        "county", "county", ("ALLEN",), "COUNTY SHERIFF")
    prosecutor = next(f for f in filings if f.office.startswith("Prosecuting Attorney of Dearborn"))
    assert (prosecutor.counties, prosecutor.district) == (("DEARBORN", "OHIO"), "7")
    judge = next(f for f in filings if f.office == "Judge of the Allen Superior Court, Criminal No. 5")
    assert (judge.group, judge.reach, judge.counties, judge.family) == (
        "judicial", "county", ("ALLEN",), "SUPERIOR COURT JUDGE")
    council = next(f for f in filings if f.office == "Allen County Council, District 2")
    assert (council.reach, council.district, council.counties) == ("part_county", "2", ("ALLEN",))
    assert not any(word in f.office for f in filings for word in ("Township", "Town ", "School", "Mayor", "Small Claims"))
    assert not any(f.incumbent for f in filings)


def test_a_list_short_of_districts_or_with_an_office_it_doesnt_know_is_refused():
    listed = rows()
    with pytest.raises(ValueError, match="89 State House races, not 90"):
        in_.parse_rows([r for r in listed if not (len(r) > 2 and r[2].startswith("State Representative, District")
                                                  and int(r[2].rsplit(" ", 1)[1]) > 89)])
    with pytest.raises(ValueError, match="an office it doesn't know: LIEUTENANT GOVERNOR OF THE MOON"):
        in_.parse_rows(listed + [["OFFICE CATEGORY:", "LIEUTENANT GOVERNOR OF THE MOON"], ["Pat Doe", "Democratic",
                                                                                         "Lieutenant Governor", ""]])
    with pytest.raises(ValueError, match="a row without a name or office"):
        in_.parse_rows(listed + [["", "Democratic", "State Senator, District 01", "1/7/2026"]])
    with pytest.raises(ValueError, match="a district it can't read"):
        in_.parse_rows(listed + [["OFFICE CATEGORY:", "US REPRESENTATIVE"],
                                 ["Pat Doe", "Democratic", "United States Representative, Eleventh-ish District", ""]])
    with pytest.raises(ValueError, match="not the general election's candidate list"):
        in_.parse_rows(listed[3:])
    with pytest.raises(ValueError, match="not a spreadsheet it can read"):
        InList.parse(b"<html><body>Service Unavailable</body></html>")


def test_an_odd_years_municipal_list_without_congress_isnt_held_to_the_even_years_minimum():
    """Ballots don't ask for an odd year's election yet (#610): this checks the adapter alone."""
    filings = in_.parse_rows([*HEADING, ["Pat Doe", "Republican", "Mayor of Attica", "1/2/2027"],
                              ["OFFICE CATEGORY:", "COUNTY COUNCIL MEMBER"],
                              ["Lee Roe", "( )", "Allen County Council, At Large", "1/2/2027"]])
    assert [(f.day, f.name, f.reach, f.party, f.counties) for f in filings] == [
        ("2027-11-02", "Lee Roe", "county", None, ("ALLEN",))]


def test_a_fort_wayne_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "fortwayne")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (3, 16, 82)
    names = [race["name"] for race in ballot["races"]]
    assert names[:5] == ["U.S. Representative District 3", "Secretary of State", "State Comptroller (Auditor of State)",
                         "Treasurer of State", "State Representative District 82"]
    assert not any(name.startswith("State Senator") for name in names)  # District 16 is up in 2028
    assert {"Allen County Sheriff", "Prosecuting Attorney of Allen County, 38th Judicial Circuit",
            "Judge of the Allen Superior Court, Civil No. 2"} <= set(names)
    assert not any("Council" in name or "Commissioner" in name for name in names)
    assert all(race["source"] == "state_in" for race in ballot["races"])
    house = find_race(ballot, "U.S. Representative District 3")
    assert house["seat"] == "IN-03"
    assert candidate_names(house) == ["Kelly Thompson", "Marlin A. Stutzman", "Phillip D. Beachy (Phil)"]
    assert [c["write_in"] for c in house["candidates"]] == [False, False, True]
    assert any(card["source"] == "fec" and card["kind"] == "money" for c in house["candidates"] for card in c["cards"])
    assert any("Township, city, town, school board" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-05",
        "mail_apply_by": "2026-10-22", "early_voting_start": "2026-10-06", "early_voting_end": "2026-11-02",
        "source": "Indiana Election Division", "source_url": "https://www.in.gov/sos/elections/", "computed": True,
    }
    assert upstream.count(HOST) == 2
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_in'")]
    assert sorted(sorted(value) for value in kept) == [["filings"], ["links"]]
    assert not any("FILED" in json.dumps(value) or "6/22/2026" in json.dumps(value) for value in kept)
    get_ballot(client, "fortwayne")
    assert logged_calls() == 0 and upstream.count(HOST) == 2


def test_an_indiana_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "fortwayne")
    upstream.state_lists[f"{HOST}{LIST_PATH}"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_in")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "fortwayne")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "Secretary of State")


def test_with_indianas_list_off_or_unreadable_its_ballot_has_the_race_for_congress_from_the_fec(client, upstream):
    switch(client, "state_in", False)
    ballot = get_ballot(client, "fortwayne")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 3")
    assert upstream.count(HOST) == 0
    switch(client, "state_in", True)
    upstream.state_lists[f"{HOST}{LIST_PATH}"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "fortwayne")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Indiana Election Division" in w for w in ballot["warnings"])


def test_a_year_the_page_doesnt_link_a_list_for_yet_leaves_the_fecs_races(client, upstream):
    upstream.state_lists[f"{HOST}/sos/elections/"] = PAGE.replace("2026 General", "2024 General")
    ballot = get_ballot(client, "fortwayne")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("The Indiana Election Division hasn't published its list of candidates" in n for n in ballot["notes"])
    assert upstream.count(HOST) == 1


def test_indianas_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_in")
    assert outcome.status == "updated" and outcome.answers == 2
    assert outcome.counts == {"races": 1239, "candidates": 1696}
    assert upstream.count(HOST) == 2
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "fortwayne")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == 2


@pytest.mark.parametrize("day, register, apply, start, end", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 5), dt.date(2026, 10, 22), dt.date(2026, 10, 6), dt.date(2026, 11, 2)),
    (dt.date(2028, 11, 7), dt.date(2028, 10, 9), dt.date(2028, 10, 26), dt.date(2028, 10, 10), dt.date(2028, 11, 6)),
])
def test_indianas_key_dates_are_worked_out_from_the_indiana_code(day, register, apply, start, end):
    found = state_key_dates.computed("IN", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, apply, start, end, "IN")
    assert state_key_dates.computed("IN", dt.date(2027, 11, 2)) is None


def test_indianas_calendar_file_and_when_to_vote_give_its_local_poll_hours_and_the_excuse_for_mail(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "IN"})
    assert response.status_code == 200 and "indiana-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls are open 6 a.m. to 6 p.m. local time\\; if you're in line at 6\\, you can vote." in text
    assert all(day in text for day in ("20261005", "20261006", "20261102", "20261103"))
    assert "It ends Monday\\, November 2." in text
    info = state_key_dates.GUIDES["IN"].voter_info()
    assert info.poll_hours == "6 a.m. – 6 p.m. local time" and info.late_registration is None
    assert info.mail_eligibility.startswith("Only if you're 65 or older, disabled, away from your county")
    assert info.mail_eligibility.endswith("by 6 p.m. on Election Day.")
