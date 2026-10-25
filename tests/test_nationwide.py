"""Ballots outside Texas (coverage.py): the races for Congress, from the people who filed with the FEC."""

from __future__ import annotations

import datetime as dt

import pytest

from pallot import coverage
from pallot.sources import census, fec, officeholders
from pallot.states import key_dates as state_key_dates
from pallot.states.adapters import ADAPTERS

from .bundling import answers, build
from .conftest import ADDRESSES, candidate_names, find_race, get_ballot, load, switch

TEXAS_ONLY_HOSTS = ("goelect.txelections.civixapps.com", "data.capitol.texas.gov", "www.sos.state.tx.us")


@pytest.fixture(autouse=True)
def georgia_without_its_list(monkeypatch):
    """Georgia and Wyoming stand in here for states without an official list or key dates, whose
    FEC filers are recorded; their own ballots are test_state_ga's and test_state_wy's."""
    for state in ("GA", "WY"):
        monkeypatch.delitem(coverage.COVERED, state)
        monkeypatch.delitem(ADAPTERS, state)
        monkeypatch.delitem(state_key_dates.RULES, state)


def test_georgia_gets_its_senate_and_house_races_from_the_fec(client, upstream):
    ballot = get_ballot(client, "atlanta")

    assert ballot["election_date"] == "2026-11-03"
    assert [e["name"] for e in ballot["elections"]] == ["2026 General Election"]
    assert ballot["coverage"] == {"ballot": "fec", "districts": ["cd"], "precincts": False, "outlines": False, "labels": {}}
    assert ballot["districts"]["cd"] == 5 and ballot["districts"]["sd"] is None and ballot["districts"]["sboe"] is None
    assert ballot["location"]["county_name"] == "Fulton County"
    assert ballot["key_dates"] is None and ballot["maybe"] == [] and ballot["left_out"] is None
    assert [r["name"] for r in ballot["races"]] == ["U.S. Senator", "U.S. Representative District 5"]

    senate = find_race(ballot, "U.S. Senator")
    assert senate["key"] == "fec:2026:GA-SEN" and senate["seat"] == "GA-SEN" and senate["source"] == "fec"
    assert candidate_names(senate)[:3] == ["T. Jonathan Ossoff", "Michael A Collins Jr", "Earl Leroy Carter"]  # most raised first
    assert len(senate["candidates"]) == 6  # those who raised $5,000 or more
    assert all(c["unverified"] for c in senate["candidates"])
    ossoff = senate["candidates"][0]
    assert ossoff["key"] == "fec:S8GA00180" and ossoff["incumbent"] and ossoff["party"] == "D"
    assert senate["holder"]["name"] == "Jon Ossoff" and not senate["open_seat"]  # matched by FEC ID, not name
    assert senate["notes"][0]["source"] == "FEC" and "raised at least $5,000" in senate["notes"][0]["text"]
    assert any(card["source"] == "fec" and card["match"] is None for card in ossoff["cards"])
    assert not any("only the races for Congress" in note for note in ballot["notes"])  # the page's coverage line says it
    assert not [host for host in TEXAS_ONLY_HOSTS if upstream.count(host)]


def test_the_second_lookup_outside_texas_makes_no_calls(client, logged_calls):
    get_ballot(client, "atlanta")
    get_ballot(client, "atlanta")
    assert logged_calls() == 0


def test_wyoming_has_one_at_large_seat(client):
    ballot = get_ballot(client, "cheyenne")
    assert ballot["districts"]["cd"] == 0
    house = find_race(ballot, "U.S. Representative At Large")
    assert house["seat"] == "WY-00" and house["key"] == "fec:2026:WY-00"
    assert find_race(ballot, "U.S. Senator")


def test_dc_has_its_delegate_and_no_senate_race(client):
    ballot = get_ballot(client, "dc")
    assert [r["name"] for r in ballot["races"]] == ["Delegate to the U.S. House of Representatives"]
    assert ballot["districts"]["cd"] == 0 and ballot["races"][0]["seat"] == "DC-00"


def test_a_territory_is_refused(client):
    response = client.post("/api/ballot", json={"address": ADDRESSES["pr"]})
    assert response.status_code == 422 and "50 states and DC" in response.json()["detail"]


def test_without_the_fec_there_is_no_ballot_outside_texas(client):
    switch(client, "fec", False)
    response = client.post("/api/ballot", json={"address": ADDRESSES["atlanta"]})
    assert response.status_code == 400 and "FEC" in response.json()["detail"]


def test_the_fec_not_answering_is_a_502(client, upstream):
    upstream.fec_status = 500
    response = client.post("/api/ballot", json={"address": ADDRESSES["atlanta"]})
    assert response.status_code == 502 and "The FEC isn't answering" in response.json()["detail"]


def test_another_election_date_shows_the_general(client):
    ballot = get_ballot(client, "atlanta", election_date="2026-12-01")
    assert ballot["election_date"] == "2026-11-03"
    assert any("only the general election" in warning for warning in ballot["warnings"])


def test_texas_keeps_its_full_coverage(client):
    assert get_ballot(client)["coverage"] == {"ballot": "state", "districts": ["cd", "sd", "hd", "sboe"],
                                              "precincts": True, "outlines": True, "labels": {}}


def test_coverage_and_where_sources_work():
    assert coverage.of("TX").ballot == "state" and coverage.of("WY") is coverage.FEDERAL
    assert coverage.works_in("tec", "TX")
    assert not coverage.works_in("tec", "GA") and coverage.works_in("polls", "GA")


def test_census_numbers_at_large_and_delegate_seats_zero():
    def place(name):
        match = load(f"census_{name}.json")["result"]["addressMatches"][0]
        return census.parse_geographies(match["geographies"], 0, 0, None)

    assert place("cheyenne").cd == 0 and place("dc").cd == 0 and place("atlanta").cd == 5
    assert place("capitol").cd == 10 and place("capitol").county_name == "Travis County"


def test_the_fec_list_keeps_who_raised_5000_and_the_incumbent():
    rows = [
        {"candidate_id": "H1", "candidate_name": "SMALL, SAM", "party_full": "REPUBLICAN PARTY", "total_receipts": 4999},
        {"candidate_id": "H2", "candidate_name": "HOLDER, HAL", "party_full": "DEMOCRATIC PARTY", "total_receipts": 0,
         "incumbent_challenge_full": "Incumbent"},
        {"candidate_id": "H3", "candidate_name": "BIG, BEA", "party_full": "WORKING FAMILIES PARTY", "total_receipts": 9000},
        {"candidate_id": "H4", "candidate_name": "BIG, BEA", "party_full": "WORKING FAMILIES PARTY", "total_receipts": 6000},
        {"candidate_id": "H5", "candidate_name": "WRITE, WILL", "party_full": "WRITE-IN", "total_receipts": 5000},
    ]
    found = fec.candidates(rows)
    assert [(c.key, c.name) for c in found] == [("fec:H3", "Bea Big"), ("fec:H5", "Will Write"), ("fec:H2", "Hal Holder")]
    assert found[0].party is None and found[0].party_name == "Working Families Party"
    assert found[1].write_in and found[1].party is None and found[2].incumbent
    assert all(c.unverified for c in found)


def test_the_federal_general_election_day():
    assert fec.general_day(dt.date(2026, 9, 27)) == dt.date(2026, 11, 3)
    assert fec.general_day(dt.date(2026, 11, 4)) == dt.date(2028, 11, 7)
    assert fec.general_day(dt.date(2027, 3, 1)) == dt.date(2028, 11, 7)
    assert fec.race_name("GA", None) == "U.S. Senator" and fec.race_name("WY", 0) == "U.S. Representative At Large"


def test_seat_holders_cover_every_state_and_the_special_elections():
    members = load("officeholders_congress.json")
    holders = officeholders.congress_holders(members, state=None)
    assert {"GA-SEN", "WY-00", "DC-00", "TX-SEN"} <= {h.seat for h in holders}
    day = dt.date(2026, 11, 3)
    appointee = officeholders.Holder("OH-SEN", "A", ["A"], "R", "Republican", ends=dt.date(2026, 11, 3))
    other = officeholders.Holder("OH-SEN", "B", ["B"], "R", "Republican", ends=dt.date(2031, 1, 3))
    assert officeholders._senator_up([other, appointee], day) is appointee
    house = officeholders.Holder("GA-05", "N", ["N"], "D", "Democrat", started=dt.date(2025, 1, 3))
    assert "Texas" not in officeholders._hint(house, "GA-05")


def test_the_race_lists_bundle_holds_every_other_state(tmp_path, upstream):
    from pallot.config import Config

    outcome = build(tmp_path, "fec_races", config=Config(data_dir=tmp_path / "data", fec_api_key="test-fec-key"))
    assert outcome.status == "updated" and outcome.counts["states"] == 50  # 49 states and DC
    urls = [(a["request"]["url"], (a["request"].get("params") or {}).get("state")) for a in answers(tmp_path, "fec_races")]
    states = {state for url, state in urls if url.endswith("/elections/")}
    assert "TX" not in states and "GU" not in states and {"GA", "WY", "DC"} <= states
    assert sum(url.endswith("/elections/search/") for url, _ in urls) == 6  # the Senate's page and the House's five
