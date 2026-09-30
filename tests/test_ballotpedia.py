from __future__ import annotations

import datetime as dt

import httpx
import pytest
import respx

from votebot.config import Ttls
from votebot.http_cache import HttpCache
from votebot.sources.ballotpedia import (
    SOURCE, URL, Ballotpedia, BallotpediaUnavailable, council_district_in, parse, precincts_in,
)

from .conftest import load


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
