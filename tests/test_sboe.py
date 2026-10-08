from __future__ import annotations

import contextlib
import io
import zipfile
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from pallot.config import Ttls
from pallot.http_cache import HttpCache, UpstreamError
from pallot.sources import RefreshFailed
from pallot.sources.sboe import (
    BUNDLED, FAILED_FLAG, KML_URL, SOURCE, District, Polygon, SboeMap, locate, outline, parse_zip, read_download,
    simplify,
)

from .conftest import get_ballot, sboe_zip, switch

SQUARE = [(-98.0, 30.0), (-97.0, 30.0), (-97.0, 31.0), (-98.0, 31.0), (-98.0, 30.0)]
HOLE = [(-97.6, 30.4), (-97.4, 30.4), (-97.4, 30.6), (-97.6, 30.6), (-97.6, 30.4)]


def districts():
    return [
        District(5, (Polygon(SQUARE, (HOLE,), (-98.0, 30.0, -97.0, 31.0)),)),
        District(10, (Polygon(HOLE, (), (-97.6, 30.4, -97.4, 30.6)),)),
    ]


def test_point_inside_outside_and_in_a_hole():
    assert locate(districts(), 30.2, -97.8) == 5
    assert locate(districts(), 30.5, -97.5) == 10  # inside district 5's hole, which is district 10
    assert locate(districts(), 35.0, -90.0) is None


def test_point_just_outside_a_boundary_snaps_to_the_nearest_district():
    assert locate(districts(), 30.5, -96.9995) == 5  # ~50 m east of the edge
    assert locate(districts(), 30.5, -96.99) is None  # ~1 km away


def test_parse_the_kml_zip():
    parsed = parse_zip(sboe_zip())
    assert sorted(d.number for d in parsed) == list(range(1, 16))
    assert locate(parsed, 30.2747, -97.7403) == 5  # Texas Capitol
    assert locate(parsed, 29.7589, -95.3632) == 4  # downtown Houston


CAPITOL = (30.2747, -97.7403)


@contextlib.asynccontextmanager
async def service(tmp_path: Path, bundled: Path | None = None):
    """An SboeMap on its own cache, as a restart would find it; with no map bundled unless ``bundled`` names one."""
    async with httpx.AsyncClient() as client:
        cache = HttpCache(tmp_path / "cache.sqlite3", client)
        try:
            yield SboeMap(cache, Ttls(), tmp_path / "map.zip", bundled or tmp_path / "no-bundled-map.zip")
        finally:
            cache.close()


def test_the_map_that_comes_with_pallot_is_plan_e2106():
    parsed = read_download(BUNDLED)
    assert locate(parsed, *CAPITOL) == 5 and locate(parsed, 29.7589, -95.3632) == 4


@pytest.mark.anyio
async def test_the_bundled_map_is_used_without_a_download_and_a_clear_goes_back_to_it(tmp_path):
    bundled = tmp_path / "bundled.zip"
    bundled.write_bytes(sboe_zip())
    with respx.mock() as router:
        route = router.get(KML_URL).mock(return_value=httpx.Response(200, content=sboe_zip()))
        async with service(tmp_path, bundled) as sboe:
            assert await sboe.district_at(*CAPITOL) == 5 and route.call_count == 0
            assert sboe.stale() is None and sboe.details()[0].value.startswith("plan E2106, came with Pallot · ")
            assert await sboe.refresh() == "Re-downloaded the State Board of Education map."  # a hard refresh still asks
            assert route.call_count == 1  # the same map: Settings still says it came with Pallot
            (tmp_path / "map.zip").write_bytes(zip_of(b"<kml/>"))
            assert sboe.details()[0].value.startswith("downloaded ")
            assert sboe.clear() == "Back to the State Board of Education map that came with Pallot."
            assert (tmp_path / "map.zip").read_bytes() == sboe_zip() and await sboe.district_at(*CAPITOL) == 5
    assert sorted(p.name for p in tmp_path.glob("*map.zip*")) == ["map.zip"]


def test_a_lookup_on_an_empty_data_folder_places_the_sboe_district_without_a_download(make_app, upstream, tmp_path):
    bundled = tmp_path / "bundled.zip"
    bundled.write_bytes(sboe_zip())
    with TestClient(make_app(sboe_bundled=bundled)) as client:
        assert (tmp_path / "data" / "plane2106_kml.zip").read_bytes() == sboe_zip()  # copied in at startup
        switch(client, "election_precincts", False)  # the precinct map's portal is the same host
        ballot = get_ballot(client)
    assert ballot["districts"]["sboe"] == 5 and upstream.count("data.capitol.texas.gov") == 0


def zip_of(kml: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("plane2106.kml", kml)
    return buffer.getvalue()


@pytest.mark.anyio
async def test_map_is_downloaded_once_and_kept(tmp_path):
    with respx.mock() as router:
        route = router.get(KML_URL).mock(return_value=httpx.Response(200, content=sboe_zip()))
        async with service(tmp_path) as first:
            assert await first.district_at(*CAPITOL) == 5
        async with service(tmp_path) as second:  # a restart
            assert await second.district_at(29.7589, -95.3632) == 4
            assert route.call_count == 1
            assert second.clear() == "The State Board of Education map will be downloaded again on the next lookup."
    assert list(tmp_path.glob("*map.zip*")) == []


@pytest.mark.anyio
@pytest.mark.parametrize("content, error", [
    (b"not a zip", zipfile.BadZipFile),
    (zip_of(b"<kml><Placemark>"), ValueError),  # not an XML ParseError, which the ballot wouldn't catch
], ids=["not a zip", "not KML"])
async def test_a_broken_download_is_not_saved(tmp_path, content, error):
    with respx.mock() as router:
        router.get(KML_URL).mock(return_value=httpx.Response(200, content=content))
        async with service(tmp_path) as sboe:
            with pytest.raises(error):
                await sboe.district_at(*CAPITOL)
    assert list(tmp_path.glob("*map.zip*")) == []  # neither the map nor its partial download


@pytest.mark.anyio
async def test_a_failed_download_isnt_asked_again_by_lookups_for_a_while(tmp_path):
    with respx.mock() as router:
        route = router.get(KML_URL).mock(return_value=httpx.Response(500))
        async with service(tmp_path) as sboe:
            with pytest.raises(UpstreamError):
                await sboe.district_at(*CAPITOL)
            with pytest.raises(UpstreamError, match="the last download failed \\(HTTP 500\\); Pallot tries again after"):
                await sboe.district_at(*CAPITOL)
            assert route.call_count == 1
            notice, tone = sboe.notice()
            assert tone == "warn" and notice.startswith(
                "The last download of the State Board of Education map failed (HTTP 500); lookups try again after "
            )
            sboe.clear()  # Clear in Settings lets the next lookup ask at once
            route.mock(return_value=httpx.Response(200, content=sboe_zip()))
            assert await sboe.district_at(*CAPITOL) == 5
            assert route.call_count == 2 and sboe.notice() is None


@pytest.mark.anyio
async def test_a_refusal_pauses_the_portal(tmp_path):
    with respx.mock() as router:
        route = router.get(KML_URL).mock(return_value=httpx.Response(403))
        async with service(tmp_path) as sboe:
            for _ in range(2):
                with pytest.raises(UpstreamError):
                    await sboe.district_at(*CAPITOL)
            assert route.call_count == 1
            assert sboe.cache.paused_until(SOURCE) and sboe.cache.flag_until(FAILED_FLAG) is None
            notice, tone = sboe.notice()
            assert tone == "warn" and "portal refused the State Board of Education map" in notice
            assert notice.endswith("; SBOE districts are missing until then.")
            with pytest.raises(RefreshFailed, match="\\(paused until .+\\); lookups try again after "):
                await sboe.refresh()
            assert route.call_count == 1


@pytest.mark.anyio
async def test_refresh_replaces_the_map_or_keeps_the_old_one(tmp_path):
    with respx.mock() as router:
        route = router.get(KML_URL).mock(return_value=httpx.Response(200, content=sboe_zip()))
        async with service(tmp_path) as sboe:
            assert await sboe.refresh() == "Re-downloaded the State Board of Education map."
            route.mock(return_value=httpx.Response(500))
            with pytest.raises(RefreshFailed, match="\\(HTTP 500\\); kept the old one\\.$"):
                await sboe.refresh()
            assert await sboe.district_at(*CAPITOL) == 5 and route.call_count == 2
            assert sboe.notice() == (
                "The last download of the State Board of Education map failed (HTTP 500); the map kept still shows.", "warn"
            )
            assert sboe.details()[0].value.startswith("downloaded ")


def test_simplify_drops_what_the_eye_would_not_see():
    ring = [(0.0, 0.0), (0.5, 0.0), (1.0, 0.0004), (1.0, 1.0), (0.5, 1.001), (0.0, 1.0), (0.0, 0.0)]
    assert simplify(ring, 0.0005) == [(0.0, 0.0), (1.0, 0.0004), (1.0, 1.0), (0.5, 1.001), (0.0, 1.0), (0.0, 0.0)]
    assert simplify(ring, 0.01) == [(0.0, 0.0), (1.0, 0.0004), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
    assert simplify([(1.123456, 2.0)], 0.1) == [(1.12346, 2.0)]


def test_outline_keeps_holes():
    assert outline(districts()[0], 0.0005) == [SQUARE, HOLE]


@pytest.mark.anyio
async def test_outline_of_a_district(tmp_path):
    with respx.mock() as router:
        router.get(KML_URL).mock(return_value=httpx.Response(200, content=sboe_zip()))
        async with service(tmp_path) as sboe:
            first = await sboe.outline(5, 0.0005)
            assert first == [[(-98.2, 30.0), (-97.4, 30.0), (-97.4, 30.7), (-98.2, 30.7), (-98.2, 30.0)]]
            assert await sboe.outline(5, 0.0005) is first  # simplified once
            assert await sboe.outline(16, 0.0005) is None
