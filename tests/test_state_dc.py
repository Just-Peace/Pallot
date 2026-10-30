"""DC's ballot (states/dc.py), from the Board of Elections' General Election Candidates in Ballot
Order, a PDF linked from its page of the year's elections, and its key dates worked out from the
D.C. Code. tests/fixtures/state_dc.html is that page cut down to its link, and state_dc.pdf the list
rewritten as its offices and candidates with the day each filed, without contact details
(scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from pallot import coverage
from pallot.models import Candidate, Race
from pallot.states import dc
from pallot.states import key_dates as state_key_dates
from pallot.states.dc import DcList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch

HOST = "www.dcboe.org"
PAGE_PATH = "/elections/2026-elections"
LIST_PATH = ("/getContentAsset/1029b813-fb27-4055-9218-fbe40360aacb/5ebbd046-860b-4ee1-81c8-43d0e3bc446e/"
             "2026-General-CANDIDATES-07152026.pdf")
LISTED = (FIXTURES / "state_dc.pdf").read_bytes()
TITLE = "<title>2026 Elections | District of Columbia Board of Elections</title>"


def test_the_years_page_links_the_general_elections_candidates_not_the_ancs_or_the_primarys():
    page = (f"<html><head>{TITLE}</head><body>"
            '<a href="/getmedia/x/2026-PRIMARY-CANDIDATES-03022026.pdf">List of Primary Election Candidates in Ballot Order</a>'
            '<a href="/getContentAsset/a/b/2026-General-CANDIDATES-07162026.pdf?language=en">Advisory Neighborhood '
            "Commission (ANC) Candidates in Ballot Order</a>"
            '<a href="/getContentAsset/c/d/2026-General-CANDIDATES-07152026.pdf?language=en&amp;x=1" target="_blank">'
            "General Election <em>Candidates</em> in Ballot Order</a></body></html>")
    assert dc.links(page) == {"links": ["https://www.dcboe.org/getContentAsset/c/d/2026-General-CANDIDATES-07152026.pdf"
                                        "?language=en&x=1"]}
    assert DcList.spec(DcList.__new__(DcList), dt.date(2026, 11, 3)).url == f"https://{HOST}{PAGE_PATH}"
    assert DcList.read_index(LISTED) is None
    assert DcList.read_index((FIXTURES / "state_dc.html").read_bytes())["links"][0].endswith(
        "2026-General-CANDIDATES-07152026.pdf?language=en")
    assert DcList.follow(DcList.__new__(DcList), {"links": []}, dt.date(2026, 11, 3)) is None
    with pytest.raises(ValueError, match="not the Board of Elections' page"):
        dc.links("<html><body>Service Unavailable</body></html>")


def test_dcs_list_has_its_delegate_and_its_offices_elected_citywide_without_its_wards_races():
    filings = DcList.parse(LISTED)
    assert {f.day for f in filings} == {"2026-11-03"} and not any(f.write_in or f.incumbent for f in filings)
    assert list(dict.fromkeys(f.office for f in filings)) == [
        "Delegate to the U.S. House of Representatives", "Mayor", "Chairman of the Council",
        "At-Large Member of the Council", "Attorney General", "Shadow U.S. Senator", "Shadow U.S. Representative"]
    delegate = [(f.name, f.party, f.party_name, f.reach, f.district, f.group) for f in filings if f.reach == "cd"]
    assert delegate == [("Denise Rosado", "R", None, "cd", "0", "federal"), ("Robert White", "D", None, "cd", "0", "federal"),
                        ("Kymone Freeman", None, "Statehood Green", "cd", "0", "federal")]
    assert all(f.reach == "state" and f.group == "state" for f in filings if f.reach != "cd")
    at_large = [(f.name, f.party, f.party_name, f.seats) for f in filings if f.office_id == "COUNCIL AT-LARGE"]
    assert at_large == [("Oye Owolewa", "D", None, 2), ("Darryl Moch", None, "Statehood Green", 2),
                        ("Darrell Green", "R", None, 2), ("Elissa Silverman", None, "Independent", 2)]
    assert [f.name for f in filings if f.office_id == "SHADOW US SENATOR"] == ["Robert Simmons", "Paul Strauss"]
    assert not any(f.name in ("Aparna Raj", "Ben Williams", "Joshua Wiley") for f in filings)  # ward races


def test_a_list_with_an_office_it_doesnt_know_or_no_delegate_is_refused():
    lines = dc.pdf_lines(LISTED)
    with pytest.raises(ValueError, match="an office it doesn't know: Lieutenant Mayor"):
        dc.candidates(lines[:3] + ["Lieutenant Mayor", "Pat Doe - Democrat              3/1/2026"] + lines[3:])
    with pytest.raises(ValueError, match="0 U.S. House races, not 1"):
        dc.candidates(lines[:1] + [line for line in lines if line.startswith("Mayor")])
    with pytest.raises(ValueError, match="not the list of general election candidates"):
        dc.candidates(["Delegate to the House of Representatives"])
    with pytest.raises(ValueError, match="not a PDF it can read"):
        DcList.parse(b"<html><body>Service Unavailable</body></html>")


def test_a_contest_with_three_candidates_or_more_on_the_ballot_is_ranked_choice():
    def race(*write_ins: bool) -> Race:
        return Race(key="r", name="r", group="state", source="state_dc", candidates=[
            Candidate(key=f"c{i}", name=f"C {i}", write_in=w) for i, w in enumerate(write_ins)])

    assert DcList.ranked_choice(race(False, False, False))
    assert not DcList.ranked_choice(race(False, False))
    assert not DcList.ranked_choice(race(False, False, True))


def test_a_dc_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "dc")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd"]}
    assert ballot["districts"]["cd"] == 0 and ballot["districts"]["sd"] is None
    assert [race["name"] for race in ballot["races"]] == [
        "Delegate to the U.S. House of Representatives", "Mayor", "Chairman of the Council",
        "At-Large Member of the Council", "Attorney General", "Shadow U.S. Senator", "Shadow U.S. Representative"]
    assert all(race["source"] == "state_dc" for race in ballot["races"])
    delegate = ballot["races"][0]
    assert delegate["seat"] == "DC-00" and candidate_names(delegate) == ["Denise Rosado", "Robert White", "Kymone Freeman"]
    assert [race["ranked_choice"] for race in ballot["races"]] == [True, True, False, True, False, False, False]
    assert find_race(ballot, "At-Large Member of the Council")["seats"] == 2
    assert find_race(ballot, "Shadow U.S. Senator")["seat"] is None
    assert any("Your ward's Council and State Board of Education races" in note for note in ballot["notes"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-13",
        "mail_apply_by": "2026-10-19", "early_voting_start": "2026-10-26", "early_voting_end": "2026-11-01",
        "source": "DC Board of Elections", "source_url": "https://www.dcboe.org", "computed": True,
    }
    assert upstream.count(HOST) == 2
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [json.loads(value) for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_dc'")]
    assert sorted(sorted(value) for value in kept) == [["filings"], ["links"]]
    assert not any("3/11/2026" in json.dumps(value) for value in kept)
    get_ballot(client, "dc")
    assert logged_calls() == 0 and upstream.count(HOST) == 2


def test_a_dc_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "dc")
    upstream.state_lists[f"{HOST}{LIST_PATH}"] = "<html><body>Service Unavailable</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_dc")
    assert status != 0 and "failed and kept their old copy" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "dc")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "Mayor")


def test_with_dcs_list_off_or_unreadable_its_ballot_has_the_delegate_from_the_fec(client, upstream):
    switch(client, "state_dc", False)
    ballot = get_ballot(client, "dc")
    assert ballot["coverage"]["ballot"] == "fec"
    assert [race["name"] for race in ballot["races"]] == ["Delegate to the U.S. House of Representatives"]
    assert upstream.count(HOST) == 0
    switch(client, "state_dc", True)
    upstream.state_lists[f"{HOST}{PAGE_PATH}"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "dc")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the DC Board of Elections" in w for w in ballot["warnings"])


def test_dcs_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_dc")
    assert outcome.status == "updated" and outcome.answers == 2
    assert outcome.counts == {"races": 7, "candidates": 18}
    assert upstream.count(HOST) == 2
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "dc")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == 2


def test_dc_shows_no_legislature():
    cover = coverage.of("DC")
    assert (cover.ballot, cover.districts, cover.labels) == ("list", ("cd",), {})


def test_dcs_2026_key_dates_are_worked_out_from_the_dc_code():
    found = state_key_dates.computed("DC", dt.date(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        dt.date(2026, 10, 13), dt.date(2026, 10, 19), dt.date(2026, 10, 26), dt.date(2026, 11, 1), "DC")


def test_dcs_calendar_file_and_when_to_vote_give_its_poll_hours_and_the_mailed_ballot(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "DC"})
    assert response.status_code == 200 and "dc-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls are open 7 a.m. to 8 p.m.\\; if you're in line at 8\\, you can vote." in text
    assert all(day in text for day in ("20261013", "20261026", "20261101", "20261103"))  # not the mail request
    info = state_key_dates.GUIDES["DC"].voter_info()
    assert info.poll_hours == "7 a.m. – 8 p.m." and "vote center" in info.late_registration.label
    assert info.mail_eligibility.startswith("Every active voter is mailed a ballot.")
