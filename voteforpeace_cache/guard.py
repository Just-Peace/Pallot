"""Validation guard (runs before anything is written) and change detection.

The guard never removes or alters rows: it either lets the whole refresh through or
aborts it, so the cache is always a complete copy of what the site showed.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from .errors import ValidationError
from .models import RATINGS
from .parser import ParseResult

MIN_RECORDS = 100

# (field, minimum share of rows where it is set). A drop below these means the site's data
# changed shape and the parser would store mostly empty fields.
MIN_COVERAGE: list[tuple[str, float]] = [("state", 0.99), ("rating", 0.9), ("office_title", 0.9), ("url", 0.99)]


def validate(result: ParseResult) -> list[str]:
    """Raise ValidationError listing every problem, or return informational notes."""
    problems: list[str] = []
    notes: list[str] = []
    count = len(result.records)
    if count < MIN_RECORDS:
        problems.append(f"parsed {count} candidates, expected at least {MIN_RECORDS}")
    if result.unnamed:
        problems.append(f"{len(result.unnamed)} candidates have no name, e.g. {result.unnamed[0]!r}")
    for field_name, share in MIN_COVERAGE if count else []:
        have = sum(1 for r in result.records if getattr(r, field_name) is not None)
        if have / count < share:
            problems.append(
                f"only {have}/{count} candidates have {field_name} (need {share:.0%}); the site's data probably changed"
            )
    twice = [cid for cid, n in Counter(r.candidate_id for r in result.records).items() if n > 1]
    if twice:
        problems.append(f"{len(twice)} candidate ids are listed more than once, e.g. {twice[0]!r}")
    unknown = Counter(r.rating for r in result.records if r.rating is not None and r.rating not in RATINGS)
    if unknown:
        problems.append(f"unknown ratings: {', '.join(sorted(unknown))}; the site's ratings changed")
    for r in result.records:
        if r.rating is None:
            notes.append(f"{r.name!r} ({r.state}) has no rating; stored as shown")
    if problems:
        raise ValidationError(problems)
    return notes


def hash_rows(rows: list[dict[str, Any]]) -> str:
    """sha256 of exactly the rows that would be stored, in page order."""
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
