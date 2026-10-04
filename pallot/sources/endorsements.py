"""Organizations' endorsement lists, frozen: one JSON file per organization in
pallot/endorsements/, captured once and never fetched (no scraper, no Refresh). Each file is its
own source, found in the folder at startup, so adding an organization is adding its file: it gets
a switch and a row in Settings, a card on each candidate it endorses, and a condition in Pick by
rule. Entries are matched to the ballot's races like Vote for Peace's (seats.py). A live feed
(endorsement_feeds.py) builds the same EndorsementList from an organization's own JSON instead.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Collection

from ..matching import NameIndex
from ..models import Badge, Fact, Link, Match, Race, SourceCard, Tone
from ..offices import OfficeScope
from ..text import display_date
from . import CardSet, RefreshFailed
from .ballotpedia import BpBallot
from .seats import match_entries, office_text, without_title

ENDORSEMENTS_DIR = Path(__file__).resolve().parent.parent / "endorsements"
FLAG = "endorsement"  # on every card from a list, for Pick by rule
_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_STATE = re.compile(r"^[A-Z]{2}$")
_URL = re.compile(r"^https?://\S+$")
_LIST_FIELDS = ("source", "label", "organization", "url", "captured", "description", "candidates")
_ENTRY_REQUIRED = ("name", "state", "office")
_ENTRY_OPTIONAL = ("district", "jurisdiction", "party", "note", "url")
_FEDERAL = re.compile(r"^U\.?\s?S\.?\s", re.IGNORECASE)


class BadList(ValueError):
    """A file in the folder that isn't a valid list; the message names the file and the field."""


@dataclass
class EndorsementList:
    """One organization's list. ``entries`` are its candidates in seats.entry_seats' shape
    (``office_title``, ``level``), each with its place in the file as ``entry_id``. ``live``: a
    feed's copy, whose ``captured`` is the day it was fetched."""

    source: str
    label: str
    organization: str
    url: str
    captured: str  # ISO date
    description: str
    entries: list[dict[str, Any]]
    live: bool = False
    _indexes: dict[str, NameIndex] = field(default_factory=dict, repr=False)
    busy = False  # never downloads

    def __post_init__(self) -> None:
        by_state: dict[str, NameIndex] = defaultdict(NameIndex)
        for entry in self.entries:
            by_state[entry["state"]].add(without_title(entry["name"]), entry)
        self._indexes = dict(by_state)

    def index(self, state: str) -> NameIndex:
        return self._indexes.get(state) or NameIndex()

    def count(self, state: str | None = None) -> int:
        return sum(1 for entry in self.entries if state is None or entry["state"] == state)

    def states(self) -> int:
        return len(self._indexes)

    # -- Settings (KeptSource) ----------------------------------------------------------------

    def notice(self) -> tuple[str, Tone]:
        return (f"A frozen list from [{self.organization}]({self.url}), captured on {display_date(self.captured)}. "
                "It came with Pallot, and Pallot never fetches it."), "info"

    def details(self) -> list[Fact]:
        return [
            Fact(label="Captured", value=display_date(self.captured) or self.captured),
            Fact(label="Texas candidates", value=f"{self.count('TX'):,}"),
            Fact(label="All candidates", value=f"{self.count():,} in {self.states()} {'state' if self.states() == 1 else 'states'}"),
        ]

    def size(self) -> int:
        return 0  # nothing in data/: the file is part of Pallot

    def refresh_size(self) -> int | None:
        return None

    async def refresh(self) -> str:
        raise RefreshFailed(f"{self.label}'s list is frozen as captured; there's nothing to refresh.")

    def clear(self) -> str:
        return f"{self.label}'s list comes with Pallot; nothing was saved to clear."

    # -- the ballot ---------------------------------------------------------------------------

    async def lookup(
        self,
        races: list[Race],
        scopes: dict[str, OfficeScope],
        county: str | None,
        bp_ballot: BpBallot | None = None,
        state: str = "TX",
    ) -> CardSet:
        """cards() in a thread, as enrich.run asks every list and feed."""
        return await asyncio.to_thread(self.cards, races, scopes, county, bp_ballot, state)

    def cards(
        self,
        races: list[Race],
        scopes: dict[str, OfficeScope],
        county: str | None,
        bp_ballot: BpBallot | None = None,
        state: str = "TX",
    ) -> CardSet:
        """Cards for the candidates it endorses in the ballot's state, in any race (seats.match_entries).
        The file keeps every state; only the ballot's is matched."""
        found = match_entries(self.index(state), races, scopes, county, bp_ballot, source=self.label, entry_id="entry_id")
        return CardSet(candidates={key: self.card(entry, match) for key, (entry, match) in found.items()})

    def card(self, entry: dict[str, Any], match: Match) -> SourceCard:
        page = entry.get("url") or self.url
        facts = [
            Fact(label="Endorsed by", value=self.organization, url=self.url),
            Fact(label="Office on the list", value=office_text(entry)),
        ]
        if entry.get("party"):
            facts.append(Fact(label="Party on the list", value=entry["party"]))
        facts.append(Fact(label="List fetched" if self.live else "List captured",
                          value=display_date(self.captured) or self.captured))
        return SourceCard(
            source=self.source,
            label=self.label,
            description=self.description,
            url=page,
            as_of=self.captured,
            match=match,
            badges=[Badge(text=f"Endorsed by {self.label}", tone="good", url=page,
                          hint=f"On {self.organization}'s endorsement list")],
            facts=facts,
            quotes=[entry["note"]] if entry.get("note") else [],
            links=[Link(label=f"{self.label}'s endorsement list", url=self.url)] if page != self.url else [],
            flags=[FLAG],
        )


def _text(value: Any, where: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise BadList(f"{where} must be {'text or null' if optional else 'non-empty text'}")
    return value.strip()


def read_entry(raw: Any, number: int, where: str) -> dict[str, Any]:
    """One candidate in a file's (or a feed adapter's) shape, checked, in seats.entry_seats' shape."""
    where = f"{where}: candidates[{number}]"
    if not isinstance(raw, dict):
        raise BadList(f"{where} must be an object")
    if unknown := set(raw) - {*_ENTRY_REQUIRED, *_ENTRY_OPTIONAL}:
        raise BadList(f"{where} has unknown fields: {', '.join(sorted(unknown))}")
    name, state, office = (_text(raw.get(key), f"{where}.{key}") for key in _ENTRY_REQUIRED)
    if not _STATE.match(state or ""):
        raise BadList(f"{where}.state must be a two-letter postal code, as \"TX\"")
    district = raw.get("district")
    if isinstance(district, bool) or not isinstance(district, (str, int, type(None))):
        raise BadList(f"{where}.district must be text, a number or null")
    jurisdiction, party, note, url = (_text(raw.get(key), f"{where}.{key}", optional=True)
                                      for key in ("jurisdiction", "party", "note", "url"))
    if url and not _URL.match(url):
        raise BadList(f"{where}.url must be an http(s) link")
    return {
        "entry_id": number, "name": name, "state": state, "office_title": office,
        "district": (str(district).strip() or None) if district is not None else None,
        "jurisdiction": jurisdiction,
        "level": "county" if jurisdiction else "federal" if _FEDERAL.match(office or "") else None,
        "party": party, "note": note, "url": url,
    }


def parse(path: Path) -> EndorsementList:
    """One organization's file, checked field by field (DEVELOPMENT.md has the format)."""
    where = path.name
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise BadList(f"{where} isn't valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise BadList(f"{where} must hold one object")
    if missing := [key for key in _LIST_FIELDS if key not in raw]:
        raise BadList(f"{where} is missing {', '.join(missing)}")
    if unknown := set(raw) - set(_LIST_FIELDS):
        raise BadList(f"{where} has unknown fields: {', '.join(sorted(unknown))}")
    source, label, organization, url, captured, description = (
        _text(raw[key], f"{where}: {key}") for key in _LIST_FIELDS[:-1]
    )
    if source != path.stem or not _ID.match(source or ""):
        raise BadList(f"{where}: source must be the file's name without .json, in lowercase letters, digits and _")
    if not _URL.match(url or ""):
        raise BadList(f"{where}: url must be an http(s) link")
    try:
        dt.date.fromisoformat(captured or "")
    except ValueError as exc:
        raise BadList(f"{where}: captured must be a date, as \"2026-10-04\"") from exc
    candidates = raw["candidates"]
    if not isinstance(candidates, list) or not candidates:
        raise BadList(f"{where}: candidates must be a list with at least one candidate")
    return EndorsementList(
        source=source, label=label, organization=organization, url=url, captured=captured, description=description,
        entries=[read_entry(entry, number, where) for number, entry in enumerate(candidates)],
    )


def load_all(directory: Path, reserved: Collection[str] = ()) -> list[EndorsementList]:
    """Every list in ``directory`` (none if it doesn't exist), by label. A list whose source is
    another source's id (``reserved``) is refused, as is any file that isn't a valid list."""
    lists = [parse(path) for path in sorted(directory.glob("*.json"))] if directory.is_dir() else []
    for found in lists:
        if found.source in reserved:
            raise BadList(f"{found.source}.json: {found.source} is already another source's id")
    return sorted(lists, key=lambda found: found.label.lower())
