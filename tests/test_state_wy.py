"""Wyoming's ballot (states/wy.py), from the Secretary of State's General Election Candidates data
file, and its key dates worked out from the Wyoming Statutes. tests/fixtures/state_wy.csv is that
file with every candidate's contact details made up (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import key_dates as state_key_dates
from pallot.states import wy
from pallot.states.wy import WyList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch

LIST = (FIXTURES / "state_wy.csv").read_text(encoding="utf-8")


def wy_calls(upstream) -> int:
    return upstream.count("sos.wyo.gov")


def test_wyomings_list_has_congress_the_statewide_offices_the_legislature_and_the_judges():
    filings = WyList.parse(LIST.encode())
    partisan = [f for f in filings if f.group != "judicial"]
    assert (len(partisan), len({f.office_id for f in partisan})) == (130, 86)
    assert Counter(f.party or f.party_name for f in partisan) == {
        "R": 83, "D": 35, "Constitution Party": 6, "L": 5, "Independent": 1}
    assert {f.day for f in filings} == {"2026-11-03"}
    house = [(f.name, f.party, f.party_name, f.office, f.reach, f.district) for f in filings if f.reach == "cd"]
    assert house == [
        ("Chuck Gray", "R", None, "U.S. Representative At Large", "cd", "0"),
        ("Lisa Kinney", "D", None, "U.S. Representative At Large", "cd", "0"),
        ("Shawn Johnson", "L", None, "U.S. Representative At Large", "cd", "0"),
        ("Jeffrey Haggit", None, "Constitution Party", "U.S. Representative At Large", "cd", "0")]
    assert list(dict.fromkeys(f.office for f in filings if f.group == "state")) == list(wy.STATEWIDE)
    assert {f.district for f in filings if f.reach == "hd"} == {str(n) for n in range(1, 63)}
    assert len({f.district for f in filings if f.reach == "sd"}) == 17
    eleventh = [(f.name, f.office) for f in filings if f.reach == "hd" and f.district == "11"]
    assert eleventh == [("Dan McIntosh", "State Representative District 11"),
                        ("Britney Tennant", "State Representative District 11"),
                        ("Ryan Shollenberger", "State Representative District 11")]


def test_the_judges_standing_for_retention_are_each_a_race_by_their_judicial_district():
    judges = [f for f in WyList.parse(LIST) if f.group == "judicial"]
    assert len(judges) == len({f.office_id for f in judges}) == 21
    assert all(f.incumbent and f.party is None and f.party_name is None for f in judges)
    supreme = [(f.office, f.reach) for f in judges if f.family == "SUPREME COURT"]
    assert supreme == [("Retain Supreme Court Justice Bridget Hill", "state"),
                       ("Retain Supreme Court Justice Robert C. Jarosh", "state")]
    cooley = next(f for f in judges if f.name == "Robin S. Cooley")
    assert (cooley.office, cooley.reach, cooley.district, cooley.counties) == (
        "Retain District Court Judge Robin S. Cooley, 1st Judicial District", "counties", "1", ("LARAMIE",))
    weisman = next(f for f in judges if f.name == "Erin E. Weisman")
    assert weisman.family == "CIRCUIT COURT" and weisman.counties == ("FREMONT", "SUBLETTE", "TETON")


def test_a_withdrawn_candidate_is_left_out():
    rows = LIST.splitlines()
    gone = next(i for i, row in enumerate(rows) if '"Ryan Shollenberger"' in row)
    rows[gone] = rows[gone].replace('"","Ryan Shollenberger"', '"10/01/2026","Ryan Shollenberger"')
    names = [f.name for f in wy.parse_text("\n".join(rows)) if f.reach == "hd" and f.district == "11"]
    assert names == ["Dan McIntosh", "Britney Tennant"]


def test_a_list_short_of_the_state_house_or_that_isnt_one_is_refused():
    rows = LIST.splitlines()
    cut = [row for row in rows if '"STATE REPRESENTATIVE 62"' not in row]
    with pytest.raises(ValueError, match="61 State House races, not 62"):
        wy.parse_text("\n".join(cut))
    with pytest.raises(ValueError, match="an office it doesn't know"):
        wy.parse_text("\n".join([rows[0], rows[1].replace("UNITED STATES SENATOR", "DOGCATCHER")]))
    with pytest.raises(ValueError, match="not the list"):
        WyList.parse(b"<html><body>Service Unavailable</body></html>")
    assert WyList.spec(None, dt.date(2028, 11, 7)).url == (
        "https://sos.wyo.gov/Elections/Docs/2028/2028_WY_General_Election_Candidates.csv")


def test_a_cheyenne_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "cheyenne")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (0, 8, 11)
    names = [race["name"] for race in ballot["races"]]
    assert names[:2] == ["U.S. Senator", "U.S. Representative At Large"]
    assert "State Representative District 11" in names and not any("State Senator" in n for n in names)
    assert "Retain District Court Judge Robin S. Cooley, 1st Judicial District" in names
    assert not any("2nd Judicial District" in n for n in names)
    senate, house = ballot["races"][:2]
    assert senate["source"] == house["source"] == "state_wy" and house["seat"] == "WY-00"
    assert candidate_names(house) == ["Chuck Gray", "Lisa Kinney", "Shawn Johnson", "Jeffrey Haggit"]
    assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
    assert any(card["source"] == "fec" and card["kind"] == "money"
               for race in (senate, house) for c in race["candidates"] for card in c["cards"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-19",
        "mail_apply_by": "2026-11-02", "early_voting_start": "2026-10-06", "early_voting_end": "2026-11-02",
        "source": "Wyoming Secretary of State", "source_url": "https://sos.wyo.gov/Elections/", "computed": True,
    }
    assert wy_calls(upstream) == 1
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [value for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_wy'")]
    assert len(kept) == 1 and list(json.loads(kept[0])) == ["filings"] and "EXAMPLE" not in kept[0]
    get_ballot(client, "cheyenne")
    assert logged_calls() == 0 and wy_calls(upstream) == 1


def test_a_wyoming_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "cheyenne")
    upstream.state_lists["sos.wyo.gov"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_wy")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "cheyenne")
    assert ballot["coverage"]["ballot"] == "list" and candidate_names(find_race(ballot, "U.S. Representative At Large"))


def test_with_wyomings_list_off_or_unreadable_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_wy", False)
    ballot = get_ballot(client, "cheyenne")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative At Large")
    assert wy_calls(upstream) == 0
    switch(client, "state_wy", True)
    upstream.state_lists["sos.wyo.gov"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "cheyenne")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Wyoming Secretary of State" in w
               for w in ballot["warnings"])


def test_wyomings_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_wy")
    assert outcome.status == "updated" and outcome.answers == 1
    assert outcome.counts == {"races": 107, "candidates": 151}
    bundled = (tmp_path / "bundles" / "state_wy.json").read_text(encoding="utf-8")
    assert "EXAMPLE" not in bundled and "555" not in bundled and wy_calls(upstream) == 1
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "cheyenne")
    assert ballot["coverage"]["ballot"] == "list" and wy_calls(upstream) == 1


@pytest.mark.parametrize("day, register, early", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 19), dt.date(2026, 10, 6)),
    (dt.date(2028, 11, 7), dt.date(2028, 10, 23), dt.date(2028, 10, 10)),
])
def test_wyomings_key_dates_are_worked_out_from_its_statutes(day, register, early):
    found = state_key_dates.computed("WY", day)
    end = day - dt.timedelta(days=1)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, end, early, end, "WY")
    assert state_key_dates.computed("WY", dt.date(2027, 11, 2)) is None


def test_wyomings_calendar_file_has_its_dates(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "WY"})
    assert response.status_code == 200 and "wyoming-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls are open 7 a.m. to 7 p.m." in text and "20261019" in text
