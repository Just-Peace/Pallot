"""Delaware's ballot (states/de.py), from the Department of Elections' general election candidate
list and its declared write-ins, two spreadsheets named for their year, and its key dates worked
out from Title 15 of the Delaware Code. tests/fixtures/state_de.xlsx and state_de_write_ins.xlsx
are the two sheets cut down to their office, name, party, status and dates
(scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import de, sheet_rows
from pallot.states import key_dates as state_key_dates
from pallot.states.de import DeList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch

HOST = "elections.delaware.gov"
LIST_PATH = "/candidates/candidatelist/genl_fcddt_2026.xlsx"
LISTED = (FIXTURES / "state_de.xlsx").read_bytes()
WRITE_INS = (FIXTURES / "state_de_write_ins.xlsx").read_bytes()


def rows() -> list[list[str]]:
    return sheet_rows(LISTED)[1]


def test_the_years_two_sheets_are_asked_by_name():
    lists = DeList.__new__(DeList)
    assert DeList.spec(lists, dt.date(2026, 11, 3)).url == f"https://{HOST}{LIST_PATH}"
    [spec] = lists.follow({"links": {}}, dt.date(2026, 11, 3))
    assert spec.url == f"https://{HOST}/candidates/candidatelist/genl_wcddt_2026.xlsx"
    assert sorted(DeList.read_index(WRITE_INS)) == ["filings", "links"]


def test_delawares_list_has_congress_the_state_the_general_assembly_and_the_county_offices():
    filings = DeList.parse(LISTED)
    assert {f.day for f in filings} == {""} and not any(f.write_in or f.incumbent for f in filings)
    races = {f.office_id: f for f in filings}
    assert Counter(f.reach for f in races.values()) == {"state": 4, "cd": 1, "sd": 11, "hd": 41, "county": 9,
                                                       "part_county": 11}
    assert sorted({f.office for f in filings if f.reach == "state"}) == [
        "Attorney General", "Auditor of Accounts", "State Treasurer", "U.S. Senator"]
    house = [(f.name, f.party, f.district) for f in filings if f.reach == "cd"]
    assert house == [("Sarah McBride", "D", "0"), ('Joseph "Dr. Joe" Arminio', "R", "0")]  # Lee Murphy withdrew
    auditor = [(f.name, f.party, f.party_name) for f in filings if f.office == "Auditor of Accounts"]
    assert auditor == [("Lydia York", "D", None), ("April Callaway", "R", None),
                       ("Austin Cassidy", None, "Independent Party of Delaware")]
    assert sorted({f.district for f in filings if f.reach == "sd"}, key=int) == [
        "1", "5", "7", "8", "9", "12", "13", "14", "15", "19", "20"]
    senator = next(f for f in filings if f.office_id == "STATE SENATE 19")
    assert (senator.name, senator.office, senator.party) == ("Brian G. Pettyjohn", "State Senator District 19", "R")
    assert not any(f.name in ("Nikki Miller", "Dan Poliseno", "Christopher W. Muntz") for f in filings)
    sheriff = next(f for f in filings if f.office == "Sussex County Sheriff")
    assert (sheriff.group, sheriff.reach, sheriff.counties, sheriff.family) == (
        "county", "county", ("SUSSEX",), "COUNTY SHERIFF")
    levy = next(f for f in filings if f.office == "Kent County Levy Court At-Large")
    assert (levy.reach, levy.family, levy.counties) == ("county", "COUNTY LEVY COURT", ("KENT",))
    council = next(f for f in filings if f.office == "New Castle County Council District 6")
    assert (council.reach, council.district, council.counties, council.family) == (
        "part_county", "6", ("NEW CASTLE",), "COUNTY COUNCIL")


def test_the_declared_write_ins_are_kept_qualified_only():
    filings = DeList.parse(WRITE_INS)
    assert all(f.write_in and f.party is None and f.party_name is None for f in filings)
    assert [(f.office, f.name) for f in filings if f.reach == "cd"] == [("U.S. Representative At Large", "Earl Cooper")]
    assert not any(f.name in ("Scott Walker", "Lance Moffa") for f in filings)  # provisional, withdrawn


def test_a_sheet_short_of_districts_or_with_an_office_it_doesnt_know_is_refused():
    listed = rows()
    with pytest.raises(ValueError, match="37 State House races, not 38"):
        de.parse_rows([r for r in listed if not (r[1].startswith("State Representative District")
                                                 and int(r[1].rsplit(" ", 1)[1]) > 37)])
    with pytest.raises(ValueError, match="an office it doesn't know: Lieutenant Governor of the Moon"):
        de.parse_rows(listed + [["Statewide", "Lieutenant Governor of the Moon", "", "Pat Doe", "Democratic", "",
                                 "Qualified"]])
    with pytest.raises(ValueError, match="a row without a name or office"):
        de.parse_rows(listed + [["Kent", "State Senator District 14", "", "", "Democratic", "", "Qualified"]])
    with pytest.raises(ValueError, match="not the list of general election candidates"):
        de.parse_rows(listed[1:])
    with pytest.raises(ValueError, match="not a spreadsheet it can read"):
        DeList.parse(b"<html><body>Service Unavailable</body></html>")


def test_a_georgetown_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "georgetown")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (0, 19, 37)
    assert [race["name"] for race in ballot["races"]] == [
        "U.S. Senator", "U.S. Representative At Large", "Attorney General", "Auditor of Accounts", "State Treasurer",
        "State Senator District 19", "State Representative District 37", "Sussex County Recorder of Deeds",
        "Sussex County Register of Wills", "Sussex County Sheriff",
    ]
    assert all(race["source"] == "state_de" for race in ballot["races"])
    assert ballot["races"][1]["seat"] == "DE-00"
    assert candidate_names(find_race(ballot, "U.S. Senator")) == [
        "Chris Coons", 'Michael "Dr. Mike" Katz', "William McVay", "John Shulli", "Travis Jack Stevens"]
    assert [c["write_in"] for c in find_race(ballot, "U.S. Senator")["candidates"]] == [False, False, True, True, True]
    assert any("County council and Levy Court seats elected by district" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-10",
        "mail_apply_by": "2026-11-02", "early_voting_start": "2026-10-22", "early_voting_end": "2026-11-01",
        "source": "Delaware Department of Elections", "source_url": "https://elections.delaware.gov",
        "computed": True,
    }
    assert upstream.count(HOST) == 2
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_de'")]
    assert sorted(sorted(value) for value in kept) == [["filings", "links"], ["filings", "links"]]
    assert not any("Qualified" in json.dumps(value) or "6/12/2026" in json.dumps(value) for value in kept)
    get_ballot(client, "georgetown")
    assert logged_calls() == 0 and upstream.count(HOST) == 2


def test_a_delaware_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "georgetown")
    upstream.state_lists[f"{HOST}{LIST_PATH}"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_de")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "georgetown")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "Auditor of Accounts")


def test_with_delawares_list_off_or_unreadable_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_de", False)
    ballot = get_ballot(client, "georgetown")
    assert ballot["coverage"]["ballot"] == "fec"
    assert upstream.count(HOST) == 0
    switch(client, "state_de", True)
    upstream.state_lists[f"{HOST}{LIST_PATH}"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "georgetown")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Delaware Department of Elections" in w
               for w in ballot["warnings"])


def test_delawares_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_de")
    assert outcome.status == "updated" and outcome.answers == 2
    assert outcome.counts == {"races": 77, "candidates": 130}
    assert upstream.count(HOST) == 2
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "georgetown")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == 2


def test_delawares_2026_key_dates_are_worked_out_from_title_15():
    found = state_key_dates.computed("DE", dt.date(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        dt.date(2026, 10, 10), dt.date(2026, 11, 2), dt.date(2026, 10, 22), dt.date(2026, 11, 1), "DE")


def test_delawares_calendar_file_and_when_to_vote_give_its_poll_hours_and_the_excuse_for_absentee(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "DE"})
    assert response.status_code == 200 and "delaware-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls are open 7 a.m. to 8 p.m.\\; if you're in line at 8\\, you can vote." in text
    assert all(day in text for day in ("20261010", "20261022", "20261101", "20261102", "20261103"))
    info = state_key_dates.GUIDES["DE"].voter_info()
    assert info.poll_hours == "7 a.m. – 8 p.m." and info.late_registration is None
    assert info.mail_eligibility.startswith("Only if you're sick or disabled, away on vacation")
    assert info.mail_eligibility.endswith("by 8 p.m. on Election Day.")
