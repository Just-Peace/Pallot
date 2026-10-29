"""Washington's ballot (states/wa.py), from the Secretary of State's CandidateList.aspx grid on
VoteWA, the CSV it exports for the election its dropdown names, and its key dates worked out from
RCW 29A. The list is the grid's fixtures (tests/fixtures/grid_wa.html, the page cut down to its
dropdown, and grid_wa.csv, the 2026 general election's export without contact details)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from pallot.config import Ttls
from pallot.http_cache import HttpCache
from pallot.states import grid
from pallot.states import key_dates as state_key_dates
from pallot.states import wa
from pallot.states.grid import GridRow
from pallot.states.wa import WaList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch

HOST = "voter.votewa.gov"
PAGE = (FIXTURES / "grid_wa.html").read_text(encoding="utf-8")
CSV = (FIXTURES / "grid_wa.csv").read_bytes()
HEADING = ('"District Type","District","Race","Term Type","Term Length","Name","Mailing Address","Email","Phone",'
           '"Filing Date","Party Preference","Status","Election Status","Ballot Order"\r\n')
# 2027's list as an odd year's would be: a legislative vacancy, a judge's unexpired term, local offices.
ODD_YEAR = HEADING + (
    '"Legislative","Legislative District 33","State Senator","Unexpired","1","Ann Able","","","","5/4/2027",'
    '"DEMOCRATIC","Active","","1"\r\n'
    '"Legislative","Legislative District 33","State Senator","Unexpired","1","Bo Baker","","","","5/5/2027",'
    '"GOP","Active","","2"\r\n'
    '"Judicial","King County Superior Court","Judge Position 12","Unexpired","1","Cy Cole","","","","5/6/2027",'
    '"","Active","","1"\r\n'
    '"Countywide","County","Assessor","Regular","4","Di Dunn","","","","5/6/2027","","Active","","1"\r\n')


def row(race: str, district_type: str, district: str, party: str = "", term: str = "Regular") -> GridRow:
    return GridRow(race, district_type, district, "Pat Doe", party, 1, {"TERM TYPE": term})


def test_the_dropdown_names_each_years_general_election_and_the_list_is_its_export():
    assert WaList.read_index(PAGE.encode()) == {
        "elections": {"2027-11-02": "906", "2026-11-03": "899", "2025-11-04": "894", "2024-11-05": "889"}}
    assert WaList.read_index(CSV) is None
    lists = WaList.__new__(WaList)
    assert lists.spec(dt.date(2026, 11, 3)).url == wa.PAGE
    index = WaList.read_index(PAGE.encode())
    [spec] = lists.follow(index, dt.date(2026, 11, 3))
    assert (spec.method, spec.url, spec.params, spec.form) == ("POST", wa.PAGE, {"e": "899"}, grid.EXPORT)
    [odd] = lists.follow(index, dt.date(2027, 11, 2))
    assert odd.params == {"e": "906"}
    assert lists.follow(index, dt.date(2028, 11, 7)) is None


def test_washingtons_list_has_congress_the_legislatures_three_seats_and_the_state_courts():
    filings = WaList.parse(CSV)
    assert {f.day for f in filings} == {""}
    races = {f.office_id: f for f in filings}
    assert Counter(f.reach for f in races.values()) == {"cd": 10, "sd": 24, "hd": 98, "state": 5, "counties": 12}
    assert [(f.office, f.name, f.party, f.party_name) for f in filings if f.office_id == "US HOUSE 7"] == [
        ("U.S. Representative District 7", "Pramila Jayapal", "D", "Prefers Democratic Party"),
        ("U.S. Representative District 7", "Nirav Sheth", "R", "Prefers Republican Party")]
    district = [(f.office_id, f.office, f.name) for f in filings if f.district == "21" and f.group == "legislature"]
    assert district == [
        ("STATE SENATE 21", "State Senator District 21", "Marko Liias"),
        ("STATE SENATE 21", "State Senator District 21", "Riaz Khan"),
        ("STATE HOUSE 21 POSITION 1", "State Representative District 21 Position 1", "Strom Peterson"),
        ("STATE HOUSE 21 POSITION 1", "State Representative District 21 Position 1", "Jason Moon"),
        ("STATE HOUSE 21 POSITION 2", "State Representative District 21 Position 2", "Lillian Ortiz-Self"),
        ("STATE HOUSE 21 POSITION 2", "State Representative District 21 Position 2", "Bruce Guthrie")]
    assert {f.district for f in filings if f.reach == "hd"} == {str(n) for n in range(1, 50)}
    supreme = races["SUPREME COURT 1"]
    assert (supreme.office, supreme.reach, supreme.unexpired, supreme.party) == (
        "Justice of the Supreme Court Position 1", "state", True, None)
    assert not races["SUPREME COURT 3"].unexpired
    appeals = races["COURT OF APPEALS 1 1 5"]
    assert (appeals.office, appeals.counties, appeals.district) == (
        "Court of Appeals, Division 1, District 1, Judge Position 5", ("KING",), "1-1")
    assert races["COURT OF APPEALS 3 3 1"].counties == ("CHELAN", "DOUGLAS", "KITTITAS", "KLICKITAT", "YAKIMA")
    superior = races["SUPERIOR COURT FERRY PEND OREILLE STEVENS 2"]
    assert (superior.office, superior.counties) == (
        "Ferry, Pend Oreille, Stevens Counties Superior Court Judge Position 2", ("FERRY", "PEND OREILLE", "STEVENS"))
    assert races["SUPERIOR COURT COWLITZ 4"].office == "Cowlitz County Superior Court Judge Position 4"
    assert not any(word in f.office for f in filings for word in ("Sheriff", "Assessor", "District Court", "Municipal",
                                                                    "Commissioner", "Council"))


def test_a_party_preference_reads_as_the_ballot_prints_it():
    def said(words: str) -> tuple[str | None, str | None]:
        return WaList.affiliation(row("State Senator", "Legislative", "Legislative District 1", words))

    assert said("DEMOCRATIC") == ("D", "Prefers Democratic Party")
    assert said("DEMOCRAT") == ("D", "Prefers Democrat Party")
    assert said("GOP") == ("R", "Prefers GOP Party")
    assert said("G.O.P.") == ("R", "Prefers G.O.P. Party")
    assert said("REPUBLICAN") == ("R", "Prefers Republican Party")
    assert said("INDEPENDENT") == ("I", "Prefers Independent Party")
    assert said("LABOR DEMOCRAT") == (None, "Prefers Labor Democrat Party")
    assert said("Socialist Workers Party") == (None, "Prefers Socialist Workers Party")
    assert said("STATES NO PARTY PREFERENCE") == (None, None)
    assert said("") == (None, None)


def test_the_statewide_offices_and_the_us_senate_are_read_and_the_president_left_out():
    assert WaList.office(row("Lt. Governor", "Statewide", "Statewide")).office == "Lieutenant Governor"
    assert WaList.office(row("Superintendent of Public Instruction", "Statewide", "Statewide")).reach == "state"
    assert WaList.office(row("U.S. Senator", "Federal", "Federal")).office_id == "US SENATE"
    assert WaList.office(row("President/Vice President", "Federal", "Federal")) is None
    assert WaList.office(row("Sheriff", "Countywide", "County")) is None
    assert WaList.office(row("Judge Position 2", "Judicial", "Everett District Court")) is None
    lincoln = WaList.office(row("SUPERIOR COURT JUDGE", "Judicial", "Lincoln Superior Court", term="Unexpired"))
    assert (lincoln.office_id, lincoln.office, lincoln.unexpired) == (
        "SUPERIOR COURT LINCOLN", "Lincoln County Superior Court Judge", True)


def test_a_list_short_of_districts_or_with_an_office_it_doesnt_know_is_refused():
    text = CSV.decode("utf-8-sig")
    with pytest.raises(ValueError, match="9 U.S. House races, not 10"):
        WaList.parse("\r\n".join(line for line in text.split("\r\n") if '"Congressional District 10"' not in line))
    with pytest.raises(ValueError, match="an office it doesn't know: State Mine Inspector"):
        WaList.office(row("State Mine Inspector", "Statewide", "Statewide"))
    with pytest.raises(ValueError, match="an office it doesn't know: State Representative Pos. 3"):
        WaList.office(row("State Representative Pos. 3", "Legislative", "Legislative District 1"))
    with pytest.raises(ValueError, match="no county 'Narnia'"):
        WaList.office(row("Judge Position 1", "Judicial", "Narnia Superior Court"))
    with pytest.raises(ValueError, match="no heading row"):
        WaList.parse(b"<html><body>Service Unavailable</body></html>")


def test_an_odd_years_list_has_its_vacancies_without_congress():
    filings = WaList.parse(ODD_YEAR)
    assert [(f.office, f.name, f.party, f.unexpired) for f in filings] == [
        ("State Senator District 33", "Ann Able", "D", True), ("State Senator District 33", "Bo Baker", "R", True),
        ("King County Superior Court Judge Position 12", "Cy Cole", None, True)]


@pytest.mark.anyio
async def test_an_odd_years_list_is_its_elections_export_dated_that_november(tmp_path):
    posted = []

    def answer(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=PAGE, headers={"content-type": "text/html; charset=utf-8"})
        posted.append((request.url.params.get("e"), parse_qs(request.content.decode(), keep_blank_values=True)))
        return httpx.Response(200, text=ODD_YEAR, headers={"content-type": "text/csv; charset=utf-8"})

    with respx.mock() as router:
        router.route(host=HOST).mock(side_effect=answer)
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "cache.sqlite3", client)
            filings = await WaList(cache, Ttls()).filings(dt.date(2027, 11, 2))
            cache.close()
    assert [(f.name, f.day) for f in filings] == [
        ("Ann Able", "2027-11-02"), ("Bo Baker", "2027-11-02"), ("Cy Cole", "2027-11-02")]
    [(election, form)] = posted
    assert election == "906" and form["__VIEWSTATE"] == ["VIEWSTATE-recorded"]


def test_a_seattle_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "seattle")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (7, 34, 34)
    names = [race["name"] for race in ballot["races"]]
    assert names == [
        "U.S. Representative District 7", "State Senator District 34", "State Representative District 34 Position 1",
        "State Representative District 34 Position 2", "Justice of the Supreme Court Position 1",
        "Justice of the Supreme Court Position 3", "Justice of the Supreme Court Position 4",
        "Justice of the Supreme Court Position 5", "Justice of the Supreme Court Position 7",
        "Court of Appeals, Division 1, District 1, Judge Position 5",
        "Court of Appeals, Division 1, District 1, Judge Position 6",
    ]
    assert all(race["source"] == "state_wa" for race in ballot["races"])
    house = find_race(ballot, "U.S. Representative District 7")
    assert house["seat"] == "WA-07" and candidate_names(house) == ["Pramila Jayapal", "Nirav Sheth"]
    assert [c["party_name"] for c in house["candidates"]] == ["Prefers Democratic Party", "Prefers Republican Party"]
    assert any(card["source"] == "fec" and card["kind"] == "money" for c in house["candidates"] for card in c["cards"])
    assert find_race(ballot, "Justice of the Supreme Court Position 1")["unexpired"]
    assert any("voters' pamphlet" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-26",
        "mail_apply_by": None, "early_voting_start": "2026-10-16", "early_voting_end": None,
        "source": "Washington Secretary of State", "source_url": "https://www.sos.wa.gov/elections",
        "computed": True,
    }
    assert upstream.count(HOST) == 3  # the page, the election's page for its hidden fields, the export
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_wa'")]
    assert sorted(sorted(value) for value in kept) == [["elections"], ["filings"]]
    assert not any("@" in json.dumps(value) or "Seattle" in json.dumps(value) for value in kept)
    get_ballot(client, "seattle")
    assert logged_calls() == 0 and upstream.count(HOST) == 3


def test_a_washington_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "seattle")
    upstream.state_lists[f"{HOST}#csv"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_wa")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "seattle")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "State Senator District 34")


def test_with_washingtons_list_off_or_unreadable_its_ballot_has_the_race_for_congress_from_the_fec(client, upstream):
    switch(client, "state_wa", False)
    ballot = get_ballot(client, "seattle")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 7")
    assert upstream.count(HOST) == 0
    switch(client, "state_wa", True)
    upstream.state_lists[f"{HOST}#csv"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "seattle")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Washington Secretary of State" in w
               for w in ballot["warnings"])


def test_an_election_the_dropdown_doesnt_list_yet_leaves_the_fecs_races(client, upstream):
    upstream.state_lists[f"{HOST}#page"] = PAGE.replace("11/03/2026", "11/03/2099")
    ballot = get_ballot(client, "seattle")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("The Washington Secretary of State hasn't published its list of candidates" in n for n in ballot["notes"])
    assert upstream.count(HOST) == 1


def test_washingtons_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_wa")
    assert outcome.status == "updated" and outcome.answers == 2
    assert outcome.counts == {"races": 149, "candidates": 269}
    assert upstream.count(HOST) == 3
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "seattle")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == 3


@pytest.mark.parametrize("day, register, start", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 26), dt.date(2026, 10, 16)),
    (dt.date(2027, 11, 2), dt.date(2027, 10, 25), dt.date(2027, 10, 15)),
    (dt.date(2028, 11, 7), dt.date(2028, 10, 30), dt.date(2028, 10, 20)),
])
def test_washingtons_key_dates_are_worked_out_from_rcw_29a_every_november(day, register, start):
    found = state_key_dates.computed("WA", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, None, start, None, "WA")
    assert register.weekday() == 0 and start.weekday() == 4
    assert state_key_dates.computed("WA", dt.date(2026, 11, 4)) is None


def test_washingtons_calendar_file_and_when_to_vote_say_every_voter_is_mailed_a_ballot(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "WA"})
    assert response.status_code == 200 and "washington-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Drop boxes and voting centers close at 8 p.m. on Election Day" in text
    assert all(day in text for day in ("20261016", "20261026", "20261103"))
    info = state_key_dates.GUIDES["WA"].voter_info()
    assert info.poll_hours == "until 8 p.m." and "8 p.m. on Election Day" in info.late_registration.label
    assert info.mail_eligibility.startswith("Every active voter is mailed a ballot. It goes out 18 days before")
