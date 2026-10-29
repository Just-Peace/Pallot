"""South Carolina's ballot (states/sc.py), from the State Election Commission's candidate tracking:
its list of the year's elections, then its search of the general election's candidates, and its
key dates worked out from South Carolina's election law. tests/fixtures/state_sc.json is that list
as served; state_sc.html is the search cut down to the rows it places and two of each office it
leaves out (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import key_dates as state_key_dates
from pallot.states import sc
from pallot.states.sc import ScList

from .bundling import build
from .conftest import FIXTURES, SC_ELECTION, candidate_names, find_race, get_ballot, switch

HOST = "vrems.scvotes.sc.gov"
ELECTIONS = (FIXTURES / "state_sc.json").read_text(encoding="utf-8")
LISTED = (FIXTURES / "state_sc.html").read_text(encoding="utf-8")
SEARCH_PATH = "/Candidate/CandidateSearch/"
DAY = dt.date(2026, 11, 3)


def row(office: str, counties: str, name: str, party: str = "Republican", status: str = "Active",
        mate: str = "") -> str:
    cells = (office, counties, name, mate, party, "State", status)
    return '<tr data-index="0">' + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"


def listed(*rows: str, drop: str | None = None) -> str:
    """The recorded search with ``rows`` added at the end, and without the rows ``drop`` matches."""
    body = LISTED
    if drop:
        body = re.sub(rf"<tr data-index[^>]*><td[^>]*>{drop}</td>.*?</tr>", "", body, flags=re.S)
    return body.replace("</tbody>", "".join(rows) + "</tbody>", 1)


def test_the_list_of_elections_names_the_general_elections_id():
    index = ScList.read_index(ELECTIONS.encode())
    assert index == {"elections": {"2026-11-03": SC_ELECTION}}
    lists = ScList.__new__(ScList)
    spec = lists.spec(DAY)
    assert (spec.method, spec.url, spec.params) == (
        "GET", f"https://{HOST}/Candidate/GetElections", {"electionType": "General", "year": "2026"})
    (search,) = lists.follow(index, DAY)
    assert (search.method, search.url, search.form["ElectionId"], search.form["SelectedCandidateStatus"]) == (
        "POST", f"https://{HOST}{SEARCH_PATH}", SC_ELECTION, "All")
    assert lists.follow(index, dt.date(2028, 11, 7)) is None
    assert ScList.read_index(b"[]") == {"elections": {}} and ScList.read_index(LISTED.encode()) is None
    with pytest.raises(ValueError, match="not the State Election Commission's list of elections"):
        ScList.read_index(b'{"error": "maintenance"}')


def test_south_carolinas_list_has_congress_the_state_the_house_the_solicitors_and_county_offices():
    filings = ScList.parse(LISTED.encode())
    assert len(filings) == 415 and {f.day for f in filings} == {""}
    races = {f.office_id: f for f in filings}
    assert Counter(f.reach for f in races.values()) == {"state": 8, "cd": 7, "hd": 124, "counties": 6, "county": 112}
    governor = [(f.name, f.party, f.party_name) for f in filings if f.office_id == "GOVERNOR"]
    assert governor == [("Michael Addison and Candace Brewer", None, "United Citizens Party"),
                        ("Walid Hakim and Arnold E Karr", "G", None), ("Jermaine Johnson and Sam Skardon", "D", None),
                        ("Alan Wilson and Mike Reichenbach", "R", None)]
    assert not any(f.name.startswith("Harry N Charles") for f in filings)  # Petition Failed
    assert Counter(f.party_name for f in filings if f.party is None)["Petition"] == 2
    solicitor = races["SOLICITOR 5"]
    assert (solicitor.office, solicitor.family, solicitor.group, solicitor.district, solicitor.counties) == (
        "Solicitor, Circuit 5", "SOLICITOR", "judicial", "5", ("KERSHAW", "RICHLAND"))
    judge = races["PROBATE JUDGE MCCORMICK"]
    assert (judge.office, judge.reach, judge.counties) == ("McCormick County Probate Judge", "county", ("MCCORMICK",))
    assert races["COUNTY TREASURER RICHLAND"].office == "Richland County Treasurer"
    assert races["STATE HOUSE 72"].office == "State Representative District 72"
    assert not any(f.write_in or f.incumbent for f in filings)
    offices = {f.office for f in filings}
    assert "Spartanburg County Council Chair" in offices
    assert not any(word in office for office in offices
                   for word in ("School", "Soil", "Council District", "at Large", "Watershed", "Fire"))


def test_a_running_mate_who_isnt_active_leaves_the_governor_alone_and_an_unexpired_term_is_marked():
    filings = sc.candidates(listed(
        row("Governor and Lieutenant Governor", "", "Jane Doe", "Libertarian", mate="John Roe (Withdrew)"),
        row("Sheriff (Unexpired Term)", "AIKEN", "Pat Smith", "Democratic"),
        row("Sheriff", "AIKEN, BARNWELL", "Two Counties"),
        row("Sheriff", "AIKEN", "Lost Primary", status="Defeated In Primary")))
    assert next(f for f in filings if f.name.startswith("Jane Doe")).name == "Jane Doe"
    sheriff = next(f for f in filings if f.name == "Pat Smith")
    assert (sheriff.office, sheriff.unexpired, sheriff.counties) == ("Aiken County Sheriff", True, ("AIKEN",))
    assert not any(f.name in ("Two Counties", "Lost Primary") for f in filings)


def test_a_list_short_of_districts_or_with_a_statewide_office_it_doesnt_know_is_refused():
    with pytest.raises(ValueError, match="6 U.S. House races, not 7"):
        sc.candidates(listed(drop="U.S. House of Representatives, District 7"))
    with pytest.raises(ValueError, match="an office it doesn't know: Lieutenant Governor of the Moon"):
        sc.candidates(listed(row("Lieutenant Governor of the Moon", "", "Moon Person")))
    sc.candidates(listed(row("Mosquito Control District", "AIKEN", "Left Out")))  # a local office, left out
    with pytest.raises(ValueError, match="not the State Election Commission's candidate search"):
        ScList.parse(b"<html><body>Service Unavailable</body></html>")
    with pytest.raises(ValueError, match="a row it can't read"):
        sc.candidates(listed('<tr data-index="0"><td>U.S. Senate</td></tr>'))


def test_a_presidential_years_list_holds_the_state_senate_to_its_minimum():
    senators = "".join(row(f"State Senate, District {n}", "AIKEN", f"Senator {n}") for n in range(1, 47))
    president = row("President and Vice President", "", "Some One", mate="Other One (Active)")
    filings = sc.candidates(listed(senators, president))
    assert len({f.district for f in filings if f.reach == "sd"}) == 46 and not any("President" in f.office for f in filings)
    with pytest.raises(ValueError, match="39 State Senate races, not 40"):
        sc.candidates(listed("".join(row(f"State Senate, District {n}", "AIKEN", f"Senator {n}") for n in range(1, 40))))
    after = sc.candidates(LISTED.replace(">Active</td>", ">Elected</td>").replace(">Petition Failed</td>",
                                                                                   ">Defeated in Election</td>"))
    assert len(after) == 416  # once it's over, those elected and defeated were on the ballot


def test_a_columbia_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "columbia")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (6, 26, 72)
    names = [race["name"] for race in ballot["races"]]
    assert names == ["U.S. Senator", "U.S. Representative District 6", "Governor and Lieutenant Governor",
                     "Secretary of State", "State Treasurer", "Attorney General", "Comptroller General",
                     "State Superintendent of Education", "Commissioner of Agriculture",
                     "State Representative District 72", "Solicitor, Circuit 5", "Richland County Probate Judge",
                     "Richland County Auditor", "Richland County Treasurer"]
    assert all(race["source"] == "state_sc" for race in ballot["races"])
    house = find_race(ballot, "U.S. Representative District 6")
    assert house["seat"] == "SC-06" and candidate_names(house) == ["James E Jim Clyburn", "John Peterson"]
    assert any(card["source"] == "fec" and card["kind"] == "money" for c in house["candidates"] for card in c["cards"])
    assert candidate_names(find_race(ballot, "Solicitor, Circuit 5")) == ["Byron E Gipson"]
    assert any("school board" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-04",
        "mail_apply_by": "2026-10-23", "early_voting_start": "2026-10-19", "early_voting_end": "2026-10-31",
        "source": "South Carolina State Election Commission", "source_url": "https://scvotes.gov/",
        "computed": True,
    }
    assert upstream.count(HOST) == 2
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_sc'")]
    assert sorted(sorted(value) for value in kept) == [["elections"], ["filings"]]
    assert not any("CandidateDetail" in json.dumps(value) for value in kept)
    get_ballot(client, "columbia")
    assert logged_calls() == 0 and upstream.count(HOST) == 2


def test_a_south_carolina_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "columbia")
    upstream.state_lists[f"{HOST}{SEARCH_PATH}"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_sc")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "columbia")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "Richland County Auditor")


def test_with_south_carolinas_list_off_or_unreadable_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_sc", False)
    ballot = get_ballot(client, "columbia")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 6")
    assert upstream.count(HOST) == 0
    switch(client, "state_sc", True)
    upstream.state_lists[f"{HOST}{SEARCH_PATH}"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "columbia")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the South Carolina State Election Commission" in w
               for w in ballot["warnings"])


def test_a_year_without_its_general_election_listed_leaves_the_fecs_races(client, upstream):
    upstream.state_lists[f"{HOST}/Candidate/GetElections"] = "[]"
    ballot = get_ballot(client, "columbia")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("The South Carolina State Election Commission hasn't published its list of candidates" in n
               for n in ballot["notes"])
    assert upstream.count(HOST) == 1


def test_south_carolinas_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_sc")
    assert outcome.status == "updated" and outcome.answers == 2
    assert outcome.counts == {"races": 257, "candidates": 415}
    assert upstream.count(HOST) == 2
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "columbia")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == 2


@pytest.mark.parametrize("day, register, apply, start, end", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 4), dt.date(2026, 10, 23), dt.date(2026, 10, 19), dt.date(2026, 10, 31)),
    (dt.date(2028, 11, 7), dt.date(2028, 10, 8), dt.date(2028, 10, 27), dt.date(2028, 10, 23), dt.date(2028, 11, 4)),
])
def test_south_carolinas_key_dates_are_worked_out_from_its_election_law(day, register, apply, start, end):
    """2026's against the State Election Commission's 2026 Election Calendar (draft of 2026-08-31):
    online registration Oct 4 (in person Fri Oct 2, by mail postmarked Mon Oct 5), absentee
    application Oct 23, early voting Oct 19 - Oct 31."""
    found = state_key_dates.computed("SC", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, apply, start, end, "SC")
    assert found.register_by.weekday() == 6 and found.early_start.weekday() == 0 and found.early_end.weekday() == 5
    assert state_key_dates.computed("SC", dt.date(2027, 11, 2)) is None


def test_south_carolinas_calendar_file_and_when_to_vote_name_each_way_to_register_and_who_can_vote_absentee(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "SC"})
    assert response.status_code == 200
    assert "south-carolina-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls are open 7 a.m. to 7 p.m.\\; if you're in line at 7\\, you can vote." in text
    assert all(day in text for day in ("20261004", "20261019", "20261031", "20261103"))
    assert "It ends Saturday\\, October 31." in text
    assert "until 5 p.m. on the Friday before" in text and "postmarked by the Monday after" in text
    info = state_key_dates.GUIDES["SC"].voter_info()
    assert info.poll_hours == "7 a.m. – 7 p.m." and info.late_registration is None
    assert info.mail_eligibility.startswith("Only if you're 65 or older, disabled,")
