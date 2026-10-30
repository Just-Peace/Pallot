"""Vermont's ballot (states/vt.py), from the Secretary of State's list of the general election's
qualified candidates, a spreadsheet named for its year, and its key dates worked out from Title 17.
tests/fixtures/state_vt.xlsx is the sheet cut down to its contest, district, name, party and seats,
with one town's justices of the peace (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import district_key, sheet_rows, vt
from pallot.states import key_dates as state_key_dates
from pallot.states.vt import VtList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch

HOST = "outside.vermont.gov"
LIST_PATH = "/dept/sos/Elections_Division/election_info_resources/candidates/2026_general_election_qualified_candidates.xlsx"
LISTED = (FIXTURES / "state_vt.xlsx").read_bytes()


def rows() -> list[list[str]]:
    return sheet_rows(LISTED)[1]


def test_the_years_sheet_is_asked_by_name():
    lists = VtList.__new__(VtList)
    assert lists.spec(dt.date(2026, 11, 3)).url == f"https://{HOST}{LIST_PATH}"


def test_vermonts_list_has_congress_the_state_the_general_assembly_and_the_county_offices():
    filings = VtList.parse(LISTED)
    assert {f.day for f in filings} == {""} and not any(f.write_in or f.incumbent for f in filings)
    races = {f.office_id: f for f in filings}
    assert Counter(f.reach for f in races.values()) == {"state": 6, "cd": 1, "sd": 16, "hd": 109, "county": 70}
    assert sorted(f.office for f in races.values() if f.reach == "state") == [
        "Attorney General", "Auditor of Accounts", "Governor", "Lieutenant Governor", "Secretary of State",
        "State Treasurer"]
    assert not any("JUSTICE" in f.office_id for f in filings)
    senate = races["STATE SENATE Chittenden South East"]
    assert (senate.office, senate.seats, senate.reach) == ("State Senator, Chittenden-Southeast District", 3, "sd")
    house = races["STATE HOUSE Windsor-Orange-2"]
    assert (house.office, house.seats, house.district) == ("State Representative, Windsor-Orange-2 District", 2,
                                                          "Windsor-Orange-2")
    sheriff = races["SHERIFF GRAND ISLE"]
    assert (sheriff.office, sheriff.group, sheriff.counties) == ("Grand Isle County Sheriff", "county", ("GRAND ISLE",))
    judge = races["ASSISTANT JUDGE WASHINGTON"]
    assert (judge.group, judge.seats, judge.family) == ("judicial", 2, "COUNTY ASSISTANT JUDGE")
    governor = {f.name: (f.party, f.party_name) for f in filings if f.office == "Governor"}
    assert governor == {"June Goodband": (None, "Peace and Justice"), "Amanda Janoo": ("D", "Democratic / Progressive"),
                        "Brian Judd": (None, "Independent"), "Dean Roy": (None, "Freedom and Unity"),
                        "Phil Scott": ("R", None)}


def test_its_districts_are_spelt_as_the_census_names_them():
    assert vt.senate_district("CHI SE 1") == ("Chittenden South East", "Chittenden-Southeast")
    assert vt.senate_district("GI 1") == ("Grand Isle", "Grand Isle")
    assert vt.house_district("ORA WAS ADD") == "Orange-Washington-Addison"
    assert vt.house_district("GI CHI") == "Grand Isle-Chittenden"
    assert district_key("Chittenden South East") == district_key(vt.senate_district("CHI SE 1")[0])
    assert vt.affiliation("REP/DEM") == ("R", "Republican / Democratic")
    assert vt.affiliation("UNKNOWN") == (None, None)


def test_a_sheet_short_of_districts_or_with_an_office_it_doesnt_know_is_refused():
    listed = rows()
    with pytest.raises(ValueError, match="104 State House races, not 105"):
        vt.parse_rows([r for r in listed if not (r[0] == "STATE REPRESENTATIVE" and r[1] in ("CHI 1", "CHI 2", "CHI 3", "CHI 4", "CHI 5"))])
    with pytest.raises(ValueError, match="an office it doesn't know: DOGCATCHER"):
        vt.parse_rows(listed + [["DOGCATCHER", "N/A", "PAT DOE", "DEMOCRATIC", "ONE"]])
    with pytest.raises(ValueError, match="a State House district it doesn't know: XYZ 1"):
        vt.parse_rows(listed + [["STATE REPRESENTATIVE", "XYZ 1", "PAT DOE", "DEMOCRATIC", "ONE"]])
    with pytest.raises(ValueError, match="a row without a name or contest"):
        vt.parse_rows(listed + [["GOVERNOR", "N/A", "", "DEMOCRATIC", "ONE"]])
    with pytest.raises(ValueError, match="not the list of general election candidates"):
        vt.parse_rows(listed[1:])
    with pytest.raises(ValueError, match="not a spreadsheet it can read"):
        VtList.parse(b"<html><body>Service Unavailable</body></html>")


def test_a_montpelier_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "montpelier")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (0, "Washington",
                                                                                                "Washington-4")
    assert [race["name"] for race in ballot["races"]] == [
        "U.S. Representative At Large", "Governor", "Lieutenant Governor", "State Treasurer", "Secretary of State",
        "Auditor of Accounts", "Attorney General", "State Senator, Washington District",
        "State Representative, Washington-4 District", "Washington County Probate Judge",
        "Washington County Assistant Judge", "Washington County State's Attorney", "Washington County Sheriff",
        "Washington County High Bailiff",
    ]
    assert all(race["source"] == "state_vt" for race in ballot["races"])
    assert ballot["races"][0]["seat"] == "VT-00"
    assert find_race(ballot, "State Senator, Washington District")["seats"] == 3
    assert "Becca Balint" in candidate_names(find_race(ballot, "U.S. Representative At Large"))
    assert any("Justices of the peace" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": None,
        "mail_apply_by": None, "early_voting_start": "2026-09-19", "early_voting_end": "2026-11-02",
        "source": "Vermont Secretary of State", "source_url": "https://sos.vermont.gov/elections",
        "computed": True,
    }
    assert upstream.count(HOST) == 1
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_vt'")]
    assert [sorted(value) for value in kept] == [["filings"]]
    assert not any(word in json.dumps(kept) for word in ("MONTPELIER", "ONE", "DEMOCRATIC"))
    get_ballot(client, "montpelier")
    assert logged_calls() == 0 and upstream.count(HOST) == 1


def test_a_vermont_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "montpelier")
    upstream.state_lists[f"{HOST}{LIST_PATH}"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_vt")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "montpelier")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "Governor")


def test_with_vermonts_list_off_or_unreadable_its_ballot_has_the_race_for_congress_from_the_fec(client, upstream):
    switch(client, "state_vt", False)
    ballot = get_ballot(client, "montpelier")
    assert ballot["coverage"]["ballot"] == "fec"
    assert upstream.count(HOST) == 0
    switch(client, "state_vt", True)
    upstream.state_lists[f"{HOST}{LIST_PATH}"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "montpelier")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Vermont Secretary of State" in w
               for w in ballot["warnings"])


def test_vermonts_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_vt")
    assert outcome.status == "updated" and outcome.answers == 1
    assert outcome.counts == {"races": 202, "candidates": 422}
    assert upstream.count(HOST) == 1
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "montpelier")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == 1


def test_vermonts_2026_key_dates_are_worked_out_from_title_17():
    found = state_key_dates.computed("VT", dt.date(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        None, None, dt.date(2026, 9, 19), dt.date(2026, 11, 2), "VT")


def test_vermonts_calendar_file_and_when_to_vote_say_every_voter_is_mailed_a_ballot_and_can_register_at_the_polls(
        client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "VT"})
    assert response.status_code == 200 and "vermont-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls close at 7 p.m.\\; your town sets when they open\\, between 5 and 10 a.m." in text
    assert "Register at your polling place when you vote." in text
    assert all(day in text for day in ("20261102", "20261103"))
    assert "Last day to register" not in text
    info = state_key_dates.GUIDES["VT"].voter_info()
    assert info.poll_hours == "until 7 p.m."
    assert info.mail_eligibility.startswith("Every active voter is mailed a ballot.")
    assert info.late_registration.label.startswith("No deadline: register any day")
