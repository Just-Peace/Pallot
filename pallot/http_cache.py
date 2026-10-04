"""Persistent cache for every outbound API call.

One SQLite row per distinct request (method + URL + params + body), tagged with the
source that made it, so the Settings page can show, clear or refresh one source at a
time. A row keeps the request itself and the lifetimes it was stored with, so refresh()
can re-issue it without knowing what it was for. A value is parsed JSON, a web page's text
(get_text) or an image as base64 (get_bytes). Decoded values also sit in an in-memory
LRU bounded by their stored size, which matters for the 2.6 MB statewide candidate list;
images stay out of it, since the browser keeps them too.

A row's dates are read through a covering index, and stats() through another: the value
is stored before them in each row, so reading them from the table walks the whole value.

When a request fails, its last good copy is served (marked stale) and the source isn't
asked for it again for ``retry_after`` seconds. Some sources answer an error with a 200
(an ArcGIS server's ``error`` body, a page without its table): a source registers a check of
its answers (check_answers), and an answer it refuses is handled like a failed request, so it
never replaces a good copy; with none, it's kept for ``retry_after`` and raised as
UpstreamError meanwhile. A source can also be paused as a whole when it answers with certain
statuses (Ballotpedia refusing us, the FEC's rate limit): while paused, whatever is stored is
served and nothing is fetched, not even by refresh().

Cached values are shared between callers: treat them as read-only.
"""

from __future__ import annotations

import asyncio
import base64
import contextvars
import hashlib
import json
import sqlite3
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Collection

import httpx

from .text import iso_utc

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
DROP INDEX IF EXISTS responses_source;
CREATE INDEX IF NOT EXISTS responses_key_dates ON responses(key, fetched_at, expires_at);
CREATE INDEX IF NOT EXISTS responses_source_stats ON responses(source, fetched_at, expires_at, bytes);
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
    as_text: bool = False  # the body as text (a web page), not parsed as JSON
    as_bytes: bool = False  # the body as bytes (an image), stored as base64 text

    @property
    def key(self) -> str:
        """Identity of the request; headers are not part of it."""
        identity = {"method": self.method.upper(), "url": self.url, "params": self.params, "json": self.json}
        if self.as_text:  # only when set, so the keys of JSON requests stay what they were
            identity["as_text"] = True
        if self.as_bytes:
            identity["as_bytes"] = True
        return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def dumps(self) -> str:
        return json.dumps(
            {"method": self.method, "url": self.url, "params": self.params, "json": self.json, "headers": self.headers,
             "as_text": self.as_text, "as_bytes": self.as_bytes},
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


@dataclass(frozen=True)
class _Stored:
    fetched_at: float
    expires_at: float
    value: Any


class UpstreamError(Exception):
    """A source could not be reached, or is paused (``until``), and nothing was cached to
    fall back on."""

    def __init__(self, source: str, message: str, status: int | None = None, until: float | None = None):
        super().__init__(f"{source}: {message}")
        self.source = source
        self.status = status
        self.until = until


@dataclass
class CallStats:
    """What one API request cost: cache hits, external calls, data age per source."""

    external_calls: int = 0
    cache_hits: int = 0
    calls: dict[str, int] = field(default_factory=dict)  # source -> external calls
    stale_sources: set[str] = field(default_factory=set)
    oldest: dict[str, float] = field(default_factory=dict)  # source -> oldest fetched_at used

    def called(self, source: str) -> None:
        self.external_calls += 1
        self.calls[source] = self.calls.get(source, 0) + 1

    def used(self, source: str, fetched_at: float) -> None:
        self.oldest[source] = min(fetched_at, self.oldest.get(source, fetched_at))


_call_stats: contextvars.ContextVar[CallStats | None] = contextvars.ContextVar("pallot_call_stats", default=None)


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
    skipped: int = 0  # not asked, because the source is paused
    paused_until: float | None = None


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


def _status(exc: Exception) -> int | None:
    return exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None


def _retry_flag(key: str) -> str:
    return f"retry:{key}"


def _pause_flag(source: str) -> str:
    return f"paused:{source}"


class HttpCache:
    """``source_headers`` are added to every request of that source when it is sent, and are
    never stored or part of the cache key: that's where API keys go. ``retry_after`` is how
    long a failed request keeps serving its old copy before the source is asked again."""

    def __init__(
        self,
        path: Path,
        client: httpx.AsyncClient,
        *,
        min_interval: dict[str, float] | None = None,
        source_headers: dict[str, dict[str, str]] | None = None,
        memory_bytes: int = 64 << 20,
        retry_after: float = 0.0,
        clock: Callable[[], float] = time.time,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA secure_delete=ON")
        self._db.executescript(_SCHEMA)
        self._lock = threading.Lock()
        self._client = client
        self._clock = clock
        self._memory: OrderedDict[str, tuple[float, Any, int]] = OrderedDict()  # key -> fetched_at, value, bytes
        self._memory_bytes = memory_bytes
        self._memory_used = 0
        self._inflight: dict[str, asyncio.Future[Cached]] = {}
        self._min_interval = dict(min_interval or {})
        self._source_headers = {source: dict(headers) for source, headers in (source_headers or {}).items()}
        self._last_call: dict[str, float] = {}
        self._throttle_locks: dict[str, asyncio.Lock] = {}
        self._retry_after = retry_after
        self._pause_on: dict[str, tuple[frozenset[int], float]] = {}
        self._checks: dict[str, Callable[[Any], str | None]] = {}

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
        stale, and keeps being returned without asking for ``retry_after``; UpstreamError
        only when there is no copy at all. An answer the source's check refuses counts as a
        failure, and a stored one is never served: UpstreamError while it's kept, then asked
        again. While the source is paused: the stored copy, fresh or not, or UpstreamError
        with ``until``. Concurrent calls for the same request share one fetch.
        """
        key = spec.key
        stored = await asyncio.to_thread(self._load, spec)
        if stored and (why := self._refusal(source, stored.value)):
            if stored.expires_at > self._clock():
                raise UpstreamError(source, why)
            stored = None
        if stored and stored.expires_at > self._clock():
            return self._hit(source, Cached(stored.value, stored.fetched_at))
        until = self.paused_until(source)
        if stored and (until or self.flag_until(_retry_flag(key))):
            return self._hit(source, Cached(stored.value, stored.fetched_at, stale=True))
        if until:
            raise UpstreamError(source, f"paused until {iso_utc(until)}", until=until)

        task = self._inflight.get(key)
        joined = task is not None
        if task is None:
            task = asyncio.ensure_future(self._fetch_and_store(source, spec, ttl, empty_ttl, empty_at))
            self._inflight[key] = task
            task.add_done_callback(lambda done, k=key: self._settle(k, done))
        result = await asyncio.shield(task)
        return self._hit(source, result) if joined else result

    async def get_text(self, source: str, spec: RequestSpec, *, ttl: float) -> Cached:
        """get_json for a web page: the value is the response body as a string."""
        return await self.get_json(source, replace(spec, as_text=True), ttl=ttl)

    async def get_bytes(self, source: str, spec: RequestSpec, *, ttl: float) -> Cached:
        """get_json for an image: the value is the response body as bytes."""
        got = await self.get_json(source, replace(spec, as_bytes=True), ttl=ttl)
        return replace(got, value=base64.b64decode(got.value))

    async def download(
        self, source: str, spec: RequestSpec, path: Path, *, max_bytes: int, hosts: Collection[str] = ()
    ) -> int:
        """Stream the response to ``spec`` into ``path``, for a file too big to keep in the
        database (a map), and return its size. The same pause, throttling, call count and
        refusals as get_json, but nothing is stored: whoever keeps the file decides when it's
        fetched again. Refused past ``max_bytes``, or when a redirect leaves ``hosts``. On any
        failure ``path`` is removed, and UpstreamError raised."""
        until = self.paused_until(source)
        if until:
            raise UpstreamError(source, f"paused until {iso_utc(until)}", until=until)
        await self._throttle(source)
        stats = current_calls()
        if stats:
            stats.called(source)
        headers = {**(spec.headers or {}), **self._source_headers.get(source, {})} or None
        written = 0
        try:
            async with self._client.stream(
                spec.method, spec.url, params=spec.params, json=spec.json, headers=headers
            ) as response:
                response.raise_for_status()
                if hosts and response.url.host not in hosts:
                    raise ValueError(f"the download was redirected to {response.url.host}")
                if int(response.headers.get("content-length") or 0) > max_bytes:
                    raise ValueError(f"the download is larger than {max_bytes:,} bytes")
                with path.open("wb") as fh:
                    async for chunk in response.aiter_bytes(1 << 20):
                        written += len(chunk)
                        if written > max_bytes:
                            raise ValueError(f"the download is larger than {max_bytes:,} bytes")
                        await asyncio.to_thread(fh.write, chunk)
        except (httpx.HTTPError, ValueError) as exc:
            path.unlink(missing_ok=True)
            self._refused(source, exc)
            message = describe_error(exc) if isinstance(exc, httpx.HTTPError) else str(exc)
            raise UpstreamError(source, message, _status(exc)) from exc
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return written

    def peek(self, spec: RequestSpec) -> Cached | None:
        """The stored copy of ``spec``, fresh or not, without asking anyone (Settings reads
        what's kept this way)."""
        stored = self._load(spec)
        return Cached(stored.value, stored.fetched_at) if stored else None

    def pause_on(self, source: str, statuses: Collection[int], seconds: float) -> None:
        """Stop asking ``source`` for ``seconds`` once it answers with one of ``statuses``."""
        self._pause_on[source] = (frozenset(statuses), seconds)

    def paused_until(self, source: str) -> float | None:
        return self.flag_until(_pause_flag(source))

    def check_answers(self, source: str, check: Callable[[Any], str | None]) -> None:
        """Refuse an answer of ``source`` that ``check`` finds wrong (it returns why, or None
        for a good one), as if the request had failed."""
        self._checks[source] = check

    def _refusal(self, source: str, value: Any) -> str | None:
        check = self._checks.get(source)
        return check(value) if check else None

    def _refused(self, source: str, exc: Exception) -> None:
        rule = self._pause_on.get(source)
        if rule and _status(exc) in rule[0]:
            self.set_flag(_pause_flag(source), source, rule[1])

    def _settle(self, key: str, task: asyncio.Future[Cached]) -> None:
        self._inflight.pop(key, None)
        if not task.cancelled():
            task.exception()  # mark it retrieved even if every waiter went away

    async def _fetch_and_store(
        self, source: str, spec: RequestSpec, ttl: float, empty_ttl: float | None, empty_at: tuple[str, ...]
    ) -> Cached:
        try:
            value = await self._request(source, spec)
        except (httpx.HTTPError, ValueError) as exc:
            self._refused(source, exc)
            kept = await self._fall_back(source, spec)
            if kept is None:
                raise UpstreamError(source, describe_error(exc), _status(exc)) from exc
            return kept
        now = self._clock()
        why = self._refusal(source, value)
        if why:
            kept = await self._fall_back(source, spec)
            if kept is None:
                await asyncio.to_thread(
                    self._store, spec, source, value, now, ttl, empty_ttl, empty_at, self._retry_after
                )
                raise UpstreamError(source, why)
            return kept
        await asyncio.to_thread(self._store, spec, source, value, now, ttl, empty_ttl, empty_at)
        stats = current_calls()
        if stats:
            stats.used(source, now)
        return Cached(value, now)

    async def _fall_back(self, source: str, spec: RequestSpec) -> Cached | None:
        """After a failed request: the last good copy, marked stale and not asked for again
        for ``retry_after``, or None when there's none (a refused answer isn't one)."""
        stored = await asyncio.to_thread(self._load, spec)
        if stored is None or self._refusal(source, stored.value):
            return None
        if self._retry_after:
            self.set_flag(_retry_flag(spec.key), source, self._retry_after)
        stats = current_calls()
        if stats:
            stats.stale_sources.add(source)
            stats.used(source, stored.fetched_at)
        return Cached(stored.value, stored.fetched_at, stale=True)

    async def _request(self, source: str, spec: RequestSpec) -> Any:
        await self._throttle(source)
        stats = current_calls()
        if stats:
            stats.called(source)
        headers = {**(spec.headers or {}), **self._source_headers.get(source, {})} or None
        response = await self._client.request(spec.method, spec.url, params=spec.params, json=spec.json, headers=headers)
        response.raise_for_status()
        if spec.as_bytes:
            return base64.b64encode(response.content).decode("ascii")
        return response.text if spec.as_text else response.json()

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
            if cached.stale:
                stats.stale_sources.add(source)
        return cached

    # -- storage -----------------------------------------------------------------

    def _load(self, spec: RequestSpec) -> _Stored | None:
        """The stored copy, or None. The dates come from the covering index, and the value
        is read only when memory doesn't hold that copy, by key and fetched_at: a Clear or a
        newer copy from another process (or thread) in between is a miss, never a value
        paired with another copy's dates."""
        key = spec.key
        with self._lock:
            row = self._db.execute(
                "SELECT fetched_at, expires_at FROM responses INDEXED BY responses_key_dates WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            fetched_at, expires_at = row
            hit = self._memory.get(key)
            if hit and hit[0] == fetched_at:
                self._memory.move_to_end(key)
                return _Stored(fetched_at, expires_at, hit[1])
            found = self._db.execute(
                "SELECT value, bytes FROM responses WHERE key = ? AND fetched_at = ?", (key, fetched_at)
            ).fetchone()
        if found is None:
            return None
        text, size = found
        value = json.loads(text)
        if not spec.as_bytes:
            with self._lock:
                self._remember(key, fetched_at, value, size)
        return _Stored(fetched_at, expires_at, value)

    def _remember(self, key: str, fetched_at: float, value: Any, size: int) -> None:
        """Keep a decoded value in memory, dropping the least recently used past
        ``memory_bytes`` of stored text; the caller holds self._lock."""
        old = self._memory.pop(key, None)
        if old:
            self._memory_used -= old[2]
        if size > self._memory_bytes:
            return
        self._memory[key] = (fetched_at, value, size)
        self._memory_used += size
        while self._memory_used > self._memory_bytes:
            self._memory_used -= self._memory.popitem(last=False)[1][2]

    def _forget_all(self) -> None:
        """Empty the in-memory copies; the caller holds self._lock."""
        self._memory.clear()
        self._memory_used = 0

    def _store(
        self,
        spec: RequestSpec,
        source: str,
        value: Any,
        now: float,
        ttl: float,
        empty_ttl: float | None,
        empty_at: tuple[str, ...],
        lifetime: float | None = None,
    ) -> None:
        """Store ``value`` for ``lifetime``, or else ``ttl`` (``empty_ttl`` when it's empty);
        the lifetimes are kept for refresh() either way."""
        if lifetime is None:
            lifetime = empty_ttl if empty_ttl is not None and value_is_empty(value, empty_at) else ttl
        text = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        size = len(text.encode("utf-8"))
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO responses"
                " (key, source, request, value, fetched_at, expires_at, ttl, empty_ttl, empty_at, bytes)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    spec.key, source, spec.dumps(), text, now, now + lifetime,
                    ttl, empty_ttl, json.dumps(list(empty_at)), size,
                ),
            )
            self._db.execute("DELETE FROM flags WHERE name = ?", (_retry_flag(spec.key),))
            if not spec.as_bytes:
                self._remember(spec.key, now, value, size)

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
        """``secure_delete`` zeroes the deleted rows, and the checkpoint empties the WAL of
        their old copies, so a cleared address can't be read back from the files."""
        with self._lock:
            if source is None:
                removed = self._db.execute("DELETE FROM responses").rowcount
                self._db.execute("DELETE FROM flags")
                self._db.execute("VACUUM")
            else:
                removed = self._db.execute("DELETE FROM responses WHERE source = ?", (source,)).rowcount
                self._db.execute("DELETE FROM flags WHERE source = ?", (source,))
            self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._forget_all()
        return removed

    def prune(self, sources: Collection[str], misses: Collection[str], older_than: float) -> int:
        """Delete what's no use even as a fallback, once it has been expired for ``older_than``
        seconds: every row of ``sources`` (what was typed for suggestions), and the empty
        answers of ``misses`` (addresses that weren't found), told apart by the shorter
        empty_ttl they were stored with. Expired flags go too. Returns the rows deleted."""
        cutoff = self._clock() - older_than
        with self._lock:
            removed = 0
            if sources:
                removed += self._db.execute(
                    f"DELETE FROM responses WHERE expires_at < ? AND source IN ({','.join('?' * len(sources))})",
                    (cutoff, *sources),
                ).rowcount
            if misses:
                removed += self._db.execute(
                    "DELETE FROM responses WHERE expires_at < ? AND empty_ttl < ttl"
                    " AND ABS(expires_at - fetched_at - empty_ttl) < 1"
                    f" AND source IN ({','.join('?' * len(misses))})",
                    (cutoff, *misses),
                ).rowcount
            self._db.execute("DELETE FROM flags WHERE expires_at <= ?", (self._clock(),))
            if removed:
                self._db.execute("VACUUM")
                self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._forget_all()
        return removed

    async def refresh(self, source: str, *, concurrency: int = 3) -> RefreshReport:
        """Re-fetch every stored request for ``source``; failures, and answers its check
        refuses, keep their old copy. While
        the source is paused (also when a refusal pauses it partway through), the rest are
        skipped rather than asked."""
        with self._lock:
            rows = self._db.execute(
                "SELECT request, ttl, empty_ttl, empty_at FROM responses WHERE source = ?", (source,)
            ).fetchall()
        gate = asyncio.Semaphore(max(1, concurrency))
        skipped = 0

        async def one(request: str, ttl: float, empty_ttl: float | None, empty_at: str) -> str | None:
            nonlocal skipped
            spec = RequestSpec.loads(request)
            async with gate:
                if self.paused_until(source):
                    skipped += 1
                    return None
                try:
                    value = await self._request(source, spec)
                except (httpx.HTTPError, ValueError) as exc:
                    self._refused(source, exc)
                    return f"{spec.url}: {describe_error(exc)}"
            why = self._refusal(source, value)
            if why:
                return f"{spec.url}: {why}"
            await asyncio.to_thread(
                self._store, spec, source, value, self._clock(), ttl, empty_ttl, tuple(json.loads(empty_at))
            )
            return None

        errors = [e for e in await asyncio.gather(*(one(*row) for row in rows)) if e]
        return RefreshReport(
            refreshed=len(rows) - len(errors) - skipped,
            failed=len(errors),
            errors=tuple(errors[:3]),
            skipped=skipped,
            paused_until=self.paused_until(source),
        )

    # -- flags: sources paused after a refusal, requests waiting to be retried ------

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
