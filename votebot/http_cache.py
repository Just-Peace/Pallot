"""Persistent cache for every outbound API call.

One SQLite row per distinct request (method + URL + params + body), tagged with the
source that made it, so the Settings page can show, clear or refresh one source at a
time. A row keeps the request itself and the lifetimes it was stored with, so refresh()
can re-issue it without knowing what it was for. Decoded values also sit in a small
in-memory LRU, which matters for the 2.6 MB statewide candidate list.

Cached values are shared between callers: treat them as read-only.
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import sqlite3
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx

_SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    request TEXT NOT NULL,
    value TEXT NOT NULL,
    fetched_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    ttl REAL NOT NULL,
    empty_ttl REAL,
    empty_at TEXT NOT NULL,
    bytes INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS responses_source ON responses(source);
CREATE TABLE IF NOT EXISTS flags (
    name TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    expires_at REAL NOT NULL
);
"""


@dataclass(frozen=True)
class RequestSpec:
    method: str
    url: str
    params: dict[str, str] | None = None
    json: Any = None
    headers: dict[str, str] | None = None

    @property
    def key(self) -> str:
        """Identity of the request; headers are not part of it."""
        identity = {"method": self.method.upper(), "url": self.url, "params": self.params, "json": self.json}
        return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def dumps(self) -> str:
        return json.dumps(
            {"method": self.method, "url": self.url, "params": self.params, "json": self.json, "headers": self.headers},
            sort_keys=True,
        )

    @classmethod
    def loads(cls, text: str) -> RequestSpec:
        return cls(**json.loads(text))


@dataclass(frozen=True)
class Cached:
    value: Any
    fetched_at: float
    stale: bool = False  # the refresh failed and this is the last good copy


class UpstreamError(Exception):
    """A source could not be reached and nothing was cached to fall back on."""

    def __init__(self, source: str, message: str, status: int | None = None):
        super().__init__(f"{source}: {message}")
        self.source = source
        self.status = status


@dataclass
class CallStats:
    """What one API request cost: cache hits, external calls, data age per source."""

    external_calls: int = 0
    cache_hits: int = 0
    stale_sources: set[str] = field(default_factory=set)
    oldest: dict[str, float] = field(default_factory=dict)  # source -> oldest fetched_at used

    def used(self, source: str, fetched_at: float) -> None:
        self.oldest[source] = min(fetched_at, self.oldest.get(source, fetched_at))


_call_stats: contextvars.ContextVar[CallStats | None] = contextvars.ContextVar("votebot_call_stats", default=None)


def track_calls() -> CallStats:
    """Count cache hits and external calls made from here on (and in tasks started from here)."""
    stats = CallStats()
    _call_stats.set(stats)
    return stats


def current_calls() -> CallStats | None:
    return _call_stats.get()


@dataclass(frozen=True)
class SourceCacheStats:
    entries: int
    bytes: int
    expired: int
    oldest: float | None
    newest: float | None


@dataclass(frozen=True)
class RefreshReport:
    refreshed: int
    failed: int
    errors: tuple[str, ...] = ()


def value_is_empty(value: Any, path: tuple[str, ...] = ()) -> bool:
    """True when the value (or the part of it at ``path``) is missing or empty."""
    for part in path:
        if not isinstance(value, dict):
            return True
        value = value.get(part)
    return value is None or value == [] or value == {}


def describe_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "timed out"
    if isinstance(exc, httpx.HTTPError):
        return type(exc).__name__
    return f"bad response ({type(exc).__name__})"


class HttpCache:
    """``source_headers`` are added to every request of that source when it is sent, and are
    never stored or part of the cache key: that's where API keys go."""

    def __init__(
        self,
        path: Path,
        client: httpx.AsyncClient,
        *,
        min_interval: dict[str, float] | None = None,
        source_headers: dict[str, dict[str, str]] | None = None,
        memory_items: int = 32,
        clock: Callable[[], float] = time.time,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._lock = threading.Lock()
        self._client = client
        self._clock = clock
        self._memory: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._memory_items = memory_items
        self._inflight: dict[str, asyncio.Future[Cached]] = {}
        self._min_interval = dict(min_interval or {})
        self._source_headers = {source: dict(headers) for source, headers in (source_headers or {}).items()}
        self._last_call: dict[str, float] = {}
        self._throttle_locks: dict[str, asyncio.Lock] = {}

    def close(self) -> None:
        self._db.close()

    async def get_json(
        self,
        source: str,
        spec: RequestSpec,
        *,
        ttl: float,
        empty_ttl: float | None = None,
        empty_at: tuple[str, ...] = (),
    ) -> Cached:
        """The response to ``spec``, from cache while fresh, otherwise fetched and stored.

        ``empty_ttl`` applies instead of ``ttl`` when the value (or its part at
        ``empty_at``) is empty. If a fetch fails, the expired copy is returned marked
        stale; UpstreamError only when there is no copy at all. Concurrent calls for the
        same request share one fetch.
        """
        key = spec.key
        meta = self._meta(key)
        if meta and meta[1] > self._clock():
            return self._hit(source, Cached(self._value(key, meta[0]), meta[0]))

        task = self._inflight.get(key)
        joined = task is not None
        if task is None:
            task = asyncio.ensure_future(self._fetch_and_store(source, spec, ttl, empty_ttl, empty_at))
            self._inflight[key] = task
            task.add_done_callback(lambda done, k=key: self._settle(k, done))
        result = await asyncio.shield(task)
        return self._hit(source, result) if joined else result

    def cached(self, source: str, spec: RequestSpec) -> Cached | None:
        """The stored copy of ``spec`` without asking the source (marked stale once it has
        expired), or None if there isn't one. For sources that are pausing their requests."""
        meta = self._meta(spec.key)
        if meta is None:
            return None
        stale = meta[1] <= self._clock()
        stats = current_calls()
        if stale and stats:
            stats.stale_sources.add(source)
        return self._hit(source, Cached(self._value(spec.key, meta[0]), meta[0], stale=stale))

    def _settle(self, key: str, task: asyncio.Future[Cached]) -> None:
        self._inflight.pop(key, None)
        if not task.cancelled():
            task.exception()  # mark it retrieved even if every waiter went away

    async def _fetch_and_store(
        self, source: str, spec: RequestSpec, ttl: float, empty_ttl: float | None, empty_at: tuple[str, ...]
    ) -> Cached:
        stats = current_calls()
        try:
            value = await self._request(source, spec)
        except (httpx.HTTPError, ValueError) as exc:
            meta = self._meta(spec.key)
            if meta is None:
                status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                raise UpstreamError(source, describe_error(exc), status) from exc
            if stats:
                stats.stale_sources.add(source)
                stats.used(source, meta[0])
            return Cached(self._value(spec.key, meta[0]), meta[0], stale=True)
        now = self._clock()
        self._store(spec, source, value, now, ttl, empty_ttl, empty_at)
        if stats:
            stats.used(source, now)
        return Cached(value, now)

    async def _request(self, source: str, spec: RequestSpec) -> Any:
        await self._throttle(source)
        stats = current_calls()
        if stats:
            stats.external_calls += 1
        headers = {**(spec.headers or {}), **self._source_headers.get(source, {})} or None
        response = await self._client.request(spec.method, spec.url, params=spec.params, json=spec.json, headers=headers)
        response.raise_for_status()
        return response.json()

    async def _throttle(self, source: str) -> None:
        interval = self._min_interval.get(source)
        if not interval:
            return
        lock = self._throttle_locks.setdefault(source, asyncio.Lock())
        async with lock:
            wait = self._last_call.get(source, 0.0) + interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call[source] = time.monotonic()

    def _hit(self, source: str, cached: Cached) -> Cached:
        stats = current_calls()
        if stats:
            stats.cache_hits += 1
            stats.used(source, cached.fetched_at)
        return cached

    # -- storage -----------------------------------------------------------------

    def _meta(self, key: str) -> tuple[float, float] | None:
        with self._lock:
            row = self._db.execute("SELECT fetched_at, expires_at FROM responses WHERE key = ?", (key,)).fetchone()
        return (row[0], row[1]) if row else None

    def _value(self, key: str, fetched_at: float) -> Any:
        hit = self._memory.get(key)
        if hit and hit[0] == fetched_at:
            self._memory.move_to_end(key)
            return hit[1]
        with self._lock:
            row = self._db.execute("SELECT value FROM responses WHERE key = ?", (key,)).fetchone()
        value = json.loads(row[0])
        self._remember(key, fetched_at, value)
        return value

    def _remember(self, key: str, fetched_at: float, value: Any) -> None:
        self._memory[key] = (fetched_at, value)
        self._memory.move_to_end(key)
        while len(self._memory) > self._memory_items:
            self._memory.popitem(last=False)

    def _store(
        self,
        spec: RequestSpec,
        source: str,
        value: Any,
        now: float,
        ttl: float,
        empty_ttl: float | None,
        empty_at: tuple[str, ...],
    ) -> None:
        lifetime = empty_ttl if empty_ttl is not None and value_is_empty(value, empty_at) else ttl
        text = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO responses"
                " (key, source, request, value, fetched_at, expires_at, ttl, empty_ttl, empty_at, bytes)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    spec.key, source, spec.dumps(), text, now, now + lifetime,
                    ttl, empty_ttl, json.dumps(list(empty_at)), len(text.encode("utf-8")),
                ),
            )
        self._remember(spec.key, now, value)

    # -- Settings page -----------------------------------------------------------

    def stats(self, source: str) -> SourceCacheStats:
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*), COALESCE(SUM(bytes), 0), COALESCE(SUM(expires_at <= ?), 0),"
                " MIN(fetched_at), MAX(fetched_at) FROM responses WHERE source = ?",
                (self._clock(), source),
            ).fetchone()
        return SourceCacheStats(entries=row[0], bytes=row[1], expired=row[2], oldest=row[3], newest=row[4])

    def file_bytes(self) -> int:
        return sum(p.stat().st_size for p in self.path.parent.glob(self.path.name + "*") if p.is_file())

    def clear(self, source: str | None = None) -> int:
        with self._lock:
            if source is None:
                removed = self._db.execute("DELETE FROM responses").rowcount
                self._db.execute("DELETE FROM flags")
                self._db.execute("VACUUM")
            else:
                removed = self._db.execute("DELETE FROM responses WHERE source = ?", (source,)).rowcount
                self._db.execute("DELETE FROM flags WHERE source = ?", (source,))
        self._memory.clear()
        return removed

    async def refresh(self, source: str, *, concurrency: int = 3) -> RefreshReport:
        """Re-fetch every stored request for ``source``; failures keep their old copy."""
        with self._lock:
            rows = self._db.execute(
                "SELECT request, ttl, empty_ttl, empty_at FROM responses WHERE source = ?", (source,)
            ).fetchall()
        gate = asyncio.Semaphore(max(1, concurrency))

        async def one(request: str, ttl: float, empty_ttl: float | None, empty_at: str) -> str | None:
            spec = RequestSpec.loads(request)
            async with gate:
                try:
                    value = await self._request(source, spec)
                except (httpx.HTTPError, ValueError) as exc:
                    return f"{spec.url}: {describe_error(exc)}"
            self._store(spec, source, value, self._clock(), ttl, empty_ttl, tuple(json.loads(empty_at)))
            return None

        errors = [e for e in await asyncio.gather(*(one(*row) for row in rows)) if e]
        return RefreshReport(refreshed=len(rows) - len(errors), failed=len(errors), errors=tuple(errors[:3]))

    # -- flags (e.g. "Ballotpedia refused us, pause until …") --------------------

    def set_flag(self, name: str, source: str, ttl: float) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO flags (name, source, expires_at) VALUES (?, ?, ?)",
                (name, source, self._clock() + ttl),
            )

    def flag_until(self, name: str) -> float | None:
        """When the flag expires, or None if it isn't set (or already expired)."""
        with self._lock:
            row = self._db.execute("SELECT expires_at FROM flags WHERE name = ?", (name,)).fetchone()
        return row[0] if row and row[0] > self._clock() else None
