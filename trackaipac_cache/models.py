"""Shared constants and data types."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date, datetime
from pathlib import Path
from typing import Any

BASE_URL = "https://www.trackaipac.com"

SOURCE_URLS: dict[str, str] = {
    "candidates": f"{BASE_URL}/candidates",
    "endorsements": f"{BASE_URL}/endorsements",
    "congress": f"{BASE_URL}/congress",
}

SOURCE_CATEGORIES: dict[str, str] = {
    "candidates": "watchlist",
    "endorsements": "endorsed",
    "congress": "congress",
}

CATEGORIES: tuple[str, ...] = ("watchlist", "endorsed", "congress")

STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia", "PR": "Puerto Rico", "GU": "Guam", "VI": "U.S. Virgin Islands",
    "AS": "American Samoa", "MP": "Northern Mariana Islands",
}


def make_seat(state: str | None, district: str | None, chamber: str | None) -> str | None:
    """"TX-23" / "TX-SEN", or None when the page doesn't pin the seat down."""
    if not state or not chamber:
        return None
    if chamber == "senate":
        return f"{state}-SEN"
    return f"{state}-{district}" if district else None


@dataclass(frozen=True)
class ParsedRecord:
    """One list item on one source page, exactly as shown.

    ``lines`` is the item's text verbatim (markdown links kept); every other field is
    parsed from it and is None/empty when the page does not show that value.
    """

    candidate_id: str
    source: str
    category: str
    section: str | None
    name: str
    title: str | None
    seat_text: str | None
    state: str | None
    district: str | None
    chamber: str | None
    party: str | None
    incumbent: bool | None
    israel_lobby_total: int | None = None
    donations: int | None = None
    ie: int | None = None
    pacs: tuple[str, ...] = ()
    election_date: str | None = None
    campaign_url: str | None = None
    donate_url: str | None = None
    notes: tuple[str, ...] = ()
    lines: tuple[str, ...] = ()

    @property
    def seat(self) -> str | None:
        return make_seat(self.state, self.district, self.chamber)

    def identity(self) -> dict[str, Any]:
        """Registry fields."""
        return {
            "name": self.name,
            "state": self.state,
            "district": self.district,
            "party": self.party,
            "chamber": self.chamber,
        }

    def snapshot_row(self) -> dict[str, Any]:
        """History-file row."""
        return {
            "candidate_id": self.candidate_id,
            "source": self.source,
            "category": self.category,
            "section": self.section,
            "name": self.name,
            "title": self.title,
            "seat_text": self.seat_text,
            "seat": self.seat,
            "state": self.state,
            "district": self.district,
            "chamber": self.chamber,
            "party": self.party,
            "incumbent": self.incumbent,
            "israel_lobby_total": self.israel_lobby_total,
            "donations": self.donations,
            "ie": self.ie,
            "pacs": list(self.pacs),
            "election_date": self.election_date,
            "campaign_url": self.campaign_url,
            "donate_url": self.donate_url,
            "notes": list(self.notes),
            "lines": list(self.lines),
        }


@dataclass(frozen=True)
class Listing:
    """One snapshot row: a person as listed on one page."""

    candidate_id: str
    source: str
    category: str
    section: str | None
    name: str
    title: str | None
    seat_text: str | None
    seat: str | None
    state: str | None
    district: str | None
    chamber: str | None
    party: str | None
    incumbent: bool | None
    israel_lobby_total: int | None
    donations: int | None
    ie: int | None
    pacs: tuple[str, ...]
    election_date: str | None
    campaign_url: str | None
    donate_url: str | None
    notes: tuple[str, ...]
    lines: tuple[str, ...]

    @classmethod
    def _kwargs(cls, row: dict[str, Any]) -> dict[str, Any]:
        kwargs = {f.name: row.get(f.name) for f in fields(Listing)}
        for name in ("pacs", "notes", "lines"):
            kwargs[name] = tuple(row.get(name) or ())
        return kwargs

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Listing:
        return Listing(**cls._kwargs(row))


@dataclass(frozen=True)
class Snapshot(Listing):
    """A listing as it appeared in one history file."""

    date: date

    @classmethod
    def from_history(cls, snapshot_date: date, row: dict[str, Any]) -> Snapshot:
        return cls(**Listing._kwargs(row), date=snapshot_date)


@dataclass(frozen=True)
class Candidate:
    """A person in current.json with every listing they have, unmodified."""

    candidate_id: str
    name: str
    state: str | None
    district: str | None
    party: str | None
    chamber: str | None
    seat: str | None
    categories: tuple[str, ...]
    listings: tuple[Listing, ...]

    def listing(self, category: str) -> Listing | None:
        """First listing in ``category`` (a person can be listed more than once on a page)."""
        return next((item for item in self.listings if item.category == category), None)

    def listings_in(self, category: str) -> tuple[Listing, ...]:
        return tuple(item for item in self.listings if item.category == category)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Candidate:
        return cls(
            candidate_id=d["candidate_id"],
            name=d["name"],
            state=d.get("state"),
            district=d.get("district"),
            party=d.get("party"),
            chamber=d.get("chamber"),
            seat=d.get("seat"),
            categories=tuple(d.get("categories", ())),
            listings=tuple(Listing.from_row(row) for row in d.get("listings", ())),
        )


@dataclass(frozen=True)
class RefreshResult:
    """Outcome of refresh(). status is "updated", "no_changes" or "would_update" (dry run)."""

    status: str
    checked_at: datetime
    changed_sources: tuple[str, ...] = ()
    record_counts: dict[str, int] = field(default_factory=dict)
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    modified: dict[str, tuple[str, ...]] = field(default_factory=dict)
    snapshot_path: Path | None = None
    warnings: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return self.status != "no_changes"

    def summary(self) -> str:
        if self.status == "no_changes":
            head = "no changes"
        else:
            verb = "updated" if self.status == "updated" else "would update"
            head = (
                f"{verb} {self.snapshot_path.name if self.snapshot_path else ''}: "
                f"sources changed: {', '.join(self.changed_sources) or 'none (forced)'}; "
                f"{len(self.added)} added, {len(self.removed)} removed, {len(self.modified)} modified"
            )
        counts = ", ".join(f"{k}={v}" for k, v in self.record_counts.items())
        lines = [head, f"records: {counts}"] if counts else [head]
        lines += [f"note: {w}" for w in self.warnings]
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.summary()
