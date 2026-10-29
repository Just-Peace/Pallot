"""Maine's ballot (states/me.py), from the Secretary of State's candidate spreadsheet and its
declared write-ins, both found by their links on its Upcoming Elections page and asked with a
browser's headers, and its key dates worked out from the Maine Revised Statutes.
tests/fixtures/state_me.html is that page cut down to its links; state_me.xlsx and
state_me_write_ins.pdf are the files as served (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.models import Candidate, Race
from pallot.states import key_dates as state_key_dates
from pallot.states import me, pdf_lines, sheet_rows
from pallot.states.me import MeList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch

HOST = "www.maine.gov"
PAGE = (FIXTURES / "state_me.html").read_text(encoding="utf-8")
LISTED = (FIXTURES / "state_me.xlsx").read_bytes()
WRITE_INS = (FIXTURES / "state_me_write_ins.pdf").read_bytes()
LIST_PATH = "/sos/sites/maine.gov.sos/files/inline-files/2026 General Candidate List - FINAL.xlsx"


def test_the_page_links_the_years_list_and_the_write_ins():
    found = me.links(PAGE)
    assert found == {
        "links": {"2026": "https://www.maine.gov/sos/sites/maine.gov.sos/files/inline-files/"
                          "2026%20General%20Candidate%20List%20-%20FINAL.xlsx"},
        "write_ins": ["https://www.maine.gov/sos/sites/maine.gov.sos/files/inline-files/"
                      "Nov26%20Declared%20Write%20in%20List%20-%20Updated%2010.15.26.pdf"],
    }
    lists = MeList.__new__(MeList)
    assert [spec.url for spec in lists.follow(found, dt.date(2026, 11, 3))] == [
        found["links"]["2026"], *found["write_ins"]]
    assert lists.follow(found, dt.date(2028, 11, 7)) is None
    assert MeList.spec(None, dt.date(2028, 11, 7)).headers["user-agent"].startswith("Mozilla/")
    with pytest.raises(ValueError, match="not the Secretary of State's Upcoming Elections page"):
        me.links("<html><head><title>Maintenance</title></head></html>")


def test_maines_list_has_congress_governor_and_the_legislature_but_not_its_county_offices():
    filings = MeList.parse(LISTED)
    assert len(filings) == 352 and {f.day for f in filings} == {"2026-11-03"}
    assert Counter(f.reach for f in {f.office_id: f for f in filings}.values()) == {"state": 2, "cd": 2, "sd": 35,
                                                                                     "hd": 151}
    senate = [(f.name, f.party, f.party_name) for f in filings if f.office_id == "US SENATE"]
    assert senate == [("Susan M. Collins", "R", None), ("Troy D. Jackson", "D", None)]
    governor = {f.name: (f.office, f.party, f.party_name) for f in filings if f.reach == "state" and f.group == "state"}
    assert governor["Rick Bennett"] == ("Governor", None, "Independent")
    house = {(f.district, f.name) for f in filings if f.reach == "cd"}
    assert ("2", "Paul R. LePage") in house and ("1", "Chellie Pingree") in house
    stewart = next(f for f in filings if f.reach == "sd" and f.district == "2" and f.party == "R")
    assert (stewart.name, stewart.office) == ("Harold L. Stewart III", "State Senator District 2")
    assert next(f for f in filings if f.name == "Stephen Richard Carey").party_name == "Unenrolled"
    assert not any(f.write_in or f.incumbent for f in filings)
    assert not any("Sheriff" in f.office or "Pellerin" in f.name for f in filings)


def test_the_declared_write_ins_are_write_ins_in_their_races():
    found = MeList.parse(WRITE_INS)
    assert [(f.office, f.name, f.party, f.party_name) for f in found] == [
        ("U.S. Senator", "Brent Andrews", None, None),
        ("U.S. Senator", "Sigrid Ann Olson", "D", None),
        ("U.S. Senator", "Gina Oswald", None, "Independent"),
        ("U.S. Senator", "Joseph Steinberger", None, "Faith in Humanity"),
        ("U.S. Senator", "Michael Turcotte", None, "Un-enrolled"),
        ("U.S. Senator", "Ashley J. Webb", "D", None),
        ("U.S. Representative District 2", "Gregory A. Ward", None, "Independent"),
        ("Governor", "John Glowa", None, "independent/unenrolled"),
        ("Governor", "Randy Wilcox", "R", None),
        ("State Representative District 24", "Daniel LaPointe", "R", None),
    ]
    assert all(f.write_in and f.day == "2026-11-03" for f in found)
    kept = MeList.read_index(WRITE_INS)
    assert kept["links"] == {} and len(kept["filings"]) == 10
    assert MeList.read_index(LISTED) is None


def test_a_list_short_of_districts_or_with_an_office_it_doesnt_know_is_refused():
    sheet, rows = sheet_rows(LISTED)
    with pytest.raises(ValueError, match="139 State House races, not 140"):
        me.parse_rows(sheet, [r for r in rows if not (r and r[0] == "SR" and int(r[1]) > 139)])
    with pytest.raises(ValueError, match="an office it doesn't know: PR"):
        me.parse_rows(sheet, rows + [["PR", "", "", "D", "46000", "Doe", "Pat", "", "", "Augusta"]])
    with pytest.raises(ValueError, match="a row without a name"):
        me.parse_rows(sheet, rows + [["SR", "5", "", "D", "46000", "", "", "", "", "Augusta"]])
    with pytest.raises(ValueError, match="not the general election's list"):
        me.parse_rows("Sheet1", rows)
    with pytest.raises(ValueError, match="not the list of general election candidates"):
        me.parse_rows(sheet, [["Name", "Office"], *rows[1:]])
    with pytest.raises(ValueError, match="not the list of declared write-in candidates"):
        me.write_ins([line for line in pdf_lines(WRITE_INS) if "Declared" not in line])
    with pytest.raises(ValueError, match="not a spreadsheet it can read"):
        MeList.parse(b"<html><body>Service Unavailable</body></html>")


def test_maines_races_for_congress_are_ranked_choice_with_three_candidates_two_on_the_ballot():
    def race(group: str, *write_ins: bool) -> Race:
        return Race(key="k", name="n", group=group, source="state_me",
                    candidates=[Candidate(key=str(i), name=str(i), write_in=w) for i, w in enumerate(write_ins)])

    assert MeList.ranked_choice(race("federal", False, False, True))
    assert MeList.ranked_choice(race("federal", False, False, False))
    assert not MeList.ranked_choice(race("federal", False, False))
    assert not MeList.ranked_choice(race("federal", False, True, True))
    assert not MeList.ranked_choice(race("state", False, False, False))


def test_a_bangor_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "bangor")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (2, 9, 22)
    names = [race["name"] for race in ballot["races"]]
    assert names == ["U.S. Senator", "U.S. Representative District 2", "Governor", "State Senator District 9",
                     "State Representative District 22"]
    assert candidate_names(find_race(ballot, "State Senator District 9")) == ["Stephen Richard Carey", "Amy J. Roeder"]
    assert all(race["source"] == "state_me" for race in ballot["races"])
    assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
    senate, house, governor = ballot["races"][:3]
    assert (senate["seat"], house["seat"]) == ("ME-SEN", "ME-02")
    assert candidate_names(house) == ["Matthew G. Dunlap", "Paul R. LePage", "Gregory A. Ward"]
    assert [c["write_in"] for c in house["candidates"]] == [False, False, True]
    assert (senate["ranked_choice"], house["ranked_choice"], governor["ranked_choice"]) == (True, True, False)
    assert any(card["source"] == "fec" and card["kind"] == "money" for c in senate["candidates"] for card in c["cards"])
    assert any("sheriff" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-13",
        "mail_apply_by": "2026-10-29", "early_voting_start": None, "early_voting_end": "2026-10-29",
        "source": "Maine Secretary of State", "source_url": "https://www.maine.gov/sos/elections-voting",
        "computed": True,
    }
    assert upstream.count(HOST) == 3
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_me'")]
    assert sorted(sorted(value) for value in kept) == [["filings"], ["filings", "links"], ["links", "write_ins"]]
    assert not any("Bangor" in json.dumps(value) or "Allagash" in json.dumps(value) for value in kept)
    get_ballot(client, "bangor")
    assert logged_calls() == 0 and upstream.count(HOST) == 3


def test_a_maine_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "bangor")
    upstream.state_lists[f"{HOST}{LIST_PATH}"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_me")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "bangor")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "Governor")


def test_with_maines_list_off_or_unreadable_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_me", False)
    ballot = get_ballot(client, "bangor")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 2")
    assert upstream.count(HOST) == 0
    switch(client, "state_me", True)
    upstream.state_lists[f"{HOST}{LIST_PATH}"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "bangor")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Maine Secretary of State" in w for w in ballot["warnings"])


def test_a_year_the_page_doesnt_link_a_list_for_yet_leaves_the_fecs_races(client, upstream):
    upstream.state_lists[f"{HOST}/sos/elections-voting/upcoming-elections"] = PAGE.replace("2026%20General", "2024%20General")
    ballot = get_ballot(client, "bangor")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("The Maine Secretary of State hasn't published its list of candidates" in n for n in ballot["notes"])
    assert upstream.count(HOST) == 1


def test_maines_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_me")
    assert outcome.status == "updated" and outcome.answers == 3
    assert outcome.counts == {"races": 190, "candidates": 362}
    assert upstream.count(HOST) == 3
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "bangor")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == 3


@pytest.mark.parametrize("day, register, apply", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 13), dt.date(2026, 10, 29)),
    (dt.date(2028, 11, 7), dt.date(2028, 10, 17), dt.date(2028, 11, 2)),
])
def test_maines_key_dates_are_worked_out_from_its_statutes(day, register, apply):
    found = state_key_dates.computed("ME", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, apply, None, apply, "ME")
    assert state_key_dates.computed("ME", dt.date(2027, 11, 2)) is None


def test_maines_calendar_file_has_its_dates_and_its_towns_poll_hours(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "ME"})
    assert response.status_code == 200 and "maine-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls close at 8 p.m.\\; your town sets when they open." in text
    assert "20261013" in text and "20261029" in text
    assert state_key_dates.GUIDES["ME"].hours == "until 8 p.m."
