"""Validation guard (runs before anything is written) and per-source change detection.

The guard never removes or alters rows: it either lets the whole refresh through or
aborts it, so the cache is always a complete copy of what the site showed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .errors import ValidationError
from .parser import ParseResult

MIN_RECORDS: dict[str, int] = {"candidates": 20, "endorsements": 20, "congress": 400}

# (field, minimum share of rows where it is set). A drop below these means the page
# layout or its labels changed and the parser would store mostly empty fields.
MIN_COVERAGE: dict[str, list[tuple[str, float]]] = {
    "candidates": [("seat", 0.9), ("israel_lobby_total", 0.5)],
    "endorsements": [("seat", 0.9), ("donate_url", 0.8)],
    "congress": [("seat", 0.9), ("israel_lobby_total", 0.8)],
}


def validate(results: Mapping[str, ParseResult]) -> list[str]:
    """Raise ValidationError listing every problem, or return informational notes."""
    problems: list[str] = []
    notes: list[str] = []
    for source, result in results.items():
        count = len(result.records)
        floor = MIN_RECORDS.get(source, 1)
        if count < floor:
            problems.append(f"{source}: parsed {count} records, expected at least {floor}")

        if result.unnamed:
            problems.append(
                f"{source}: {len(result.unnamed)} list items have no name heading, e.g. {result.unnamed[0]!r}"
            )

        for field_name, share in MIN_COVERAGE.get(source, []) if count else []:
            have = sum(1 for r in result.records if getattr(r, field_name) is not None)
            if have / count < share:
                problems.append(
                    f"{source}: only {have}/{count} records have {field_name} (need {share:.0%}); "
                    "the page layout or labels probably changed"
                )

        for r in result.records:
            if r.seat_text is None:
                where = f"state {r.state} from section {r.section!r}" if r.state else "no state shown"
                notes.append(f"{source}: {r.name!r} is listed without a seat line; stored as shown ({where})")
    if problems:
        raise ValidationError(problems)
    return notes


def hash_rows(rows: list[dict[str, Any]]) -> str:
    """sha256 of exactly the rows that would be stored, in page order."""
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def changed_sources(new_hashes: Mapping[str, str], meta: Mapping[str, Any], snapshot_present: bool) -> list[str]:
    """Sources whose rows differ from the last write (all of them if no snapshot exists)."""
    if not snapshot_present:
        return list(new_hashes)
    old = meta.get("source_hashes", {})
    return [source for source, digest in new_hashes.items() if old.get(source) != digest]
