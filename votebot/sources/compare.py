"""A race's candidates side by side, for the Compare dialog.

The money sources already build each candidate's Breakdowns for their card; these helpers
pivot them. A category every candidate has ("Individuals", "$500 to $4,999") becomes a row
with a bar per candidate, and a list of names (donors, spenders) becomes a column per
candidate, with a name that turns up in more than one column flagged.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from ..matching import full_key
from ..models import Breakdown, CompareEntry, CompareRow, CompareSection, CompareValue, Share


def _merged(label_lists: Iterable[list[str]]) -> list[str]:
    """Every label once, each list's order kept: a label only some lists have goes right
    after the label it follows there."""
    merged: list[str] = []
    for labels in label_lists:
        previous: str | None = None
        for label in labels:
            if label not in merged:
                merged.insert(merged.index(previous) + 1 if previous is not None else 0, label)
            previous = label
    return merged


def row(
    label: str, amounts: dict[str, float | None], counts: dict[str, int | None] | None = None, *, counted: str | None = None
) -> CompareRow:
    """One figure for each candidate (keys in ballot order)."""
    counts = counts or {}
    return CompareRow(label=label, counted=counted, values=[
        CompareValue(candidate_key=key, amount=amount, count=counts.get(key)) for key, amount in amounts.items()])


def figures(title: str, rows: list[CompareRow], *, note: str | None = None) -> CompareSection | None:
    """Totals side by side; a row no candidate has anything in is left out."""
    kept = [r for r in rows if any(v.amount for v in r.values)]
    return CompareSection(title=title, note=note, rows=kept) if kept else None


def bars(title: str, per: dict[str, Breakdown | None], *, note: str | None = None) -> CompareSection | None:
    """Grouped bars from each candidate's breakdown (keys in ballot order). A candidate with
    the breakdown but not one of its categories has 0 of it; a candidate without the
    breakdown has no figure. Each breakdown's total is what that candidate's shares are of."""
    have = {key: b for key, b in per.items() if b and b.parts}
    if not have:
        return None
    parts = {key: {p.label: p for p in b.parts} for key, b in have.items()}
    rows = []
    for label in _merged([p.label for p in b.parts] for b in have.values()):
        values = []
        for key in per:
            if key not in have:
                values.append(CompareValue(candidate_key=key))
                continue
            part = parts[key].get(label)
            values.append(CompareValue(candidate_key=key, amount=part.amount, count=part.count) if part
                          else CompareValue(candidate_key=key, amount=0.0))
        rows.append(CompareRow(label=label, values=values))
    totals = {key: b.total for key, b in have.items() if b.total}
    return CompareSection(title=title, note=note, rows=rows, totals=totals)


def named(breakdown: Breakdown | None) -> list[tuple[Share, str]]:
    """A breakdown's parts, each with its name to match on in other candidates' columns."""
    return [(part, full_key(part.label)) for part in (breakdown.parts if breakdown else [])]


def columns(
    title: str, per: dict[str, list[tuple[Share, str]]], *, note: str | None = None, counted: str = "donation"
) -> CompareSection | None:
    """A column per candidate of named entries, given as (entry, name to match on). An entry
    whose name is in another candidate's column says whose."""
    has = {key: entries for key, entries in per.items() if entries}
    if not has:
        return None
    owners: dict[str, list[str]] = defaultdict(list)
    for candidate, entries in has.items():
        for _, name in entries:
            if name and candidate not in owners[name]:
                owners[name].append(candidate)

    def entry(share: Share, name: str, candidate: str) -> CompareEntry:
        others = [o for o in owners[name] if o != candidate] if name else []
        return CompareEntry(**share.model_dump(), shared_with=others, match_key=name if others else None)

    return CompareSection(
        title=title,
        note=note,
        counted=counted,
        columns={candidate: [entry(share, name, candidate) for share, name in entries] for candidate, entries in has.items()},
    )
