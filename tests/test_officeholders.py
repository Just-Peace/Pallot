from __future__ import annotations

import datetime as dt

from pallot.models import Candidate, Race
from pallot.sources import officeholders
from pallot.sources.officeholders import Holder, congress_holders, legislature_holders, seat_info

from .conftest import fixture_bytes, find_race, get_ballot, last_use, load, switch


def people(race):
    return {c["name"]: c for c in race["candidates"]}


def test_the_capitol_ballot_says_who_holds_each_seat(client, upstream):
    ballot = get_ballot(client)
    senate = find_race(ballot, "U.S. Senator")
    assert senate["open_seat"] and senate["holder"] == {
        "name": "John Cornyn", "party": "R", "party_name": "Republican", "hint": "Held by John Cornyn, a Republican"}
    assert {name: c["party_holds_seat"] for name, c in people(senate).items()} == {
        "Ken Paxton": True, "James Talarico": False, "Ted Brown": False}

    house = find_race(ballot, "U.S. Representative District 10")
    assert house["open_seat"] and house["holder"]["name"] == "Michael T. McCaul"
    assert house["holder"]["hint"].endswith("elected under the district's lines before Texas redrew its U.S. House map in 2025")
    assert people(house)["Chris Gober"]["party_holds_seat"] and not people(house)["Caitlin Rourk"]["party_holds_seat"]

    rep = find_race(ballot, "State Representative District 49")
    assert rep["open_seat"] and rep["holder"]["hint"] == "Held by Gina Hinojosa, a Democrat"
    assert people(rep)["Montserrat Garibay"]["party_holds_seat"]
    assert not [r for r in ballot["races"] if r["group"] in ("state", "judicial", "county", "local") and r["holder"]]
    assert upstream.count("unitedstates.github.io") == 1 and upstream.count("data.openstates.org") == 1
    assert last_use(client, "officeholders")["status"] == "used"

    get_ballot(client)
    assert get_ballot(client)["meta"]["external_calls"] == 0


def test_a_holder_on_the_ballot_is_the_incumbent(client, upstream):
    members = load("officeholders_congress.json")
    cornyn = next(m for m in members if m["name"].get("official_full") == "John Cornyn")
    cornyn["name"] = {"first": "Warren", "last": "Paxton", "official_full": "Warren Kenneth Paxton", "nickname": "Ken"}
    upstream.congress_members = members
    senate = find_race(get_ballot(client), "U.S. Senator")
    paxton = people(senate)["Ken Paxton"]
    assert paxton["incumbent"] and not paxton["party_holds_seat"]  # by his nickname and last name
    assert not senate["open_seat"]


def test_a_source_kept_off_shows_nothing(client, upstream):
    switch(client, "officeholders", False)
    ballot = get_ballot(client)
    assert not [r for r in ballot["races"] if r["holder"] or r["open_seat"]]
    assert not [c for r in ballot["races"] for c in r["candidates"] if c["party_holds_seat"]]
    assert upstream.count("unitedstates.github.io") == 0 and upstream.count("data.openstates.org") == 0
    assert last_use(client, "officeholders")["status"] == "off"


def test_a_refusal_pauses_it_and_the_ballot_still_loads(client, upstream):
    upstream.officeholders_status = 403
    ballot = get_ballot(client)
    assert "Couldn't load who holds each seat (HTTP 403)." in ballot["warnings"]
    assert not find_race(ballot, "U.S. Senator")["holder"]
    asked = upstream.count("unitedstates.github.io")
    again = get_ballot(client)
    assert upstream.count("unitedstates.github.io") == asked  # paused: not asked again
    assert any("paused until" in w for w in again["warnings"])
    status = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "officeholders")
    assert status["notice"].startswith("Paused until") and status["notice_tone"] == "warn"


def test_the_lists_are_read():
    congress = congress_holders(load("officeholders_congress.json"))
    assert len([h for h in congress if h.seat == "TX-SEN"]) == 2
    assert all(h.seat.startswith("TX-") for h in congress)
    carter = next(h for h in congress if h.name == "John R. Carter")
    assert (carter.seat, carter.party, carter.started) == ("TX-31", "R", dt.date(2025, 1, 3))
    legislature = legislature_holders(fixture_bytes("officeholders_tx.csv").decode())
    assert {h.seat.split(":")[0] for h in legislature} == {"STATESEN", "STATEREP"}
    assert len({h.seat for h in legislature}) == len(legislature)
    hinojosa = next(h for h in legislature if h.seat == "STATESEN:27")
    assert (hinojosa.name, hinojosa.party, hinojosa.party_name) == ("Adam Hinojosa", "R", "Republican")


def test_the_senator_up_is_the_one_whose_term_ends_after_the_election():
    holders = congress_holders(load("officeholders_congress.json"))
    senators = [h for h in holders if h.seat == "TX-SEN"]
    assert officeholders._senator_up(senators, dt.date(2026, 11, 3)).name == "John Cornyn"
    assert officeholders._senator_up(senators, dt.date(2030, 11, 5)).name == "Ted Cruz"
    assert officeholders._senator_up(senators, dt.date(2027, 5, 1)) is None


def race(*candidates, seat="TX-07"):
    return Race(key="r", name="Race", group="federal", source="sos", seat=seat, candidates=[
        Candidate(key=f"c{i}", name=name, party=party) for i, (name, party) in enumerate(candidates)])


def holder(name="Jane Q. Public", party="D", seat="TX-07"):
    return Holder(seat=seat, name=name, names=[name], party=party, party_name={"D": "Democrat", "R": "Republican"}[party],
                  started=dt.date(2027, 1, 3))


def test_a_full_or_first_and_last_name_is_the_holder():
    for name in ("Jane Q. Public", "Jane Public"):
        info, key = seat_info(race((name, "D"), ("Rob Roe", "R"), ("Dee Doe", "D")), holder(), "TX-07")
        assert key == "c0" and not info.open and info.party_holds == {"c2"}
        assert info.holder.hint == "Held by Jane Q. Public, a Democrat"  # a term from the new map: no caveat


def test_a_likely_match_claims_nothing():
    """Troy Nehls holds the seat and Trever Nehls runs for it: "T. Nehls" both, so nothing's said."""
    info, key = seat_info(race(("Trever Nehls", "R"), ("Al Green", "D")), holder("Troy Nehls", "R", "TX-22"), "TX-22")
    assert key is None and not info.open and info.party_holds == set() and info.holder.name == "Troy Nehls"


def test_a_vacant_seat_is_open():
    info, key = seat_info(race(("Rob Roe", "R")), None, "TX-18")
    assert (info.holder, info.open, key) == (None, True, None)


def test_another_partys_primary_isnt_called_open():
    info, _ = seat_info(race(("Rob Roe", "R"), ("Bo Bee", "R")), holder(), "TX-07")
    assert not info.open and info.holder


def test_another_source_saying_incumbent_keeps_the_seat_from_being_open():
    from pallot.enrich import _set_seat
    found = race(("Rob Roe", "R"), ("Dee Doe", "D"))
    found.candidates[1].incumbent = True  # the state's filing says so
    info, _ = seat_info(found, holder(), "TX-07")
    _set_seat(found, info)
    assert not found.open_seat and not found.candidates[1].party_holds_seat
