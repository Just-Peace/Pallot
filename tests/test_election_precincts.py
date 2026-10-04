"""The election precinct, from the Texas Legislative Council's precinct map (made up in conftest):
the projection, the portal's index, the lookup, the outline, and how the map is downloaded and
kept; then through the ballot and Settings."""

from __future__ import annotations

import asyncio
import contextlib
import io
import threading
import types
import zipfile
from pathlib import Path

import httpx
import pytest
import respx

from pallot.config import Ttls
from pallot.http_cache import HttpCache, UpstreamError
from pallot.sources import election_precincts as ep
from pallot.sources.election_precincts import ElectionPrecincts, Lambert, StillDownloading, display_name, read_prj

from .conftest import (
    ANDERSON, HARRIS, HOLE, LINE, OVERLAP, PRJ, PROJECTION, TRAVIS, TWO_PIECES, census_points, election_precincts_zip,
    get_ballot, last_use, load, middle, nudge, precincts_index, precincts_zip,
)

LABEL = "2026 Primary Election Voting Precincts"
US_FOOT = 0.3048006096012192


@contextlib.asynccontextmanager
async def service(tmp_path: Path, **options):
    async with httpx.AsyncClient() as client:
        cache = HttpCache(tmp_path / "cache.sqlite3", client)
        precincts = ElectionPrecincts(cache, Ttls(), tmp_path / "election_precincts", **options)
        try:
            yield precincts
        finally:
            await precincts.aclose()
            cache.close()


async def settled(precincts: ElectionPrecincts) -> None:
    """Wait for a download started in the background."""
    while precincts.busy:
        await asyncio.sleep(0.01)


def newer_map(size: int, **fields) -> dict:
    """The 2026 general election's map, as the portal would list it after that election."""
    return {
        "name": "Precincts26G.zip", "description": "2026 General Election Voting Precincts Shapefile", "format": "SHP",
        "url": "https://data.capitol.texas.gov/dataset/d04c72b9/resource/9f0e/download/precincts26g.zip",
        "created": "2027-01-27T21:00:00.000000", "last_modified": "2027-01-27T21:00:00.000000", "size": size, **fields,
    }


def zips(upstream) -> int:
    return upstream.count("download/precincts")


def cut_short(zipped: bytes) -> bytes:
    """The map with its .shp cut off halfway."""
    with zipfile.ZipFile(io.BytesIO(zipped)) as source:
        files = {name: source.read(name) for name in source.namelist()}
    files["Precincts26P.shp"] = files["Precincts26P.shp"][:len(files["Precincts26P.shp"]) // 2]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def deflate64(zipped: bytes) -> bytes:
    """The map with its .shp marked as Deflate64, a compression zipfile can't unpack."""
    data, name = bytearray(zipped), b"Precincts26P.shp"
    with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
        local = archive.getinfo(name.decode()).header_offset
    data[local + 8:local + 10] = (9).to_bytes(2, "little")
    central = data.find(b"PK\x01\x02")
    while data[central + 46:central + 46 + len(name)] != name:
        central = data.find(b"PK\x01\x02", central + 4)
    data[central + 10:central + 12] = (9).to_bytes(2, "little")
    return bytes(data)


# -- the projection ---------------------------------------------------------------------------


def test_the_maps_projection_is_read_from_its_prj():
    assert read_prj(PRJ) == Lambert(
        a=6378137.0, inverse_flattening=298.257222101, false_easting=1_000_000.0, false_northing=1_000_000.0,
        central_meridian=-100.0, parallel_1=27.41666666666667, parallel_2=34.91666666666666,
        origin_latitude=31.16666666666667,
    )
    assert PROJECTION.project(31.16666666666667, -100.0) == pytest.approx((1_000_000.0, 1_000_000.0))


def test_the_projection_matches_epsgs_worked_example():
    """EPSG Guidance Note 7-2's example for method 9802 (Texas South Central, NAD27, in US feet)."""
    texas_south_central = Lambert(
        a=6378206.4, inverse_flattening=294.97869821, false_easting=2_000_000 * US_FOOT, false_northing=0.0,
        central_meridian=-99.0, parallel_1=28 + 23 / 60, parallel_2=30 + 17 / 60, origin_latitude=27 + 50 / 60,
    )
    x, y = texas_south_central.project(28.5, -96.0)
    assert (x / US_FOOT, y / US_FOOT) == pytest.approx((2963503.91, 254759.80), abs=0.01)
    assert texas_south_central.unproject(x, y) == pytest.approx((-96.0, 28.5), abs=1e-9)
    capitol = census_points("capitol")[0]
    assert PROJECTION.unproject(*PROJECTION.project(*capitol)) == pytest.approx(capitol[::-1], abs=1e-9)


@pytest.mark.parametrize("change", [
    ('PROJECTION["Lambert_Conformal_Conic"]', 'PROJECTION["Transverse_Mercator"]'),
    ('UNIT["Meter",1.0]', 'UNIT["Foot_US",0.3048006096012192]'),
    ('PARAMETER["Standard_Parallel_2",34.91666666666666],', ""),
    ('PRIMEM["Greenwich",0.0]', 'PRIMEM["Paris",2.337229166666667]'),
])
def test_another_projection_is_refused(change):
    with pytest.raises(ValueError):
        read_prj(PRJ.replace(*change))


# -- the portal's index -----------------------------------------------------------------------


def test_display_names():
    assert [display_name(code) for code in ("0300", "0000", "101A", "03-3", "01CR")] == ["300", "0", "101A", "03-3", "01CR"]


def test_the_newest_map_is_the_latest_election():
    index = load("election_precincts_index.json")
    found = ep.newest(index)
    assert (found.name, found.label, found.primary, found.size) == ("Precincts26P.zip", LABEL, True, 45497861)
    assert found.url.startswith("https://data.capitol.texas.gov/") and found.url.endswith("/precincts26p.zip")

    index["result"]["resources"].append(newer_map(1000))
    later = ep.newest(index)
    assert (later.name, later.label, later.primary) == ("Precincts26G.zip", "2026 General Election Voting Precincts", False)
    assert later.newer_than(found) and not found.newer_than(later)


def test_an_older_election_uploaded_later_or_a_link_off_the_portal_is_not_the_newest():
    index = load("election_precincts_index.json")
    index["result"]["resources"] += [
        newer_map(1000, name="Precincts24G_fixed.zip", description="2024 General Election Voting Precincts Shapefile",
                  created="2026-09-01T00:00:00"),
        newer_map(1000, url="https://example.com/precincts26g.zip"),
        newer_map(1000, url="http://data.capitol.texas.gov/download/precincts26g.zip"),
        newer_map(1000, format="XLS"),
        newer_map(0),
    ]
    assert ep.newest(index).name == "Precincts26P.zip"
    assert ep.newest({}) is None and ep.newest([]) is None


def test_the_same_map_uploaded_again_is_newer():
    found = ep.newest(load("election_precincts_index.json"))
    again = ep.Resource(**{**found.__dict__, "last_modified": "2026-08-01T00:00:00"})
    assert again.newer_than(found) and not found.newer_than(found)


# -- the lookup -------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_fixture_addresses_precincts(tmp_path, upstream):
    async with service(tmp_path) as precincts:
        capitol = await precincts.at(TRAVIS, *census_points("capitol"))
        assert capitol == ep.Answer(ep.Found("0300", "300", TRAVIS, LABEL, True), codes=("0300",))
        assert (await precincts.at(TRAVIS, *census_points("ut"))).found.name == "312"
        assert (await precincts.at(HARRIS, *census_points("harris"))).found.name == "890"
        assert (await precincts.at(ANDERSON, *census_points("capitol"))).found.name == "1"  # the county decides
        assert (await precincts.at(TRAVIS, census_points("capitol")[0], None)).found.name == "300"  # no block point
    assert upstream.count("package_show") == 1 and zips(upstream) == 1


@pytest.mark.anyio
async def test_holes_pieces_lines_and_overlaps(tmp_path, upstream):
    async with service(tmp_path) as precincts:
        async def at(address, block):
            return await precincts.at(TRAVIS, address, block)

        assert (await at(HOLE, HOLE)).found.name == "401A"  # fills 0400's hole
        assert (await at(nudge(HOLE, 600), nudge(HOLE, 700))).found.name == "400"
        assert (await at(nudge(TWO_PIECES, 1000), nudge(TWO_PIECES, 1050))).found.name == "101"  # its second piece
        assert await at(nudge(LINE, -10), nudge(LINE, 10)) == ep.Answer(between=("600", "601"), reason="between",
                                                                         codes=("0600", "0601"))
        assert await at(nudge(OVERLAP, 200), nudge(OVERLAP, 200)) == ep.Answer(reason="outside")  # in two at once
        assert await at(nudge(LINE, 5000), None) == ep.Answer(reason="outside")  # in none


@pytest.mark.anyio
async def test_an_outline_is_simplified_once_and_never_downloads(tmp_path, upstream):
    async with service(tmp_path) as precincts:
        assert await precincts.outline(TRAVIS, "0101") is None  # no map yet, and none asked for
        assert upstream.calls == []
        await precincts.at(TRAVIS, *census_points("capitol"))
        pieces = await precincts.outline(TRAVIS, "0101")
        assert len(pieces) == 2 and all(ring[0] == ring[-1] and len(ring) == 5 for ring in pieces)
        lat, lon = TWO_PIECES
        assert min(abs(x - lon) + abs(y - lat) for x, y in pieces[0]) < 0.01  # lon/lat, near where it was drawn
        assert await precincts.outline(TRAVIS, "0101") is pieces
        assert len(await precincts.outline(TRAVIS, "0400")) == 2  # the hole too
        assert await precincts.outline(TRAVIS, "9999") is None and await precincts.outline(HARRIS, "0300") is None


def test_interior_points_stay_inside_and_away_from_the_edges():
    square = [(0, 0), (0, 800), (800, 800), (800, 0), (0, 0)]
    points = ep.interior_points([square], 50)
    assert 1 <= len(points) <= 16 and all(50 <= x <= 750 and 50 <= y <= 750 for x, y in points)
    hole = [(300, 300), (500, 300), (500, 500), (300, 500), (300, 300)]
    assert all(not (250 < x < 550 and 250 < y < 550) for x, y in ep.interior_points([square, hole], 50))
    assert ep.interior_points([[(0, 0), (0, 80), (80, 80), (80, 0), (0, 0)]], 50) == []  # too small for any
    assert ep.interior_points([], 50) == []


def test_a_narrow_precinct_gets_a_finer_grid():
    """Two strips 160 m wide in an L: no point of the 9×9 grid is in one, so the 27×27 grid's are taken."""
    corner = [(0, 0), (2970, 0), (2970, 160), (160, 160), (160, 2970), (0, 2970), (0, 0)]
    points = ep.interior_points([corner], 50)
    assert points and all(x >= 50 and y >= 50 and (x <= 110 or y <= 110) for x, y in points)


@pytest.mark.anyio
async def test_a_countys_codes_and_points_inside_a_precinct(tmp_path, upstream):
    async with service(tmp_path) as precincts:
        await precincts.at(TRAVIS, *census_points("capitol"))
        assert await precincts.codes(TRAVIS) == {"0300", "0312", "0101", "0400", "401A", "0500", "0501", "0600", "0601"}
        assert await precincts.codes(9999) == frozenset()
        points = await precincts.interior(TRAVIS, "0300", 50)
        assert 1 <= len(points) <= 16 and await precincts.interior(TRAVIS, "0300", 50) is points  # kept
        lat, lon = middle(census_points("capitol"))
        assert all(abs(x - lon) < 0.004 and abs(y - lat) < 0.004 for x, y in points)  # lon/lat, within its 800 m square
        with pytest.raises(ValueError):
            await precincts.interior(TRAVIS, "9999", 50)
        precincts.clear()
        with pytest.raises(ValueError):
            await precincts.codes(TRAVIS)


@pytest.mark.anyio
async def test_an_outline_from_a_map_cleared_meanwhile_isnt_kept(tmp_path, upstream, monkeypatch):
    async with service(tmp_path) as precincts:
        await precincts.at(TRAVIS, *census_points("capitol"))
        simplify = ep.simplify

        def cleared_meanwhile(ring, tolerance):
            precincts.clear()  # as a Clear, or a newer map taking over, while the outline is worked out
            return simplify(ring, tolerance)

        monkeypatch.setattr(ep, "simplify", cleared_meanwhile)
        assert await precincts.outline(TRAVIS, "0300")
        monkeypatch.setattr(ep, "simplify", simplify)
        assert await precincts.outline(TRAVIS, "0300") is None


@pytest.mark.anyio
async def test_the_map_kept_is_known_while_a_thread_reads_it(tmp_path, upstream):
    async with service(tmp_path) as precincts:
        await precincts.at(TRAVIS, *census_points("capitol"))
        with precincts._lock:  # as while a lookup reads the map in its thread
            assert await asyncio.wait_for(asyncio.to_thread(precincts.stored), 1)


# -- downloading ------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_map_is_downloaded_once_and_kept_after_a_restart(tmp_path, upstream):
    async with service(tmp_path) as precincts:
        await precincts.at(TRAVIS, *census_points("capitol"))
        assert precincts.stored().resource.label == LABEL and precincts.downloaded_at()
        files = sorted(p.suffix for p in (tmp_path / "election_precincts").iterdir())
        assert files == [".dbf", ".json", ".shp", ".shx"] and precincts.size() > len(election_precincts_zip())
    async with service(tmp_path) as restarted:
        assert (await restarted.at(TRAVIS, *census_points("capitol"))).found.name == "300"
    assert upstream.count("package_show") == 1 and zips(upstream) == 1


@pytest.mark.anyio
async def test_the_first_lookup_goes_on_while_the_map_downloads(tmp_path, upstream):
    async with service(tmp_path, first_wait=0) as precincts:
        with pytest.raises(StillDownloading) as waiting:
            await precincts.at(TRAVIS, *census_points("capitol"))
        assert waiting.value.size == len(election_precincts_zip()) and precincts.busy
        await settled(precincts)
        assert (await precincts.at(TRAVIS, *census_points("capitol"))).found.name == "300"
    assert zips(upstream) == 1


@pytest.mark.anyio
async def test_one_download_for_everyone(tmp_path, upstream):
    async with service(tmp_path, first_wait=0) as precincts:
        got = await asyncio.gather(
            precincts.at(TRAVIS, *census_points("capitol")), precincts.at(TRAVIS, *census_points("ut")),
            precincts.update(), return_exceptions=True,
        )
        assert [type(g) for g in got[:2]] == [StillDownloading] * 2 and got[2].startswith("Downloaded the precinct map")
    assert zips(upstream) == 1


@pytest.mark.anyio
async def test_a_newer_map_downloads_in_the_background(tmp_path, upstream):
    async with service(tmp_path) as precincts:
        await precincts.at(TRAVIS, *census_points("capitol"))
        old = precincts.stored()
        precincts.cache.clear(ep.SOURCE)  # the week-old index expires
        upstream.precinct_index = precincts_index(len(election_precincts_zip()), newer=newer_map(len(election_precincts_zip())))
        answer = await precincts.at(TRAVIS, *census_points("capitol"))
        assert answer.found.label == LABEL  # from the map kept, meanwhile
        await settled(precincts)
        assert precincts.stored().resource.name == "Precincts26G.zip"
        assert (await precincts.at(TRAVIS, *census_points("capitol"))).found.label == "2026 General Election Voting Precincts"
        assert not old.file(precincts.folder, "shp").exists() and len(list(precincts.folder.iterdir())) == 4
        assert await precincts.update() == "The precinct map “2026 General Election Voting Precincts” is already the newest."
    assert zips(upstream) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("broken, why", [
    ("size", "larger than 1,000 bytes"),
    ("no prj", "isn't one shapefile"),
    ("lines", "a shape of type 3, not polygons"),
    ("feet", "isn't in meters"),
    ("short", "cut short"),
    ("deflate64", "couldn't be unpacked (NotImplementedError"),
])
async def test_a_newer_map_that_fails_keeps_the_old_one_and_isnt_downloaded_again(tmp_path, upstream, broken, why):
    async with service(tmp_path) as precincts:
        await precincts.at(TRAVIS, *census_points("capitol"))
        precincts.cache.clear(ep.SOURCE)
        served = {
            "size": election_precincts_zip(),
            "no prj": precincts_zip(prj=None),
            "lines": precincts_zip(shape_type=3),
            "feet": precincts_zip(prj=PRJ.replace('UNIT["Meter",1.0]', 'UNIT["Foot_US",0.3048006096012192]')),
            "short": cut_short(election_precincts_zip()),
            "deflate64": deflate64(election_precincts_zip()),
        }[broken]
        upstream.precinct_map = served
        listed = 1000 if broken == "size" else len(served)
        upstream.precinct_index = precincts_index(len(election_precincts_zip()), newer=newer_map(listed))
        for _ in range(3):
            assert (await precincts.at(TRAVIS, *census_points("capitol"))).found.label == LABEL
            await settled(precincts)
        assert why in precincts.last_error and precincts.stored().resource.name == "Precincts26P.zip"
        assert zips(upstream) == 2  # the failed map was tried once
        assert sorted(p.suffix for p in precincts.folder.iterdir()) == [".dbf", ".json", ".shp", ".shx"]
        with pytest.raises((UpstreamError, ValueError)):
            await precincts.update()  # Refresh always tries
        assert zips(upstream) == 3


@pytest.mark.anyio
async def test_with_no_map_a_failed_download_waits_before_trying_again(tmp_path, upstream):
    upstream.precinct_index = precincts_index(1000)  # the map is bigger than the portal says
    async with service(tmp_path) as precincts:
        with pytest.raises(UpstreamError, match="larger than 1,000 bytes"):
            await precincts.at(TRAVIS, *census_points("capitol"))
        with pytest.raises(UpstreamError, match="the last download failed .* Pallot tries again after"):
            await precincts.at(TRAVIS, *census_points("capitol"))
        assert zips(upstream) == 1 and list(precincts.folder.iterdir()) == []
        upstream.precinct_index = None
        precincts.cache.clear(ep.SOURCE)  # Settings' Clear also ends the wait
        assert (await precincts.at(TRAVIS, *census_points("capitol"))).found.name == "300"
    assert zips(upstream) == 2


@pytest.mark.anyio
async def test_with_no_map_one_that_cant_be_unpacked_is_a_failed_download(tmp_path, upstream):
    upstream.precinct_map = deflate64(election_precincts_zip())
    async with service(tmp_path) as precincts:
        with pytest.raises(ValueError, match="couldn't be unpacked"):
            await precincts.at(TRAVIS, *census_points("capitol"))
        with pytest.raises(UpstreamError, match="the last download failed"):
            await precincts.at(TRAVIS, *census_points("capitol"))
        assert list(precincts.folder.iterdir()) == []
    assert zips(upstream) == 1


def stalled_portal(router: respx.MockRouter) -> None:
    """The portal sends the map's first 1,000 bytes, then nothing more."""
    size = len(election_precincts_zip())

    async def stalled():
        yield election_precincts_zip()[:1000]
        await asyncio.Event().wait()

    router.get(url__regex="package_show").mock(return_value=httpx.Response(200, json=precincts_index(size)))
    router.get(url__regex="precincts26p").mock(
        return_value=httpx.Response(200, content=stalled(), headers={"content-length": str(size)}))


@pytest.mark.anyio
async def test_only_the_lookup_that_starts_the_first_download_waits_for_it(tmp_path):
    with respx.mock() as router:
        stalled_portal(router)
        async with service(tmp_path, first_wait=0) as precincts:
            with pytest.raises(StillDownloading):
                await precincts.at(TRAVIS, *census_points("capitol"))
            precincts.first_wait = 30
            with pytest.raises(StillDownloading):  # a reload meanwhile goes on at once
                await asyncio.wait_for(precincts.at(TRAVIS, *census_points("capitol")), 1)


@pytest.mark.anyio
async def test_shutting_down_mid_download_leaves_no_partial_file(tmp_path):
    with respx.mock() as router:
        stalled_portal(router)
        async with service(tmp_path, first_wait=0) as precincts:
            with pytest.raises(StillDownloading):
                await precincts.at(TRAVIS, *census_points("capitol"))
            while not list(precincts.folder.glob("*.part")):
                await asyncio.sleep(0.01)
            await precincts.aclose()
            assert list(precincts.folder.iterdir()) == [] and not precincts.busy


@pytest.mark.anyio
async def test_shutting_down_mid_unpack_finishes_the_map_and_removes_the_zip(tmp_path, upstream, monkeypatch):
    unzipping, go_on = threading.Event(), threading.Event()
    unzip = ElectionPrecincts._unzip

    def held(self, resource, part):
        unzipping.set()
        go_on.wait(5)
        unzip(self, resource, part)

    monkeypatch.setattr(ElectionPrecincts, "_unzip", held)
    async with service(tmp_path, first_wait=0) as precincts:
        with pytest.raises(StillDownloading):
            await precincts.at(TRAVIS, *census_points("capitol"))
        await asyncio.to_thread(unzipping.wait, 5)
        await precincts.aclose()  # a thread can't be stopped, so it goes on unpacking
        go_on.set()
        for _ in range(500):
            if precincts.stored() and not list(precincts.folder.glob("*.part")):
                break
            await asyncio.sleep(0.01)
        assert sorted(p.suffix for p in precincts.folder.iterdir()) == [".dbf", ".json", ".shp", ".shx"]


# -- through the ballot and Settings ----------------------------------------------------------


def precincts_row(client) -> dict:
    return next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == ep.SOURCE)


def test_a_repeat_lookup_asks_the_portal_nothing(client, upstream):
    first = get_ballot(client)
    assert first["districts"]["election_precinct"]["name"] == "300"
    assert upstream.count("package_show") == 1 and zips(upstream) == 1
    assert last_use(client, ep.SOURCE)["status"] == "used" and last_use(client, ep.SOURCE)["calls"] == 2
    again = get_ballot(client)
    assert again["districts"]["election_precinct"] == first["districts"]["election_precinct"]
    assert again["meta"]["external_calls"] == 0 and last_use(client, ep.SOURCE)["calls"] == 0


def test_an_approximate_address_gets_no_precinct(client, upstream):
    ballot = get_ballot(client, "mopac")
    assert ballot["location"]["approximate"] and ballot["districts"]["election_precinct"] is None
    assert "Your address could only be placed approximately, so your election precinct isn't shown; it's on your " \
           "voter registration certificate." in ballot["notes"]
    assert upstream.count("package_show") == 0 and zips(upstream) == 0


def test_switched_off_the_portal_is_not_asked(client, upstream):
    client.put(f"/api/sources/{ep.SOURCE}", json={"enabled": False})
    ballot = get_ballot(client)
    assert ballot["districts"]["election_precinct"] is None and not [n for n in ballot["notes"] if "precinct map" in n]
    assert upstream.count("package_show") == 0 and last_use(client, ep.SOURCE)["status"] == "off"


def test_the_first_lookup_says_when_the_map_is_still_downloading(client, upstream):
    client.app.state.svc.election_precincts.first_wait = 0
    ballot = get_ballot(client)
    assert ballot["districts"]["election_precinct"] is None
    assert any(n.startswith("Your election precinct will show once its map has downloaded (0 MB, the first time only).")
               for n in ballot["notes"])


def test_the_portal_down_with_no_map_is_a_warning(client, upstream):
    upstream.precincts_status = 500
    ballot = get_ballot(client)
    assert ballot["districts"]["election_precinct"] is None and ballot["districts"]["sboe"] == 5
    assert "Couldn't load the Texas Legislative Council's precinct map, so your election precinct isn't shown; it's on " \
           "your voter registration certificate." in ballot["warnings"]
    assert last_use(client, ep.SOURCE)["status"] == "error"


def test_a_map_that_cant_be_unpacked_is_a_warning_not_a_failed_ballot(client, upstream):
    upstream.precinct_map = deflate64(election_precincts_zip())
    ballot = get_ballot(client)
    assert ballot["districts"]["election_precinct"] is None and ballot["races"]
    assert any(w.startswith("Couldn't load the Texas Legislative Council's precinct map") for w in ballot["warnings"])
    get_ballot(client)
    assert zips(upstream) == 1


def test_a_refusal_pauses_the_portal(client, upstream):
    upstream.precincts_status = 429
    get_ballot(client)
    get_ballot(client)
    assert upstream.count("package_show") == 1  # paused: not asked again
    row = precincts_row(client)
    assert row["notice"].startswith("Paused until") and "Texas Legislative Council's portal refused" in row["notice"]


def test_settings_shows_refreshes_and_clears_the_map(client, upstream, tmp_path):
    get_ballot(client)
    row = precincts_row(client)
    size = len(election_precincts_zip())
    kept, listed = (f["value"] for f in row["details"])
    assert kept.startswith(f"“{LABEL}”, downloaded ") and kept.endswith(" KB")
    assert listed == f"“{LABEL}” · {size / 1024:.0f} KB"
    assert f"downloads it ({size / 1024:.0f} KB)" in row["refresh_confirm"] and row["busy"] is False
    assert client.get("/api/sources").json()["total_bytes"] > size

    refreshed = client.post(f"/api/sources/{ep.SOURCE}/refresh").json()["message"]
    assert refreshed == f"Refreshed 1 cached response. The precinct map “{LABEL}” is already the newest."
    assert upstream.count("package_show") == 2 and zips(upstream) == 1

    cleared = client.post(f"/api/sources/{ep.SOURCE}/clear").json()["message"]
    assert cleared == "Cleared 1 cached response. The precinct map will be downloaded again on the next lookup."
    assert list((tmp_path / "data" / "election_precincts").iterdir()) == []
    assert precincts_row(client)["details"][0]["value"] == "downloaded on the first lookup"
    assert get_ballot(client)["districts"]["election_precinct"]["name"] == "300" and zips(upstream) == 2

    message = client.post("/api/cache/clear").json()["message"]
    assert "the SBOE map and the precinct map" in message
    assert list((tmp_path / "data" / "election_precincts").iterdir()) == []


def test_refresh_downloads_a_newer_map(client, upstream):
    get_ballot(client)
    size = len(election_precincts_zip())
    upstream.precinct_index = precincts_index(size, newer=newer_map(size))
    message = client.post(f"/api/sources/{ep.SOURCE}/refresh").json()["message"]
    assert message == ("Refreshed 1 cached response. Downloaded the precinct map “2026 General Election Voting Precincts” "
                       f"({size / 1_048_576:.1f} MB).")
    assert get_ballot(client)["districts"]["election_precinct"]["map_label"] == "2026 General Election Voting Precincts"


def test_nothing_is_cleared_while_the_map_downloads(client, upstream):
    precincts = client.app.state.svc.election_precincts
    precincts._task = types.SimpleNamespace(done=lambda: False)  # a download under way
    try:
        row = precincts_row(client)
        assert row["busy"] is True and row["notice"] == "Downloading the precinct map…"
        assert client.post(f"/api/sources/{ep.SOURCE}/clear").status_code == 409
        assert client.post(f"/api/sources/{ep.SOURCE}/refresh").status_code == 409
        assert client.post("/api/cache/clear").status_code == 409
    finally:
        precincts._task = None
