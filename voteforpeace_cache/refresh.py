"""refresh(): fetch -> parse -> validate -> hash-compare -> write if changed."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import store
from .fetch import fetch_page
from .guard import hash_rows, validate
from .models import RefreshResult
from .parser import parse_page

Fetcher = Callable[[], str]


def refresh(
    force: bool = False,
    dry_run: bool = False,
    *,
    data_dir: str | Path | None = None,
    fetcher: Fetcher | None = None,
    now: datetime | None = None,
    raw_dir: str | Path | None = None,
) -> RefreshResult:
    """Refresh the cache from voteforpeace.info.

    force: write a snapshot even if nothing changed.
    dry_run: run the whole pipeline and report what would change, writing nothing.
    Raises FetchError / ParseError / ValidationError without touching any file.
    """
    paths = store.Paths(store.resolve_data_dir(data_dir))
    now = _utc(now or datetime.now(timezone.utc))

    page = fetcher() if fetcher is not None else fetch_page(raw_dir=raw_dir)
    result = parse_page(page)
    notes = validate(result)
    rows = [record.snapshot_row() for record in result.records]
    digest = hash_rows(rows)

    meta = store.load_meta(paths)
    latest = paths.latest_snapshot()
    if latest is not None and meta.get("rows_hash") == digest and not force:
        if not dry_run:
            meta["last_checked"] = _iso(now)
            store.write_json(paths.meta, meta)
        return RefreshResult(status="no_changes", checked_at=now, record_count=len(rows), warnings=tuple(notes))

    previous = store.read_json(latest, default=[]) if latest else []
    added, removed, modified = diff_rows(previous, rows)
    snapshot_path = paths.snapshot(now.date())
    result_kwargs = dict(
        checked_at=now,
        record_count=len(rows),
        added=added,
        removed=removed,
        modified=modified,
        snapshot_path=snapshot_path,
        warnings=tuple(notes),
    )
    if dry_run:
        return RefreshResult(status="would_update", **result_kwargs)

    store.write_json(snapshot_path, rows)
    store.write_json(paths.current, store.build_current(rows, snapshot_path.stem))
    meta.update(
        schema_version=store.SCHEMA_VERSION,
        last_refresh=_iso(now),
        last_checked=_iso(now),
        latest_snapshot=snapshot_path.stem,
        rows_hash=digest,
    )
    store.write_json(paths.meta, meta)
    return RefreshResult(status="updated", **result_kwargs)


def diff_rows(
    old: list[dict[str, Any]], new: list[dict[str, Any]]
) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, tuple[str, ...]]]:
    """Candidates added, removed and changed (with the fields that changed), by "STATE/slug"."""

    def key(row: dict[str, Any]) -> str:
        return f"{row.get('state')}/{row.get('slug') or row['candidate_id']}"

    old_by = {row["candidate_id"]: row for row in old}
    new_by = {row["candidate_id"]: row for row in new}
    added = tuple(sorted(key(new_by[c]) for c in new_by.keys() - old_by.keys()))
    removed = tuple(sorted(key(old_by[c]) for c in old_by.keys() - new_by.keys()))
    modified: dict[str, tuple[str, ...]] = {}
    for cid in sorted(new_by.keys() & old_by.keys(), key=lambda c: key(new_by[c])):
        a, b = old_by[cid], new_by[cid]
        changed = tuple(sorted(f for f in a.keys() | b.keys() if a.get(f) != b.get(f)))
        if changed:
            modified[key(b)] = changed
    return added, removed, modified


def _utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")
