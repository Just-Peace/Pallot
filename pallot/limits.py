"""How often one client may make Pallot ask outside sources: a token bucket per client address for
each kind of request that can (a ballot, an address suggestion, the map's outlines, a street map
tile). The client is uvicorn's ``request.client``, which reads X-Forwarded-For only from the
proxies PALLOT_TRUSTED_PROXIES names. Loopback clients (the machine Pallot runs on) aren't limited."""

from __future__ import annotations

import ipaddress
import math
import re
import time
from dataclasses import dataclass, field
from typing import Callable

_UNITS = {"s": 1, "sec": 1, "second": 1, "m": 60, "min": 60, "minute": 60, "h": 3600, "hour": 3600,
          "d": 86400, "day": 86400}
_RATE = re.compile(r"^\s*(\d+)\s*/\s*(\d*\.?\d*)\s*([a-z]+?)s?\s*$")
MAX_CLIENTS = 10_000  # past this many buckets, the full ones (clients idle long enough) are forgotten at once


@dataclass(frozen=True)
class Rate:
    """``count`` requests a ``per`` seconds, all at once or spread out."""

    count: int
    per: float


def parse_rate(value: str) -> Rate | None:
    """"30/hour", "600/10min", "5/30s" -> a Rate; "0" or "off" -> None (no limit). Raises ValueError
    on anything else, so a mistyped limit stops Pallot from starting rather than turning it off."""
    text = value.strip().lower()
    if text in ("0", "off", "none"):
        return None
    found = _RATE.match(text)
    if not found or found[3] not in _UNITS:
        raise ValueError(f"{value!r} isn't a rate like 30/hour or 600/10min")
    count, per = int(found[1]), float(found[2] or 1) * _UNITS[found[3]]
    if count == 0:
        return None
    if per <= 0:
        raise ValueError(f"{value!r} isn't a rate like 30/hour or 600/10min")
    return Rate(count, per)


@dataclass
class _Bucket:
    tokens: float
    at: float


@dataclass
class Limiter:
    """One budget, a token bucket per client: ``rate.count`` tokens at most, refilled over ``rate.per``.
    A full bucket is forgotten within another ``rate.per``, so a client's address is held in memory
    only while it counts."""

    rate: Rate
    clock: Callable[[], float] = time.monotonic
    buckets: dict[str, _Bucket] = field(default_factory=dict)
    swept: float | None = None

    def take(self, client: str) -> float:
        """Spend one of ``client``'s tokens: 0 when there was one, otherwise how many seconds
        until there is (nothing spent)."""
        now = self.clock()
        refill = self.rate.count / self.rate.per
        if self.swept is None or now - self.swept >= self.rate.per or len(self.buckets) >= MAX_CLIENTS:
            self._forget_idle(now, refill)
            self.swept = now
        bucket = self.buckets.get(client)
        if bucket is None:
            bucket = self.buckets[client] = _Bucket(float(self.rate.count), now)
        bucket.tokens = min(self.rate.count, bucket.tokens + (now - bucket.at) * refill)
        bucket.at = now
        if bucket.tokens >= 1:
            bucket.tokens -= 1
            return 0.0
        return (1 - bucket.tokens) / refill

    def _forget_idle(self, now: float, refill: float) -> None:
        """Drop the buckets that have filled up again: forgetting them changes nothing."""
        self.buckets = {
            client: bucket for client, bucket in self.buckets.items()
            if bucket.tokens + (now - bucket.at) * refill < self.rate.count
        }


@dataclass(frozen=True)
class RateLimits:
    """Each budget's rate, None for no limit. Set with PALLOT_LIMIT_<NAME>."""

    ballot: Rate | None = Rate(30, 3600)
    suggest: Rate | None = Rate(600, 3600)
    outlines: Rate | None = Rate(60, 3600)
    tiles: Rate | None = Rate(2000, 3600)


def budget(method: str, path: str) -> str | None:
    """Which budget a request spends, or None for one that never asks outside sources."""
    if path == "/api/ballot" and method == "POST":
        return "ballot"
    if path == "/api/suggest":
        return "suggest"
    if path == "/api/district-outlines":
        return "outlines"
    if path.startswith("/api/tiles/"):
        return "tiles"
    return None


def is_loopback(host: str | None) -> bool:
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


class ClientLimits:
    """Every budget's limiter, made once per server."""

    def __init__(self, limits: RateLimits, clock: Callable[[], float] = time.monotonic):
        self.limiters = {
            name: Limiter(rate, clock) for name in ("ballot", "suggest", "outlines", "tiles")
            if (rate := getattr(limits, name)) is not None
        }

    def wait(self, method: str, path: str, client: str | None) -> int:
        """Seconds the client must wait before this request (0: go ahead, a token spent)."""
        limiter = self.limiters.get(budget(method, path) or "")
        if limiter is None or is_loopback(client):
            return 0
        return math.ceil(limiter.take(client or ""))
