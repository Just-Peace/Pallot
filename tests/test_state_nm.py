"""New Mexico's ballot (states/nm.py), from the Secretary of State's CandidateList.aspx grid, found
by its link on the Secretary of State's home page, and its key dates worked out from NMSA 1978.
tests/fixtures/state_nm.html is that page cut down to its links to the grid; state_nm_list.html is
the grid's page for the 2026 general election with every row, the candidates' contact details
emptied (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import key_dates as state_key_dates
from pallot.states import nm
from pallot.states.grid import GridRow
from pallot.states.nm import NmList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch

HOST = "candidateportal.servis.sos.state.nm.us"
INDEX = (FIXTURES / "state_nm.html").read_text(encoding="utf-8")
LISTED = (FIXTURES / "state_nm_list.html").read_bytes()


def test_the_home_page_links_the_years_general_election_to_the_grid():
    assert NmList.read_index(INDEX.encode()) == {"elections": {"2026": "2917"}}
    assert NmList.read_index(LISTED) is None
    lists = NmList.__new__(NmList)
    assert NmList.spec(lists, dt.date(2026, 11, 3)).url == nm.INDEX
    [spec] = lists.follow({"elections": {"2026": "2917"}}, dt.date(2026, 11, 3))
    assert (spec.method, spec.url, spec.params, spec.form) == ("GET", nm.PAGE, {"cty": "99", "eid": "2917"}, None)
    assert lists.follow({"elections": {"2026": "2917"}}, dt.date(2028, 11, 7)) is None
    with pytest.raises(ValueError, match="no link to a candidate list"):
        NmList.read_index(b"<html><body>Down for maintenance</body></html>")


def test_new_mexicos_list_has_congress_the_statewide_offices_the_legislature_and_retention():
    filings = NmList.parse(LISTED)
    assert {f.day for f in filings} == {""}
    races = {f.office_id: f for f in filings}
    assert Counter(f.reach for f in races.values()) == {"state": 11, "cd": 3, "sd": 1, "hd": 70}
    assert [(f.name, f.party, f.party_name) for f in filings if f.office_id == "US SENATE"] == [
        ("Ben R Lujan", "D", None), ("Larry E Marker", "R", None)]
    assert [(f.office, f.name, f.party) for f in filings if f.office_id == "GOVERNOR"] == [
        ("Governor and Lieutenant Governor", "Greggory D Hull and David M Gallegos", "R"),
        ("Governor and Lieutenant Governor", "Deb Haaland and Stephanie Garcia Richard", "D")]
    assert {f.office for f in filings if f.reach == "state" and not f.retention} == {
        "U.S. Senator", "Governor and Lieutenant Governor", "Secretary of State", "Attorney General", "State Auditor",
        "State Treasurer", "Commissioner of Public Lands", "Judge of the Court of Appeals Position 1"}
    assert [f.name for f in filings if f.office_id == "COMMISSIONER OF PUBLIC LANDS"] == [
        "Michael Jack Perry", "Juan De Jesus Sanchez, III"]
    assert [(f.office, f.name) for f in filings if f.reach == "sd"] == [
        ("State Senator District 33", "Rex A Wilson"), ("State Senator District 33", "William Neil Griffin")]
    retained = [(f.office, f.name, f.group, f.incumbent) for f in filings if f.retention]
    assert retained == [("Retain David K Thomson", "David K Thomson", "judicial", True),
                        ("Retain Shannon Bacon", "Shannon Bacon", "judicial", True),
                        ("Retain J Miles Hanisee", "J Miles Hanisee", "judicial", True)]
    assert not any(word in f.office for f in filings for word in ("Education", "County", "Magistrate", "Probate"))
    assert not any(f.name in ("Mira Oconnell", "Maggie Toulouse Oliver") for f in filings)  # disqualified, withdrawn


def test_names_in_capitals_read_as_on_the_ballot_and_dts_is_no_party():
    assert [NmList.named(n) for n in ("CLAIRE ANN MCDANIEL", "DAYAN \"DAY\" MERCEDES HOCHMAN-VIGIL",
                                      "WILLIAM (BILL) SCOTT", "AMANDA LÓPEZ ASKIN", "Ann McKay")] == [
        "Claire Ann McDaniel", "Dayan \"Day\" Mercedes Hochman-Vigil", "William (Bill) Scott", "Amanda López Askin",
        "Ann McKay"]
    row = GridRow("State Representative", "LGX", "DISTRICT 1", "PAT DOE", "DTS", 1, {})
    assert NmList.affiliation(row) == (None, None)
    assert NmList.affiliation(GridRow("State Representative", "LGX", "DISTRICT 1", "PAT DOE", "FWD", 1, {})) == (
        None, "Forward")


def test_a_list_short_of_districts_or_with_an_office_it_doesnt_know_is_refused():
    text = LISTED.decode()
    with pytest.raises(ValueError, match="2 U.S. House races, not 3"):
        NmList.parse("\n".join(line for line in text.splitlines()
                               if "<td>United States Representative</td><td>DISTRICT 3</td>" not in line))
    with pytest.raises(ValueError, match="an office it doesn't know: State Mine Inspector"):
        NmList.parse(text.replace("<td>State Auditor</td><td>State Auditor</td>",
                                  "<td>State Mine Inspector</td><td>State Mine Inspector</td>"))
    with pytest.raises(ValueError, match="no district for State Representative"):
        NmList.parse(text.replace("<td>DISTRICT 11</td>", "<td>AT LARGE</td>"))
    with pytest.raises(ValueError, match="no heading row"):
        NmList.parse(b"<html><body>Service Unavailable</body></html>")


def test_an_albuquerque_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "albuquerque")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (1, 13, 11)
    names = [race["name"] for race in ballot["races"]]
    assert names == [
        "U.S. Senator", "U.S. Representative District 1", "Governor and Lieutenant Governor", "Secretary of State",
        "Attorney General", "State Auditor", "State Treasurer", "Commissioner of Public Lands",
        "State Representative District 11", "Judge of the Court of Appeals Position 1", "Retain David K Thomson",
        "Retain Shannon Bacon", "Retain J Miles Hanisee",
    ]
    assert all(race["source"] == "state_nm" for race in ballot["races"])
    assert find_race(ballot, "Retain Shannon Bacon")["retention"]
    senate, house = ballot["races"][:2]
    assert (senate["seat"], house["seat"]) == ("NM-SEN", "NM-01")
    assert candidate_names(house) == ["Melanie Ann Stansbury", "Ndidiamaka Ekwua Charlene Okpareke"]
    assert any(card["source"] == "fec" and card["kind"] == "money" for c in house["candidates"] for card in c["cards"])
    assert any("Public Education Commission" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-06",
        "mail_apply_by": "2026-10-20", "early_voting_start": "2026-10-06", "early_voting_end": "2026-10-31",
        "source": "New Mexico Secretary of State", "source_url": "https://www.sos.nm.gov/voting-and-elections/",
        "computed": True,
    }
    assert upstream.count("www.sos.nm.gov") == 1 and upstream.count(HOST) == 1
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_nm'")]
    assert sorted(sorted(value) for value in kept) == [["elections"], ["filings"]]
    assert not any("Albuquerque" in json.dumps(value) or "Bernalillo" in json.dumps(value) for value in kept)
    get_ballot(client, "albuquerque")
    assert logged_calls() == 0 and upstream.count(HOST) == 1


def test_a_new_mexico_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "albuquerque")
    upstream.state_lists[HOST] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_nm")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "albuquerque")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "Attorney General")


def test_with_new_mexicos_list_off_or_unreadable_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_nm", False)
    ballot = get_ballot(client, "albuquerque")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 1")
    assert upstream.count(HOST) == 0
    switch(client, "state_nm", True)
    upstream.state_lists[HOST] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "albuquerque")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the New Mexico Secretary of State" in w
               for w in ballot["warnings"])


def test_a_year_the_home_page_doesnt_link_a_list_for_yet_leaves_the_fecs_races(client, upstream):
    upstream.state_lists["www.sos.nm.gov"] = INDEX.replace("2026 General", "2024 General")
    ballot = get_ballot(client, "albuquerque")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("The New Mexico Secretary of State hasn't published its list of candidates" in n for n in ballot["notes"])
    assert upstream.count(HOST) == 0


def test_new_mexicos_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_nm")
    assert outcome.status == "updated" and outcome.answers == 2
    assert outcome.counts == {"races": 85, "candidates": 129}
    assert upstream.count(HOST) == 1
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "albuquerque")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == 1


@pytest.mark.parametrize("day, register, apply, start, end", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 6), dt.date(2026, 10, 20), dt.date(2026, 10, 6), dt.date(2026, 10, 31)),
    (dt.date(2028, 11, 7), dt.date(2028, 10, 10), dt.date(2028, 10, 24), dt.date(2028, 10, 10), dt.date(2028, 11, 4)),
])
def test_new_mexicos_key_dates_are_worked_out_from_its_statutes(day, register, apply, start, end):
    found = state_key_dates.computed("NM", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, apply, start, end, "NM")
    assert register.weekday() == apply.weekday() == 1 and end.weekday() == 5
    assert state_key_dates.computed("NM", dt.date(2027, 11, 2)) is None


def test_new_mexicos_calendar_file_has_its_dates_and_hours(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "NM"})
    assert response.status_code == 200 and "new-mexico-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls are open 7 a.m. to 7 p.m." in text
    assert all(day in text for day in ("20261006", "20261031", "20261103"))
    info = state_key_dates.GUIDES["NM"].voter_info()
    assert info.poll_hours == "7 a.m. – 7 p.m." and "Election Day" in info.late_registration.label
