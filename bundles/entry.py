"""What a registry entry is (Bundle), and what its builder is given (Context) and raises (BundleError)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Mapping

from pallot.config import DAY, Config, Ttls
from pallot.http_cache import HttpCache, RequestSpec

Cadence = Literal["daily", "weekly"]
CADENCES: dict[str, float] = {"daily": DAY, "weekly": 7 * DAY}  # seconds between refreshes worth making


class BundleError(Exception):
    """Nothing was written for a source: it couldn't be asked for everything a lookup asks."""


@dataclass(frozen=True)
class Context:
    """What a builder gets: the configuration (its keys), a throwaway cache to make the lookup's
    requests through (inside http_cache.offline()), and the day it counts as today."""

    config: Config
    cache: HttpCache
    today: Callable[[], dt.date]


@dataclass(frozen=True)
class Bundle:
    """A source whose answers come with Pallot. ``source`` is the HttpCache source the answers are
    kept under, the data file's name (data/<source>.json) and the Ttls field of their bundle
    lifetime (<source>_bundle). ``build`` makes the requests a lookup would make through the
    context's cache, raising BundleError unless every one succeeded, and returns counts for
    meta.json and the summary (e.g. {"races": 39}). ``cadence`` is how often a refresh is worth it
    (``--due``). ``lifetime``, for a source whose answers last differently, picks each one's."""

    source: str
    build: Callable[[Context], Awaitable[Mapping[str, int]]]
    cadence: Cadence
    lifetime: Callable[[Ttls, RequestSpec], float] | None = None

    def ttl(self, ttl: Ttls, spec: RequestSpec) -> float:
        return self.lifetime(ttl, spec) if self.lifetime else getattr(ttl, f"{self.source}_bundle")
