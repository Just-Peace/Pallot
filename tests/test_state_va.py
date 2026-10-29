"""Virginia's ballot (states/va.py), from the Department of Elections' candidate lists, found by
their links on its Candidates & Referendums page, and its key dates worked out from the Code of
Virginia. tests/fixtures/state_va.html is that page cut down to its links; state_va_all.html is
2026's list of all offices and state_va_2023.html 2023's General Assembly list, both without
their contact columns and the first cut down (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import key_dates as state_key_dates
from pallot.states import va
from pallot.states.va import VaList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot

HOST = "www.elections.virginia.gov"
PAGE = (FIXTURES / "state_va.html").read_text(encoding="utf-8")
ALL = (FIXTURES / "state_va_all.html").read_text(encoding="utf-8")
ODD_YEAR = (FIXTURES / "state_va_2023.html").read_text(encoding="utf-8")
LISTS = "https://www.elections.virginia.gov/casting-a-ballot/candidate-list/"


def test_the_page_links_each_elections_lists_and_the_one_of_all_offices_is_read():
    found = va.links(PAGE)
    assert found == {"links": {"2026-11-03": {
        kind: f"{LISTS}november-3-2026-gen-elect-{kind}/" for kind in ("all-offices", "federal-offices", "local-offices")}}}
    lists = VaList.__new__(VaList)
    assert [spec.url for spec in lists.follow(found, dt.date(2026, 11, 3))] == [f"{LISTS}november-3-2026-gen-elect-all-offices/"]
    assert lists.follow(found, dt.date(2027, 11, 2)) is None
    assert VaList.read_index(PAGE.encode()) == found and VaList.read_index(ALL.encode()) is None
    with pytest.raises(ValueError, match="not the Department of Elections' Candidates & Referendums page"):
        va.links("<html><head><title>Page not found</title></head></html>")


def test_an_odd_years_lists_are_found_by_their_links_whatever_theyre_named():
    odd = {kind: f"https://www.elections.virginia.gov/casting-a-ballot/candidate-list/november-4-2025-gen-elect-{kind}/"
           for kind in ("house-of-del", "local-offices", "statewide-offices")}
    page = PAGE.replace("</body>", "".join(f'<p><a href="{url}">{kind}</a></p>' for kind, url in odd.items()) + "</body>")
    found = va.links(page)["links"]
    assert set(found) == {"2026-11-03", "2025-11-04"}
    assert va.read(found["2025-11-04"]) == [odd["house-of-del"], odd["statewide-offices"]]
    assert va.read({**found["2025-11-04"], "all-office": f"{LISTS}november-4-2025-gen-elect-all-office/"}) == [
        f"{LISTS}november-4-2025-gen-elect-all-office/"]


def test_the_list_of_all_offices_has_congress_and_the_special_once_each_without_the_local_offices():
    filings = VaList.parse(ALL)
    assert {f.day for f in filings} == {"2026-11-03"} and len(filings) == 40
    assert Counter(f.reach for f in {f.office_id: f for f in filings}.values()) == {"state": 1, "cd": 11, "hd": 1}
    senate = sorted((f for f in filings if f.office_id == "US SENATE"), key=lambda f: f.order)
    assert [(f.name, f.party, f.incumbent) for f in senate] == [("Mark R. Warner", "D", True), ("Bert Mizusawa", "R", False)]
    fourth = sorted((f for f in filings if f.district == "4" and f.reach == "cd"), key=lambda f: f.order)
    assert [(f.name, f.party, f.party_name, f.incumbent) for f in fourth] == [
        ("Jennifer L. McClellan", "D", None, True), ('Robert P. "Family Man" Murray, Jr.', "R", None, False),
        ('Joan E. "Andrews" Bell', None, "Independent", False)]
    special = {f.office for f in filings if f.reach == "hd"}
    assert special == {"House of Delegates District 20"}
    assert not any("School Board" in f.office or f.name == "Anne B. Holton" for f in filings)


def test_an_odd_years_list_has_the_whole_legislature_on_its_election_day():
    filings = VaList.parse(ODD_YEAR)
    assert {f.day for f in filings} == {"2023-11-07"} and len(filings) == 251
    races = {f.office_id: f for f in filings}.values()
    assert Counter((f.reach, f.group) for f in races) == {("sd", "legislature"): 40, ("hd", "legislature"): 100}
    first = sorted((f for f in filings if f.reach == "sd" and f.district == "2"), key=lambda f: f.order)
    assert [(f.office, f.name, f.party) for f in first] == [
        ("State Senator District 2", "Kathy A. Beery", "D"), ("State Senator District 2", "Mark D. Obenshain", "R"),
        ("State Senator District 2", "Joshua J. Huffman", "L")]
    third = [(f.office, f.name, f.party, f.party_name) for f in filings if f.reach == "hd" and f.district == "3"]
    assert third == [("House of Delegates District 3", "Alfonso H. Lopez", "D", None),
                     ("House of Delegates District 3", "Major Mike Webb", None, "Independent")]
    assert not any(f.incumbent for f in filings)  # its columns don't say


def test_a_page_that_isnt_a_whole_list_is_refused():
    with pytest.raises(ValueError, match="no election date or column headings"):
        VaList.parse("<html><body><h1>Page not found</h1></body></html>")
    short = "\n".join(line for line in ODD_YEAR.splitlines() if not re.search(r"Delegates</td><td>(9\d|100)<", line))
    with pytest.raises(ValueError, match="89 State House races, not 90"):
        VaList.parse(short)
    with pytest.raises(ValueError, match="not the columns it reads"):
        VaList.parse(ALL.replace("Candidate Party", "Party"))


def test_a_richmond_ballot_has_its_races_from_the_list_and_keeps_only_the_candidates(client, upstream, logged_calls,
                                                                                      tmp_path):
    ballot = get_ballot(client, "richmond")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"],
                                  "labels": {"hd": "House of Delegates"}}
    assert (ballot["districts"]["sd"], ballot["districts"]["hd"]) == (14, 78)
    assert [race["name"] for race in ballot["races"]] == ["U.S. Senator", "U.S. Representative District 4"]
    house = find_race(ballot, "U.S. Representative District 4")
    assert [c["incumbent"] for c in house["candidates"]] == [True, False, False]
    assert candidate_names(house)[0] == "Jennifer L. McClellan"
    assert any("general registrar's sample ballot" in note for note in ballot["notes"])
    assert upstream.count(HOST) == 2
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_va'")]
    assert sorted(sorted(value) for value in kept) == [["filings"], ["links"]]
    assert not any("Holton" in json.dumps(value) for value in kept)
    get_ballot(client, "richmond")
    assert logged_calls() == 0 and upstream.count(HOST) == 2


def test_virginias_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_va")
    assert outcome.status == "updated" and outcome.answers == 2
    assert outcome.counts == {"races": 13, "candidates": 40}
    asked = upstream.count(HOST)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "richmond")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == asked


@pytest.mark.parametrize("day, register, early", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 23), dt.date(2026, 9, 18)),
    (dt.date(2027, 11, 2), dt.date(2027, 10, 22), dt.date(2027, 9, 17)),
])
def test_virginias_key_dates_come_every_november(day, register, early):
    found = state_key_dates.computed("VA", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        register, register, early, day - dt.timedelta(days=3))
