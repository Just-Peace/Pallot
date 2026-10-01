"""Commissioner and JP precincts from the county's own records (made up in conftest from the
made-up precinct map): reading numbers and finding layers, Travis's and Harris's lists, a made-up
county's maps laid over a precinct, and how they reach the ballot and Settings."""

from __future__ import annotations

import contextlib
from pathlib import Path

import httpx
import pytest

from votebot.config import Ttls
from votebot.http_cache import HttpCache, UpstreamError
from votebot.sources import county_precincts as cp
from votebot.sources.county_precincts import Areas, County, CountyPrecincts, Layer, Table, number, pick, services_root
from votebot.sources.election_precincts import ElectionPrecincts

from .conftest import (
    ANDERSON, HARRIS, PROJECTION, TRAVIS, TRAVIS_LIST, TRAVIS_QUERY, box, census_points, get_ballot, last_use, middle,
    travis_rows,
)

FOLDER = "https://gis.example.test/arcgis/rest/services"
MAPS = County(TRAVIS, "Travis",  # Travis, as a county that only publishes maps of its commissioner and JP precincts
              commissioner=Areas(Layer(FOLDER, "Boundaries", "MapServer", "Commissioner Precincts"), "COMM"),
              jp=Areas(Layer(FOLDER, "Boundaries", "MapServer", "JP Precincts"), "JP"))
CAPITOL = middle(census_points("capitol"))  # the middle of precinct 300, an 800 m square


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


@contextlib.asynccontextmanager
async def service(tmp_path: Path, counties: dict[int, County] = cp.COUNTIES, clock: Clock | None = None):
    """The county records, with the made-up precinct map already downloaded."""
    async with httpx.AsyncClient() as client:
        cache = HttpCache(tmp_path / "cache.sqlite3", client, retry_after=Ttls().retry_after, clock=clock or Clock())
        precincts = ElectionPrecincts(cache, Ttls(), tmp_path / "election_precincts")
        try:
            await precincts.at(TRAVIS, *census_points("capitol"))
            yield CountyPrecincts(cache, Ttls(), precincts, counties)
        finally:
            await precincts.aclose()
            cache.close()


def area(number_field: str, value, west: float, south: float, east: float, north: float) -> dict:
    """A feature of a county's map, as ArcGIS sends it in lon/lat: a box so many metres around the Capitol's precinct."""
    ring = [PROJECTION.unproject(x, y) for x, y in box(CAPITOL, west, south, east, north)]
    return {"attributes": {number_field: value}, "geometry": {"rings": [ring]}}


def serve_maps(upstream, commissioners: list[dict], jps: list[dict]) -> None:
    upstream.arcgis["gis.example.test"] = {
        "/arcgis/rest/services": {"services": [{"name": "Boundaries", "type": "MapServer"}]},
        "/arcgis/rest/services/Boundaries/MapServer": {"layers": [{"id": 0, "name": "Commissioner Precincts"},
                                                                  {"id": 1, "name": "JP Precincts"}]},
        "/arcgis/rest/services/Boundaries/MapServer/0/query": commissioners,
        "/arcgis/rest/services/Boundaries/MapServer/1/query": jps,
    }


# -- reading what counties publish -----------------------------------------------------------------


def test_numbers_as_counties_write_them():
    assert [number(v, 4) for v in (2, 2.0, "2", "02", "P02", " J02 ")] == [2] * 6
    assert number("J15", 99) == 15
    assert [number(v, 4) for v in ("9", 5, 0, "0", "", None, True, 2.5, "P", "100", "2a")] == [None] * 11


def test_the_newest_service_and_layer_by_year_never_a_proposal():
    services = [{"name": "VPCTs_2023", "type": "FeatureServer"}, {"name": "VPCTS_2024", "type": "FeatureServer"},
                {"name": "VPCTs_2026", "type": "FeatureServer"}, {"name": "VPCTs_2028", "type": "MapServer"},
                {"name": "HC_Voting_Precinct_2026_Proposed", "type": "FeatureServer"}]
    assert pick(services, r"VPCTs_(\d{4})", server="FeatureServer")["name"] == "VPCTs_2026"
    assert pick(services, r"VPCTs_(\d{4})", server="MapServer")["name"] == "VPCTs_2028"
    assert pick(services, r"HC_Voting_Precinct_(\d{4})_\w+") is None  # only a proposal matches
    layers = [{"id": 0, "name": "Proposed precinct changes"}, {"id": 2, "name": "Tax_Voting_Pct"}, {"id": 3, "name": "Draft"}]
    assert pick(layers, ".*")["id"] == 2
    assert pick([{"id": 1, "name": "Voter Precincts 2022"}, {"id": 5, "name": "Voter Precincts 2025"}],
                r"Voter Precincts (\d{4})")["id"] == 5
    assert pick(None, ".*") is None and pick([{"name": "Precincts"}], "Precinct") is None  # the whole name
    assert services_root("https://h/arcgis/rest/services/Dynamic") == "https://h/arcgis/rest/services"


# -- counties' lists of their election precincts ---------------------------------------------------


@pytest.mark.anyio
async def test_a_countys_list_gives_both_numbers_and_is_asked_once(tmp_path, upstream):
    async with service(tmp_path) as county:
        found = await county.at(TRAVIS, ("0300",))
        assert (found.county.name, found.numbers, found.unsettled) == ("Travis", {"commissioner": 2, "jp": 5}, {})
        assert (await county.at(TRAVIS, ("401A",))).numbers == {"commissioner": 4, "jp": 4}
        assert upstream.count("traviscountytx") == 3  # its services, the one with the list, and the list
        assert (await county.at(TRAVIS, ("0312",))).numbers == {"commissioner": 1, "jp": 2}
        assert upstream.count("traviscountytx") == 3
        assert (await county.at(HARRIS, ("0890",))).numbers == {"commissioner": 1, "jp": 1}  # numbers, not "P01"
        assert await county.at(ANDERSON, ("0001",)) is None and await county.at(TRAVIS, ()) is None
        assert upstream.count("services.arcgis.com") == 3 and upstream.count("example.test") == 0


@pytest.mark.anyio
async def test_near_a_line_only_what_both_precincts_share(tmp_path, upstream):
    async with service(tmp_path) as county:
        found = await county.at(TRAVIS, ("0600", "0601"))
    assert found.numbers == {"commissioner": 3}
    assert found.unsettled == {"jp": "The two election precincts your address could be in are in different justice of "
                                     "the peace precincts"}


@pytest.mark.anyio
@pytest.mark.parametrize("rows, why", [
    (travis_rows({**TRAVIS_LIST, "999": (1, 1)}), "isn't the precinct map's (1 only on its list, 0 only on the map), so "
                                                  "it may be another year's"),
    (travis_rows({k: v for k, v in TRAVIS_LIST.items() if k != "312"}), "(0 only on its list, 1 only on the map)"),
    (travis_rows({**TRAVIS_LIST, "300": ("P05", "J05")}), "gives precinct 300 commissioner precinct 'P05'"),
    (travis_rows() + travis_rows({"300": (3, 5)}), "has precinct 300 twice, with different numbers"),
    (travis_rows() + [{"attributes": {"Precinct": None, "Commissioner": "P01", "JPConstable": "J01"}}],
     "has a row without a precinct"),
])
async def test_a_list_that_isnt_right_is_refused_whole(tmp_path, upstream, rows, why):
    upstream.arcgis["taxmaps.traviscountytx.gov"][TRAVIS_QUERY] = rows
    async with service(tmp_path) as county:
        with pytest.raises(ValueError, match="^Travis County's list") as refused:
            await county.at(TRAVIS, ("0300",))
    assert why in str(refused.value)


@pytest.mark.anyio
async def test_a_row_listed_twice_alike_is_fine(tmp_path, upstream):
    upstream.arcgis["taxmaps.traviscountytx.gov"][TRAVIS_QUERY] = travis_rows() + travis_rows({"300": (2, 5)})
    async with service(tmp_path) as county:
        assert (await county.at(TRAVIS, ("0300",))).numbers == {"commissioner": 2, "jp": 5}


@pytest.mark.anyio
async def test_a_long_list_comes_a_page_at_a_time(tmp_path, upstream, monkeypatch):
    monkeypatch.setattr(cp, "PAGE", 4)
    async with service(tmp_path) as county:
        assert (await county.at(TRAVIS, ("0601",))).numbers == {"commissioner": 3, "jp": 4}  # on the third page
    assert upstream.count(TRAVIS_QUERY) == 3


@pytest.mark.anyio
async def test_an_error_answer_is_asked_again_after_a_few_minutes(tmp_path, upstream):
    clock = Clock()
    travis = upstream.arcgis["taxmaps.traviscountytx.gov"]
    travis[TRAVIS_QUERY] = {"error": {"code": 400, "message": "Invalid field: Commissioner", "details": []}}
    async with service(tmp_path, clock=clock) as county:
        with pytest.raises(ValueError, match="^Travis County's map server answered: Invalid field: Commissioner$"):
            await county.at(TRAVIS, ("0300",))
        travis[TRAVIS_QUERY] = travis_rows()
        with pytest.raises(ValueError):
            await county.at(TRAVIS, ("0300",))  # its answer kept a while, like any
        clock.now += Ttls().retry_after + 1
        assert (await county.at(TRAVIS, ("0300",))).numbers == {"commissioner": 2, "jp": 5}
    assert upstream.count(TRAVIS_QUERY) == 2


@pytest.mark.anyio
async def test_a_service_or_layer_that_isnt_there(tmp_path, upstream):
    folder = cp.COUNTIES[TRAVIS].table.layer.folder
    nothing = County(TRAVIS, "Travis", Table(Layer(folder, r"Precincts_(\d{4})", "FeatureServer"), "Precinct", "Commissioner"))
    no_layer = County(TRAVIS, "Travis", Table(Layer(folder, "Precincts", "FeatureServer", "Commissioners"), "Precinct",
                                              "Commissioner"))
    async with service(tmp_path, {TRAVIS: nothing}) as county:
        with pytest.raises(ValueError, match=r"has no service named like Precincts_\(\\d\{4\}\)"):
            await county.at(TRAVIS, ("0300",))
    async with service(tmp_path / "again", {TRAVIS: no_layer}) as county:
        with pytest.raises(ValueError, match="Travis County's Precincts has no layer named like Commissioners"):
            await county.at(TRAVIS, ("0300",))


@pytest.mark.anyio
async def test_a_list_without_jp_precincts(tmp_path, upstream):
    table = cp.COUNTIES[TRAVIS].table
    commissioners_only = County(TRAVIS, "Travis", Table(table.layer, table.precinct, table.commissioner))
    async with service(tmp_path, {TRAVIS: commissioners_only}) as county:
        found = await county.at(TRAVIS, ("0300",))
    assert (found.numbers, found.unsettled) == ({"commissioner": 2}, {})


@pytest.mark.anyio
async def test_a_refusal_pauses_the_counties(tmp_path, upstream):
    upstream.county_status = 403
    async with service(tmp_path) as county:
        with pytest.raises(UpstreamError):
            await county.at(TRAVIS, ("0300",))
        with pytest.raises(UpstreamError, match="paused"):
            await county.at(HARRIS, ("0890",))
    assert upstream.count("traviscountytx") == 1 and upstream.count("services.arcgis.com") == 0


# -- counties' maps of their commissioner and JP precincts -----------------------------------------


@pytest.mark.anyio
async def test_a_precinct_inside_one_of_each(tmp_path, upstream):
    serve_maps(upstream,
               [area("COMM", "3", 2000, 2000, 2000, 2000), area("COMM", "1", -3000, 2000, 5000, 2000)],
               [area("JP", 4, 370, 370, 370, 370)])  # its edge 30 m inside the precinct's: still settled
    async with service(tmp_path, {TRAVIS: MAPS}) as county:
        found = await county.at(TRAVIS, ("0300",))
        assert (found.county.method, found.numbers, found.unsettled) == ("maps", {"commissioner": 3, "jp": 4}, {})
        asked = len(upstream.calls)
        await county.at(TRAVIS, ("0300",))
    assert len(upstream.calls) == asked


@pytest.mark.anyio
async def test_a_precinct_across_two_or_outside_them_is_unsettled(tmp_path, upstream):
    serve_maps(upstream,
               [area("COMM", 1, 2000, 2000, 0, 2000), area("COMM", 2, 0, 2000, 2000, 2000)],  # split down the middle
               [area("JP", 1, 2000, 2000, 2000, -300)])  # only its southern 100 m
    async with service(tmp_path, {TRAVIS: MAPS}) as county:
        found = await county.at(TRAVIS, ("0300",))
    assert found.numbers == {}
    assert found.unsettled == {
        "commissioner": "Your election precinct isn't wholly inside one of Travis County's commissioner precincts on its map",
        "jp": "Your election precinct isn't wholly inside one of Travis County's justice of the peace precincts on its map",
    }


@pytest.mark.anyio
async def test_a_precinct_too_small_for_the_maps(tmp_path, upstream):
    serve_maps(upstream, [area("COMM", 3, 2000, 2000, 2000, 2000)], [area("JP", 4, 2000, 2000, 2000, 2000)])
    async with service(tmp_path, {TRAVIS: MAPS}) as county:
        async def nowhere(*args):
            return []

        county.precincts.interior = nowhere
        found = await county.at(TRAVIS, ("0300",))
    assert found.unsettled["jp"] == ("Your election precinct is too small to place on Travis County's map of its justice "
                                     "of the peace precincts")


@pytest.mark.anyio
@pytest.mark.parametrize("feature, why", [
    (area("COMM", "9", 2000, 2000, 2000, 2000), "has precinct '9'"),
    ({"attributes": {"COMM": 2}, "geometry": None}, "has precinct 2 without a shape"),
])
async def test_a_map_that_isnt_right_is_refused_whole(tmp_path, upstream, feature, why):
    serve_maps(upstream, [area("COMM", 3, 2000, 2000, 2000, 2000), feature], [])
    async with service(tmp_path, {TRAVIS: MAPS}) as county:
        with pytest.raises(ValueError, match=f"^Travis County's map of its commissioner precincts {why}"):
            await county.at(TRAVIS, ("0300",))


# -- through the ballot and Settings ---------------------------------------------------------------


def test_a_repeat_lookup_asks_the_county_nothing(client, upstream):
    first = get_ballot(client)
    assert (first["districts"]["commissioner"], first["districts"]["jp"]) == (2, 5)
    assert last_use(client, cp.SOURCE)["status"] == "used" and last_use(client, cp.SOURCE)["calls"] == 3
    again = get_ballot(client)
    assert again["districts"] == first["districts"] and again["meta"]["external_calls"] == 0
    assert last_use(client, cp.SOURCE)["calls"] == 0 and upstream.count("traviscountytx") == 3


def test_without_election_precincts_the_county_isnt_asked(client, upstream):
    client.put("/api/sources/election_precincts", json={"enabled": False})
    d = get_ballot(client)["districts"]
    assert d["precinct_sources"] == {"jp": "ballotpedia", "constable": "ballotpedia"}
    assert upstream.count("traviscountytx") == 0 and last_use(client, cp.SOURCE)["status"] == "off"


def test_a_county_that_cant_be_read_is_a_note(client, upstream):
    upstream.down.add("taxmaps.traviscountytx.gov")
    ballot = get_ballot(client)
    assert ("Couldn't read Travis County's records of its election precincts, so they don't give your commissioner and "
            "JP precincts this time.") in ballot["notes"]
    assert ballot["districts"]["precinct_sources"]["jp"] == "ballotpedia" and ballot["districts"]["county_source"] is None
    assert last_use(client, cp.SOURCE)["status"] == "error"


def test_maps_on_the_ballot(client, upstream, monkeypatch):
    monkeypatch.setitem(cp.COUNTIES, TRAVIS, MAPS)
    serve_maps(upstream, [area("COMM", 2, 2000, 2000, 2000, 2000)],
               [area("JP", 1, 2000, 2000, 0, 2000), area("JP", 5, 0, 2000, 2000, 2000)])
    client.put("/api/sources/ballotpedia", json={"enabled": False})
    ballot = get_ballot(client)
    d = ballot["districts"]
    assert (d["commissioner"], d["jp"], d["county_source"]) == (2, None, {"county": "Travis", "method": "maps"})
    assert d["precinct_sources"] == {"commissioner": "county"}
    assert ("Your election precinct isn't wholly inside one of Travis County's justice of the peace precincts on its map, "
            "so VoteBot doesn't guess your justice of the peace precinct; it's on your voter registration certificate."
            ) in ballot["notes"]
    assert "precinct" in [s["id"] for s in ballot["maybe"]]  # the JP and constable races wait for the voter


def test_settings_refreshes_and_clears_the_countys_records(client, upstream):
    get_ballot(client)
    row = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == cp.SOURCE)
    assert row["cache"]["entries"] == 3 and row["notice"] is None
    refreshed = client.post(f"/api/sources/{cp.SOURCE}/refresh").json()["message"]
    assert refreshed == "Refreshed 3 cached responses." and upstream.count("traviscountytx") == 6
    assert client.post(f"/api/sources/{cp.SOURCE}/clear").json()["message"] == "Cleared 3 cached responses."
    upstream.county_status = 429
    get_ballot(client)
    row = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == cp.SOURCE)
    assert row["notice"].startswith("Paused until ") and "after a county's map server refused a request" in row["notice"]
