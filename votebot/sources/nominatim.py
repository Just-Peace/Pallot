"""OpenStreetMap Nominatim, for addresses the Census geocoder can't match.

Usage policy: an identifying User-Agent (set on the shared client), at most one request
per second (HttpCache throttles this source), and cache the results (we do, for 30 days).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec
from .census import normalize_address

SOURCE = "nominatim"
URL = "https://nominatim.openstreetmap.org/search"

# Result types that are an area or a street rather than the address itself.
_APPROXIMATE = {
    "road", "postcode", "suburb", "neighbourhood", "quarter", "city_district", "city", "town",
    "village", "hamlet", "municipality", "county", "state",
}


@dataclass(frozen=True)
class Point:
    lat: float
    lon: float
    label: str
    approximate: bool


class Nominatim:
    def __init__(self, cache: HttpCache, ttl: Ttls):
        self.cache = cache
        self.ttl = ttl

    async def locate(self, address: str) -> Point | None:
        spec = RequestSpec(
            "GET",
            URL,
            params={"q": normalize_address(address), "format": "jsonv2", "countrycodes": "us", "limit": "1"},
        )
        got = await self.cache.get_json(SOURCE, spec, ttl=self.ttl.geocode, empty_ttl=self.ttl.geocode_miss)
        if not got.value:
            return None
        hit = got.value[0]
        return Point(
            lat=float(hit["lat"]),
            lon=float(hit["lon"]),
            label=hit.get("display_name") or "",
            approximate=hit.get("addresstype") in _APPROXIMATE,
        )
