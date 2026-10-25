"""Colorado's ballot (states/co.py), from the Secretary of State's official candidate spreadsheet,
and its key dates worked out from the Colorado Revised Statutes. tests/fixtures/state_co.xlsx is
the spreadsheet as served: it has no contact details."""

from __future__ import annotations

import datetime as dt
import io
import json
import sqlite3
import zipfile
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import co, sheet_rows
from pallot.states import key_dates as state_key_dates
from pallot.states.co import CoList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch

LISTED = (FIXTURES / "state_co.xlsx").read_bytes()


def co_calls(upstream) -> int:
    return upstream.count("www.coloradosos.gov")


def rows() -> tuple[str, list[list[str]]]:
    return co._rows(LISTED)


def test_the_spreadsheet_reads_as_its_rows_with_the_year_in_its_sheets_name():
    sheet, read = sheet_rows(LISTED)
    assert sheet == "2026GeneralElectionCandidates" and len(read) == 406
    assert read[0] == list(co.COLUMNS) and read[1] == ["Mark Baisley", "US Senate", "State", "Republican Party", "N"]
    assert CoList.spec(None, dt.date(2028, 11, 7)).url == (
        "https://www.coloradosos.gov/pubs/elections/vote/files/2028/2028GeneralCandidateListOfficial.xlsx")
    with pytest.raises(ValueError, match="not a spreadsheet it can read"):
        sheet_rows(b"<html><body>Service Unavailable</body></html>")


def test_colorados_list_has_every_race_placed_and_the_governors_tickets():
    filings = CoList.parse(LISTED)
    assert len(filings) == 397 and {f.day for f in filings} == {"2026-11-03"}
    assert Counter((f.group, f.reach) for f in filings) == {
        ("federal", "state"): 9, ("federal", "cd"): 38, ("state", "state"): 18, ("state", "cd"): 17,
        ("legislature", "sd"): 46, ("legislature", "hd"): 135, ("local", "unplaced"): 10,
        ("judicial", "state"): 7, ("judicial", "counties"): 62, ("judicial", "county"): 55}
    assert {f.district for f in filings if f.family == "US HOUSE"} == {str(n) for n in range(1, 9)}
    governor = [f for f in filings if f.family == "GOVERNOR"]
    assert {f.office for f in governor} == {"Governor and Lieutenant Governor"} and len(governor) == 7
    assert [(f.name, f.party, f.party_name) for f in governor[:3]] == [
        ("Victor Marx and George Washington Markert", "R", None), ("Phil Weiser and Lesley Dahlkemper", "D", None),
        ("Stephen T. Hamilton and James K Treibert", None, "American Constitution Party")]
    assert not any("LT" in f.family for f in filings)
    assert sum(f.write_in for f in filings) == 10
    regents = {(f.office, f.reach, f.group) for f in filings if f.family == "UNIVERSITY OF COLORADO BOARD OF REGENTS"}
    assert ("University of Colorado Regent District 2", "cd", "state") in regents
    assert {f.district for f in filings if f.family == "RTD"} == set("BCJKLNO")


def test_colorados_judges_stand_for_retention_where_their_court_reaches():
    judges = {f.office: f for f in CoList.parse(LISTED) if f.group == "judicial"}
    assert len(judges) == 124 and all(f.incumbent for f in judges.values())
    hood = judges["Retain William W. Hood, III, Justice of the Colorado Supreme Court"]
    assert (hood.name, hood.reach, hood.counties) == ("William W. Hood, III", "state", ())
    baum = judges["Retain Andrew Baum, District Court Judge, 23rd Judicial District"]
    assert (baum.reach, baum.district, baum.counties) == ("counties", "23", ("DOUGLAS", "ELBERT", "LINCOLN"))
    probate = judges["Retain Elizabeth D. Leith, Judge of the Denver Probate Court"]  # "Distirct" in the file
    assert (probate.reach, probate.counties) == ("county", ("DENVER",))
    assert judges["Retain Jay A. Edwards, Rio Blanco Associate County Court Judge"].counties == ("RIO BLANCO",)
    assert judges["Retain Jay A. Edwards, Rio Blanco County Court Judge"].office_id != judges[
        "Retain Jay A. Edwards, Rio Blanco Associate County Court Judge"].office_id
    assert sum(len(counties) for counties in co._JUDICIAL.values()) == 64


def test_a_list_short_of_house_races_or_tickets_or_with_an_office_it_doesnt_know_is_refused():
    day, read = rows()
    with pytest.raises(ValueError, match="7 U.S. House races, not 8"):
        co.parse_rows(day, [r for r in read if not (r[1] == "US House of Representatives" and r[2] == "8")])
    with pytest.raises(ValueError, match="don't pair into tickets"):
        co.parse_rows(day, [r for r in read if r[0] != "Taralyn Romero"])
    with pytest.raises(ValueError, match="an office it doesn't know"):
        co.parse_rows(day, read + [["Pat Doe", "Water Court", "State", "", "N"]])
    with pytest.raises(ValueError, match="no county"):
        co.parse_rows(day, read + [["Pat Doe", "County Court", "Gotham", "", "N"]])
    with pytest.raises(ValueError, match="not the general election's list"):
        CoList.parse(renamed_sheet("Sheet1"))


def renamed_sheet(name: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(LISTED)) as book, zipfile.ZipFile(out, "w") as copy:
        for item in book.infolist():
            data = book.read(item)
            if item.filename == "xl/workbook.xml":
                data = data.replace(b'name="2026GeneralElectionCandidates"', f'name="{name}"'.encode())
            copy.writestr(item, data)
    return out.getvalue()


def test_a_denver_ballot_has_every_race_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "denver")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (1, 31, 5)
    names = [race["name"] for race in ballot["races"]]
    assert names[:10] == [
        "U.S. Senator", "U.S. Representative District 1", "Governor and Lieutenant Governor", "Secretary of State",
        "State Treasurer", "Attorney General", "State Board of Education District 1", "State Senator District 31",
        "State Representative District 5", "Retain William W. Hood, III, Justice of the Colorado Supreme Court"]
    assert len([n for n in names if n.startswith("Retain ")]) == 23
    assert "Retain Elizabeth D. Leith, Judge of the Denver Probate Court" in names
    assert not any("Regent" in n or "RTD" in n or "18th Judicial" in n for n in names)
    assert all(race["source"] == "state_co" for race in ballot["races"])
    assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
    senate, house = ballot["races"][:2]
    assert (senate["seat"], house["seat"]) == ("CO-SEN", "CO-01")
    assert find_race(ballot, "State Board of Education District 1")["seat"] is None
    assert candidate_names(house)[:2] == ["Melat Kiros", "Christy Peterson"]
    assert [c["name"] for c in house["candidates"] if c["write_in"]] == ["Kevin StClair", "John Wren", "Stephen Replin"]
    assert any(card["source"] == "fec" and card["kind"] == "money" for card in house["candidates"][0]["cards"])
    assert not any(card["source"] == "fec" for race in ballot["races"][2:] for c in race["candidates"] for card in c["cards"])
    assert any("7 RTD races" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-26",
        "mail_apply_by": None, "early_voting_start": "2026-10-19", "early_voting_end": "2026-11-02",
        "source": "Colorado Secretary of State", "source_url": "https://www.coloradosos.gov/pubs/elections/main.html",
        "computed": True,
    }
    assert co_calls(upstream) == 1
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_co'")]
    assert [sorted(value) for value in kept] == [["filings"]]
    get_ballot(client, "denver")
    assert logged_calls() == 0 and co_calls(upstream) == 1


def test_a_colorado_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "denver")
    upstream.state_lists["www.coloradosos.gov"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_co")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "denver")
    assert ballot["coverage"]["ballot"] == "list" and candidate_names(find_race(ballot, "State Representative District 5"))


def test_with_colorados_list_off_or_unreadable_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_co", False)
    ballot = get_ballot(client, "denver")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 1")
    assert co_calls(upstream) == 0
    switch(client, "state_co", True)
    upstream.state_lists["www.coloradosos.gov"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "denver")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Colorado Secretary of State" in w for w in ballot["warnings"])


def test_colorados_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_co")
    assert outcome.status == "updated" and outcome.answers == 1
    assert outcome.counts == {"races": 236, "candidates": 397}
    assert co_calls(upstream) == 1
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "denver")
    assert ballot["coverage"]["ballot"] == "list" and co_calls(upstream) == 1


@pytest.mark.parametrize("day, register, early, end", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 26), dt.date(2026, 10, 19), dt.date(2026, 11, 2)),
    (dt.date(2028, 11, 7), dt.date(2028, 10, 30), dt.date(2028, 10, 23), dt.date(2028, 11, 6)),
])
def test_colorados_key_dates_are_worked_out_from_its_statutes(day, register, early, end):
    found = state_key_dates.computed("CO", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, None, early, end, "CO")
    assert state_key_dates.computed("CO", dt.date(2026, 11, 10)) is None
    assert state_key_dates.computed("CO", dt.date(2027, 11, 2)) is None


def test_colorados_calendar_file_has_its_dates(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "CO"})
    assert response.status_code == 200 and "colorado-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "open 7 a.m. to 7 p.m." in text and "20261026" in text and "20261019" in text
