"""refresh(): fetch -> parse -> validate -> hash-compare -> write if changed."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from . import store
from .errors import FetchError
from .fetch import fetch_all
from .guard import changed_sources, hash_rows, validate
from .models import SOURCE_URLS, RefreshResult
from .parser import parse_source

Fetcher = Callable[[], Mapping[str, str]]


def refresh(
    force: bool = False,
    dry_run: bool = False,
    *,
    data_dir: str | Path | None = None,
    fetcher: Fetcher | None = None,
    now: datetime | None = None,
    raw_dir: str | Path | None = None,
) -> RefreshResult:
    """Refresh the cache from trackaipac.com.

    force: write a snapshot even if no source changed.
    dry_run: run the whole pipeline and report what would change, writing nothing.
    Raises FetchError / ValidationError without touching any file.
    """
    paths = store.Paths(store.resolve_data_dir(data_dir))
    now = _utc(now or datetime.now(timezone.utc))

    pages = fetcher() if fetcher is not None else fetch_all(raw_dir=raw_dir)
    missing = [source for source in SOURCE_URLS if source not in pages]
    if missing:
        raise FetchError(f"fetcher returned no page for: {', '.join(missing)}")

    results = {source: parse_source(source, pages[source]) for source in SOURCE_URLS}
    notes = validate(results)

    records = [record for result in results.values() for record in result.records]
    hashes = {source: hash_rows(store.snapshot_rows(result.records)) for source, result in results.items()}
    counts = {source: len(result.records) for source, result in results.items()}

    meta = store.load_meta(paths)
    latest = paths.latest_snapshot()
    changed = changed_sources(hashes, meta, snapshot_present=latest is not None)

    if not changed and not force:
        if not dry_run:
            meta["last_checked"] = _iso(now)
            store.write_json(paths.meta, meta)
        return RefreshResult(status="no_changes", checked_at=now, record_counts=counts, warnings=tuple(notes))

    rows = store.snapshot_rows(records)
    previous = store.read_json(latest, default=[]) if latest else []
    added, removed, modified = diff_rows(previous, rows)
    snapshot_path = paths.snapshot(now.date())

    result_kwargs = dict(
        checked_at=now,
        changed_sources=tuple(changed),
        record_counts=counts,
        added=added,
        removed=removed,
        modified=modified,
        snapshot_path=snapshot_path,
        warnings=tuple(notes),
    )
    if dry_run:
        return RefreshResult(status="would_update", **result_kwargs)

    registry = store.read_json(paths.registry, default={}) or {}
    new_registry = store.upsert_registry(registry, records)
    store.write_json(snapshot_path, rows)
    store.write_json(paths.registry, new_registry)
    store.write_json(paths.current, store.build_current(new_registry, rows, snapshot_path.stem))
    meta.update(
        schema_version=store.SCHEMA_VERSION,
        last_refresh=_iso(now),
        last_checked=_iso(now),
        latest_snapshot=snapshot_path.stem,
        source_hashes=hashes,
    )
    store.write_json(paths.meta, meta)
    return RefreshResult(status="updated", **result_kwargs)


def row_keys(rows: list[dict[str, Any]]) -> list[str]:
    """"category/candidate_id", with "#2", "#3"… for a person listed again on the same page."""
    seen: dict[str, int] = {}
    keys = []
    for row in rows:
        base = f"{row['category']}/{row['candidate_id']}"
        seen[base] = seen.get(base, 0) + 1
        keys.append(base if seen[base] == 1 else f"{base}#{seen[base]}")
    return keys


def diff_rows(
    old: list[dict[str, Any]], new: list[dict[str, Any]]
) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, tuple[str, ...]]]:
    old_by = dict(zip(row_keys(old), old))
    new_by = dict(zip(row_keys(new), new))
    added = tuple(sorted(k for k in new_by if k not in old_by))
    removed = tuple(sorted(k for k in old_by if k not in new_by))
    modified: dict[str, tuple[str, ...]] = {}
    for key in sorted(new_by.keys() & old_by.keys()):
        a, b = old_by[key], new_by[key]
        changed_fields = tuple(sorted(f for f in a.keys() | b.keys() if a.get(f) != b.get(f)))
        if changed_fields:
            modified[key] = changed_fields
    return added, removed, modified


def _utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")
