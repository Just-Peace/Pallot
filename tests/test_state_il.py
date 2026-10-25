"""Illinois's ballot (states/il.py), from the State Board of Elections' candidate data file, posted
back for on the election's download page found on its list of elections, and its key dates worked
out from the Election Code. tests/fixtures/state_il.tsv is that file with its contact columns
emptied (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import il
from pallot.states import key_dates as state_key_dates
from pallot.states.il import IlList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch

FILE = (FIXTURES / "state_il.tsv").read_text(encoding="utf-8")
INDEX = (FIXTURES / "state_il.html").read_text(encoding="utf-8")
DOWNLOAD = "www.elections.il.gov/ElectionOperations/DownloadCandidates.aspx"


def il_calls(upstream) -> int:
    return upstream.count("www.elections.il.gov")


def test_the_list_of_elections_gives_each_general_elections_page():
    found = il.elections(INDEX)["elections"]
    assert found["2026-11-03"] == "sejIrI%2bQmww%3d" and "2026-03-17" not in found
    assert IlList.download(found["2026-11-03"]).url == (
        "https://www.elections.il.gov/ElectionOperations/DownloadCandidates.aspx?ID=sejIrI%2bQmww%3d")
    with pytest.raises(ValueError, match="list of elections"):
        il.elections("<html><body>Service Unavailable</body></html>")


def test_illinoiss_file_has_its_active_candidates_and_the_parties_nominees():
    filings = il.parse(FILE)
    assert len(filings) == 370 and {f.day for f in filings} == {"2026-11-03"}
    reach = Counter(f.reach for f in filings)
    assert (reach["state"], reach["cd"], reach["county"]) == (14, 36, 6)
    assert {f.district for f in filings if f.reach == "cd"} == {str(n) for n in range(1, 18)}
    assert all({"D", "R"} <= {f.party for f in filings if f.district == str(n) and f.reach == "cd"} for n in range(1, 18))
    assert not any("Macias" in f.name or "Sigcho" in f.name for f in filings)  # removed from the ballot
    assert not any("RETAIN" in f.office_id for f in filings)
    governor = sorted((f for f in filings if f.office == "Governor and Lieutenant Governor"), key=lambda f: f.order)
    assert [(f.name, f.party, f.party_name) for f in governor] == [
        ("JB Pritzker and Christian Mitchell", "D", None), ("Darren Bailey and Aaron B. Del Mar", "R", None),
        ("Collin Corbett and Carolyn Schofield", None, "Independent")]
    fourth = sorted((f for f in filings if f.office == "U.S. Representative District 4"), key=lambda f: f.order)
    assert [(f.name, f.party, f.party_name) for f in fourth] == [
        ("Patty Garcia", "D", None), ("Lupe Castillo", "R", None), ("Ed Hershey", None, "Working Class Party"),
        ("Chris Getty", None, "Independent")]
    names = {f.name for f in filings}
    assert {"Erin O'Brien", "D'Anthony \"Tony\" Thedford"} <= names and not any("Char(39)" in n for n in names)
    house = next(f for f in filings if f.office_id == "56TH REPRESENTATIVE")
    assert (house.office, house.reach, house.district, house.group) == ("State Representative District 56", "hd", "56",
                                                                        "legislature")
    cook = {f.office: f for f in filings if f.reach == "county"}
    assert cook["Judge of the Appellate Court, 1st District (Hoffman vacancy)"].counties == ("COOK",)
    assert "Judge of the Circuit Court of Cook County (Burke vacancy)" in cook
    unplaced = {f.office_id for f in filings if f.reach == "unplaced"}
    assert "COOK CIRCUIT - 1ST SUBCIRCUIT - BALANOFF VACANCY" in unplaced and "3RD APPELLATE - MCDADE VACANCY" in unplaced
    assert "Judge of the Appellate Court, 3rd District (McDade vacancy)" in {f.office for f in filings}
    assert any("SUPERINTENDENT" in office for office in unplaced)


def test_a_file_short_of_congress_or_that_isnt_one_is_refused():
    lines = FILE.splitlines()
    cut = "\n".join(line for line in lines if "\t17TH CONGRESS\t" not in line)
    with pytest.raises(ValueError, match="16 U.S. House races, not 17"):
        il.parse(cut)
    with pytest.raises(ValueError, match="no CandidateStatus column"):
        il.parse(FILE.replace("CandidateStatus", "Status", 1))
    with pytest.raises(ValueError, match="not a candidate data file"):
        IlList.parse(b"CandidateID")
    with pytest.raises(ValueError, match="no form to post"):
        il.hidden_fields("<html><body>Just a moment...</body></html>")


def test_a_chicago_ballot_has_the_statewide_races_its_districts_and_cook_countys_judges(client, upstream, logged_calls,
                                                                                        tmp_path):
    ballot = get_ballot(client, "chicago")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert ballot["districts"]["cd"] == 7
    names = [race["name"] for race in ballot["races"]]
    assert names[:7] == ["U.S. Senator", "U.S. Representative District 7", "Governor and Lieutenant Governor",
                         "Attorney General", "Secretary of State", "Comptroller", "Treasurer"]
    assert "Judge of the Circuit Court of Cook County (Burke vacancy)" in names
    assert "Judge of the Appellate Court, 1st District (Hoffman vacancy)" in names
    assert not any("Subcircuit" in name or "Superintendent" in name.title() for name in names)
    assert {race["source"] for race in ballot["races"]} == {"state_il"}
    house = find_race(ballot, "U.S. Representative District 7")
    assert house["seat"] == "IL-07" and candidate_names(house) == ["La Shawn K. Ford", "Chad Koppie"]
    assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
    ford = house["candidates"][0]
    assert any(card["source"] == "fec" and card["kind"] == "money" for card in ford["cards"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-18",
        "mail_apply_by": "2026-10-29", "early_voting_start": "2026-09-24", "early_voting_end": "2026-11-02",
        "source": "Illinois State Board of Elections", "source_url": "https://www.elections.il.gov/", "computed": True,
    }
    assert il_calls(upstream) == 3
    page, posted = upstream.il_forms
    assert page == {} and posted["__VIEWSTATE"] == "VIEWSTATE-recorded"
    assert posted["__EVENTTARGET"] == "ctl00$ContentPlaceHolder1$btnText"
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [(json.loads(request), json.loads(value))
                for request, value in db.execute("SELECT request, value FROM responses WHERE source = 'state_il'")]
    assert sorted(sorted(value) for _, value in kept) == [["elections"], ["filings"]]
    assert not any("VIEWSTATE" in json.dumps(request) for request, _ in kept)
    get_ballot(client, "chicago")
    assert logged_calls() == 0 and il_calls(upstream) == 3


def test_an_illinois_file_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "chicago")
    upstream.state_lists[DOWNLOAD] = "<html>Error</html>"
    status, said = make_app.cache_command("hard-refresh", "state_il")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "chicago")
    assert ballot["coverage"]["ballot"] == "list" and candidate_names(find_race(ballot, "U.S. Representative District 7"))


def test_with_illinoiss_list_off_or_unreadable_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_il", False)
    ballot = get_ballot(client, "chicago")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 7")
    assert il_calls(upstream) == 0
    switch(client, "state_il", True)
    upstream.state_lists[DOWNLOAD] = "CandidateID\tLastName\n1\tSmith\n"
    ballot = get_ballot(client, "chicago")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Illinois State Board of Elections" in w
               for w in ballot["warnings"])


def test_a_list_of_elections_without_this_ones_yet_leaves_the_fecs_races(client, upstream):
    upstream.state_lists["www.elections.il.gov/ElectionOperations/CandidateOfficeFilingSearch.aspx"] = INDEX.replace(
        "11/3/2026", "11/3/2030")
    ballot = get_ballot(client, "chicago")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 7")
    assert any("hasn't published its list of candidates" in n for n in ballot["notes"])
    assert il_calls(upstream) == 1


def test_illinoiss_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_il")
    assert outcome.status == "updated" and outcome.answers == 2
    assert outcome.counts == {"races": 260, "candidates": 370}
    bundled = (tmp_path / "bundles" / "state_il.json").read_text(encoding="utf-8")
    assert "VIEWSTATE" not in bundled and "Address1" not in bundled and il_calls(upstream) == 3
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "chicago")
    assert ballot["coverage"]["ballot"] == "list" and il_calls(upstream) == 3


@pytest.mark.parametrize("day, register, apply, early, end", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 18), dt.date(2026, 10, 29), dt.date(2026, 9, 24), dt.date(2026, 11, 2)),
    (dt.date(2028, 11, 7), dt.date(2028, 10, 22), dt.date(2028, 11, 2), dt.date(2028, 9, 28), dt.date(2028, 11, 6)),
])
def test_illinoiss_key_dates_are_worked_out_from_its_election_code(day, register, apply, early, end):
    found = state_key_dates.computed("IL", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, apply, early, end, "IL")
    assert state_key_dates.computed("IL", dt.date(2026, 11, 10)) is None
    assert state_key_dates.computed("IL", dt.date(2027, 11, 2)) is None


def test_illinoiss_calendar_file_has_its_dates(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "IL"})
    assert response.status_code == 200 and "illinois-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls are open 6 a.m. to 7 p.m." in text and "20261018" in text
