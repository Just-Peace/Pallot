"""Address suggestions as the voter types, from Google's Places Autocomplete (New), anywhere in
the US. Only with a key in PALLOT_GOOGLE_API_KEY (the Places API enabled for it), sent in a
header as the geocoding fallback's is, so it never reaches a RequestSpec or the cache.

Requests go through HttpCache like every other source (Ttls.suggest, a pause after a refusal,
and at most Config.suggest_daily_max a day, since Google bills by the request), so the same text
is sent once. Only street addresses are asked for, and only text that starts with a house number
is sent.
"""

from __future__ import annotations

import re
from typing import Any

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec
from ..models import AddressSuggestion

SOURCE = "suggestions"
URL = "https://places.googleapis.com/v1/places:autocomplete"
DESCRIPTION = "Suggests addresses as you type, from Google Maps."
MIN_LENGTH = 5
MAX_SUGGESTIONS = 5
TYPES = ["street_address", "premise", "subpremise"]  # a building's address, not a business or an area

# "1100 Congress Ave": a house number, then at least three characters of the street.
_ADDRESS = re.compile(r"^(\d+[a-z]?)\s+(\S.{2,})$")


def normalize(text: str) -> str:
    """What's cached: lowercase, single spaces, no trailing commas."""
    return " ".join(text.split()).lower().rstrip(" ,.")


def wanted(text: str) -> bool:
    """Whether ``text`` looks enough like the start of an address to be worth asking about."""
    return len(text) >= MIN_LENGTH and bool(_ADDRESS.match(text))


def request(text: str) -> RequestSpec:
    return RequestSpec("POST", URL, json={"input": text, "includedRegionCodes": ["us"], "includedPrimaryTypes": TYPES,
                                          "languageCode": "en"})


def parse(answer: dict[str, Any]) -> list[AddressSuggestion]:
    """Google's predictions as "1100 Congress Avenue, Austin, TX", without the country."""
    found = []
    for suggestion in answer.get("suggestions") or []:
        text = (((suggestion.get("placePrediction") or {}).get("text") or {}).get("text") or "").strip()
        if text:
            found.append(AddressSuggestion(label=re.sub(r",\s*USA$", "", text)))
    return found[:MAX_SUGGESTIONS]


class Suggestions:
    def __init__(self, cache: HttpCache, ttl: Ttls, api_key: str = "", daily_max: int = 0):
        self.cache = cache
        self.ttl = ttl
        self.keyed = bool(api_key)
        cache.pause_on(SOURCE, ttl.suggest_backoff, also=(401,))
        if daily_max:
            cache.cap_daily(SOURCE, daily_max)

    async def suggest(self, text: str) -> list[AddressSuggestion]:
        """Up to five addresses for ``text``; nothing is sent without a key, or unless it looks
        like the start of one. Raises UpstreamError if Google can't be asked and nothing is cached."""
        text = normalize(text)
        if not (self.keyed and wanted(text)):
            return []
        got = await self.cache.get_json(
            SOURCE, request(text), ttl=self.ttl.suggest, empty_ttl=self.ttl.geocode_miss, empty_at=("suggestions",)
        )
        return parse(got.value or {})
