"""What a registry entry is (Bundle), and what its builder is given (Context) and raises (BundleError)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Mapping

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
    """A source's answers that come with Pallot. ``source`` is the HttpCache source the answers are
    kept under. ``name`` (the source's by default) is the bundle's: its data file (data/<name>.json),
    its key in meta.json and ``--only``, and the Ttls field of its bundle lifetime (<name>_bundle).
    ``build`` makes the requests a lookup would make through the context's cache, raising
    BundleError unless every one succeeded, and returns counts for meta.json and the summary (e.g.
    {"races": 39}). ``cadence`` is how often a refresh is worth it (``--due``). ``lifetime``, for a
    source whose answers last differently, picks each one's. ``include`` picks the requests that
    belong in this bundle, when a source is split over several; ``keep`` leaves out answers a
    lookup should ask live (e.g. an empty one, kept briefly)."""

    source: str
    build: Callable[[Context], Awaitable[Mapping[str, int]]]
    cadence: Cadence
    lifetime: Callable[[Ttls, RequestSpec], float] | None = None
    name: str = ""
    include: Callable[[RequestSpec], bool] | None = None
    keep: Callable[[Any], bool] | None = None

    def __post_init__(self) -> None:
        if not self.name:
            object.__setattr__(self, "name", self.source)

    def ttl(self, ttl: Ttls, spec: RequestSpec) -> float:
        return self.lifetime(ttl, spec) if self.lifetime else getattr(ttl, f"{self.name}_bundle")

    def wants(self, spec: RequestSpec, value: Any) -> bool:
        """Whether this answer belongs in the bundle."""
        return (self.include is None or self.include(spec)) and (self.keep is None or self.keep(value))
