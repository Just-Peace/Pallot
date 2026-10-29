"""Kentucky's ballot (states/ky.py), from the Secretary of State's candidate filings: its page's
election dropdown, then the list of all candidates a postback of its own form answers, and its key
dates worked out from Kentucky's election law. tests/fixtures/state_ky.html is the page cut down to
its dropdown and its hidden fields (made-up values); state_ky_list.html is the list as served for
the 2026 general election, each row without its post office box or email
(scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot import counties
from pallot.states import key_dates as state_key_dates
from pallot.states import ky
from pallot.states.ky import KyList

from .bundling import build
from .conftest import FIXTURES, KY_ELECTION, candidate_names, find_race, get_ballot, switch

HOST = "web.sos.ky.gov"
PAGE = (FIXTURES / "state_ky.html").read_text(encoding="utf-8")
LISTED = (FIXTURES / "state_ky_list.html").read_text(encoding="utf-8")
DAY = dt.date(2026, 11, 3)


def row(name: str, office: str, district: str = "", party: str = "Republican Party") -> str:
    return f'<tr class="boldleft"><td>{name}</td><td></td><td>{office}</td><td>{district}</td><td>{party}</td></tr>'


def listed(*rows: str, year: str = "2026", drop: str | None = None) -> str:
    """The recorded list with ``rows`` added to its candidates, its election ``year``'s, and
    without the rows of the office ``drop``."""
    body = LISTED.replace("2026 General Election", f"{year} General Election")
    if drop:
        body = "\n".join(line for line in body.split("\n") if f"<td>{drop}</td>" not in line)
    return body.replace("</table>", "\n".join(rows) + "\n</table>", 1)


def test_the_page_names_the_general_elections_id_and_the_list_is_its_postback():
    index = KyList.read_index(PAGE.encode())
    assert index == {"elections": {"2026-11-03": KY_ELECTION}}
    lists = KyList.__new__(KyList)
    spec = lists.spec(DAY)
    assert (spec.method, spec.url) == ("GET", f"https://{HOST}/CandidateFilings/Default.aspx")
    (post,) = lists.follow(index, DAY)
    assert (post.method, post.url, post.form) == ("POST", spec.url, {
        "ctl00$MainContent$ddlElection": KY_ELECTION, "ctl00$MainContent$bListAll": "List All Candidates"})
    assert lists.follow(index, dt.date(2027, 11, 2)) is None
    assert KyList.read_index(LISTED.encode()) is None
    odd = PAGE.replace("2027 Primary Election", "2027 General Election")
    assert KyList.read_index(odd.encode()) == {"elections": {"2026-11-03": KY_ELECTION, "2027-11-02": "89"}}
    with pytest.raises(ValueError, match="not the Secretary of State's candidate filings"):
        KyList.read_index(b"<html><body>Service Unavailable</body></html>")


def test_kentuckys_list_has_congress_the_general_assembly_and_the_courts_by_their_counties():
    filings = KyList.parse(LISTED.encode())
    assert len(filings) == 348 and {f.day for f in filings} == {""}
    races = {f.office_id: f for f in filings}
    assert Counter(f.reach for f in races.values()) == {"state": 1, "cd": 6, "sd": 19, "hd": 100, "counties": 63,
                                                         "county": 62}
    assert {int(f.district) % 2 for f in races.values() if f.reach == "sd"} == {0}
    senate = [(f.name, f.party, f.party_name, f.write_in)
              for f in sorted((f for f in filings if f.office_id == "US SENATE"), key=lambda f: f.order)]
    assert senate == [("Charles Booker", "D", None, False), ("Andy Barr", "R", None, False),
                      ("Christopher Campbell", None, "Kentucky Party", False),
                      ("Thomas Michael Murphy", None, None, True)]  # listed by name; shown by party, write-ins last
    appeals = races["COURT OF APPEALS 5 1"]
    assert (appeals.office, appeals.family, appeals.group, appeals.reach, appeals.district) == (
        "Judge of the Court of Appeals, 5th Appellate District, 1st Division", "COURT OF APPEALS", "judicial",
        "counties", "5")
    assert "FRANKLIN" in appeals.counties and len(appeals.counties) == 8
    assert races["CIRCUIT JUDGE 8 3"].counties == ("EDMONSON", "WARREN")
    assert races["DISTRICT JUDGE 59"].counties == ("CUMBERLAND", "MONROE")
    assert races["COMMONWEALTHS ATTORNEY 1"].office == "Commonwealth's Attorney, 1st Circuit"
    assert races["SUPREME COURT 3"].office == "Justice of the Supreme Court, 3rd Supreme Court District"
    assert all(f.party is None and f.party_name is None for f in filings
               if f.group == "judicial" and f.family != "COMMONWEALTHS ATTORNEY")
    names = {f.name for f in filings}
    assert not names & {"Mohammad Wael Ahmad", "Tyler K. Dean", "Yes", "No"}  # withdrawn; the amendment
    assert not any(f.incumbent for f in filings)


def test_each_court_table_covers_every_county_once():
    known = {county.name.upper() for county in counties.counties("KY")}
    for table in (ky.SUPREME, ky.CIRCUITS, ky.DISTRICTS, ky.DISTRICTS_2031):
        placed = [county for places in table.values() for county in places]
        assert len(placed) == len(set(placed)) == len(known) and set(placed) == known


def test_an_odd_years_list_has_the_governors_ticket_and_the_statewide_offices():
    rows = (row("Daniel Cameron<br />Jane Doe", "Governor"), row("Rocky Adams<br />Pat Roe", "Governor",
                                                                 party="Democratic Party"),
            row("Michael G. Adams", "Secretary of State"), row("Allison Ball", "Auditor of Public Accounts"),
            row("Someone Else", "Lieutenant Governor"))
    body = listed(*rows, year="2027")
    body = body[:body.index("<table>")] + "<table>\n" + "\n".join(rows) + "\n</table></div></form></body></html>"
    filings = ky.candidates(body)
    assert [(f.office, f.name, f.party) for f in filings] == [
        ("Governor and Lieutenant Governor", "Daniel Cameron and Jane Doe", "R"),
        ("Governor and Lieutenant Governor", "Rocky Adams and Pat Roe", "D"),
        ("Secretary of State", "Michael G. Adams", "R"), ("Auditor of Public Accounts", "Allison Ball", "R")]
    assert {f.reach for f in filings} == {"state"}


def test_district_judges_from_2030_are_placed_on_the_2031_map():
    judge = row("Some Judge", "District Judge", "42nd", "Nonpartisan")
    filings = ky.candidates(listed(judge, year="2030"))
    assert next(f for f in filings if f.name == "Some Judge").counties == ("CALLOWAY", "MARSHALL")
    assert next(f for f in ky.candidates(listed(judge)) if f.name == "Some Judge").counties == ("CALLOWAY",)


def test_a_list_short_of_districts_or_with_a_row_it_cant_read_is_refused():
    with pytest.raises(ValueError, match="5 U.S. House races, not 6"):
        ky.candidates(listed(drop="6th"))
    with pytest.raises(ValueError, match="a district it can't read"):
        ky.candidates(listed(row("Some One", "State Senator", "Lower Valley")))
    with pytest.raises(ValueError, match="a row it can't read"):
        ky.candidates(listed('<tr class="boldleft"><td>US Senator</td></tr>'))
    with pytest.raises(ValueError, match="not the Secretary of State's list of all candidates"):
        KyList.parse(PAGE.encode())
    unknown = ky.candidates(listed(row("Some One", "Master Commissioner", "3rd")))
    assert next(f for f in unknown if f.name == "Some One").reach == "unplaced"


def test_a_frankfort_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "frankfort")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (1, 20, 57)
    names = [race["name"] for race in ballot["races"]]
    assert names == ["U.S. Senator", "U.S. Representative District 1", "State Senator District 20",
                     "State Representative District 57",
                     "Judge of the Court of Appeals, 5th Appellate District, 1st Division",
                     "District Judge, 48th District, 1st Division", "District Judge, 48th District, 2nd Division"]
    appeals = find_race(ballot, "Judge of the Court of Appeals, 5th Appellate District, 1st Division")
    assert candidate_names(appeals) == ["Lucy Ferguson VanMeter", "Will Moynahan"]
    assert all(race["source"] == "state_ky" for race in ballot["races"])
    house = find_race(ballot, "U.S. Representative District 1")
    assert house["seat"] == "KY-01" and candidate_names(house) == ['John "Drew" Williams', "James R. Comer"]
    assert any(card["source"] == "fec" and card["kind"] == "money" for c in house["candidates"] for card in c["cards"])
    assert candidate_names(find_race(ballot, "State Senator District 20")) == ["Stella R. Pollard", 'Gex "jay" Williams']
    assert any("constitutional amendments" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-05",
        "mail_apply_by": "2026-10-20", "early_voting_start": "2026-10-29", "early_voting_end": "2026-10-31",
        "source": "Kentucky State Board of Elections", "source_url": "https://elect.ky.gov/", "computed": True,
    }
    assert upstream.count(HOST) == 3  # the page, the page again for its form's hidden fields, and the postback
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_ky'")]
    assert sorted(sorted(value) for value in kept) == [["elections"], ["filings"]]
    assert "VIEWSTATE" not in json.dumps(kept)
    get_ballot(client, "frankfort")
    assert logged_calls() == 0 and upstream.count(HOST) == 3


def test_a_kentucky_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "frankfort")
    upstream.state_lists[f"{HOST}#list"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_ky")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "frankfort")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "State Senator District 20")


def test_with_kentuckys_list_off_or_unreadable_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_ky", False)
    ballot = get_ballot(client, "frankfort")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 1")
    assert upstream.count(HOST) == 0
    switch(client, "state_ky", True)
    upstream.state_lists[f"{HOST}#list"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "frankfort")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Kentucky Secretary of State" in w
               for w in ballot["warnings"])


def test_an_election_not_in_the_dropdown_or_without_candidates_leaves_the_fecs_races(make_app, upstream):
    upstream.state_lists[f"{HOST}#page"] = PAGE.replace("2026 General Election", "2026 Special Election")
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "frankfort")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("The Kentucky Secretary of State hasn't published its list of candidates" in n for n in ballot["notes"])
    assert upstream.count(HOST) == 1
    upstream.state_lists.pop(f"{HOST}#page")
    upstream.state_lists[f"{HOST}#list"] = PAGE  # an election with no candidates yet: the page, without the list
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "frankfort")
    assert ballot["coverage"]["ballot"] == "fec"


def test_kentuckys_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_ky")
    assert outcome.status == "updated" and outcome.answers == 2
    assert outcome.counts == {"races": 251, "candidates": 348}
    asked = upstream.count(HOST)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "frankfort")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == asked


@pytest.mark.parametrize("day, register, apply, start, end", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 5), dt.date(2026, 10, 20), dt.date(2026, 10, 29), dt.date(2026, 10, 31)),
    (dt.date(2027, 11, 2), dt.date(2027, 10, 4), dt.date(2027, 10, 19), dt.date(2027, 10, 28), dt.date(2027, 10, 30)),
    # Its 29th day before is Columbus Day, a federal holiday: registration runs through the Tuesday.
    (dt.date(2022, 11, 8), dt.date(2022, 10, 11), dt.date(2022, 10, 25), dt.date(2022, 11, 3), dt.date(2022, 11, 5)),
])
def test_kentuckys_key_dates_are_worked_out_from_its_election_law(day, register, apply, start, end):
    """2026's against the State Board of Elections' 2026 Election Calendar (final version,
    2025-10-06): registration Oct 5 (online by 4 p.m. local time, by mail postmarked that day), the
    mail-in absentee portal closing Oct 20, no-excuse in-person voting Thu Oct 29 - Sat Oct 31
    (excused in-person from Wed Oct 21)."""
    found = state_key_dates.computed("KY", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, apply, start, end, "KY")
    assert found.early_start.weekday() == 3 and found.early_end.weekday() == 5
    assert state_key_dates.computed("KY", dt.date(2026, 11, 10)) is None


def test_kentuckys_calendar_file_and_when_to_vote_say_who_can_vote_by_mail_and_the_local_poll_hours(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "KY"})
    assert response.status_code == 200
    assert "kentucky-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls are open 6 a.m. to 6 p.m. local time\\; if you're in line at 6\\, you can vote." in text
    assert all(day in text for day in ("20261005", "20261029", "20261031", "20261103"))
    assert "online by 4 p.m. local time" in text and "only with a reason the law allows" in text
    info = state_key_dates.GUIDES["KY"].voter_info()
    assert info.poll_hours == "6 a.m. – 6 p.m. local time" and info.late_registration is None
    assert info.mail_eligibility.startswith("Only if you're in the military or overseas,")
    assert info.mail_deadline == "Ask on the State Board of Elections' portal by 11:59 p.m. local time on "
