"""Kansas's ballot (states/ks.py), from the Secretary of State's candidate list: its page's election
dropdown, then the list a postback of its own form answers, and its key dates worked out from
Kansas's election law. tests/fixtures/state_ks.html is the page cut down to its dropdown and its
hidden fields (made-up values); state_ks_list.html is the list as served for the 2026 general
election, each row cut down to its first six columns, without addresses, phones or emails
(scripts/record_fixtures.py)."""

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
from pallot.states import ks
from pallot.states.ks import KsList
from pallot.states.place import where

from .bundling import build
from .conftest import FIXTURES, KS_ELECTION, candidate_names, find_race, get_ballot, switch

HOST = "www.sos.ks.gov"
PAGE = (FIXTURES / "state_ks.html").read_text(encoding="utf-8")
LISTED = (FIXTURES / "state_ks_list.html").read_text(encoding="utf-8")
DAY = dt.date(2026, 11, 3)


def row(name: str, office: str, district: int = 0, party: str = "Republican", position: int = 0) -> str:
    return (f"<tr><td>{name}</td><td>{office}</td><td>{district}</td><td>{position}</td><td>0</td>"
            f"<td>{party}</td></tr>")


def listed(*rows: str, drop: str | None = None) -> str:
    """The recorded list with ``rows`` added, and without the rows holding ``drop``."""
    body = LISTED
    if drop:
        body = "\n".join(line for line in body.split("\n") if drop not in line)
    return body.replace("</table>", "\n".join(rows) + "\n</table>", 1)


def test_the_page_names_the_general_elections_id_and_the_list_is_its_postback():
    index = KsList.read_index(PAGE.encode())
    assert index["elections"]["2026-11-03"] == KS_ELECTION and index["elections"]["2024-11-05"] == "34"
    assert not any(day.startswith("2017") for day in index["elections"])  # its special election
    lists = KsList.__new__(KsList)
    spec = lists.spec(DAY)
    assert (spec.method, spec.url) == ("GET", f"https://{HOST}/elections/elections_upcoming_candidate.aspx")
    (post,) = lists.follow(index, DAY)
    assert (post.method, post.url, post.form) == ("POST", spec.url, {"ddlElections": KS_ELECTION, "btnSubmit": "Submit"})
    assert lists.follow(index, dt.date(2028, 11, 7)) is None
    assert KsList.read_index(LISTED.encode()) is None
    empty = LISTED[:LISTED.index("<tr><td>")] + "</table></form></body></html>"
    assert KsList.read_index(empty.encode()) == index  # no candidates yet: no list
    with pytest.raises(ValueError, match="not the Secretary of State's candidate list"):
        KsList.read_index(b"<html><body>Service Unavailable</body></html>")


def test_kansass_list_has_congress_the_statewide_offices_the_legislature_the_board_and_the_courts():
    filings = KsList.parse(LISTED.encode())
    assert len(filings) == 362 and {f.day for f in filings} == {""}
    races = {f.office_id: f for f in filings}
    assert Counter(f.reach for f in races.values()) == {"hd": 125, "counties": 72, "unplaced": 26, "state": 13,
                                                         "sd": 7, "cd": 4}
    governor = [(f.name, f.party) for f in filings if f.office_id == "GOVERNOR"]
    assert governor == [("Cindy Holscher and KC Ohaebosim", "D"), ("Ty Masterson and Jeffrey Klemp", "R")]
    assert {(f.party, f.party_name) for f in filings if f.office_id == "SECRETARY OF STATE"} == {
        ("D", None), ("R", None), (None, "United Kansas")}
    senate = races["STATE SENATE 24"]
    assert (senate.office, senate.unexpired, senate.group) == ("State Senator District 24", True, "legislature")
    board = races["STATE BOARD OF EDUCATION 7"]
    assert (board.office, board.group, board.reach, board.district) == (
        "State Board of Education District 7", "state", "sd", "24,31,33,34")
    justice = races["SUPREME COURT 4 ERIC S. ROSEN"]
    assert (justice.office, justice.reach, justice.retention, justice.incumbent, justice.party) == (
        "Retain Eric S. Rosen, Justice of the Supreme Court", "state", True, True, None)
    retained = races["DISTRICT COURT 3 1 JASON E. GEIER"]
    assert (retained.office, retained.counties, retained.retention) == (
        "Retain Jason E. Geier, District Judge, 3rd Judicial District, Division 1", ("SHAWNEE",), True)
    elected = races["DISTRICT COURT 29 3"]
    assert (elected.office, elected.counties, elected.retention, elected.party) == (
        "District Judge, 29th Judicial District, Division 3", ("WYANDOTTE",), False, "D")
    assert races["DISTRICT COURT 24"].office == "District Judge, 24th Judicial District"
    assert all(f.reach == "unplaced" for f in filings if f.family == "DISTRICT MAGISTRATE")
    assert not any(f.write_in for f in filings)


def test_each_judicial_district_and_board_district_is_counted_once():
    known = {county.name.upper() for county in counties.counties("KS")}
    placed = [county for places in ks.JUDICIAL.values() for county in places]
    assert len(placed) == len(set(placed)) == len(known) and set(placed) == known
    senate = [number for numbers in ks.BOARD.values() for number in numbers]
    assert sorted(senate) == list(range(1, 41))


def test_the_board_is_placed_by_the_voters_senate_district_and_isnt_a_senate_seat():
    board = next(f for f in KsList.parse(LISTED.encode()) if f.office_id == "STATE BOARD OF EDUCATION 7")
    assert where(board, Districts(cd=1, sd=31, hd=1), "SALINE", None, set()) == "include"
    assert where(board, Districts(cd=1, sd=3, hd=1), "SALINE", None, set()) == "skip"
    assert where(board, Districts(cd=1, hd=1), "SALINE", None, set()) == "unconfirmed"


def test_a_list_short_of_districts_or_with_a_row_it_cant_read_is_refused():
    with pytest.raises(ValueError, match="3 U.S. House races, not 4"):
        ks.candidates(listed(drop="United States House of Representatives</td><td>4<"))
    with pytest.raises(ValueError, match="a district it can't read"):
        ks.candidates(listed(row("Some One", "Kansas House of Representatives", "Lower Valley")))
    with pytest.raises(ValueError, match="a row it can't read"):
        ks.candidates(listed("<tr><td>Some One</td><td>Kansas Senate</td></tr>"))
    with pytest.raises(ValueError, match="a federal office it doesn't know"):
        ks.candidates(listed(row("Some One", "United States President")))
    with pytest.raises(ValueError, match="its columns aren't the list's"):
        ks.candidates(LISTED.replace("<th>Party</th>", "<th>Affiliation</th>"))
    with pytest.raises(ValueError, match="not the Secretary of State's list of a general election's candidates"):
        KsList.parse(PAGE.encode())
    unknown = ks.candidates(listed(row("Some One", "County Surveyor", 3)))
    assert next(f for f in unknown if f.name == "Some One").reach == "unplaced"


def test_a_topeka_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "topeka")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (2, 19, 57)
    names = [race["name"] for race in ballot["races"]]
    assert names[:8] == ["U.S. Senator", "U.S. Representative District 2", "Governor and Lieutenant Governor",
                         "Secretary of State", "Attorney General", "State Treasurer", "Commissioner of Insurance",
                         "State Representative District 57"]
    assert not any("Board of Education" in name or "State Senator" in name for name in names)  # SBOE 6 isn't up
    judges = names[8:]
    assert len(judges) == 12 and judges[0] == "Retain Eric S. Rosen, Justice of the Supreme Court"
    assert "Retain Cheryl A. Rios, District Judge, 3rd Judicial District, Division 11" in judges
    assert all(race["retention"] for race in ballot["races"][8:])
    assert all(race["source"] == "state_ks" for race in ballot["races"])
    house = find_race(ballot, "U.S. Representative District 2")
    assert house["seat"] == "KS-02" and candidate_names(house) == ["Don Coover", "Derek Schmidt", "John Hauer"]
    assert any(card["source"] == "fec" and card["kind"] == "money" for c in house["candidates"] for card in c["cards"])
    assert any("district magistrate judges" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-13",
        "mail_apply_by": "2026-10-27", "early_voting_start": "2026-10-14", "early_voting_end": "2026-11-02",
        "source": "Kansas Secretary of State", "source_url": "https://www.sos.ks.gov/elections/elections.html",
        "computed": True,
    }
    assert upstream.count(HOST) == 3  # the page, the page again for its form's hidden fields, and the postback
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_ks'")]
    assert sorted(sorted(value) for value in kept) == [["elections"], ["filings"]]
    assert "VIEWSTATE" not in json.dumps(kept)
    get_ballot(client, "topeka")
    assert logged_calls() == 0 and upstream.count(HOST) == 3


def test_a_kansas_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "topeka")
    upstream.state_lists[f"{HOST}#list"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_ks")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "topeka")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "State Representative District 57")


def test_with_kansass_list_off_or_unreadable_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_ks", False)
    ballot = get_ballot(client, "topeka")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 2")
    assert upstream.count(HOST) == 0
    switch(client, "state_ks", True)
    upstream.state_lists[f"{HOST}#list"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "topeka")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Kansas Secretary of State" in w for w in ballot["warnings"])


def test_an_election_not_in_the_dropdown_leaves_the_fecs_races(make_app, upstream):
    upstream.state_lists[f"{HOST}#page"] = PAGE.replace("2026 General", "2026 Special")
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "topeka")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("The Kansas Secretary of State hasn't published its list of candidates" in n for n in ballot["notes"])
    assert upstream.count(HOST) == 1


def test_kansass_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_ks")
    assert outcome.status == "updated" and outcome.answers == 2
    assert outcome.counts == {"races": 247, "candidates": 362}
    asked = upstream.count(HOST)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "topeka")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == asked


@pytest.mark.parametrize("day, register, apply, start, end", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 13), dt.date(2026, 10, 27), dt.date(2026, 10, 14), dt.date(2026, 11, 2)),
])
def test_kansass_key_dates_are_worked_out_from_its_election_law(day, register, apply, start, end):
    """2026's against the Secretary of State's Important Election Dates: registration Oct 13, advance
    voting from Oct 14 (in every county by Tue Oct 27); applications by mail through Tue Oct 27
    (K.S.A. 25-1122(f)); in person through noon Mon Nov 2 (25-1122(g))."""
    found = state_key_dates.computed("KS", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, apply, start, end, "KS")
    assert found.mail_apply_by.weekday() == 1 and found.early_end.weekday() == 0


def test_kansass_calendar_file_and_when_to_vote_give_both_zones_poll_hours(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "KS"})
    assert response.status_code == 200
    assert "kansas-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "7 a.m. to 7 p.m. Central time\\, 6 a.m. to 6 p.m. Mountain time" in text
    assert all(day in text for day in ("20261013", "20261014", "20261102", "20261103"))
    assert "through 12 noon on the day before Election Day" in text.replace("\\", "")
    assert "by 7 p.m. on Election Day" in state_key_dates.GUIDES["KS"].mail
    info = state_key_dates.GUIDES["KS"].voter_info()
    assert info.poll_hours == "7 a.m. – 7 p.m. Central, 6 a.m. – 6 p.m. Mountain" and info.late_registration is None
    assert info.mail_eligibility.startswith("Any registered voter can vote by mail")
