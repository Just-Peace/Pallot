"""Nebraska's ballot (states/ne.py), from the Secretary of State's candidate list and its judges
for retention, both PDFs found by their links on its elections page, and its key dates worked out
from the Nebraska Revised Statutes. tests/fixtures/state_ne.html is that page cut down to its
links; state_ne.pdf is the candidate list rewritten without contact details, its pages turned
sideways as served, and state_ne_retention.pdf the judges' list as served
(scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import key_dates as state_key_dates
from pallot.states import ne, pdf_lines
from pallot.states.ne import NeList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch

HOST = "sos.nebraska.gov"
PAGE = (FIXTURES / "state_ne.html").read_text(encoding="utf-8")
LISTED = (FIXTURES / "state_ne.pdf").read_bytes()
JUDGES = (FIXTURES / "state_ne_retention.pdf").read_bytes()
FOLDER = "https://sos.nebraska.gov/sites/default/files/doc/elections/2026/"
LIST_PATH = "/sites/default/files/doc/elections/2026/Final_Statewide_General_Candidate_Filing_List_9.11.26.pdf"


def test_the_page_links_the_years_list_and_its_judges():
    found = ne.links(PAGE)
    assert found == {
        "links": {"2026": f"{FOLDER}Final_Statewide_General_Candidate_Filing_List_9.11.26.pdf"},
        "retention": {"2026": f"{FOLDER}Final_List_of_Judges_Who_Filed_for_Retention_List_8.3.26.pdf"},
    }
    lists = NeList.__new__(NeList)
    assert [spec.url for spec in lists.follow(found, dt.date(2026, 11, 3))] == [
        found["links"]["2026"], found["retention"]["2026"]]
    assert lists.follow(found, dt.date(2028, 11, 7)) is None
    assert [spec.url for spec in lists.follow({**found, "retention": {}}, dt.date(2026, 11, 3))] == [
        found["links"]["2026"]]
    earlier = PAGE.replace("Final_Statewide", "Statewide").replace("</body>", (
        '<p><a href="/sites/default/files/doc/elections/2026/Final_Statewide_General_Candidate_Filing_List_9.11.26.pdf">'
        "x</a></p></body>"))
    assert ne.links(earlier)["links"]["2026"].endswith("/Final_Statewide_General_Candidate_Filing_List_9.11.26.pdf")
    with pytest.raises(ValueError, match="not the Secretary of State's elections page"):
        ne.links("<html><head><title>Maintenance</title></head></html>")


def test_the_lists_pages_are_read_upright():
    lines = pdf_lines(LISTED)
    assert "Final Statewide General Candidate List" in lines[0]
    assert any(line.startswith("For United States Senator") for line in lines)


def test_nebraskas_list_has_congress_the_statewide_offices_and_a_nonpartisan_legislature():
    filings = NeList.parse(LISTED)
    assert len(filings) == 77 and {f.day for f in filings} == {"2026-11-03"}
    assert Counter(f.reach for f in {f.office_id: f for f in filings}.values()) == {"state": 6, "cd": 3, "sd": 25}
    senate = [(f.name, f.party, f.party_name, f.incumbent) for f in filings if f.office_id == "US SENATE"]
    assert senate == [("Pete Ricketts", "R", None, True), ("Mike Marvin", None, "Legal Marijuana NOW", False),
                      ("Robin Richards", None, "Nebraska Working People", False),
                      ("Chuck Conboy", None, "America First", False), ("Dan Osborn", None, "By Petition", False)]
    governor = [(f.office, f.name, f.party) for f in filings if f.office_id == "GOVERNOR"][0]
    assert governor == ("Governor and Lieutenant Governor", "Jim Pillen and Joe Kelly", "R")
    assert {f.office for f in filings if f.reach == "state"} == {
        "U.S. Senator", "Governor and Lieutenant Governor", "Secretary of State", "State Treasurer", "Attorney General",
        "Auditor of Public Accounts"}
    legislature = [f for f in filings if f.reach == "sd"]
    assert all(f.party is None and f.party_name is None and f.group == "legislature" for f in legislature)
    assert sorted({int(f.district) for f in legislature}) == sorted([*range(2, 50, 2), 41])
    assert [(f.office, f.name, f.unexpired) for f in legislature if f.district == "41"] == [
        ("Member of the Legislature District 41", "Joe Johnson", True),
        ("Member of the Legislature District 41", "Jeremy Heneger", True)]
    assert not any(f.unexpired for f in filings if f.district != "41")
    assert not any("Regent" in f.office or "Board" in f.office or "Commission" in f.office for f in filings)


def test_the_judges_it_places_are_retention_questions():
    found = NeList.parse(JUDGES)
    assert [(f.office, f.reach, f.counties, f.name) for f in found] == [
        ("Retain Workers' Compensation Court Judge Thomas E. Stine", "state", (), "Thomas E. Stine"),
        ("Retain Workers' Compensation Court Judge Dirk V. Block", "state", (), "Dirk V. Block"),
        ("Retain Sarpy County Separate Juvenile Court Judge Sarah M. Moore", "county", ("SARPY",), "Sarah M. Moore"),
        ("Retain Douglas County Separate Juvenile Court Judge Matthew R. Kahler", "county", ("DOUGLAS",),
         "Matthew R. Kahler"),
    ]
    assert all(f.retention and f.incumbent and f.group == "judicial" and f.day == "2026-11-03" for f in found)
    kept = NeList.read_index(JUDGES)
    assert kept["links"] == {} and len(kept["filings"]) == 4
    assert "links" not in NeList.read_index(LISTED)


def test_a_list_short_of_districts_or_with_an_office_it_doesnt_know_is_refused():
    lines = pdf_lines(LISTED)
    with pytest.raises(ValueError, match="19 State Senate races, not 20"):
        ne.candidates([line for line in lines if not (line.startswith("For Member of the Legislature")
                                                      and any(f"District {n} " in line for n in range(40, 50)))])
    with pytest.raises(ValueError, match="an office it doesn't know: For Lieutenant Governor"):
        ne.candidates([line.replace("For State Treasurer", "For Lieutenant Governor") for line in lines])
    with pytest.raises(ValueError, match="not the list of general election candidates"):
        ne.candidates(lines[2:])
    with pytest.raises(ValueError, match="a court it can't place"):
        ne.retention([line.replace("Statewide", "Eastern") for line in pdf_lines(JUDGES)])
    with pytest.raises(ValueError, match="not a PDF it can read"):
        NeList.parse(b"<html><body>Service Unavailable</body></html>")


def test_an_omaha_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "omaha")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd"],
                                  "labels": {"sd": "Legislature"}}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"]) == (2, 8)
    names = [race["name"] for race in ballot["races"]]
    assert names == [
        "U.S. Senator", "U.S. Representative District 2", "Governor and Lieutenant Governor", "Secretary of State",
        "State Treasurer", "Attorney General", "Auditor of Public Accounts", "Member of the Legislature District 8",
        "Retain Workers' Compensation Court Judge Thomas E. Stine",
        "Retain Workers' Compensation Court Judge Dirk V. Block",
        "Retain Douglas County Separate Juvenile Court Judge Matthew R. Kahler",
    ]
    legislature = find_race(ballot, "Member of the Legislature District 8")
    assert candidate_names(legislature) == ["Josh Livingston", "Erin Feichtinger"]
    assert all(c["party"] is None and c["party_name"] is None for c in legislature["candidates"])
    holder = legislature["holder"]
    assert (holder["name"], holder.get("party"), holder.get("party_name")) == ("Megan Hunt", None, None)
    assert all(race["source"] == "state_ne" for race in ballot["races"])
    assert find_race(ballot, "Retain Douglas County Separate Juvenile Court Judge Matthew R. Kahler")["retention"]
    senate, house = ballot["races"][:2]
    assert (senate["seat"], house["seat"]) == ("NE-SEN", "NE-02")
    assert candidate_names(house) == ["Brinker Harding", "Denise Powell", "Eric Michael Foreman"]
    assert any(card["source"] == "fec" and card["kind"] == "money" for c in senate["candidates"] for card in c["cards"])
    assert any("Public Service Commission" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-16",
        "mail_apply_by": "2026-10-23", "early_voting_start": "2026-10-05", "early_voting_end": "2026-11-02",
        "source": "Nebraska Secretary of State", "source_url": "https://sos.nebraska.gov/elections",
        "computed": True,
    }
    assert upstream.count(HOST) == 3
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_ne'")]
    assert sorted(sorted(value) for value in kept) == [["filings"], ["filings", "links"], ["links", "retention"]]
    assert not any("Omaha" in json.dumps(value) or "Plattsmouth" in json.dumps(value) for value in kept)
    get_ballot(client, "omaha")
    assert logged_calls() == 0 and upstream.count(HOST) == 3


def test_a_nebraska_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "omaha")
    upstream.state_lists[f"{HOST}{LIST_PATH}"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_ne")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "omaha")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "Attorney General")


def test_with_nebraskas_list_off_or_unreadable_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_ne", False)
    ballot = get_ballot(client, "omaha")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 2")
    assert upstream.count(HOST) == 0
    switch(client, "state_ne", True)
    upstream.state_lists[f"{HOST}{LIST_PATH}"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "omaha")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Nebraska Secretary of State" in w for w in ballot["warnings"])


def test_a_year_the_page_doesnt_link_a_list_for_yet_leaves_the_fecs_races(client, upstream):
    upstream.state_lists[f"{HOST}/elections"] = PAGE.replace("/2026/", "/2024/")
    ballot = get_ballot(client, "omaha")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("The Nebraska Secretary of State hasn't published its list of candidates" in n for n in ballot["notes"])
    assert upstream.count(HOST) == 1


def test_nebraskas_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_ne")
    assert outcome.status == "updated" and outcome.answers == 3
    assert outcome.counts == {"races": 38, "candidates": 81}
    assert upstream.count(HOST) == 3
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "omaha")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == 3


@pytest.mark.parametrize("day, register, apply, start, end", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 16), dt.date(2026, 10, 23), dt.date(2026, 10, 5), dt.date(2026, 11, 2)),
    (dt.date(2028, 11, 7), dt.date(2028, 10, 20), dt.date(2028, 10, 27), dt.date(2028, 10, 9), dt.date(2028, 11, 6)),
])
def test_nebraskas_key_dates_are_worked_out_from_its_statutes(day, register, apply, start, end):
    found = state_key_dates.computed("NE", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, apply, start, end, "NE")
    assert register.weekday() == apply.weekday() == 4 and start.weekday() == 0
    assert state_key_dates.computed("NE", dt.date(2027, 11, 2)) is None


def test_nebraskas_calendar_file_has_its_dates_and_both_time_zones_hours(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "NE"})
    assert response.status_code == 200 and "nebraska-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "8 a.m. to 8 p.m. Central time\\, 7 a.m. to 7 p.m. Mountain time" in text
    assert all(day in text for day in ("20261016", "20261005", "20261102", "20261103"))
    assert state_key_dates.GUIDES["NE"].hours == "8 a.m. – 8 p.m. Central, 7 a.m. – 7 p.m. Mountain"
