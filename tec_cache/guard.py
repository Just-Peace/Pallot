"""Checks that run before anything is written. A refresh that found implausibly little
(a renamed column, a truncated download) is aborted, so the snapshot is never replaced
with a broken one."""

from __future__ import annotations

from typing import Mapping

from .errors import ValidationError

# Floors well below what a real TEC export holds (tens of thousands of filers, hundreds
# of thousands of contributions a cycle).
MIN_COUNTS: dict[str, int] = {"filers": 2_000, "reports": 1_000, "contribs": 20_000, "snapshot_filers": 300}


def validate(counts: Mapping[str, int], minimums: Mapping[str, int] = MIN_COUNTS) -> list[str]:
    """Raise ValidationError listing every problem, or return informational notes."""
    problems = [
        f"{name}: {counts.get(name, 0):,} found, expected at least {floor:,}"
        for name, floor in minimums.items()
        if counts.get(name, 0) < floor
    ]
    if problems:
        raise ValidationError(problems)
    return [] if counts.get("dce") else ["no direct campaign expenditures naming candidates in this window"]
