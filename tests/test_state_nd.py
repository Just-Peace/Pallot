"""North Dakota's ballot (states/nd.py), from the Secretary of State's candidatelist.aspx grid and the
table its Search postback answers, and its key dates worked out from the North Dakota Century Code.
tests/fixtures/state_nd.html is the Candidate page cut down to its link to the grid;
state_nd_grid.html the grid's page cut down to its hidden fields (made-up values); state_nd_list.html
the 2026 general election's table, each row cut down to its contest, term, district, county, name
and party (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import key_dates as state_key_dates
from pallot.states import nd
from pallot.states.nd import NdList

from .bundling import build
from .conftest import FIXTURES, ND_ELECTION, candidate_names, find_race, get_ballot, switch

HOST = "vip.sos.nd.gov"
INDEX = (FIXTURES / "state_nd.html").read_text(encoding="utf-8")
LISTED = (FIXTURES / "state_nd_list.html").read_text(encoding="utf-8")


def test_the_candidate_page_gives_the_grids_id_and_the_list_is_its_search_postback():
    assert NdList.read_index(INDEX.encode()) == {"elections": {"2026": ND_ELECTION}}
    assert NdList.read_index(LISTED.encode()) is None
    with pytest.raises(ValueError, match="no link"):
        NdList.read_index(b"<html><body>Service Unavailable</body></html>")
    lists = NdList.__new__(NdList)
    spec = NdList.spec(lists, dt.date(2026, 11, 3))
    assert (spec.method, spec.url) == ("GET", nd.INDEX)
    [spec] = lists.follow({"elections": {"2026": ND_ELECTION}}, dt.date(2026, 11, 3))
    assert (spec.method, spec.url, spec.params) == ("POST", nd.PAGE, {"eid": ND_ELECTION})
    assert spec.form["ctl00$ContentPlaceHolder1$btnSearch"] == "Search"
    assert spec.form["ctl00$ContentPlaceHolder1$ddlJursdiction"] == "AL"
    assert lists.follow({"elections": {"2026": ND_ELECTION}}, dt.date(2028, 11, 7)) is None


def test_north_dakotas_list_has_congress_the_statewide_offices_and_the_legislature():
    filings = NdList.parse(LISTED)
    races = {f.office_id: f for f in filings}
    assert Counter((f.group, f.reach) for f in races.values()) == {
        ("federal", "cd"): 1, ("state", "state"): 5, ("legislature", "sd"): 24, ("legislature", "hd"): 27}
    in_order = sorted(filings, key=lambda f: f.order)
    assert [(f.name, f.party, f.party_name) for f in in_order if f.office_id == "US HOUSE"] == [
        ("Julie Fedorchak", "R", None), ("Trygve Hammer", "D", None), ("Helene Neville", None, "Independent"),
        ("Charles Tuttle", None, "Independent")]
    assert races["US HOUSE"].office == "U.S. Representative At Large" and races["US HOUSE"].district == "0"
    assert {f.party for f in filings if f.office_id == "SUPERINTENDENT OF PUBLIC INSTRUCTION"} == {None}
    assert (races["STATE HOUSE 35"].office, races["STATE HOUSE 35"].seats) == ("State Representative District 35", 2)
    assert races["STATE HOUSE 9"].district == "9" and races["STATE SENATE 1"].district == "1"
    assert {d: (races[f"STATE HOUSE {d}"].seats, races[f"STATE HOUSE {d}"].unexpired) for d in (20, 26, 42)} == {
        20: (1, True), 26: (1, True), 42: (1, True)}
    assert not any(f.office_id.startswith(("PUBLIC SERVICE", "JUSTICE", "JUDGE", "COUNTY")) for f in filings)
    assert len(filings) == 141


def test_an_office_or_district_it_cant_read_and_a_short_list_are_refused():
    with pytest.raises(ValueError, match="no district for State Senator: 'Burleigh'"):
        NdList.parse(LISTED.replace("<td>District 01</td>", "<td>Burleigh</td>", 1))
    with pytest.raises(ValueError, match="0 U.S. House races, not 1"):
        NdList.parse(LISTED.replace("Representative in Congress", "Delegate"))
    with pytest.raises(ValueError, match="no heading row"):
        NdList.parse(b"<html><body>Service Unavailable</body></html>")


def test_a_bismarck_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "bismarck")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (0, 35, 35)
    assert [race["name"] for race in ballot["races"]] == [
        "U.S. Representative At Large", "Secretary of State", "Attorney General", "Agriculture Commissioner",
        "Tax Commissioner", "Superintendent of Public Instruction", "State Senator District 35",
        "State Representative District 35",
    ]
    assert all(race["source"] == "state_nd" for race in ballot["races"])
    assert ballot["races"][0]["seat"] == "ND-00"
    assert sorted(candidate_names(find_race(ballot, "State Senator District 35"))) == ["Dale Pittman", "Sean Cleary"]
    assert find_race(ballot, "State Representative District 35")["seats"] == 2
    assert any("Public Service Commission's two races" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": None,
        "mail_apply_by": "2026-11-02", "early_voting_start": "2026-09-24", "early_voting_end": "2026-11-02",
        "source": "North Dakota Secretary of State", "source_url": "https://www.sos.nd.gov/elections",
        "computed": True,
    }
    assert upstream.count("sos.nd.gov") == 3  # the Candidate page, the grid's page for the postback's fields, the table
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_nd'")]
    assert sorted(sorted(value) for value in kept) == [["elections"], ["filings"]]
    assert not any("Bismarck" in json.dumps(value) for value in kept)
    get_ballot(client, "bismarck")
    assert logged_calls() == 0 and upstream.count("sos.nd.gov") == 3


def test_a_north_dakota_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "bismarck")
    upstream.state_lists[f"{HOST}#list"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_nd")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "bismarck")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "Tax Commissioner")


def test_with_north_dakotas_list_off_or_unreadable_its_ballot_has_the_race_for_congress_from_the_fec(client, upstream):
    switch(client, "state_nd", False)
    ballot = get_ballot(client, "bismarck")
    assert ballot["coverage"]["ballot"] == "fec"
    assert upstream.count("sos.nd.gov") == 0
    switch(client, "state_nd", True)
    upstream.state_lists[f"{HOST}#list"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "bismarck")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the North Dakota Secretary of State" in w
               for w in ballot["warnings"])


def test_a_year_the_page_doesnt_link_yet_leaves_the_fecs_race(client, upstream):
    upstream.state_lists["www.sos.nd.gov#index"] = INDEX.replace("2026 General Election", "2024 General Election")
    ballot = get_ballot(client, "bismarck")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("The North Dakota Secretary of State hasn't published its list of candidates" in n for n in ballot["notes"])
    assert upstream.count("sos.nd.gov") == 1


def test_north_dakotas_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_nd")
    assert outcome.status == "updated" and outcome.answers == 2
    assert outcome.counts == {"races": 57, "candidates": 141}
    asked = upstream.count("sos.nd.gov")
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "bismarck")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count("sos.nd.gov") == asked


def test_north_dakotas_2026_key_dates_are_worked_out_from_its_century_code():
    found = state_key_dates.computed("ND", dt.date(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        None, dt.date(2026, 11, 2), dt.date(2026, 9, 24), dt.date(2026, 11, 2), "ND")


def test_north_dakotas_calendar_file_has_its_dates_and_no_registration(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "ND"})
    assert response.status_code == 200 and "north-dakota-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "close between 7 and 9 p.m." in text and "register" not in text.lower().replace("no voter registration", "")
    assert all(day in text for day in ("20261102", "20261103"))
    info = state_key_dates.GUIDES["ND"].voter_info()
    assert (info.registration.label, info.registration.short) == ("Voter ID", "ID")
    assert info.poll_hours == "until 7–9 p.m." and info.late_registration is None
