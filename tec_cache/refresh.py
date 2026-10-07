"""refresh(): read TEC's zip -> stage -> summarize -> validate -> write if anything changed."""

from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path
from typing import Any, Mapping

import httpx

from . import store
from .errors import FetchError
from .guard import MIN_COUNTS, validate
from .models import NEWEST_CONTRIB_FILES, ZIP_URL, RefreshResult, window_start
from .parse import Stage, contrib_number, member_kind
from .remote_zip import Directory, LocalZip, Member, RemoteZip
from .summarize import summarize

FIXED = ("filers.csv", "cover.csv", "cand.csv")
MORE_AT_ONCE = 10  # older contribution files read per extra request, when the window reaches further back
MAX_EXTRA_ROUNDS = 5


def refresh(
    force: bool = False,
    dry_run: bool = False,
    *,
    data_dir: str | Path | None = None,
    zip_path: str | Path | None = None,
    url: str = ZIP_URL,
    client: httpx.Client | None = None,
    pause: float = 10.0,
    user_agent: str | None = None,
    now: dt.datetime | None = None,
    minimums: Mapping[str, int] | None = None,
) -> RefreshResult:
    """Rebuild the snapshot from TEC's zip (downloaded, or ``zip_path``) and write it if it
    changed. The first request tells whether TEC's zip changed since the last refresh;
    if it didn't, that's the only one.

    force: rebuild and write even if nothing changed.
    dry_run: do everything but write.
    Raises FetchError (BlockedError when TEC refuses us) or ValidationError without
    touching any file.
    """
    paths = store.Paths(store.resolve_data_dir(data_dir))
    now = _utc(now or dt.datetime.now(dt.timezone.utc))
    window = window_start(now.date())
    meta = store.read_json(paths.meta, default={}) or {}
    source = LocalZip(zip_path) if zip_path else RemoteZip(url, client=client, pause=pause, user_agent=user_agent)
    with source:
        directory = source.directory()
        missing = [name for name in FIXED if name not in directory.members]
        if missing:
            raise FetchError(f"TEC's zip has no {', '.join(missing)}")
        same_zip = bool(directory.etag) and (meta.get("zip") or {}).get("etag") == directory.etag
        same_shape = meta.get("schema_version") == store.SCHEMA_VERSION and meta.get("window_start") == window.isoformat()
        if same_zip and same_shape and not force and paths.current.exists():
            if not dry_run:
                store.write_json(paths.meta, {**meta, "last_checked": _iso(now)})
            return RefreshResult(
                "no_changes", now, source.source, snapshot=meta.get("snapshot"), window_start=window,
                filers=(meta.get("counts") or {}).get("snapshot_filers", 0),
                requests=source.requests, downloaded=source.downloaded,
            )
        with tempfile.TemporaryDirectory(prefix="tec-stage-") as tmp:
            stage = Stage(Path(tmp) / "stage.sqlite3", window)
            try:
                members = _load(source, directory, stage, meta, window)
                counts = stage.counts()
                built = summarize(stage.db, window)
            finally:
                stage.close()

    counts["snapshot_filers"] = len(built["filers"])
    notes = validate(counts, MIN_COUNTS if minimums is None else minimums)
    digest = store.content_hash(built)
    changed = force or digest != meta.get("content_hash") or not paths.current.exists()
    snapshot = now.date().isoformat() if changed else meta.get("snapshot")
    result: dict[str, Any] = dict(
        checked_at=now, source=source.source, snapshot=snapshot, window_start=window,
        filers=counts["snapshot_filers"], requests=source.requests, downloaded=source.downloaded, warnings=tuple(notes),
    )
    if dry_run:
        return RefreshResult("would_update" if changed else "no_changes", **result)
    if changed:
        store.write_snapshot(paths.current, {"snapshot": snapshot, "tec_updated": directory.last_modified, **built})
    store.write_json(paths.meta, {
        "schema_version": store.SCHEMA_VERSION,
        "last_checked": _iso(now),
        "last_refresh": _iso(now) if changed else meta.get("last_refresh"),
        "snapshot": snapshot,
        "window_start": window.isoformat(),
        "zip": {"etag": directory.etag, "last_modified": directory.last_modified, "size": directory.size},
        "members": members,
        "counts": counts,
        "content_hash": digest,
    })
    return RefreshResult("updated" if changed else "no_changes", **result)


def _settled(known: dict[str, Any] | None, member: Member, start: str) -> bool:
    """A contribution file we've read before, unchanged, holding only reports filed before the window."""
    return bool(known) and known.get("crc") == member.crc and (known.get("last") or "") < start


def _load(source: LocalZip | RemoteZip, directory: Directory, stage: Stage, meta: dict[str, Any], window: dt.date) -> dict[str, Any]:
    """Stage filers, cover sheets, direct expenditures and every contribution file that can
    hold reports from the window. Returns what meta.json keeps about each contribution file:
    its CRC and the first and last dates its reports were received."""
    start = window.strftime("%Y%m%d")
    contribs = sorted((number, name) for name in directory.members if (number := contrib_number(name)) is not None)
    known: dict[str, Any] = meta.get("members") or {}
    read_before = [number for name in known if (number := contrib_number(name)) is not None]
    if read_before:
        oldest = min(read_before)
        wanted = [name for number, name in contribs if number >= oldest and not _settled(known.get(name), directory.members[name], start)]
    else:
        wanted = [name for _, name in contribs[-NEWEST_CONTRIB_FILES:]]

    kept: dict[str, Any] = {}
    batch, rounds = [*FIXED, *wanted], 0
    while batch:
        for member, chunks in source.read(batch):
            stats = stage.load(member.name, chunks)
            if member_kind(member.name) == "contribs":
                kept[member.name] = {"crc": member.crc, "first": stats.first, "last": stats.last}
        # The files are in filing order: if the oldest one read starts inside the window, older
        # ones may hold more of it (unless we already know they don't).
        read = sorted((contrib_number(name), name) for name in kept)
        older = [name for number, name in contribs
                 if read and number < read[0][0] and not _settled(known.get(name), directory.members[name], start)]
        batch = []
        if older and read and (kept[read[0][1]]["first"] or "0") >= start and rounds < MAX_EXTRA_ROUNDS:
            batch, rounds = older[-MORE_AT_ONCE:], rounds + 1
    for name, info in known.items():  # files skipped as settled stay settled
        if name not in kept and name in directory.members and _settled(info, directory.members[name], start):
            kept[name] = info
    return kept


def _utc(moment: dt.datetime) -> dt.datetime:
    return moment.replace(tzinfo=dt.timezone.utc) if moment.tzinfo is None else moment.astimezone(dt.timezone.utc)


def _iso(moment: dt.datetime) -> str:
    return moment.isoformat(timespec="seconds")
