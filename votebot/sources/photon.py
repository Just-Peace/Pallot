"""Address suggestions as the voter types, from Photon (photon.komoot.io, OpenStreetMap data).

Nominatim's usage policy forbids search-as-you-type, so suggestions come from Photon,
which is built for it and asks only for reasonable use. Requests go through HttpCache like
every other source (30 days, a pause after a refusal), so the same text is sent once.

OpenStreetMap knows the house numbers of some Texas addresses and only the street of most,
and Photon ranks shops and museums by their names. So a result counts only if its street
matches what was typed. A house with the typed number becomes a full address; anything
else on a matching street suggests that street with the typed number, and without a ZIP,
which can change along a street.
"""

from __future__ import annotations

import re
from typing import Any

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec
from ..models import AddressSuggestion

SOURCE = "photon"
URL = "https://photon.komoot.io/api/"
DESCRIPTION = (
    "Suggests addresses as you type in the address box, from Photon (OpenStreetMap data). "
    "What you type is sent from the 5th character on."
)
REFUSALS = (403, 429)  # answers that pause Photon for Ttls.suggest_backoff
TEXAS_BBOX = "-106.65,25.84,-93.51,36.50"
MIN_LENGTH = 5
MAX_SUGGESTIONS = 5

# "1100 Congress Ave": a house number, then at least three characters of the street.
_ADDRESS = re.compile(r"^(\d+[a-z]?)\s+(\S.{2,})$")
# Words that don't tell streets apart: suffixes, directions, the state.
_GENERIC = frozenset({
    "st", "street", "ave", "av", "avenue", "rd", "road", "dr", "drive", "ln", "lane", "blvd", "boulevard", "ct", "court",
    "cir", "circle", "pl", "place", "pkwy", "parkway", "hwy", "highway", "fwy", "freeway", "expy", "expressway", "trl",
    "trail", "way", "loop", "ter", "terrace", "cv", "cove", "sq", "square", "xing", "crossing", "bnd", "bend", "run",
    "n", "s", "e", "w", "ne", "nw", "se", "sw", "north", "south", "east", "west", "northeast", "northwest", "southeast",
    "southwest", "tx", "texas", "usa", "us", "and", "the", "of", "apt", "unit", "ste", "suite",
})
# Paths that carry a street's name but aren't where anyone lives.
_NOT_STREETS = frozenset({"footway", "cycleway", "path", "steps", "bridleway", "track", "construction", "proposed", "platform"})


def normalize(text: str) -> str:
    """What's sent and cached: lowercase, single spaces, no trailing commas."""
    return " ".join(text.split()).lower().rstrip(" ,.")


def wanted(text: str) -> bool:
    """Whether ``text`` looks enough like the start of an address to be worth asking about."""
    return len(text) >= MIN_LENGTH and bool(_ADDRESS.match(text))


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _significant(text: str) -> list[str]:
    words = _words(text)
    return [w for w in words if w not in _GENERIC and not re.fullmatch(r"\d{5}", w)] or words


def _street_matches(street: str, typed: list[str], city: str) -> bool:
    """A typed word (the last may be half typed) starts a word of the street's name. Words
    that name the result's city don't count, so "austin" alone doesn't match Austin Avenue
    in Austin."""
    names = _significant(street)
    city_words = set(_words(city))
    return any(
        name.startswith(word) for word in typed if len(word) >= 2 and word not in city_words for name in names
    )


def suggestions(features: list[dict[str, Any]], text: str) -> list[AddressSuggestion]:
    """Photon's features as addresses for what was typed (``text``, normalized)."""
    found = _ADDRESS.match(text)
    if not found:
        return []
    number, rest = found.groups()
    typed = [w for w in _words(rest) if w not in _GENERIC and not re.fullmatch(r"\d{5}", w)]
    houses: list[tuple[str, AddressSuggestion]] = []  # (street and city, suggestion)
    streets: list[tuple[str, AddressSuggestion]] = []
    for feature in features:
        p = feature.get("properties") or {}
        if p.get("countrycode") != "US" or p.get("state") != "Texas":
            continue
        if p.get("type") == "house":
            street = p.get("street") or ""
        elif p.get("type") == "street" and p.get("osm_value") not in _NOT_STREETS:
            street = p.get("name") or ""
        else:
            continue
        city, postcode = p.get("city") or "", p.get("postcode") or ""
        if not street or not (city or postcode) or not _street_matches(street, typed, city):
            continue
        exact = p.get("type") == "house" and (p.get("housenumber") or "").lower() == number
        state = f"TX {postcode}" if postcode and (exact or not city) else "TX"
        label = f"{number.upper()} {street}, {city + ', ' if city else ''}{state}"
        suggestion = AddressSuggestion(label=label, street_only=not exact)
        (houses if exact else streets).append((f"{street}|{city or postcode}".lower(), suggestion))
    seen: set[str] = set()
    unique = []
    for place, suggestion in houses + streets:  # a street is left out once the house itself is in
        if place not in seen:
            seen.add(place)
            unique.append(suggestion)
    return unique[:MAX_SUGGESTIONS]


class Photon:
    def __init__(self, cache: HttpCache, ttl: Ttls):
        self.cache = cache
        self.ttl = ttl
        cache.pause_on(SOURCE, REFUSALS, ttl.suggest_backoff)

    def paused_until(self) -> float | None:
        return self.cache.paused_until(SOURCE)

    async def suggest(self, text: str) -> list[AddressSuggestion]:
        """Up to five addresses for ``text``; nothing is sent unless it looks like the start
        of one. Raises UpstreamError if Photon can't be asked and nothing is cached."""
        text = normalize(text)
        if not wanted(text):
            return []
        spec = RequestSpec("GET", URL, params={"q": text, "limit": "10", "lang": "en", "bbox": TEXAS_BBOX})
        got = await self.cache.get_json(
            SOURCE, spec, ttl=self.ttl.suggest, empty_ttl=self.ttl.geocode_miss, empty_at=("features",)
        )
        return suggestions((got.value or {}).get("features") or [], text)
