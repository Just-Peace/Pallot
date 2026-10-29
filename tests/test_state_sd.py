"""South Dakota's ballot (states/sd.py), from the Secretary of State's candidatelist.aspx grid and the
CSV its postback exports, and its key dates worked out from the South Dakota Codified Laws.
tests/fixtures/state_sd.html is the Upcoming Elections page cut down to its menu's link to the
grid; state_sd_grid.html the grid's page cut down to its hidden fields (made-up values);
state_sd.csv the 2026 general election's export without the candidates' mailing addresses
(scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import key_dates as state_key_dates
from pallot.states import sd
from pallot.states.sd import SdList

from .bundling import build
from .conftest import FIXTURES, SD_ELECTION, candidate_names, find_race, get_ballot, switch

HOST = "vip.sdsos.gov"
INDEX = (FIXTURES / "state_sd.html").read_text(encoding="utf-8")
LISTED = (FIXTURES / "state_sd.csv").read_text(encoding="utf-8")


def test_the_upcoming_elections_page_gives_the_grids_id_and_the_export_is_its_postback():
    assert SdList.read_index(INDEX.encode()) == {"elections": {"2026": SD_ELECTION}}
    assert SdList.read_index(LISTED.encode()) is None
    with pytest.raises(ValueError, match="no link"):
        SdList.read_index(b"<html><body>Service Unavailable</body></html>")
    lists = SdList.__new__(SdList)
    spec = SdList.spec(lists, dt.date(2026, 11, 3))
    assert (spec.method, spec.url) == ("GET", sd.INDEX)
    [spec] = lists.follow({"elections": {"2026": SD_ELECTION}}, dt.date(2026, 11, 3))
    assert (spec.method, spec.url, spec.params) == ("POST", sd.PAGE, {"eid": SD_ELECTION})
    assert spec.form["__EVENTTARGET"].endswith("$MainContent$grdCandidates$ctl00$ctl02$ctl00$ExportToCsvButton")
    assert lists.follow({"elections": {"2026": SD_ELECTION}}, dt.date(2028, 11, 7)) is None


def test_south_dakotas_list_has_congress_the_statewide_offices_and_the_legislature():
    filings = SdList.parse(LISTED)
    races = {f.office_id: f for f in filings}
    assert Counter((f.group, f.reach) for f in races.values()) == {
        ("federal", "state"): 1, ("federal", "cd"): 1, ("state", "state"): 7, ("legislature", "sd"): 35,
        ("legislature", "hd"): 37}
    in_order = sorted(filings, key=lambda f: f.order)
    assert [(f.name, f.party, f.party_name) for f in in_order if f.office_id == "US SENATE"] == [
        ("Mike Rounds", "R", None), ("Brian L Bengs", None, "Independent")]
    assert races["US HOUSE"].office == "U.S. Representative At Large" and races["US HOUSE"].district == "0"
    assert [f.name for f in in_order if f.office_id == "GOVERNOR"] == ["Larry Rhoden and Tony Venhuizen",
                                                                       "Dan Ahlers and Steven McCleerey"]
    assert {races["PUBLIC UTILITIES COMMISSIONER"].reach, races["COMMISSIONER OF SCHOOL AND PUBLIC LANDS"].reach} == {
        "state"}
    assert (races["STATE HOUSE 24"].office, races["STATE HOUSE 24"].seats) == ("State Representative District 24", 2)
    assert {races[f"STATE HOUSE {d}"].seats for d in sd.SINGLE} == {1}
    assert races["STATE SENATE 26"].district == "26" and "STATE HOUSE 26" not in races
    assert not any("Withdrawn" in f.name or f.name == "Julian Beaudion" for f in filings)
    assert not any(f.office_id.startswith(("COUNTY", "SHERIFF")) for f in filings)
    assert len(filings) == 178


def test_an_office_or_district_it_cant_read_and_a_short_list_are_refused():
    with pytest.raises(ValueError, match="no district for State (Senator|Representative): 'Hughes'"):
        SdList.parse(LISTED.replace(",District 24,", ",Hughes,", 1))
    with pytest.raises(ValueError, match="0 U.S. House races, not 1"):
        SdList.parse("\n".join(line for line in LISTED.splitlines() if not line.startswith("United States Rep")))
    with pytest.raises(ValueError, match="no heading row"):
        SdList.parse(b"<html><body>Service Unavailable</body></html>")


def test_a_pierre_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "pierre")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (0, 24, 24)
    assert [race["name"] for race in ballot["races"]] == [
        "U.S. Senator", "U.S. Representative At Large", "Governor and Lieutenant Governor", "Secretary of State",
        "Attorney General", "State Auditor", "State Treasurer", "Commissioner of School and Public Lands",
        "Public Utilities Commissioner", "State Senator District 24", "State Representative District 24",
    ]
    assert all(race["source"] == "state_sd" for race in ballot["races"])
    senate, house = ballot["races"][:2]
    assert (senate["seat"], house["seat"]) == ("SD-SEN", "SD-00")
    assert "Marty Jackley" in candidate_names(house)
    assert sorted(candidate_names(find_race(ballot, "State Representative District 24"))) == ["Laurie Gill",
                                                                                             "Mike Weisgram"]
    assert any("water development districts" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-19",
        "mail_apply_by": "2026-11-02", "early_voting_start": "2026-09-18", "early_voting_end": "2026-11-02",
        "source": "South Dakota Secretary of State", "source_url": "https://sdsos.gov/elections-voting/default.aspx",
        "computed": True,
    }
    assert upstream.count("sdsos.gov") == 3  # the index, the grid's page for the postback's fields, the export
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_sd'")]
    assert sorted(sorted(value) for value in kept) == [["elections"], ["filings"]]
    assert not any("Pierre" in json.dumps(value) for value in kept)
    get_ballot(client, "pierre")
    assert logged_calls() == 0 and upstream.count("sdsos.gov") == 3


def test_a_south_dakota_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "pierre")
    upstream.state_lists[f"{HOST}#csv"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_sd")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "pierre")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "Public Utilities Commissioner")


def test_with_south_dakotas_list_off_or_unreadable_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_sd", False)
    ballot = get_ballot(client, "pierre")
    assert ballot["coverage"]["ballot"] == "fec"
    assert upstream.count("sdsos.gov") == 0
    switch(client, "state_sd", True)
    upstream.state_lists[f"{HOST}#csv"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "pierre")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the South Dakota Secretary of State" in w
               for w in ballot["warnings"])


def test_a_year_the_page_doesnt_link_yet_leaves_the_fecs_races(client, upstream):
    upstream.state_lists["sdsos.gov#index"] = INDEX.replace("2026 Election Information", "2024 Election Information")
    ballot = get_ballot(client, "pierre")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("The South Dakota Secretary of State hasn't published its list of candidates" in n for n in ballot["notes"])
    assert upstream.count("sdsos.gov") == 1


def test_south_dakotas_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_sd")
    assert outcome.status == "updated" and outcome.answers == 2
    assert outcome.counts == {"races": 81, "candidates": 178}
    asked = upstream.count("sdsos.gov")
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "pierre")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count("sdsos.gov") == asked


def test_south_dakotas_2026_key_dates_are_worked_out_from_its_codified_laws():
    found = state_key_dates.computed("SD", dt.date(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        dt.date(2026, 10, 19), dt.date(2026, 11, 2), dt.date(2026, 9, 18), dt.date(2026, 11, 2), "SD")


def test_south_dakotas_calendar_file_has_its_dates_and_local_hours(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "SD"})
    assert response.status_code == 200 and "south-dakota-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls are open 7 a.m. to 7 p.m. local time" in text
    assert all(day in text for day in ("20261019", "20261102", "20261103"))
    info = state_key_dates.GUIDES["SD"].voter_info()
    assert info.poll_hours == "7 a.m. – 7 p.m. local time" and info.late_registration is None
