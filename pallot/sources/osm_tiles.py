"""The street map around the voter's address, under their districts' outlines where Pallot has
them: OpenStreetMap's tiles, through Pallot.

The browser asks Pallot for a tile (GET /api/tiles/{z}/{x}/{y}.png) and Pallot asks
tile.openstreetmap.org, keeping each tile for 7 days. That's what OSM's tile usage policy
asks of a proxy: a User-Agent that names Pallot (Config.user_agent), tiles kept at least 7
days, and only the tiles someone is looking at. A prefetch or a bulk re-download is
forbidden, so pallot-cache never refreshes them: it only prunes them. Only tiles over the 50
states and DC are asked for, so Pallot can't be used as a tile proxy for anywhere else.
"""

from __future__ import annotations

import math

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec

SOURCE = "osm_tiles"
DESCRIPTION = (
    "The street map around your address, under your districts' outlines, from OpenStreetMap."
)
URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
MIN_ZOOM = 5
MAX_ZOOM = 18
REGIONS = (  # lon/lat: the 48 states and DC, Alaska, the Aleutians past the antimeridian, Hawaii; as in district-map.js
    (-127.0, 22.5, -64.0, 51.0),
    (-180.0, 50.0, -128.0, 72.5),
    (172.0, 50.0, 180.0, 54.0),
    (-162.0, 18.0, -154.0, 23.0),
)


def _lon(x: float, z: int) -> float:
    return x / 2**z * 360 - 180


def _lat(y: float, z: int) -> float:
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2**z))))


def wanted(z: int, x: int, y: int) -> bool:
    """A real tile at a zoom the map allows, over the 50 states or DC."""
    if not MIN_ZOOM <= z <= MAX_ZOOM or not (0 <= x < 2**z and 0 <= y < 2**z):
        return False
    return any(
        _lon(x + 1, z) > west and _lon(x, z) < east and _lat(y + 1, z) < north and _lat(y, z) > south
        for west, south, east, north in REGIONS
    )


class Tiles:
    def __init__(self, cache: HttpCache, ttl: Ttls):
        self.cache = cache
        self.ttl = ttl
        cache.pause_on(SOURCE, ttl.tiles_backoff, also=(418,))

    async def tile(self, z: int, x: int, y: int) -> bytes:
        """The PNG of one tile; UpstreamError when it can't be had and nothing is cached."""
        got = await self.cache.get_bytes(SOURCE, RequestSpec("GET", URL.format(z=z, x=x, y=y)), ttl=self.ttl.tiles)
        return got.value
