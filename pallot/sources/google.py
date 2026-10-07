"""Google's Geocoding API, the last place an address is looked for: only when the Census geocoder
and Nominatim both came up empty (new streets, mostly), and only with a key in PALLOT_GOOGLE_API_KEY.

Uses the current Geocoding API (v4), which takes the key in a header, so it never reaches a
RequestSpec or the cache. Google's terms allow keeping coordinates for 30 days, which is Ttls.geocode.
"""

from __future__ import annotations

from urllib.parse import quote

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec
from .census import normalize_address
from .nominatim import Point

SOURCE = "google"
URL = "https://geocode.googleapis.com/v4beta/geocode/address"
KEY_HEADER = "X-Goog-Api-Key"
KEY_SIGNUP = "https://developers.google.com/maps/documentation/geocoding/get-api-key"
REFUSALS = (403, 429)  # a key Google refuses or a quota used up: pause for Ttls.geocode_backoff
DESCRIPTION = (
    "Finds addresses the Census geocoder and OpenStreetMap can't, such as streets too new for either. Your address "
    "is sent to Google only when both of them found nothing, and only if the server has a Google Geocoding API key."
)
KEY_NOTE = (
    "No key is set, so this isn't used. Set PALLOT_GOOGLE_API_KEY to a "
    f"[Google Geocoding API key]({KEY_SIGNUP}) and restart Pallot."
)

# Granularities that name the building itself; anything coarser is an area or a street.
_EXACT = {"ROOFTOP", "RANGE_INTERPOLATED", "PREMISE", "SUB_PREMISE"}


class Google:
    def __init__(self, cache: HttpCache, ttl: Ttls, api_key: str):
        self.cache = cache
        self.ttl = ttl
        self.keyed = bool(api_key)
        cache.pause_on(SOURCE, REFUSALS, ttl.geocode_backoff)

    async def locate(self, address: str) -> Point | None:
        spec = RequestSpec(
            "GET", f"{URL}/{quote(normalize_address(address), safe='')}", params={"regionCode": "US"}
        )
        got = await self.cache.get_json(
            SOURCE, spec, ttl=self.ttl.geocode, empty_ttl=self.ttl.geocode_miss, empty_at=("results",)
        )
        results = (got.value or {}).get("results") or []
        if not results:
            return None
        hit = results[0]
        where = hit.get("location") or {}
        if "latitude" not in where or "longitude" not in where:
            return None
        return Point(
            lat=float(where["latitude"]),
            lon=float(where["longitude"]),
            label=hit.get("formattedAddress") or "",
            approximate=hit.get("granularity") not in _EXACT or bool(hit.get("partialMatch")),
        )
