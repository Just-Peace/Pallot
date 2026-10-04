"""The street map's tiles: OpenStreetMap's, through Pallot (GET /api/tiles/{z}/{x}/{y}.png)."""

from __future__ import annotations

import math

import pytest

from pallot.sources import osm_tiles

from . import conftest
from .conftest import PNG, capitol_point, switch


def tile_at(z: int, lat: float, lon: float) -> tuple[int, int, int]:
    n = 2**z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return z, x, y


def get_tile(client, z: int, x: int, y: int):
    return client.get(f"/api/tiles/{z}/{x}/{y}.png")


def test_only_tiles_over_texas_at_the_maps_zooms():
    lat, lon = capitol_point()
    assert osm_tiles.wanted(*tile_at(12, lat, lon))
    assert osm_tiles.wanted(*tile_at(5, 31.0, -100.0))
    assert not osm_tiles.wanted(*tile_at(12, 27.95, -82.46))  # Tampa
    assert not osm_tiles.wanted(*tile_at(12, 40.71, -74.0))  # New York
    assert not osm_tiles.wanted(*tile_at(4, lat, lon)) and not osm_tiles.wanted(*tile_at(19, lat, lon))
    assert not osm_tiles.wanted(12, -1, 0) and not osm_tiles.wanted(12, 0, 4096)


def test_a_tile_is_asked_for_once_and_names_pallot(client, upstream):
    z, x, y = tile_at(14, *capitol_point())
    first = get_tile(client, z, x, y)
    assert first.status_code == 200 and first.content == PNG
    assert first.headers["content-type"] == "image/png" and first.headers["cache-control"] == "private, max-age=86400"
    assert get_tile(client, z, x, y).content == PNG
    assert upstream.count("tile.openstreetmap.org") == 1
    (agent,) = upstream.tile_agents  # OpenStreetMap's tile policy: a User-Agent that names the app and how to reach it
    assert agent.startswith("Pallot/") and "github.com/Just-Peace/Pallot" in agent


def test_tiles_are_not_gzipped(client, upstream, monkeypatch):
    """A PNG is compressed already: gzip would only cost time."""
    big = PNG + bytes(range(256)) * 20
    monkeypatch.setattr(conftest, "PNG", big)
    z, x, y = tile_at(14, *capitol_point())
    response = client.get(f"/api/tiles/{z}/{x}/{y}.png", headers={"Accept-Encoding": "gzip"})
    assert response.content == big and "content-encoding" not in response.headers

def test_tiles_outside_texas_are_refused_without_asking(client, upstream):
    assert get_tile(client, *tile_at(12, 40.71, -74.0)).status_code == 404
    assert get_tile(client, *tile_at(19, *capitol_point())).status_code == 404
    assert upstream.count("tile.openstreetmap.org") == 0


def test_street_map_off(client, upstream):
    switch(client, osm_tiles.SOURCE, False)
    assert client.get("/api/district-outlines", params={"hd": 49}).json()["street_map"] is False  # so the map asks for no tiles
    assert upstream.count("tile.openstreetmap.org") == 0


def test_the_outlines_say_the_street_map_is_on(client, upstream):
    assert client.get("/api/district-outlines", params={"hd": 49}).json()["street_map"] is True


@pytest.mark.parametrize("status", [403, 429])
def test_a_refusal_pauses_the_tiles(client, upstream, status):
    upstream.tiles_status = status
    tile = tile_at(12, *capitol_point())
    assert get_tile(client, *tile).status_code == 502
    assert get_tile(client, tile[0], tile[1] + 1, tile[2]).status_code == 502
    assert upstream.count("tile.openstreetmap.org") == 1  # paused: the second tile wasn't asked for
    row = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == osm_tiles.SOURCE)
    assert row["notice"].startswith("Paused until") and row["notice"].endswith(
        "after OpenStreetMap's tile server refused a request; tiles it already sent still show.")


def test_tiles_are_deleted_but_never_refreshed(client, make_app, upstream):
    get_tile(client, *tile_at(12, *capitol_point()))
    row = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == osm_tiles.SOURCE)
    assert (row["label"], row["cache"]["entries"]) == ("Street map (OpenStreetMap)", 1)
    assert make_app.cache_command("hard-refresh", osm_tiles.SOURCE) == (0, "")
    assert upstream.count("tile.openstreetmap.org") == 1
    assert make_app.cache_command("rebuild", osm_tiles.SOURCE) == (0, "Deleted 1 saved response.")
    assert upstream.count("tile.openstreetmap.org") == 1
