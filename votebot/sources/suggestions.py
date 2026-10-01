"""Address suggestions as the voter types, from Ballotpedia's address search (Esri data).

The endpoint behind Ballotpedia's own sample-ballot widget: unofficial, answers only
requests that carry Ballotpedia's origin header, and for personal use. Requests go through
HttpCache like every other source (30 days, a pause after a refusal), so the same text is
sent once.

It searches the whole US and answers five addresses at most, so "tx " goes in front of what
was typed (on the end, the half-typed last word would no longer count as the start of one),
and anything outside Texas is left out. It only knows addresses, so text without a house
number isn't sent.
"""

from __future__ import annotations

import re
from typing import Any

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec
from ..models import AddressSuggestion
from .ballotpedia import ORIGIN

SOURCE = "suggestions"
URL = "https://api4.ballotpedia.org/address_autocomplete"
DESCRIPTION = (
    "Suggests Texas addresses as you type in the address box, from Ballotpedia's address search (unofficial "
    "endpoint, personal use). What you type is sent once it's a house number and a few letters of the street."
)
REFUSALS = (401, 403, 429)  # answers that pause suggestions for Ttls.suggest_backoff
MIN_LENGTH = 5
MAX_SUGGESTIONS = 5

# "1100 Congress Ave": a house number, then at least three characters of the street.
_ADDRESS = re.compile(r"^(\d+[a-z]?)\s+(\S.{2,})$")
# "1100 Congress Ave, Austin, TX, 78701, USA"
_TEXAS = re.compile(r"^(?P<place>.+?), TX(?:, (?P<zip>\d{5}))?(?:, USA)?$")


def normalize(text: str) -> str:
    """What's cached: lowercase, single spaces, no trailing commas."""
    return " ".join(text.split()).lower().rstrip(" ,.")


def wanted(text: str) -> bool:
    """Whether ``text`` looks enough like the start of an address to be worth asking about."""
    return len(text) >= MIN_LENGTH and bool(_ADDRESS.match(text))


def query(text: str) -> str:
    """What's sent for ``text`` (normalized): "tx " in front, unless it already names Texas."""
    return text if {"tx", "texas"} & set(re.findall(r"[a-z]+", text)) else f"tx {text}"


def parse(results: list[dict[str, Any]]) -> list[AddressSuggestion]:
    """The Texas addresses among Ballotpedia's results, as "1100 Congress Ave, Austin, TX 78701"."""
    found = []
    for result in results:
        texas = _TEXAS.match((result.get("Text") or "").strip())
        if texas:
            label = f"{texas['place']}, TX {texas['zip']}" if texas["zip"] else f"{texas['place']}, TX"
            found.append(AddressSuggestion(label=label))
    return found[:MAX_SUGGESTIONS]


class Suggestions:
    def __init__(self, cache: HttpCache, ttl: Ttls):
        self.cache = cache
        self.ttl = ttl
        cache.pause_on(SOURCE, REFUSALS, ttl.suggest_backoff)

    async def suggest(self, text: str) -> list[AddressSuggestion]:
        """Up to five addresses for ``text``; nothing is sent unless it looks like the start
        of one. Raises UpstreamError if Ballotpedia can't be asked and nothing is cached."""
        text = normalize(text)
        if not wanted(text):
            return []
        spec = RequestSpec(
            "GET", URL, params={"location": query(text)}, headers={"Origin": ORIGIN, "Accept": "application/json"}
        )
        got = await self.cache.get_json(
            SOURCE, spec, ttl=self.ttl.suggest, empty_ttl=self.ttl.geocode_miss, empty_at=("data", "Results")
        )
        return parse(((got.value or {}).get("data") or {}).get("Results") or [])
