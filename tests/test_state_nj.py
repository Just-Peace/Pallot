"""New Jersey's ballot (states/nj.py), from the Division of Elections' official U.S. Senate and
House lists, two PDFs found by their links on its election information page, and its key dates
worked out from the New Jersey Statutes. tests/fixtures/state_nj_*.pdf are those lists rewritten
without the candidates' addresses (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import key_dates as state_key_dates
from pallot.states import nj, pdf_lines
from pallot.states.nj import NjList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch

PAGE = (FIXTURES / "state_nj.html").read_text(encoding="utf-8")
HOUSE = nj.links(PAGE)["links"]["house"]


def listed(kind: str) -> bytes:
    return (FIXTURES / f"state_nj_{kind}.pdf").read_bytes()


def nj_calls(upstream) -> int:
    return upstream.count("www.nj.gov")


def test_the_page_links_the_official_lists_however_the_house_ones_file_is_dated():
    assert nj.links(PAGE) == {"year": 2026, "links": {
        "senate": "https://www.nj.gov/state/elections/assets/pdf/election-results/2026/2026-official-general-candidates-us-senate.pdf",
        "house": "https://www.nj.gov/state/elections/assets/pdf/election-results/2026/2026-official-general-candidates-us-house-0904.pdf",
    }}
    assert nj.links(PAGE.replace("2026-official-general-candidates", "2026-unofficial-general-candidates"))["links"] == {}
    assert NjList.spec(None, dt.date(2028, 11, 7)).url == "https://www.nj.gov/state/elections/election-information-2028.shtml"
    with pytest.raises(ValueError, match="election information page"):
        nj.links("<html><head><title>Page Not Found</title></head></html>")


def test_new_jerseys_lists_have_the_senate_and_every_house_district_with_parties_and_incumbents():
    senate = NjList.parse(listed("senate"))
    assert [(f.name, f.party, f.party_name, f.incumbent) for f in senate] == [
        ("Cory Booker", "D", None, True), ("Justin Murphy", "R", None, False),
        ("Veronica Fernandez", None, "END THE CORRUPTION!", False), ("Joanne Kuniansky", None, "SOCIALIST WORKERS PARTY", False)]
    assert {(f.day, f.office, f.reach, f.group) for f in senate} == {("2026-11-03", "U.S. Senator", "state", "federal")}
    house = NjList.parse(listed("house"))
    assert len(house) == 35 and {f.district for f in house} == {str(n) for n in range(1, 13)}
    assert {f.reach for f in house} == {"cd"} and sum(f.incumbent for f in house) == 11
    assert not any(f.incumbent for f in house if f.district == "12")
    parties = Counter(f.party or f.party_name for f in house)
    assert (parties["D"], parties["R"], parties["G"], parties["Independent"]) == (12, 11, 2, 2)
    seventh = sorted((f for f in house if f.district == "7"), key=lambda f: f.order)
    assert [(f.name, f.party, f.party_name, f.office) for f in seventh] == [
        ("Thomas H. Kean Jr.", "R", None, "U.S. Representative District 7"),
        ("Rebecca Bennett", "D", None, "U.S. Representative District 7"),
        ("Seamus Patrick O'Toole", None, "STOP ISRAEL'S GENOCIDE", "U.S. Representative District 7")]
    second = [f.name for f in house if f.district == "2"]
    assert second == ["Jeff Van Drew", "Zack Mullock", "Ramon Mora Jr."]  # under a heading wrapped onto two lines


def test_a_list_short_of_its_total_or_of_a_house_district_or_that_isnt_one_is_refused():
    lines = pdf_lines(listed("house"))
    start = next(i for i, line in enumerate(lines) if line.startswith("Twelfth Congressional District"))
    end = next(i for i, line in enumerate(lines) if "Page 13 of 13" in line)
    cut = lines[:start] + lines[end:]
    with pytest.raises(ValueError, match="31 candidates, not the 35"):
        nj.parse_lines(cut)
    with pytest.raises(ValueError, match="11 U.S. House races, not 12"):
        nj.parse_lines(["Total Candidates 31" if "Total Candidates" in line else line for line in cut])
    with pytest.raises(ValueError, match="no general election date"):
        nj.parse_lines(["Official List", "Total Candidates 0"])
    with pytest.raises(ValueError, match="not a PDF"):
        NjList.parse(b"<html><body>Service Unavailable</body></html>")


def test_a_trenton_ballot_has_the_senate_and_its_house_race_from_the_lists(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "trenton")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"],
                                  "labels": {"hd": "General Assembly"}}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (12, 15, 15)
    assert [race["name"] for race in ballot["races"]] == ["U.S. Senator", "U.S. Representative District 12"]
    senate, house = ballot["races"]
    assert senate["source"] == house["source"] == "state_nj" and house["seat"] == "NJ-12"
    assert candidate_names(senate)[:2] == ["Cory Booker", "Justin Murphy"] and senate["candidates"][0]["incumbent"]
    assert candidate_names(house) == ["Adam Hamawy", "Gregg Mele", "Andres Jinete", "Winston Jordan"]
    assert not any(c["incumbent"] for c in house["candidates"])
    assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
    hamawy = house["candidates"][0]
    assert any(card["source"] == "fec" and card["kind"] == "money" for card in hamawy["cards"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-13",
        "mail_apply_by": "2026-10-27", "early_voting_start": "2026-10-24", "early_voting_end": "2026-11-01",
        "source": "New Jersey Division of Elections", "source_url": "https://www.nj.gov/state/elections/", "computed": True,
    }
    assert nj_calls(upstream) == 3
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_nj'")]
    assert sorted(sorted(value) for value in kept) == [["filings"], ["filings"], ["links", "year"]]
    get_ballot(client, "trenton")
    assert logged_calls() == 0 and nj_calls(upstream) == 3


def test_a_new_jersey_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "trenton")
    upstream.state_lists[HOUSE.removeprefix("https://")] = "%PDF-1.7 cut short"
    status, said = make_app.cache_command("hard-refresh", "state_nj")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "trenton")
    assert ballot["coverage"]["ballot"] == "list" and candidate_names(find_race(ballot, "U.S. Representative District 12"))


def test_with_new_jerseys_list_off_or_unreadable_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_nj", False)
    ballot = get_ballot(client, "trenton")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 12")
    assert nj_calls(upstream) == 0
    switch(client, "state_nj", True)
    upstream.state_lists[HOUSE.removeprefix("https://")] = "%PDF-1.7 cut short"
    ballot = get_ballot(client, "trenton")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the New Jersey Division of Elections" in w
               for w in ballot["warnings"])


def test_a_page_without_this_years_house_list_yet_leaves_the_fecs_races(client, upstream):
    upstream.state_lists["www.nj.gov/state/elections/election-information-2026.shtml"] = PAGE.replace(
        "2026-official-general-candidates-us-house", "2026-unofficial-general-candidates-us-house")
    ballot = get_ballot(client, "trenton")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 12")
    assert any("hasn't published its list of candidates" in n for n in ballot["notes"])
    assert not any("us-senate" in call for call in upstream.calls)


def test_new_jerseys_bundled_lists_serve_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_nj")
    assert outcome.status == "updated" and outcome.answers == 3
    assert outcome.counts == {"races": 13, "candidates": 39}
    bundled = json.loads((tmp_path / "bundles" / "state_nj.json").read_text(encoding="utf-8"))
    assert "BOX" not in json.dumps(bundled) and nj_calls(upstream) == 3
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "trenton")
    assert ballot["coverage"]["ballot"] == "list" and nj_calls(upstream) == 3


@pytest.mark.parametrize("day, register, apply, early, end", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 13), dt.date(2026, 10, 27), dt.date(2026, 10, 24), dt.date(2026, 11, 1)),
    (dt.date(2028, 11, 7), dt.date(2028, 10, 17), dt.date(2028, 10, 31), dt.date(2028, 10, 28), dt.date(2028, 11, 5)),
])
def test_new_jerseys_key_dates_are_worked_out_from_its_statutes(day, register, apply, early, end):
    found = state_key_dates.computed("NJ", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, apply, early, end, "NJ")
    assert state_key_dates.computed("NJ", dt.date(2026, 11, 10)) is None


def test_new_jerseys_calendar_file_has_its_dates(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "NJ"})
    assert response.status_code == 200 and "new-jersey-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls are open 6 a.m. to 8 p.m." in text and "20261013" in text
