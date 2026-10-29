"""Montana's ballot (states/mt.py), from the Secretary of State's CandidateList.aspx grid and the CSV
its postback exports, and its key dates worked out from the Montana Code Annotated.
tests/fixtures/state_mt.html is the grid's page cut down to its election dropdown and its hidden
fields (made-up values); state_mt.csv is the 2026 general election's export without the candidates'
contact details (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import key_dates as state_key_dates
from pallot.states import mt
from pallot.states.grid import GridRow
from pallot.states.mt import MtList

from .bundling import build
from .conftest import FIXTURES, MT_ELECTION, candidate_names, find_race, get_ballot, switch

HOST = "candidatefiling.mt.gov"
PAGE = (FIXTURES / "state_mt.html").read_text(encoding="utf-8")
LISTED = (FIXTURES / "state_mt.csv").read_text(encoding="utf-8")


def test_the_dropdown_gives_the_general_elections_id_and_the_export_is_its_postback():
    assert MtList.read_index(PAGE.encode()) == {"elections": {"2026-11-03": MT_ELECTION}}
    assert MtList.read_index(LISTED.encode()) is None
    lists = MtList.__new__(MtList)
    spec = MtList.spec(lists, dt.date(2026, 11, 3))
    assert (spec.method, spec.url) == ("GET", mt.PAGE)
    [spec] = lists.follow({"elections": {"2026-11-03": MT_ELECTION}}, dt.date(2026, 11, 3))
    assert (spec.method, spec.url, spec.params) == ("POST", mt.PAGE, {"e": MT_ELECTION})
    assert spec.form["__EVENTTARGET"].endswith("$ExportToCsvButton")
    assert lists.follow({"elections": {"2026-11-03": MT_ELECTION}}, dt.date(2028, 11, 7)) is None


def test_montanas_list_has_congress_the_psc_the_supreme_court_and_the_legislature():
    filings = MtList.parse(LISTED)
    races = {f.office_id: f for f in filings}
    assert Counter((f.group, f.reach) for f in races.values()) == {
        ("federal", "state"): 1, ("federal", "cd"): 2, ("state", "hd"): 2, ("judicial", "state"): 1,
        ("legislature", "sd"): 25, ("legislature", "hd"): 100}
    assert [(f.name, f.party, f.party_name, f.write_in) for f in filings if f.office_id == "US SENATE"] == [
        ("Kurt Alme", "R", None, False), ("Kyle Austin", "L", None, False), ("Alani Bankhead", "D", None, False),
        ("Seth Bodnar", None, "Independent", False), ("Jami Dee Woodman", None, None, True)]
    assert [(f.name, f.incumbent) for f in filings if f.office_id == "US HOUSE 2"][0] == ("Troy Downing", True)
    assert not any("*" in f.name for f in filings)
    assert [(f.name, f.party) for f in filings if f.office_id == "SUPREME COURT 4"] == [
        ("Amy Eddy", None), ("Dan Wilson", None)]
    psc = races["PUBLIC SERVICE COMMISSIONER 5"]
    assert (psc.office, psc.district) == ("Public Service Commissioner District 5", ",".join(map(str, mt.PSC[5])))
    assert [f.name for f in filings if f.office_id == "STATE SENATE 22" and f.write_in] == [
        "Elijah Tidswell", "Cari Lynn Olson"]
    assert not any("District Court" in f.office or "DISTRICT COURT" in f.office_id for f in filings)
    assert len(filings) == 256


def test_each_state_house_district_is_in_one_public_service_commission_district():
    seats = sorted(n for districts in mt.PSC.values() for n in districts)
    assert seats == list(range(1, 101)) and all(len(d) == 20 for d in mt.PSC.values())


def test_withdrawn_candidates_unexpired_terms_and_marks():
    row = '"{}","House","HOUSE DISTRICT 7","STATE REPRESENTATIVE DISTRICT 7","{}","2","{}","","{}","","","REP",""\n'
    text = (LISTED + row.format("WITHDRAWN", "REGULAR", "PAT GONE", "")
            + row.format("FILED", "UNEXPIRED", "*PAT O'DOE", "pat@example.com<br />WRITE IN"))
    found = [f for f in MtList.parse(text) if f.name in ("Pat Gone", "Pat O'Doe")]
    assert [(f.name, f.unexpired, f.incumbent, f.write_in, f.party) for f in found] == [
        ("Pat O'Doe", True, True, True, "R")]
    assert MtList.affiliation(GridRow("", "", "", "", "NON", 0, {})) == (None, None)


def test_a_list_short_of_districts_or_with_an_office_it_doesnt_know_is_refused():
    with pytest.raises(ValueError, match="1 U.S. House races, not 2"):
        MtList.parse("\n".join(line for line in LISTED.splitlines() if "2ND CONGRESSIONAL" not in line))
    with pytest.raises(ValueError, match="an office it doesn't know: STATE AUDITOR"):
        MtList.parse(LISTED.replace('"STATE","UNITED STATES SENATOR"', '"STATE","STATE AUDITOR"', 1))
    with pytest.raises(ValueError, match="no Public Service Commission district 6"):
        MtList.parse(LISTED.replace("PUBLIC SERVICE COMMISSIONER, DISTRICT 5", "PUBLIC SERVICE COMMISSIONER, DISTRICT 6"))
    with pytest.raises(ValueError, match="no heading row"):
        MtList.parse(b"<html><body>Service Unavailable</body></html>")


def test_a_helena_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "helena")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (2, 41, 82)
    assert [race["name"] for race in ballot["races"]] == [
        "U.S. Senator", "U.S. Representative District 2", "Public Service Commissioner District 5",
        "State Senator District 41", "State Representative District 82", "Supreme Court Justice No. 4",
    ]
    assert all(race["source"] == "state_mt" for race in ballot["races"])
    senate, house = ballot["races"][:2]
    assert (senate["seat"], house["seat"]) == ("MT-SEN", "MT-02")
    assert "Troy Downing" in candidate_names(house)
    assert candidate_names(find_race(ballot, "Public Service Commissioner District 5")) == ["Annie Bukacek", "Kevin Hamm"]
    assert any("district court judges" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-05",
        "mail_apply_by": "2026-11-02", "early_voting_start": "2026-10-05", "early_voting_end": "2026-11-02",
        "source": "Montana Secretary of State", "source_url": "https://sosmt.gov/elections/", "computed": True,
    }
    assert upstream.count(HOST) == 3  # the page, its own page again for the postback's fields, the export
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_mt'")]
    assert sorted(sorted(value) for value in kept) == [["elections"], ["filings"]]
    assert not any("Helena" in json.dumps(value) or "WRITE" in json.dumps(value) for value in kept)
    get_ballot(client, "helena")
    assert logged_calls() == 0 and upstream.count(HOST) == 3


def test_a_montana_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "helena")
    upstream.state_lists[f"{HOST}#csv"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_mt")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "helena")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "Supreme Court Justice No. 4")


def test_with_montanas_list_off_or_unreadable_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_mt", False)
    ballot = get_ballot(client, "helena")
    assert ballot["coverage"]["ballot"] == "fec"
    assert upstream.count(HOST) == 0
    switch(client, "state_mt", True)
    upstream.state_lists[f"{HOST}#csv"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "helena")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Montana Secretary of State" in w
               for w in ballot["warnings"])


def test_an_election_the_dropdown_doesnt_list_yet_leaves_the_fecs_races(client, upstream):
    upstream.state_lists[f"{HOST}#page"] = PAGE.replace("11/03/2026", "11/05/2024")
    ballot = get_ballot(client, "helena")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("The Montana Secretary of State hasn't published its list of candidates" in n for n in ballot["notes"])
    assert upstream.count(HOST) == 1


def test_montanas_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_mt")
    assert outcome.status == "updated" and outcome.answers == 2
    assert outcome.counts == {"races": 131, "candidates": 256}
    asked = upstream.count(HOST)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "helena")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == asked


def test_montanas_2026_key_dates_are_worked_out_from_its_code():
    found = state_key_dates.computed("MT", dt.date(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        dt.date(2026, 10, 5), dt.date(2026, 11, 2), dt.date(2026, 10, 5), dt.date(2026, 11, 2), "MT")
    assert state_key_dates.computed("MT", dt.date(2027, 11, 2)) is None


def test_montanas_calendar_file_has_its_dates_and_hours(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "MT"})
    assert response.status_code == 200 and "montana-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls are open 7 a.m. to 8 p.m." in text and "noon" in text
    assert all(day in text for day in ("20261005", "20261102", "20261103"))
    info = state_key_dates.GUIDES["MT"].voter_info()
    assert info.poll_hours == "until 8 p.m." and "Election Day" in info.late_registration.label
