from __future__ import annotations

import pytest

from votebot.matching import (
    NameIndex, full_key, initial_key, match_trackaipac, match_unique, name_tokens, seats_in, short_key,
)

from .conftest import load


def person(name, seat, party, *listings):
    return {"name": name, "state": "TX", "seat": seat, "party": party, "listings": list(listings)}


def listing(seat=None, seat_text=None):
    return {"seat": seat, "seat_text": seat_text}


@pytest.fixture
def index():
    people = [
        person("August Pfluger", "TX-11", "R", listing("TX-11", "TX-11 [R]")),
        person("Ken Paxton", "TX-SEN", "R", listing("TX-SEN", "Texas [R]")),
        person("Greg Casar", "TX-35", "D", listing("TX-35", "TX-35 (TX-37 2026)"), listing("TX-35", "TX-35 [D]")),
        person("Al Green", "TX-09", "D", listing("TX-09", "TX-09 [D]")),
        person("John Smith", "TX-05", "R", listing("TX-05")),
        person("John Smith", "TX-30", "D", listing("TX-30")),
        person("Wesley Hunt", "TX-38", "R", listing("TX-38")),
        person("Robert Hall", "TX-02", "R", listing("TX-02")),
    ]
    idx = NameIndex()
    for p in people:
        idx.add(p["name"], p)
    return idx


def test_names_normalize_across_sources():
    assert name_tokens("JOSÉ O'ROURKE JR.") == ["JOSE", "OROURKE"]
    assert full_key('KENNETH "KEN" PAXTON') == "KENNETH PAXTON"
    assert short_key("CHRISTIAN DASHAUN MENEFEE") == "CHRISTIAN MENEFEE"
    assert initial_key("TOM BAKER") == initial_key("Thomas Baker") == "T BAKER"


def test_seats_in_text():
    assert seats_in("TX-35 (TX-37 2026)") == {"TX-35", "TX-37"}
    assert seats_in("TX-5 [R]") == {"TX-05"}
    assert seats_in("Texas [R]") == set()


def test_exact_match_on_name_and_seat(index):
    person_, match = match_trackaipac(index, "AUGUST PFLUGER", "R", "TX-11")
    assert person_["name"] == "August Pfluger"
    assert (match.confidence, match.method) == ("exact", "full name + seat TX-11")


def test_senate_seat(index):
    _, match = match_trackaipac(index, "KEN PAXTON", "R", "TX-SEN")
    assert match.confidence == "exact"


def test_2026_seat_from_seat_text_after_redistricting(index):
    person_, match = match_trackaipac(index, "GREG CASAR", "D", "TX-37")
    assert person_["seat"] == "TX-35"
    assert match.confidence == "exact"


def test_same_name_running_for_another_seat_is_only_likely(index):
    _, match = match_trackaipac(index, "AL GREEN", "D", "TX-18")
    assert match.confidence == "likely"
    assert "TX-09" in match.note


def test_party_mismatch_is_only_likely(index):
    _, match = match_trackaipac(index, "WESLEY HUNT", "D", "TX-38")
    assert match.confidence == "likely"
    assert "party differs" in match.note


def test_ambiguous_names_are_settled_by_seat_or_left_alone(index):
    person_, _ = match_trackaipac(index, "JOHN SMITH", "D", "TX-30")
    assert person_["seat"] == "TX-30"
    assert match_trackaipac(index, "JOHN SMITH", "I", "TX-02") is None


def test_first_initial_match_is_only_likely(index):
    person_, match = match_trackaipac(index, "WES HUNT", "R", "TX-38")
    assert person_["name"] == "Wesley Hunt"
    assert (match.confidence, match.method) == ("likely", "first initial and last name + seat TX-38")


def test_last_name_and_seat_fallback_for_nicknames(index):
    person_, match = match_trackaipac(index, "BOB HALL", "R", "TX-02")
    assert person_["name"] == "Robert Hall"
    assert (match.confidence, match.method) == ("likely", "last name + seat")


def test_unknown_person_gets_no_match(index):
    assert match_trackaipac(index, "CHRIS GOBER", "R", "TX-10") is None


def test_match_unique_tiers():
    idx = NameIndex()
    for name in ("Thomas Baker", "Kyle Hawkins", "Kristen Hawkins", "Christian Menefee"):
        idx.add(name, name)
    assert match_unique(idx, "THOMAS BAKER")[1].confidence == "exact"
    found, match = match_unique(idx, "TOM BAKER")
    assert found == "Thomas Baker" and match.confidence == "likely"
    assert match_unique(idx, "CHRISTIAN DASHAUN MENEFEE")[0] == "Christian Menefee"
    assert match_unique(idx, "K. HAWKINS") is None  # two people fit


def test_recorded_trackaipac_fixture_matches_the_senate_candidates():
    idx = NameIndex()
    for p in load("trackaipac/current.json")["candidates"]:
        idx.add(p["name"], p)
    for name in ("KEN PAXTON", "JAMES TALARICO"):
        found = match_trackaipac(idx, name, None, "TX-SEN")
        assert found and found[1].confidence == "exact"
