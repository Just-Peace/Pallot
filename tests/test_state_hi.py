"""Hawaii's ballot (states/hi.py), from the Office of Elections' CandidateFiling.aspx grid and the
CSV its postback exports, and its key dates worked out from Hawaii's election law.
tests/fixtures/state_hi.html is the Candidate Reports page cut down to its year and its link to
the grid; state_hi_grid.html the grid's page cut down to its hidden fields (made-up values);
state_hi.csv the 2026 report's export without the candidates' legal names and contact details
(scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import hi
from pallot.states import key_dates as state_key_dates
from pallot.states.hi import HiList

from .bundling import build
from .conftest import FIXTURES, HI_ELECTION, candidate_names, find_race, get_ballot, switch

HOST = "olvr.hawaii.gov"
INDEX = (FIXTURES / "state_hi.html").read_text(encoding="utf-8")
LISTED = (FIXTURES / "state_hi.csv").read_text(encoding="utf-8")


def test_the_candidate_reports_page_gives_the_grids_id_and_the_export_is_its_postback():
    assert HiList.read_index(INDEX.encode()) == {"elections": {"2026": HI_ELECTION}}
    assert HiList.read_index(LISTED.encode()) is None
    with pytest.raises(ValueError, match="no link"):
        HiList.read_index(b"<html><body>Service Unavailable</body></html>")
    lists = HiList.__new__(HiList)
    spec = HiList.spec(lists, dt.date(2026, 11, 3))
    assert (spec.method, spec.url) == ("GET", hi.INDEX)
    [spec] = lists.follow({"elections": {"2026": HI_ELECTION}}, dt.date(2026, 11, 3))
    assert (spec.method, spec.url, spec.params) == ("POST", hi.PAGE, {"elid": HI_ELECTION})
    assert spec.form == {**hi.EXPORT, hi.DROPDOWN: HI_ELECTION}
    assert lists.follow({"elections": {"2026": HI_ELECTION}}, dt.date(2028, 11, 7)) is None


def test_hawaiis_list_has_congress_the_governors_ticket_the_legislature_and_oha():
    filings = HiList.parse(LISTED)
    races = {f.office_id: f for f in filings}
    assert Counter((f.group, f.reach) for f in races.values()) == {
        ("federal", "cd"): 2, ("state", "state"): 4, ("legislature", "sd"): 6, ("legislature", "hd"): 31}
    in_order = sorted(filings, key=lambda f: f.order)
    assert [(f.name, f.party) for f in in_order if f.office_id == "US HOUSE 1"] == [
        ("Nathan M. Berning", None), ("Ed Case", "D"), ("Jordan S. Conley", "G"), ("Adriel C. Lam", "R")]
    assert races["US HOUSE 2"].office == "U.S. Representative District 2"
    assert races["GOVERNOR"].office == "Governor and Lieutenant Governor" and "LIEUTENANT GOVERNOR" not in races
    assert [(f.name, f.party) for f in in_order if f.office_id == "GOVERNOR"] == [
        ("Gary Cordery and Daniel Anthony", "R"), ("Josh Green and Derek S.K. Kawakami", "D")]
    assert {races[f"STATE SENATE {d}"].unexpired for d in (18, 19)} == {True} and not races["STATE SENATE 13"].unexpired
    assert (races["OHA AT-LARGE TRUSTEE"].seats, races["OHA AT-LARGE TRUSTEE"].reach) == (3, "state")
    assert races["OHA MAUI RESIDENT TRUSTEE"].office == "Office of Hawaiian Affairs Trustee, Maui Resident"
    assert "John Waihee IV" in {f.name for f in filings} and not any(f.party_name for f in filings)
    assert "STATE HOUSE 25" not in races  # its one candidate was elected after the primary
    assert not any("MAYOR" in f.office_id or "COUNCIL" in f.office_id for f in filings)
    assert len(filings) == 94


def test_an_office_or_district_it_cant_read_and_a_short_list_are_refused():
    with pytest.raises(ValueError, match="no U.S. House district 'III'"):
        HiList.parse(LISTED.replace('"U.S. REPRESENTATIVE, DIST II"', '"U.S. REPRESENTATIVE, DIST III"'))
    with pytest.raises(ValueError, match="an office it doesn't know: BOARD OF EDUCATION"):
        HiList.parse(LISTED.replace('"GOVERNOR"', '"BOARD OF EDUCATION"'))
    with pytest.raises(ValueError, match="1 U.S. House races, not 2"):
        HiList.parse(LISTED.replace("DIST II", "DIST I"))
    with pytest.raises(ValueError, match="no heading row"):
        HiList.parse(b"<html><body>Service Unavailable</body></html>")


def test_a_honolulu_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "honolulu")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (1, 13, 25)
    assert [race["name"] for race in ballot["races"]] == [
        "U.S. Representative District 1", "Governor and Lieutenant Governor",
        "Office of Hawaiian Affairs Trustee, Maui Resident", "Office of Hawaiian Affairs Trustee, Oahu Resident",
        "Office of Hawaiian Affairs Trustee, At-Large", "State Senator District 13",
    ]
    assert all(race["source"] == "state_hi" for race in ballot["races"])
    assert ballot["races"][0]["seat"] == "HI-01" and "Ed Case" in candidate_names(ballot["races"][0])
    assert sorted(candidate_names(find_race(ballot, "State Senator District 13"))) == [
        "Tricia Kwai Lin Nakamatsu", "Wallyn Kanoelani Christian"]
    assert any("unopposed after the primary" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-26",
        "mail_apply_by": None, "early_voting_start": "2026-10-20", "early_voting_end": None,
        "source": "Hawaii Office of Elections", "source_url": "https://elections.hawaii.gov/", "computed": True,
    }
    assert upstream.count("hawaii.gov") == 3  # the index, the grid's page for the postback's fields, the export
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_hi'")]
    assert sorted(sorted(value) for value in kept) == [["elections"], ["filings"]]
    assert not any("HONOLULU, HI" in json.dumps(value) for value in kept)
    get_ballot(client, "honolulu")
    assert logged_calls() == 0 and upstream.count("hawaii.gov") == 3


def test_a_hawaii_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "honolulu")
    upstream.state_lists[f"{HOST}#csv"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_hi")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "honolulu")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "Governor and Lieutenant Governor")


def test_with_hawaiis_list_off_or_unreadable_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_hi", False)
    ballot = get_ballot(client, "honolulu")
    assert ballot["coverage"]["ballot"] == "fec"
    assert upstream.count("hawaii.gov") == 0
    switch(client, "state_hi", True)
    upstream.state_lists[f"{HOST}#csv"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "honolulu")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Hawaii Office of Elections" in w
               for w in ballot["warnings"])


def test_a_year_the_page_doesnt_link_yet_leaves_the_fecs_races(client, upstream):
    upstream.state_lists["elections.hawaii.gov#index"] = INDEX.replace("2026 Elections", "2024 Elections")
    ballot = get_ballot(client, "honolulu")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("The Hawaii Office of Elections hasn't published its list of candidates" in n for n in ballot["notes"])
    assert upstream.count("hawaii.gov") == 1


def test_hawaiis_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_hi")
    assert outcome.status == "updated" and outcome.answers == 2
    assert outcome.counts == {"races": 43, "candidates": 94}
    asked = upstream.count("hawaii.gov")
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "honolulu")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count("hawaii.gov") == asked


def test_hawaiis_2026_key_dates_are_worked_out_from_its_election_law():
    found = state_key_dates.computed("HI", dt.date(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        dt.date(2026, 10, 26), None, dt.date(2026, 10, 20), None, "HI")


def test_hawaiis_calendar_file_and_voter_info_say_every_voter_is_mailed_a_ballot(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "HI"})
    assert response.status_code == 200 and "hawaii-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Voter service centers and drop boxes close at 7 p.m. on Election Day" in text
    assert all(day in text for day in ("20261026", "20261020", "20261103"))
    info = state_key_dates.GUIDES["HI"].voter_info()
    assert info.poll_hours == "until 7 p.m." and info.mail_eligibility.startswith("Every active voter is mailed a ballot.")
    assert info.late_registration.label.startswith("After that, register online")
