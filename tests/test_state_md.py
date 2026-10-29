"""Maryland's ballot (states/md.py), from the State Board of Elections' statewide candidate list, a
CSV found by its link on the year's general candidate listings page, and its key dates worked out
from Maryland's election law. tests/fixtures/state_md.html is that page cut down to its link;
state_md.csv is the list with its contact columns emptied (scripts/record_fixtures.py)."""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.states import md
from pallot.states import key_dates as state_key_dates
from pallot.states.md import MdList

from .bundling import build
from .conftest import FIXTURES, MD_NOT_FOUND, candidate_names, find_race, get_ballot, switch

HOST = "elections.maryland.gov"
PAGE = (FIXTURES / "state_md.html").read_text(encoding="utf-8")
LISTED = (FIXTURES / "state_md.csv").read_text(encoding="utf-8")
LIST_PATH = "/elections/2026/general_candidates/2026_GG_statewide_candidatelist.csv"
INDEX_PATH = "/elections/2026/general_candidates/index.html"


def rows() -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(LISTED)))


def written(listed: list[dict[str, str]]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, list(listed[0]), lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(listed)
    return out.getvalue()


def row(**cells: str) -> dict[str, str]:
    return {**dict.fromkeys(rows()[0], ""), "Candidate Status": "Active", **cells}


def test_the_page_links_the_years_statewide_list():
    found = md.links(PAGE)
    assert found == {"links": {"2026": f"https://{HOST}{LIST_PATH}"}}
    lists = MdList.__new__(MdList)
    assert lists.spec(dt.date(2026, 11, 3)).url == f"https://{HOST}{INDEX_PATH}"
    assert [spec.url for spec in lists.follow(found, dt.date(2026, 11, 3))] == [found["links"]["2026"]]
    assert lists.follow(found, dt.date(2028, 11, 7)) is None
    assert md.links(MD_NOT_FOUND) == {"links": {}}
    assert MdList.read_index(PAGE.encode()) == found and MdList.read_index(LISTED.encode("utf-8-sig")) is None
    with pytest.raises(ValueError, match="not the State Board of Elections' general candidate listings"):
        md.links("<html><head><title>Elections</title></head><body>Maintenance</body></html>")


def test_marylands_list_has_congress_the_state_the_legislature_and_the_appellate_judges():
    filings = MdList.parse(LISTED.encode("utf-8-sig"))
    assert len(filings) == 323 and {f.day for f in filings} == {"2026-11-03"}
    races = {f.office_id: f for f in filings}
    assert Counter(f.reach for f in races.values()) == {"state": 4, "cd": 8, "sd": 47, "hd": 71, "counties": 1}
    governor = [(f.name, f.party, f.party_name) for f in filings if f.office_id == "GOVERNOR"]
    assert governor == [("Wes Moore and Aruna Miller", "D", None), ("Dan Cox and Rob Krop", "R", None),
                        ("Andy Ellis and Owen Silverman Andrews", "G", None),
                        ("Cathy White and Cathy Permut", None, "Working Class Party")]
    assert next(f for f in filings if f.office == "Attorney General" and f.party == "R").name == "James B. Rutledge III"
    coffman = next(f for f in filings if f.name == "Robert L. Coffman")
    assert (coffman.office, coffman.party, coffman.write_in) == ("U.S. Representative District 3", "R", True)
    assert next(f for f in filings if f.name == "Edward Shlikas").party is None  # Unaffiliated
    seats = {f.district: f.seats for f in filings if f.reach == "hd"}
    assert (seats["1A"], seats["2A"], seats["2B"], seats["30A"], seats["3"], seats["44B"]) == (1, 2, 1, 2, 3, 2)
    delegate = next(f for f in filings if f.district == "30A")
    assert (delegate.office, delegate.office_id, delegate.family) == (
        "House of Delegates District 30A", "STATE HOUSE 30A", "STATE HOUSE")
    justice = next(f for f in filings if f.retention and f.reach == "counties")
    assert (justice.office, justice.name, justice.counties, justice.district, justice.incumbent) == (
        "Retain Supreme Court of Maryland Justice Peter Killough", "Peter Killough", ("PRINCE GEORGE'S",), "4", True)
    judge = next(f for f in filings if f.retention and f.reach == "state")
    assert judge.office == "Retain Appellate Court of Maryland Judge Dan Friedman" and judge.party is None
    assert not any("Circuit Court" in f.office or f.name == "Timothy McGarrahan" and f.party == "D" for f in filings)
    assert not any(f.incumbent for f in filings if not f.retention)


def test_a_withdrawn_running_mate_leaves_the_governor_alone_and_a_withdrawn_candidate_is_left_out():
    listed = rows()
    listed[0] = {**listed[0], "Related Candidate Status": "Withdrawn - 08/01/2026"}
    listed[1] = {**listed[1], "Candidate Status": "Withdrawn - 08/01/2026"}
    governor = [f.name for f in md.parse_text(written(listed)) if f.office_id == "GOVERNOR"]
    assert governor[:2] == ["Wes Moore", "Andy Ellis and Owen Silverman Andrews"]


def test_a_list_short_of_districts_or_with_an_office_it_doesnt_know_is_refused():
    listed = rows()
    with pytest.raises(ValueError, match="44 State Senate races, not 45"):
        md.parse_text(written([r for r in listed if not (r["Office Name"] == "State Senator" and int(
            r["Contest Run By District Name and Number"].rsplit(" ", 1)[1]) > 44)]))
    with pytest.raises(ValueError, match="an office it doesn't know: Lieutenant Governor of the Moon"):
        md.parse_text(written(listed + [row(**{"Office Name": "Lieutenant Governor of the Moon",
                                               "Filing Type and Date": "Regular - 01/02/2026"})]))
    with pytest.raises(ValueError, match="a district it can't read"):
        md.parse_text(written(listed + [row(**{"Office Name": "House of Delegates",
                                               "Contest Run By District Name and Number": "Congressional District 3"})]))
    with pytest.raises(ValueError, match="no Candidate Status column"):
        md.parse_text(LISTED.replace("Candidate Status", "Status", 1))
    with pytest.raises(ValueError, match="not the list of general election candidates"):
        MdList.parse(b"<html><body>Service Unavailable</body></html>")


def test_a_presidential_years_list_without_the_legislature_isnt_held_to_its_minimum():
    listed = [r for r in rows() if r["Office Name"] == "Representative in Congress"]
    listed = [{**r, "Filing Type and Date": r["Filing Type and Date"].replace("2026", "2028").replace("2025", "2027")}
              for r in listed]
    filings = md.parse_text(written(listed))
    assert {f.day for f in filings} == {"2028-11-07"} and {f.reach for f in filings} == {"cd"}


def test_an_annapolis_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "annapolis")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"],
                                  "labels": {"hd": "House of Delegates"}}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (3, 30, "30A")
    names = [race["name"] for race in ballot["races"]]
    assert names == ["U.S. Representative District 3", "Governor and Lieutenant Governor", "Comptroller",
                     "Attorney General", "State Senator District 30", "House of Delegates District 30A",
                     "Retain Appellate Court of Maryland Judge Dan Friedman"]
    assert all(race["source"] == "state_md" for race in ballot["races"])
    house = find_race(ballot, "U.S. Representative District 3")
    assert house["seat"] == "MD-03"
    assert candidate_names(house) == ["Sarah Elfreth", "Berney Flowers", "Robert L. Coffman"]
    assert [c["write_in"] for c in house["candidates"]] == [False, False, True]
    assert any(card["source"] == "fec" and card["kind"] == "money" for c in house["candidates"] for card in c["cards"])
    delegates = find_race(ballot, "House of Delegates District 30A")
    assert delegates["seats"] == 2
    assert find_race(ballot, "Retain Appellate Court of Maryland Judge Dan Friedman")["retention"]
    assert any("circuit and orphans' courts' judges" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-13",
        "mail_apply_by": "2026-10-27", "early_voting_start": "2026-10-22", "early_voting_end": "2026-10-29",
        "source": "Maryland State Board of Elections", "source_url": "https://elections.maryland.gov/",
        "computed": True,
    }
    assert upstream.count(HOST) == 2
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_md'")]
    assert sorted(sorted(value) for value in kept) == [["filings"], ["links"]]
    assert not any("Regular - " in json.dumps(value) for value in kept)
    get_ballot(client, "annapolis")
    assert logged_calls() == 0 and upstream.count(HOST) == 2


def test_a_maryland_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "annapolis")
    upstream.state_lists[f"{HOST}{LIST_PATH}"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_md")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "annapolis")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "Comptroller")


def test_with_marylands_list_off_or_unreadable_its_ballot_has_the_race_for_congress_from_the_fec(client, upstream):
    switch(client, "state_md", False)
    ballot = get_ballot(client, "annapolis")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 3")
    assert upstream.count(HOST) == 0
    switch(client, "state_md", True)
    upstream.state_lists[f"{HOST}{LIST_PATH}"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "annapolis")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Maryland State Board of Elections" in w
               for w in ballot["warnings"])


def test_a_year_whose_page_isnt_made_yet_leaves_the_fecs_races(client, upstream):
    upstream.state_lists[f"{HOST}{INDEX_PATH}"] = MD_NOT_FOUND
    ballot = get_ballot(client, "annapolis")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("The Maryland State Board of Elections hasn't published its list of candidates" in n
               for n in ballot["notes"])
    assert upstream.count(HOST) == 1


def test_marylands_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_md")
    assert outcome.status == "updated" and outcome.answers == 2
    assert outcome.counts == {"races": 131, "candidates": 323}
    assert upstream.count(HOST) == 2
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "annapolis")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == 2


@pytest.mark.parametrize("day, register, apply, start, end", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 13), dt.date(2026, 10, 27), dt.date(2026, 10, 22), dt.date(2026, 10, 29)),
    (dt.date(2028, 11, 7), dt.date(2028, 10, 17), dt.date(2028, 10, 31), dt.date(2028, 10, 26), dt.date(2028, 11, 2)),
])
def test_marylands_key_dates_are_worked_out_from_its_election_law(day, register, apply, start, end):
    """2026's against the State Board of Elections' 2026 Election Calendar."""
    found = state_key_dates.computed("MD", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, apply, start, end, "MD")
    assert state_key_dates.computed("MD", dt.date(2027, 11, 2)) is None


def test_marylands_calendar_file_and_when_to_vote_give_same_day_registration_and_no_excuse_for_mail(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "MD"})
    assert response.status_code == 200 and "maryland-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls are open 7 a.m. to 8 p.m.\\; if you're in line at 8\\, you can vote." in text
    assert all(day in text for day in ("20261013", "20261022", "20261029", "20261103"))
    assert "It ends Thursday\\, October 29." in text
    info = state_key_dates.GUIDES["MD"].voter_info()
    assert info.poll_hours == "7 a.m. – 8 p.m." and info.late_registration is not None
    assert info.mail_eligibility.startswith("Any registered voter can vote by mail")
