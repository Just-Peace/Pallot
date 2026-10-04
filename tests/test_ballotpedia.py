from __future__ import annotations

import datetime as dt

import httpx
import pytest
import respx

from pallot.config import Ttls
from pallot.http_cache import HttpCache
from pallot.models import Candidate, Race
from pallot.sources.ballotpedia import (
    SOURCE, URL, Ballotpedia, BallotpediaUnavailable, BpNote, cards, council_district_in, counterparts, parse,
    precincts_in,
)

from .conftest import load

DAY = dt.date(2026, 11, 3)


def _payload(*districts):
    return {"data": {"elections": [{"date": DAY.isoformat(), "districts": list(districts)}]}}


def _bp_race(race_id, office, *candidates, **extra):
    return {"id": race_id, "office": {"name": office}, "candidates": list(candidates), **extra}


def _bp_candidate(candidate_id, name, party="Democratic Party", **extra):
    return {"id": candidate_id, "person": {"name": name}, "party_affiliation": [{"name": party}], **extra}


def _state_race(key, *people):
    return Race(key=key, name=key, group="county", source="sos",
                candidates=[Candidate(key=f"{key}:{i}", name=name, party=party) for i, (name, party) in enumerate(people)])


def test_without_a_date_the_ballot_is_the_next_election_or_else_the_latest():
    def election(day):
        return {"date": day, "districts": [{"type": "State", "name": "Texas",
                                            "races": [_bp_race(day, f"Race on {day}", _bp_candidate(1, "A B"))]}]}

    payload = {"data": {"elections": [election("2026-11-03"), election("2026-03-03")]}}
    for today, expected in ((dt.date(2026, 1, 1), dt.date(2026, 3, 3)), (dt.date(2026, 3, 3), dt.date(2026, 3, 3)),
                            (dt.date(2026, 10, 3), DAY), (dt.date(2026, 12, 1), DAY)):
        assert parse(payload, None, 0.0, today).day == expected, today


@pytest.fixture(scope="module")
def ballot():
    return parse(load("ballotpedia_capitol.json"), dt.date(2026, 11, 3), fetched_at=0.0)


def test_local_races_and_special_districts_are_separated(ballot):
    by_group = {}
    for race in ballot.races:
        by_group.setdefault(race.group, []).append(race.office)
    assert "Austin City Council District 9" in by_group["local"]
    assert any("Independent School District" in office for office in by_group["local"])
    assert all("Utility" in o or "Water" in o or "District" in o for o in by_group["special"])
    assert not any("Utility District" in o for o in by_group.get("county", []))


def test_precincts_come_from_county_subdivisions(ballot):
    assert ballot.precincts == {"jp": 5, "constable": 5}
    assert precincts_in("Harris County Commissioners Court Precinct 2") == {"commissioner": 2}
    assert precincts_in("Travis County") == {}


def test_a_precinct_named_without_its_kind_takes_it_from_its_races():
    assert precincts_in("Fort Bend County Precinct 1", ["Fort Bend County Justice of the Peace, Precinct 1-Place 2"]) == {"jp": 1}
    assert precincts_in("Harris County Commissioners Court Precinct 2", ["Harris County Justice of the Peace Precinct 2"]) == {
        "commissioner": 2}  # the name says which, so the races don't
    assert precincts_in("Fort Bend County Precinct 1", ["Fort Bend County Judge"]) == {}
    fort_bend = parse(_payload({"type": "County subdivision", "name": "Fort Bend County Precinct 1", "races": [
        _bp_race(1, "Fort Bend County Justice of the Peace, Precinct 1-Place 1", _bp_candidate(10, "Martin Sanchez")),
    ]}), DAY, 0.0)
    assert fort_bend.precincts == {"jp": 1}


def test_notes_are_plain_text_with_their_link():
    replaced = {"text": "Paula Miller won the <b>Democratic</b> primary &amp; was replaced."}
    district = {
        "type": "Judicial District", "name": "Fort Bend County Court at Law, Texas",
        "disclaimers": [{"text": 'Texas redrew its map. <a href="https://ballotpedia.org/Redistricting" target="_blank">'
                                 "Click here to learn more.</a>"}],
        "races": [_bp_race(1, "Fort Bend County Court at Law No. 3", _bp_candidate(10, "Juli Mathew"),
                           race_disclaimers=[replaced, replaced, {"text": '<a href="javascript:alert(1)">See</a> the court.'}],
                           stage_disclaimers=None)],
    }
    race = parse(_payload(district), DAY, 0.0).races[0]
    assert race.notes == (
        BpNote("Paula Miller won the Democratic primary & was replaced."),
        BpNote("See the court."),  # not a web link, so no link
        BpNote("Texas redrew its map.", "https://ballotpedia.org/Redistricting"),
    )


@pytest.fixture
def courts():
    return parse(_payload({"type": "Judicial District", "name": "Fort Bend County Court at Law, Texas", "races": [
        _bp_race(3, "Fort Bend County Court at Law No. 3", _bp_candidate(31, "Jessica Jaramillo", "Republican Party"),
                 _bp_candidate(32, "Juli Mathew", is_incumbent=True)),
        _bp_race(4, "Fort Bend County Court at Law No. 4", _bp_candidate(41, "Toni Wallace", is_incumbent=True),
                 _bp_candidate(42, "Thomas Baker", is_incumbent=True)),
    ]}), DAY, 0.0)


def test_a_state_race_finds_its_own_race_on_ballotpedia(courts):
    ccl3 = _state_race("ccl3", ("Jessica Jaramillo", "R"), ("Juli A. Mathew", "D"))
    mixed = _state_race("mixed", ("Jessica Jaramillo", "R"), ("Toni Wallace", "D"))  # two races: neither
    own = Race(key="bp:4", name="Fort Bend County Court at Law No. 4", group="judicial", source="ballotpedia")
    found = counterparts(courts, [ccl3, mixed, own])
    assert {key: race.id for key, race in found.items()} == {"ccl3": 3, "bp:4": 4}


def test_a_write_in_doesnt_count_toward_its_races_own_race(courts):
    ccl3 = _state_race("ccl3", ("Jessica Jaramillo", "R"), ("Juli A. Mathew", "D"))
    ccl3.candidates.append(Candidate(key="ccl3:w", name="Toni Wallace", write_in=True))  # printed in race 4 on Ballotpedia
    assert counterparts(courts, [ccl3])["ccl3"].id == 3


def test_a_match_in_its_own_race_and_party_is_exact(courts):
    ccl3 = _state_race("ccl3", ("Jessica Jaramillo", "R"), ("Juli A. Mathew", "D"))
    ccl4 = _state_race("ccl4", ("Toni Wallace", "R"), ("Tom Baker", "D"))
    races = [ccl3, ccl4]
    got = cards(courts, races, counterparts(courts, races))
    mathew = got.candidates["ccl3:1"].match
    assert (mathew.confidence, mathew.method) == ("exact", "first and last name, in the same seat")
    wallace = got.candidates["ccl4:0"].match
    assert wallace.confidence == "likely" and wallace.note == "party differs (Ballotpedia says D)"
    assert got.candidates["ccl4:1"].match.confidence == "likely"  # Tom and Thomas: initials only
    assert got.incumbents == {"ccl3:1"}  # exact matches only
    alone = cards(courts, [ccl3])  # without its own race, a middle initial leaves it likely
    assert alone.candidates["ccl3:1"].match.confidence == "likely" and not alone.incumbents


def test_city_council_district_comes_from_city_subdivisions(ballot):
    assert ballot.city_council == "District 9"
    assert council_district_in("Houston City Council District C") == "District C"
    assert council_district_in("Round Rock City Council Place 3") == "Place 3"
    assert council_district_in("Ward 2") == "Ward 2"
    assert council_district_in("") is None


def test_race_details(ballot):
    senate = next(r for r in ballot.races if r.office == "U.S. Senate Texas")
    assert senate.group == "federal" and senate.seat == "TX-SEN"
    assert [c.write_in for c in senate.candidates] == sorted(c.write_in for c in senate.candidates)  # write-ins last
    house = next(r for r in ballot.races if r.district_type == "Congress")
    assert house.seat == "TX-10"
    assert any(r.seats > 1 for r in ballot.races if r.group == "special")


def test_a_date_with_no_ballotpedia_election_gives_an_empty_ballot():
    empty = parse(load("ballotpedia_capitol.json"), dt.date(2030, 1, 1), fetched_at=0.0)
    assert empty.races == () and empty.precincts == {} and empty.city_council is None


@pytest.mark.anyio
async def test_refusal_pauses_further_calls(tmp_path):
    with respx.mock() as router:
        route = router.get(URL).mock(return_value=httpx.Response(403))
        async with httpx.AsyncClient() as client:
            source = Ballotpedia(HttpCache(tmp_path / "c.sqlite3", client), Ttls())
            with pytest.raises(BallotpediaUnavailable):
                await source.ballot(30.27, -97.74)
            assert source.cache.paused_until(SOURCE) is not None
            with pytest.raises(BallotpediaUnavailable, match="paused"):
                await source.ballot(30.27, -97.74)
    assert route.call_count == 1


@pytest.mark.anyio
async def test_a_paused_ballotpedia_still_serves_what_it_has(tmp_path):
    with respx.mock() as router:
        route = router.get(URL).mock(side_effect=[httpx.Response(200, json=load("ballotpedia_capitol.json")), httpx.Response(403)])
        async with httpx.AsyncClient() as client:
            source = Ballotpedia(HttpCache(tmp_path / "c.sqlite3", client), Ttls())
            first = await source.ballot(30.27, -97.74, dt.date(2026, 11, 3))
            with pytest.raises(BallotpediaUnavailable):
                await source.ballot(29.76, -95.37)  # somewhere else: refused, which pauses Ballotpedia
            assert source.cache.paused_until(SOURCE) is not None
            again = await source.ballot(30.27, -97.74, dt.date(2026, 11, 3))
    assert again.races == first.races and route.call_count == 2
