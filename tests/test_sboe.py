from __future__ import annotations

import httpx
import pytest
import respx

from votebot.sources.sboe import KML_URL, District, Polygon, SboeMap, locate, parse_zip

from .conftest import sboe_zip

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


@pytest.mark.anyio
async def test_map_is_downloaded_once_and_kept(tmp_path):
    with respx.mock() as router:
        route = router.get(KML_URL).mock(return_value=httpx.Response(200, content=sboe_zip()))
        async with httpx.AsyncClient() as client:
            first = SboeMap(tmp_path / "map.zip", client)
            assert await first.district_at(30.2747, -97.7403) == 5
            second = SboeMap(tmp_path / "map.zip", client)  # a restart
            assert await second.district_at(29.7589, -95.3632) == 4
            assert route.call_count == 1
            second.clear()
            assert not (tmp_path / "map.zip").exists()


@pytest.mark.anyio
async def test_a_broken_download_is_not_saved(tmp_path):
    with respx.mock() as router:
        router.get(KML_URL).mock(return_value=httpx.Response(200, content=b"not a zip"))
        async with httpx.AsyncClient() as client:
            sboe = SboeMap(tmp_path / "map.zip", client)
            with pytest.raises(Exception):
                await sboe.district_at(30.2747, -97.7403)
    assert not (tmp_path / "map.zip").exists()
