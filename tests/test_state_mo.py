"""Missouri's ballot (states/mo.py), from the Secretary of State's certification of candidates, a PDF
found by its link on its elections page, its U.S. House district on the 2022 map in force rather than
the geocoder's (tigerweb.GOVERNING), and its key dates worked out from the Revised Statutes of
Missouri. tests/fixtures/state_mo.html is that page cut down to its links (2024's left in its HTML
comment); state_mo.pdf is the certification as its text alone; tigerweb_layers_mo.json and
tigerweb_identify_jeffersoncity.json are TIGERweb's 2022 map at the Capitol (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.sources import tigerweb
from pallot.states import key_dates as state_key_dates
from pallot.states import mo, pdf_lines
from pallot.states.mo import MoList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, load, switch

HOST = "www.sos.mo.gov"
PAGE = (FIXTURES / "state_mo.html").read_text(encoding="utf-8")
LISTED = (FIXTURES / "state_mo.pdf").read_bytes()
LIST_URL = f"https://{HOST}/CMSImages/ElectionCandidates/2026GeneralElectionCertifiedCandidates.pdf"
CHALLENGE = "<!DOCTYPE html><html><head><title>Just a moment...</title></head><body></body></html>"


def lines() -> list[str]:
    return pdf_lines(LISTED)


def test_the_page_links_the_years_certification_but_not_one_left_in_a_comment():
    found = mo.links(PAGE)
    assert found == {"links": {"2026": LIST_URL}}
    assert "CertificationOfCandidatesNovember2024.pdf" in PAGE
    lists = MoList.__new__(MoList)
    assert lists.spec(dt.date(2026, 11, 3)).url == mo.PAGE
    assert [spec.url for spec in lists.follow(found, dt.date(2026, 11, 3))] == [LIST_URL]
    assert lists.follow(found, dt.date(2028, 11, 7)) is None
    assert MoList.read_index(PAGE.encode()) == found and MoList.read_index(LISTED) is None
    uncommented = PAGE.replace("<!--", "").replace("-->", "")
    assert mo.links(uncommented)["links"]["2024"].endswith("/CertificationOfCandidatesNovember2024.pdf")
    with pytest.raises(ValueError, match="not the Secretary of State's elections page"):
        mo.links(CHALLENGE)


def test_missouris_certification_has_congress_the_auditor_the_legislature_and_the_courts():
    filings = MoList.parse(LISTED)
    assert len(filings) == 425 and {f.day for f in filings} == {"2026-11-03"}
    races = {f.office_id: f for f in filings}
    assert Counter(f.reach for f in races.values()) == {
        "hd": 163, "unplaced": 29, "county": 20, "sd": 17, "counties": 9, "cd": 8, "state": 2}
    assert sorted(int(f.district) for f in races.values() if f.reach == "sd") == list(range(2, 35, 2))
    auditor = [(f.name, f.party, f.party_name) for f in filings if f.office_id == "STATE AUDITOR"]
    assert auditor == [("Scott Fitzpatrick", "R", None), ("Quentin Wilson", "D", None), ("Dustin Coffell", "L", None)]
    independent = next(f for f in filings if f.name == "Shane Sawyer")
    assert (independent.office, independent.party, independent.party_name) == (
        "State Representative District 128", None, "Independent")
    house = [(f.name, f.party) for f in filings if f.office == "U.S. Representative District 5"]
    assert house == [("Rick Brattin", "R"), ("Emanuel Cleaver, II", "D"), ("Randall (Randy) Langkraehr", "L")]
    judge = [(f.office, f.reach, f.counties, f.party) for f in filings if f.office_id == "CIRCUIT JUDGE 19 2"]
    assert judge == [("Circuit Judge, Circuit 19 Division 2", "county", ("COLE",), "R")]
    assert next(f for f in filings if f.office_id == "CIRCUIT JUDGE 13 4").counties == ("BOONE", "CALLAWAY")
    assert next(f for f in filings if f.office_id == "CIRCUIT JUDGE 36").reach == "unplaced"
    wilson = next(f for f in filings if f.family == "SUPREME COURT")
    assert (wilson.office, wilson.reach, wilson.retention, wilson.incumbent, wilson.party) == (
        "Retain Supreme Court Judge Paul C. Wilson", "state", True, True, None)
    appeals = next(f for f in filings if f.name == "Lisa White Hardwick")
    assert (appeals.office, appeals.district) == ("Retain Court of Appeals Western District Judge Lisa White Hardwick",
                                                  "Western")
    assert "COLE" in appeals.counties and "JACKSON" in appeals.counties and "ST. LOUIS" not in appeals.counties
    jackson = next(f for f in filings if f.name == "Abbie Rothermich")
    assert (jackson.office, jackson.reach, jackson.counties) == (
        "Retain Circuit 16 Division 25 Associate Circuit Judge Abbie Rothermich", "county", ("JACKSON",))
    assert {f.reach for f in filings if f.district in ("21", "22") and f.family.endswith("CIRCUIT JUDGE")} == {"unplaced"}
    assert not any(f.incumbent for f in filings if not f.retention) and not any(f.write_in for f in filings)


def test_the_court_of_appeals_districts_cover_every_county_once():
    every = {c for district in mo.APPEALS.values() for c in district}
    assert len(every) == sum(len(district) for district in mo.APPEALS.values()) == 114  # St. Louis's city and county alike
    assert {c for counties in mo.CIRCUITS.values() for c in counties} <= every


def test_a_presidential_years_headings_without_for_and_its_president_left_out():
    year = [line.replace("2026", "2028").replace("November 3,", "November 7,") for line in lines()]
    at = next(i for i, line in enumerate(year) if line.strip() == "REPUBLICAN CANDIDATES")
    year[at + 1:at + 1] = ["", "For President and Vice President", "Jane Doe, John Roe", "", "U.S. Senator", "Josh Hawley",
                           "", "Governor", "Mike Kehoe", "Attorney General", "Andrew Bailey"]
    filings = mo.candidates(year)
    assert {f.day for f in filings} == {"2028-11-07"}
    assert [(f.office, f.name) for f in filings[:3]] == [
        ("U.S. Senator", "Josh Hawley"), ("Governor", "Mike Kehoe"), ("Attorney General", "Andrew Bailey")]
    assert not any("President" in f.office or f.name == "Jane Doe, John Roe" for f in filings)


def test_a_list_short_of_districts_or_with_an_office_it_doesnt_know_is_refused():
    text = lines()
    with pytest.raises(ValueError, match="14 State Senate races, not 15"):
        mo.candidates(_without_senate_districts(text, ("2", "4", "6")))
    with pytest.raises(ValueError, match="an office it doesn't know: For Lieutenant Governor of the Moon"):
        mo.candidates([line.replace("For State Auditor", "For Lieutenant Governor of the Moon") for line in text])
    with pytest.raises(ValueError, match="not the certification of general election candidates"):
        mo.candidates(["Elections & Voting Division", "Maintenance"])
    with pytest.raises(ValueError, match="not a PDF it can read"):
        MoList.parse(CHALLENGE.encode())


def _without_senate_districts(text: list[str], districts: tuple[str, ...]) -> list[str]:
    """The certification's lines without every party's State Senate candidates in ``districts``."""
    kept, heading = [], ""
    for line in text:
        if line.strip().startswith("For "):
            heading = line.strip()
        if heading == "For State Senator" and any(line.strip().startswith(f"District {n},") for n in districts):
            continue
        kept.append(line)
    return kept


def test_a_jefferson_city_ballot_has_its_races_on_the_2022_map(client, upstream, logged_calls, tmp_path):
    census = load("census_jeffersoncity.json")["result"]["addressMatches"][0]["geographies"]
    assert census["120th Congressional Districts"][0]["BASENAME"] == "5"  # the 2025 map the geocoder gives
    ballot = get_ballot(client, "jeffersoncity")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"], "labels": {}}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (3, 6, 60)
    names = [race["name"] for race in ballot["races"]]
    assert names == [
        "U.S. Representative District 3", "State Auditor", "State Senator District 6", "State Representative District 60",
        "Circuit Judge, Circuit 19 Division 2", "Circuit Judge, Circuit 19 Division 3",
        "Retain Supreme Court Judge Paul C. Wilson", "Retain Court of Appeals Western District Judge Lisa White Hardwick",
    ]
    assert all(race["source"] == "state_mo" for race in ballot["races"])
    house = find_race(ballot, "U.S. Representative District 3")
    assert house["seat"] == "MO-03" and candidate_names(house) == ["Bob Onder", "Bethany E Mann", "Jim Higgins"]
    assert any(card["source"] == "fec" and card["kind"] == "money" for c in house["candidates"] for card in c["cards"])
    assert find_race(ballot, "Retain Supreme Court Judge Paul C. Wilson")["retention"]
    assert any("Missouri's 2022 map" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-07",
        "mail_apply_by": "2026-10-21", "early_voting_start": "2026-10-20", "early_voting_end": "2026-11-02",
        "source": "Missouri Secretary of State", "source_url": "https://www.sos.mo.gov/elections", "computed": True,
    }
    assert upstream.count(HOST) == 2 and upstream.count("tigerWMS_ACS2024") == 2
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_mo'")]
    assert sorted(sorted(value) for value in kept) == [["filings"], ["links"]]
    get_ballot(client, "jeffersoncity")
    assert logged_calls() == 0 and upstream.count(HOST) == 2 and upstream.count("tigerWMS_ACS2024") == 2


def test_only_missouris_house_district_comes_from_its_map_in_force(client, upstream):
    get_ballot(client, "annapolis")
    assert upstream.count("tigerWMS_ACS2024") == 0
    assert tigerweb.service_of("cd", "MO") == tigerweb.GOVERNING["MO"]
    assert tigerweb.service_of("sd", "MO") == tigerweb.service_of("cd", "TX") == tigerweb.SERVICE
    response = client.get("/api/district-outlines", params={"state": "MO", "cd": 3, "sd": 6})
    assert response.status_code == 200
    assert upstream.count("tigerWMS_ACS2024/MapServer/54/query") == 1 and "GEOID='2903'" in upstream.tigerweb_wheres
    assert upstream.count("tigerWMS_Current/MapServer/54/query") == 0


def test_a_missouri_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "jeffersoncity")
    upstream.state_lists[f"{HOST}/CMSImages/ElectionCandidates/2026GeneralElectionCertifiedCandidates.pdf"] = CHALLENGE
    status, said = make_app.cache_command("hard-refresh", "state_mo")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "jeffersoncity")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "State Auditor")


def test_with_missouris_list_off_or_unreadable_its_ballot_has_the_race_for_congress_from_the_fec(client, upstream):
    switch(client, "state_mo", False)
    ballot = get_ballot(client, "jeffersoncity")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 3")
    assert upstream.count(HOST) == 0
    switch(client, "state_mo", True)
    upstream.state_lists[f"{HOST}/elections"] = CHALLENGE
    ballot = get_ballot(client, "jeffersoncity")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Missouri Secretary of State" in w for w in ballot["warnings"])


def test_a_year_the_page_doesnt_link_yet_leaves_the_fecs_races(client, upstream):
    upstream.state_lists[f"{HOST}/elections"] = PAGE.replace("November 2026", "November 2024").replace("2026General",
                                                                                                        "2024General")
    ballot = get_ballot(client, "jeffersoncity")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("The Missouri Secretary of State hasn't published its list of candidates" in n for n in ballot["notes"])
    assert upstream.count(HOST) == 1


def test_missouris_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_mo")
    assert outcome.status == "updated" and outcome.answers == 2
    assert outcome.counts == {"races": 248, "candidates": 425}
    assert upstream.count(HOST) == 2
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "jeffersoncity")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == 2


@pytest.mark.parametrize("day, register, apply, start, end", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 7), dt.date(2026, 10, 21), dt.date(2026, 10, 20), dt.date(2026, 11, 2)),
    (dt.date(2028, 11, 7), dt.date(2028, 10, 11), dt.date(2028, 10, 25), dt.date(2028, 10, 24), dt.date(2028, 11, 6)),
])
def test_missouris_key_dates_are_worked_out_from_its_statutes(day, register, apply, start, end):
    """2026's against the Secretary of State's 2026 election calendar."""
    found = state_key_dates.computed("MO", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, apply, start, end, "MO")
    assert register.weekday() == apply.weekday() == 2 and start.weekday() == 1
    assert state_key_dates.computed("MO", dt.date(2027, 11, 2)) is None


def test_missouris_calendar_file_and_when_to_vote_need_an_excuse_to_vote_by_mail(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "MO"})
    assert response.status_code == 200 and "missouri-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls are open 6 a.m. to 7 p.m.\\; if you're in line at 7\\, you can vote." in text
    assert all(day in text for day in ("20261007", "20261021", "20261020", "20261102", "20261103"))
    info = state_key_dates.GUIDES["MO"].voter_info()
    assert info.poll_hours == "6 a.m. – 7 p.m." and info.late_registration is None
    assert info.mail_eligibility.startswith("Only if you're away on Election Day")
