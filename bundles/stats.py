"""stats(): every bundled snapshot's counts -> one Markdown table, with the change since a git ref,
written to README's "What the snapshots hold" (between MARKERS) and printed for the run's summary.

It reads only the repo's files: bundles/data/meta.json (the builders' counts), Texas SOS's candidate
lists (sos.json, by election), and TrackAIPAC's, Vote for Peace's and TEC's snapshots."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import registry, store
from .entry import CADENCES
from .refresh import DUE_SLACK

REPO_DIR = Path(__file__).resolve().parent.parent
MARKERS = ("<!-- source-stats:start -->", "<!-- source-stats:end -->")
SOS_CANDIDATES = "/findQualifiedCandidates"

Reader = Callable[[str], Any]  # a repo-relative path -> its JSON, or None when there's none


@dataclass(frozen=True)
class Row:
    """One source's line: its candidates (a total under "", then its breakdown) and its other figures."""

    key: str
    title: str
    cadence: str
    candidates: dict[str, int] = field(default_factory=dict)
    other: dict[str, int] = field(default_factory=dict)
    refreshed: str | None = None  # when its data last changed
    checked: str | None = None  # when it was last asked


BUNDLES: dict[str, tuple[str, dict[str, tuple[str, str]]]] = {
    "fec": ("FEC", {"candidates": ("c", ""), "races": ("o", "races")}),
    "fec_races": ("FEC race lists, other states", {"races": ("o", "races"), "states": ("o", "states")}),
    "sos": ("Texas SOS candidate lists", {"candidates": ("c", ""), "elections": ("o", "elections")}),
    "sos_ballot_order": ("Texas SOS ballot orders", {"ballot_orders": ("o", "county ballot orders"),
                                                     "elections": ("o", "elections"),
                                                     "server_errors": ("w", "counties left out")}),
    "officeholders": ("Seat holders", {"congress": ("o", "Texas members of Congress"),
                                       "legislature": ("o", "Texas legislators")}),
    "wikidata": ("Wikidata", {"people": ("o", "Texas officeholders"), "with_seats": ("o", "with their seat")}),
    "tigerweb": ("TIGERweb district outlines", {"cd": ("o", "U.S. House"), "sd": ("o", "State Senate"),
                                                "hd": ("o", "State House"), "missing": ("w", "missing")}),
    "county_precincts": ("County precinct records", {"counties": ("o", "counties"), "missing": ("w", "left out")}),
    "polls": ("FiftyPlusOne polls", {"senate": ("o", "Texas Senate polls"), "house": ("o", "Texas House polls"),
                                     "governor": ("o", "Texas Governor polls")}),
    "mupac": ("Muslims United PAC", {"candidates": ("c", ""), "texas": ("c", "Texas")}),
    "cair": ("CAIR Action", {"candidates": ("c", ""), "texas": ("c", "Texas")}),
    "emgage": ("Emgage PAC", {"candidates": ("c", ""), "texas": ("c", "Texas")}),
}
SKIP = {"answers", "answers_hash", "last_checked", "last_refresh"}


def disk(root: Path) -> Reader:
    return lambda path: store.read_json(root / path)


def at_ref(root: Path, ref: str) -> Reader:
    """The files as committed at ``ref``; None for a file it doesn't have (or no git)."""
    def read(path: str) -> Any:
        try:
            done = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=root, capture_output=True, check=False)
        except OSError:
            return None
        return json.loads(done.stdout) if done.returncode == 0 else None
    return read


def election_name(name: str) -> str:
    return " ".join(word if word.isdigit() else word.capitalize() for word in name.split())


def sos_by_election(read: Reader) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for answer in (read("bundles/data/sos.json") or {}).get("answers") or []:
        if answer["request"]["url"].endswith(SOS_CANDIDATES):
            for row in answer["value"] or []:
                counts[election_name(row.get("txElectionName") or "Unnamed election")] += 1
    return dict(sorted(counts.items()))


def bundle_rows(read: Reader) -> list[Row]:
    meta = ((read("bundles/data/meta.json") or {}).get("sources")) or {}
    rows = []
    for entry in registry.BUNDLES:
        title, labels = BUNDLES.get(entry.name, (entry.name, {}))
        got = meta.get(entry.name, {})
        candidates: dict[str, int] = {}
        other: dict[str, int] = {}
        for key in [*(k for k in labels if k in got), *sorted(k for k in got if k not in labels and k not in SKIP)]:
            n = got[key]
            kind, label = labels.get(key, ("o", key.replace("_", " ")))
            if not isinstance(n, int) or (kind == "w" and not n):
                continue
            (candidates if kind == "c" else other)[label] = n
        if entry.name == "sos":
            candidates.update(sos_by_election(read))
        rows.append(Row(entry.name, title, entry.cadence, candidates, other,
                        got.get("last_refresh"), got.get("last_checked")))
    return rows


def level_name(level: str) -> str:
    return level.replace("_", " ").capitalize()


def cache_rows(read: Reader) -> list[Row]:
    rows = []
    aipac = (read("trackaipac_cache/data/current.json") or {}).get("candidates") or []
    meta = read("trackaipac_cache/data/meta.json") or {}
    chambers = Counter((c.get("chamber") or "other").capitalize() for c in aipac)
    rows.append(Row("trackaipac", "TrackAIPAC", "daily",
                    {"": len(aipac), "Texas": sum(c.get("state") == "TX" for c in aipac), **dict(sorted(chambers.items()))},
                    {}, meta.get("last_refresh"), meta.get("last_checked")))
    peace = (read("voteforpeace_cache/data/current.json") or {}).get("candidates") or []
    meta = read("voteforpeace_cache/data/meta.json") or {}
    levels = Counter(level_name(c.get("level") or "other") for c in peace)
    rows.append(Row("voteforpeace", "Vote for Peace", "daily",
                    {"": len(peace), "Texas": sum(c.get("state") == "TX" for c in peace),
                     **dict(levels.most_common())},
                    {}, meta.get("last_refresh"), meta.get("last_checked")))
    meta = read("tec_cache/data/meta.json") or {}
    counts = meta.get("counts") or {}
    rows.append(Row("tec", "Texas Ethics Commission", "daily",
                    {"": counts["snapshot_filers"]} if "snapshot_filers" in counts else {},
                    {label: counts[key] for key, label in (("contribs", "contributions"), ("reports", "reports"))
                     if key in counts},
                    meta.get("last_refresh"), meta.get("last_checked")))
    return rows


def rows(read: Reader) -> list[Row]:
    return bundle_rows(read) + cache_rows(read)


def change(n: int, before: int | None) -> str:
    return f" ({n - before:+,})" if before is not None and n != before else ""


def figures(now: dict[str, int], before: dict[str, int] | None, number_first: bool = False) -> str:
    """"**1,020** (+3) · Texas: 101 (+1)", or "39 races" with ``number_first``."""
    before = before or {}
    parts = []
    for label, n in now.items():
        text = f"**{n:,}**" if not label else f"{n:,} {label}" if number_first else f"{label}: {n:,}"
        parts.append(text + change(n, before.get(label)))
    return " · ".join(parts)


def day(stamp: str | None) -> str:
    return stamp[:10] if stamp else "never"


def overdue(row: Row, now: dt.datetime) -> bool:
    if not row.checked:
        return True
    return (now - dt.datetime.fromisoformat(row.checked)).total_seconds() > CADENCES[row.cadence] + DUE_SLACK


def table(current: list[Row], previous: list[Row], now: dt.datetime) -> list[str]:
    before = {row.key: row for row in previous}
    lines = ["| Source | Candidates | Also | Data changed | Checked |", "|---|---|---|---|---|"]
    for row in current:
        old = before.get(row.key)
        checked = day(row.checked) + (f" ⚠ overdue ({row.cadence})" if overdue(row, now) else "")
        lines.append(f"| {row.title} | {figures(row.candidates, old and old.candidates) or '—'} "
                     f"| {figures(row.other, old and old.other, number_first=True) or '—'} "
                     f"| {day(row.refreshed)} | {checked} |")
    return lines


def write_readme(path: Path, lines: list[str]) -> None:
    """Replace what's between MARKERS, keeping the file's own line endings."""
    with path.open(encoding="utf-8", newline="") as fh:
        text = fh.read()
    start, end = MARKERS
    if start not in text or end not in text:
        raise ValueError(f"{path} has no {start} … {end} section")
    eol = "\r\n" if "\r\n" in text else "\n"
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(head + start + eol + eol.join(lines) + eol + end + tail)


def stats(root: Path = REPO_DIR, since: str | None = None, now: dt.datetime | None = None) -> list[str]:
    """The table's lines, with each figure's change since ``since`` (a git ref) when it has one."""
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    return table(rows(disk(root)), rows(at_ref(root, since)) if since else [], now)
