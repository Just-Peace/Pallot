"""On-disk layout: registry.json, current.json, meta.json."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .models import CATEGORIES, ParsedRecord, make_seat

DATA_DIR_ENV = "TRACKAIPAC_CACHE_DIR"
PACKAGE_DATA_DIR = Path(__file__).resolve().parent / "data"
SCHEMA_VERSION = 2

# When one person's listings show different seats, the registry takes the sitting-member
# listing's; every listing still keeps its own seat as shown.
_IDENTITY_PRECEDENCE = ("congress", "endorsed", "watchlist")


def resolve_data_dir(data_dir: str | Path | None = None) -> Path:
    if data_dir is not None:
        return Path(data_dir)
    env = os.environ.get(DATA_DIR_ENV)
    return Path(env) if env else PACKAGE_DATA_DIR


class Paths:
    def __init__(self, root: Path):
        self.root = root
        self.registry = root / "registry.json"
        self.current = root / "current.json"
        self.meta = root / "meta.json"

    def current_rows(self) -> list[dict[str, Any]] | None:
        """The rows of the last refresh, read back out of current.json (None before any)."""
        document = read_json(self.current)
        if document is None:
            return None
        return [listing for candidate in document.get("candidates", []) for listing in candidate.get("listings", [])]


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_json(path: Path, obj: Any) -> None:
    """Atomic write: temp file in the same directory, then os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(dump_json(obj))
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load_meta(paths: Paths) -> dict[str, Any]:
    meta = read_json(paths.meta, default={}) or {}
    meta.setdefault("schema_version", SCHEMA_VERSION)
    meta.setdefault("last_refresh", None)
    meta.setdefault("last_checked", None)
    meta.setdefault("source_hashes", {})
    return meta


def snapshot_rows(records: Iterable[ParsedRecord]) -> list[dict[str, Any]]:
    """Rows in page order (sources in fetch order). Array order carries page order, so an
    inserted candidate shows up as one inserted row in a git diff."""
    return [r.snapshot_row() for r in records]


def upsert_registry(registry: dict[str, dict[str, Any]], records: Iterable[ParsedRecord]) -> dict[str, dict[str, Any]]:
    """Return a new registry. Ids seen in this fetch get their identity exactly as this
    fetch shows it; ids no longer listed keep their last-seen identity."""
    by_id: dict[str, list[ParsedRecord]] = {}
    for record in records:
        by_id.setdefault(record.candidate_id, []).append(record)

    updated = {cid: dict(ident) for cid, ident in registry.items()}
    for cid, recs in by_id.items():
        recs = sorted(recs, key=lambda r: _IDENTITY_PRECEDENCE.index(r.category))
        seat_source = next((r for r in recs if r.seat), None) or next((r for r in recs if r.state), recs[0])
        updated[cid] = {
            "name": recs[0].name,
            "state": seat_source.state,
            "district": seat_source.district,
            "chamber": seat_source.chamber,
            "party": next((r.party for r in recs if r.party), None),
        }
    return dict(sorted(updated.items()))


def build_current(registry: dict[str, dict[str, Any]], rows: list[dict[str, Any]], snapshot_name: str) -> dict[str, Any]:
    """Join the registry with one snapshot: one entry per person, holding every one of
    their snapshot rows unmodified (grouped by category, page order within)."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["candidate_id"], []).append(row)

    candidates = []
    for cid in sorted(grouped):
        listings = sorted(grouped[cid], key=lambda r: CATEGORIES.index(r["category"]))
        ident = registry.get(cid, {})
        candidates.append(
            {
                "candidate_id": cid,
                "name": ident.get("name"),
                "state": ident.get("state"),
                "district": ident.get("district"),
                "party": ident.get("party"),
                "chamber": ident.get("chamber"),
                "seat": make_seat(ident.get("state"), ident.get("district"), ident.get("chamber")),
                "categories": [c for c in CATEGORIES if any(r["category"] == c for r in listings)],
                "listings": listings,
            }
        )
    return {"snapshot": snapshot_name, "candidates": candidates}
