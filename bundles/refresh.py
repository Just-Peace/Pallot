"""refresh(): run each asked-for bundle's builder on a throwaway cache -> write its answers if they changed.

The throwaway cache's rows under the source, those the bundle wants (Bundle.wants), are the bundle:
exactly the requests a lookup makes, asked with the configured keys at their offline pace
(http_cache.offline).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Collection, Mapping

import httpx

from pallot.config import HOUR, Config, load_config
from pallot.http_cache import HttpCache, RequestSpec, offline
from pallot.services import MIN_INTERVAL
from pallot.sources import sos

from . import registry, store
from .entry import CADENCES, Bundle, BundleError, Context

DUE_SLACK = 2 * HOUR  # a daily run that starts a little earlier than yesterday's still counts as due
BUILD_INTERVAL = {**MIN_INTERVAL, sos.SOURCE: 1.0}  # a lookup asks Texas SOS for one county; a build, for all 254


@dataclass(frozen=True)
class Outcome:
    source: str  # the bundle's name
    status: str  # "updated", "no_changes", "would_update", "skipped" or "failed"
    answers: int = 0
    counts: Mapping[str, int] = field(default_factory=dict)
    detail: str = ""  # why it was skipped or failed

    def summary(self) -> str:
        if self.status in ("skipped", "failed"):
            return f"{self.source}: {self.status}, {self.detail}."
        what = f"{self.answers:,} answers" + "".join(f", {n:,} {name}" for name, n in self.counts.items())
        return f"{self.source}: " + {"updated": f"updated ({what}).", "no_changes": f"no changes ({what}).",
                                     "would_update": f"would update ({what})."}[self.status]


def json_request(spec: RequestSpec) -> dict[str, Any]:
    """What RequestSpec(**…) needs again: its key's fields, without the defaults, and never its headers."""
    request: dict[str, Any] = {"method": spec.method, "url": spec.url, "params": spec.params}
    if spec.json is not None:
        request["json"] = spec.json
    if spec.as_text:
        request["as_text"] = True
    if spec.as_bytes:
        request["as_bytes"] = True
    return request


def is_due(entry: Bundle, meta: Mapping[str, Any], now: dt.datetime) -> bool:
    checked = meta.get("last_checked")
    if not checked:
        return True
    return (now - dt.datetime.fromisoformat(checked)).total_seconds() >= CADENCES[entry.cadence] - DUE_SLACK


async def build(entry: Bundle, config: Config, today: Callable[[], dt.date],
                min_interval: Mapping[str, float]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """The answers a lookup would get from ``entry``'s source, sorted by request, and the builder's counts."""
    with tempfile.TemporaryDirectory() as tmp:
        async with httpx.AsyncClient(
            timeout=config.http_timeout, headers={"User-Agent": config.user_agent}, follow_redirects=True
        ) as client:
            cache = HttpCache(Path(tmp) / "cache.sqlite3", client, min_interval=dict(min_interval))
            try:
                with offline():
                    counts = dict(await entry.build(Context(config, cache, today)))
                answers = []
                for saved in cache.saved(entry.source):
                    spec = RequestSpec.loads(saved.request)
                    kept = cache.peek(spec)
                    if kept is not None and entry.wants(spec, kept.value):
                        answers.append({"request": json_request(spec), "value": kept.value})
            finally:
                cache.close()
    if not answers:
        raise BundleError("the builder got no answers to bundle")
    answers.sort(key=store.request_order)
    return answers, counts


def refresh_one(entry: Bundle, root: Path, *, force: bool, dry_run: bool, config: Config,
                today: Callable[[], dt.date], now: dt.datetime, min_interval: Mapping[str, float]) -> Outcome:
    """Rebuild one source's bundle. Its answers are written only when they changed (or ``force``);
    its last_checked is updated either way, unless ``dry_run``. Raises BundleError without writing."""
    answers, counts = asyncio.run(build(entry, config, today, min_interval))
    digest = store.answers_hash(answers)
    meta = store.read_meta(root).get(entry.name, {})
    stamp = now.isoformat(timespec="seconds")
    if meta.get("answers_hash") == digest and (root / f"{entry.name}.json").exists() and not force:
        if not dry_run:
            store.write_meta(root, entry.name, {**meta, "last_checked": stamp})
        return Outcome(entry.name, "no_changes", len(answers), counts)
    if dry_run:
        return Outcome(entry.name, "would_update", len(answers), counts)
    store.write_answers(root / f"{entry.name}.json", answers)
    store.write_meta(root, entry.name, {"last_refresh": stamp, "last_checked": stamp, "answers_hash": digest,
                                        "answers": len(answers), **counts})
    return Outcome(entry.name, "updated", len(answers), counts)


def refresh(
    only: Collection[str] = (),
    *,
    due: bool = False,
    force: bool = False,
    dry_run: bool = False,
    data_dir: str | Path | None = None,
    config: Config | None = None,
    today: Callable[[], dt.date] = dt.date.today,
    now: dt.datetime | None = None,
    min_interval: Mapping[str, float] = BUILD_INTERVAL,
    bundles: tuple[Bundle, ...] | None = None,
) -> list[Outcome]:
    """Refresh the bundles named in ``only`` (all by default) in ``data_dir`` (the package's by
    default), one after another. With ``due``, a source checked within its cadence is skipped. A
    source that fails is reported and written nothing; the others still go."""
    root = Path(data_dir) if data_dir else store.PACKAGE_DATA_DIR
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    config = config or load_config()
    meta = store.read_meta(root)
    outcomes = []
    for entry in registry.BUNDLES if bundles is None else bundles:
        if only and entry.name not in only:
            continue
        if due and not is_due(entry, meta.get(entry.name, {}), now):
            checked = meta[entry.name]["last_checked"]
            outcomes.append(Outcome(entry.name, "skipped", detail=f"checked {checked}, within its {entry.cadence} cadence"))
            continue
        try:
            outcomes.append(refresh_one(entry, root, force=force, dry_run=dry_run, config=config, today=today,
                                        now=now, min_interval=min_interval))
        except BundleError as exc:
            outcomes.append(Outcome(entry.name, "failed", detail=str(exc)))
    return outcomes
