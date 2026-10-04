"""Shared constants and data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_URL = "https://voteforpeace.info"
SOURCE_URL = f"{BASE_URL}/candidates"

# The site's rating -> how it labels it on a candidate's page.
RATINGS: dict[str, str] = {"vote": "Ally", "reject": "Opposed", "neutral": "Neutral"}


@dataclass(frozen=True)
class Endorsement:
    organization: str
    type: str | None = None
    notes: str | None = None
    link: str | None = None

    def row(self) -> dict[str, Any]:
        return {"organization": self.organization, "type": self.type, "notes": self.notes, "link": self.link}


@dataclass(frozen=True)
class Article:
    title: str | None
    url: str | None
    description: str | None

    def row(self) -> dict[str, Any]:
        return {"title": self.title, "url": self.url, "description": self.description}


@dataclass(frozen=True)
class ParsedRecord:
    """One candidate on the All Candidates page, as the site's own data lists them.

    Text is kept as the site wrote it, except ``notes``: the site's notes are sometimes HTML,
    so they're stored as plain text (paragraphs on their own lines).
    """

    candidate_id: str
    name: str
    slug: str | None
    url: str | None
    state: str | None
    section: str | None
    party: str | None
    rating: str | None
    office_title: str | None
    district: str | None
    level: str | None
    jurisdiction: str | None
    election_date: str | None
    election_label: str | None
    election_stage: str | None
    election_result: str | None
    featured_text: str | None = None
    notes: str | None = None
    endorsements: tuple[Endorsement, ...] = ()
    articles: tuple[Article, ...] = ()

    def snapshot_row(self) -> dict[str, Any]:
        """History-file row."""
        return {
            "candidate_id": self.candidate_id,
            "name": self.name,
            "slug": self.slug,
            "url": self.url,
            "state": self.state,
            "section": self.section,
            "party": self.party,
            "rating": self.rating,
            "office_title": self.office_title,
            "district": self.district,
            "level": self.level,
            "jurisdiction": self.jurisdiction,
            "election_date": self.election_date,
            "election_label": self.election_label,
            "election_stage": self.election_stage,
            "election_result": self.election_result,
            "featured_text": self.featured_text,
            "notes": self.notes,
            "endorsements": [e.row() for e in self.endorsements],
            "articles": [a.row() for a in self.articles],
        }


@dataclass(frozen=True)
class RefreshResult:
    """Outcome of refresh(). status is "updated", "no_changes" or "would_update" (dry run)."""

    status: str
    checked_at: datetime
    record_count: int = 0
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
                f"{len(self.added)} added, {len(self.removed)} removed, {len(self.modified)} modified"
            )
        lines = [head, f"candidates: {self.record_count}"]
        lines += [f"note: {w}" for w in self.warnings]
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.summary()
