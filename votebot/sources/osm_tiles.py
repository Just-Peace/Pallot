"""The street map under your districts' outlines: OpenStreetMap's tiles, through VoteBot.

The browser asks VoteBot for a tile (GET /api/tiles/{z}/{x}/{y}.png) and VoteBot asks
tile.openstreetmap.org, keeping each tile for 7 days. That's what OSM's tile usage policy
asks of a proxy: a User-Agent that names VoteBot (Config.user_agent), tiles kept at least 7
days, and only the tiles someone is looking at. A prefetch or a bulk re-download is
forbidden, so the source has Clear in Settings but no Refresh. Only tiles over Texas are
asked for, so VoteBot can't be used as a tile proxy for anywhere else.
"""

from __future__ import annotations

import math

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec

SOURCE = "osm_tiles"
DESCRIPTION = (
    "The street map under your districts' outlines, from OpenStreetMap. The server asks for the map tiles of the "
    "area you look at, which shows roughly where your address is, and keeps each one for 7 days."
)
URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
REFUSALS = (403, 418, 429)  # answers that pause the tiles for Ttls.tiles_backoff
MIN_ZOOM = 5
MAX_ZOOM = 18
TEXAS = (-109.0, 23.5, -91.0, 38.5)  # lon/lat: the state and 2 degrees around it, so its edges have streets


def _lon(x: float, z: int) -> float:
    return x / 2**z * 360 - 180


def _lat(y: float, z: int) -> float:
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2**z))))


def wanted(z: int, x: int, y: int) -> bool:
    """A real tile at a zoom the map allows, over Texas."""
    if not MIN_ZOOM <= z <= MAX_ZOOM or not (0 <= x < 2**z and 0 <= y < 2**z):
        return False
    west, south, east, north = TEXAS
    return _lon(x + 1, z) > west and _lon(x, z) < east and _lat(y + 1, z) < north and _lat(y, z) > south


class Tiles:
    def __init__(self, cache: HttpCache, ttl: Ttls):
        self.cache = cache
        self.ttl = ttl
        cache.pause_on(SOURCE, REFUSALS, ttl.tiles_backoff)

    async def tile(self, z: int, x: int, y: int) -> bytes:
        """The PNG of one tile; UpstreamError when it can't be had and nothing is cached."""
        got = await self.cache.get_bytes(SOURCE, RequestSpec("GET", URL.format(z=z, x=x, y=y)), ttl=self.ttl.tiles)
        return got.value
