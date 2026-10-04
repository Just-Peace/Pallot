"""Tie the same person together across sources that write names and seats differently.

Names: "JAMES TALARICO" in the state filing, "James Talarico" elsewhere, with middle
initials, suffixes and quoted nicknames varying. Seats: TrackAIPAC lists members of
Congress by their current seat, which Texas's 2025 redistricting changed for 2026, so the
name is the primary signal and the seat only corroborates it. Anything ambiguous is left
unmatched rather than guessed.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from .models import Match

_SUFFIXES = {"JR", "SR", "II", "III", "IV", "V"}
TITLES = {"MR", "MRS", "MS", "MISS", "DR", "HON", "HONORABLE", "SEN", "SENATOR", "REP", "GOV", "JUDGE", "REV"}
_NICKNAME = re.compile(r"[\"“”(][^\"“”()]*[\"“”)]")  # KENNETH "KEN" SMITH, JOHN (JACK) DOE
_SEAT = re.compile(r"\b([A-Z]{2})-(\d{1,2}|SEN|AL)\b")


def name_tokens(name: str) -> list[str]:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).upper()
    text = _NICKNAME.sub(" ", text).replace("'", "").replace("’", "")
    return [t for t in re.sub(r"[^A-Z0-9]+", " ", text).split() if t not in _SUFFIXES]


def full_key(name: str) -> str:
    return " ".join(name_tokens(name))


def short_key(name: str) -> str:
    """First and last name only, so middle names and initials don't block a match."""
    tokens = name_tokens(name)
    return f"{tokens[0]} {tokens[-1]}" if len(tokens) > 1 else " ".join(tokens)


def last_name(name: str) -> str:
    tokens = name_tokens(name)
    return tokens[-1] if tokens else ""


def last_first(name: str) -> str:
    """Filings write the last name first: "PAXTON, WARREN KENNETH JR." -> "WARREN KENNETH
    PAXTON JR.", "Lucero, Homero R. (Mr.)" -> "Homero R. Lucero". Titles (SEN, MR, "(The
    Honorable)") are dropped; a name without a comma is returned as it is."""
    last, comma, rest = _NICKNAME.sub(" ", name).partition(",")
    if not comma:
        return " ".join(name.split())
    words = [word for word in rest.split() if word.strip(".").upper() not in TITLES]
    suffixes = [word for word in words if word.strip(".").upper() in _SUFFIXES]
    return " ".join([*(w for w in words if w not in suffixes), *last.split(), *suffixes])


def seats_in(text: str | None) -> set[str]:
    """ "TX-35 (TX-37 2026)" -> {"TX-35", "TX-37"}."""
    return {
        f"{state}-{int(seat):02d}" if seat.isdigit() else f"{state}-{seat}"
        for state, seat in _SEAT.findall((text or "").upper())
    }


def initial_key(name: str) -> str:
    """First initial and last name, so "TOM BAKER" can meet "Thomas Baker"."""
    tokens = name_tokens(name)
    return f"{tokens[0][0]} {tokens[-1]}" if len(tokens) > 1 else " ".join(tokens)


FULL, FIRST_LAST, INITIAL = "full name", "first and last name", "first initial and last name"


@dataclass
class NameIndex:
    """People looked up by full name, then first + last name, then first initial + last name."""

    by_full: dict[str, list[Any]] = field(default_factory=lambda: defaultdict(list))
    by_short: dict[str, list[Any]] = field(default_factory=lambda: defaultdict(list))
    by_initial: dict[str, list[Any]] = field(default_factory=lambda: defaultdict(list))
    by_last: dict[str, list[Any]] = field(default_factory=lambda: defaultdict(list))

    def add(self, name: str, item: Any) -> None:
        self.by_full[full_key(name)].append(item)
        self.by_short[short_key(name)].append(item)
        self.by_initial[initial_key(name)].append(item)
        self.by_last[last_name(name)].append(item)

    def find(self, name: str) -> tuple[list[Any], str]:
        """Everyone with this name, and which rule found them ("" when nobody did)."""
        for rule, table, key in (
            (FULL, self.by_full, full_key(name)),
            (FIRST_LAST, self.by_short, short_key(name)),
            (INITIAL, self.by_initial, initial_key(name)),
        ):
            if found := table.get(key):
                return found, rule
        return [], ""


def match_unique(index: NameIndex, name: str) -> tuple[Any, Match] | None:
    """The one entry with this name, if exactly one exists."""
    found, how = index.find(name)
    if len(found) != 1:
        return None
    return found[0], Match(confidence="exact" if how == FULL else "likely", method=how)


def trackaipac_seats(person: dict[str, Any]) -> set[str]:
    """Every seat a TrackAIPAC entry mentions: its own, each listing's, and any in the
    listing's seat text (which is where a 2026 seat change shows up)."""
    seats = {person["seat"]} if person.get("seat") else set()
    for listing in person.get("listings", ()):
        if listing.get("seat"):
            seats.add(listing["seat"])
        seats |= seats_in(listing.get("seat_text"))
    return seats


def _once(items: list[Any]) -> list[Any]:
    """An entry indexed under two names (its nickname too) still counts once."""
    return list({id(item): item for item in items}.values())


def match_person(
    index: NameIndex,
    name: str,
    party: str | None,
    seat: str | None,
    *,
    seats_of: Callable[[Any], set[str]],
    party_of: Callable[[Any], str | None] = lambda item: None,
    source: str = "The source",
    seat_text: Callable[[Any], str | None] = lambda item: None,
    name_of: Callable[[Any], str | None] = lambda item: None,
) -> tuple[Any, Match] | None:
    """The one entry for this candidate: found by name, with the seat and party to confirm.

    Several people with the name are narrowed to the one in this seat. A unique name in
    another seat, or with another party, is only "likely". With no name match, a unique
    last name in this seat is "likely" too (nicknames, or a first name the source keeps
    as a middle name: Ken Paxton is "PAXTON, WARREN KENNETH" to the FEC).
    """
    found, how = index.find(name)
    found = _once(found)
    if len(found) > 1 and seat:
        found = [item for item in found if seat in seats_of(item)]
    if len(found) == 1:
        item = found[0]
        notes = []
        if seat and seat in seats_of(item):
            confidence = "exact" if how in (FULL, FIRST_LAST) else "likely"
            method = f"{how}, in the same seat"
        else:
            confidence, method = "likely", how
            notes.append(f"{source} lists them for {seat_text(item) or 'another seat'}")
        their_party = party_of(item)
        if party and their_party and their_party != party:
            confidence = "likely"
            notes.append(f"party differs ({source} says {their_party})")
        return item, Match(confidence=confidence, method=method, note="; ".join(notes) or None)
    if not found and seat:
        same_seat = [
            item
            for item in _once(index.by_last.get(last_name(name), []))
            if seat in seats_of(item) and (not party or party_of(item) in (None, party))
        ]
        if len(same_seat) == 1:
            listed = name_of(same_seat[0])
            return same_seat[0], Match(
                confidence="likely",
                method="last name, in the same seat",
                note=f"first names differ ({source} lists {listed}); check it's the same person" if listed
                else "first names differ; check it's the same person",
            )
    return None


def match_trackaipac(
    index: NameIndex, name: str, party: str | None, seat: str | None
) -> tuple[dict[str, Any], Match] | None:
    return match_person(
        index, name, party, seat,
        seats_of=trackaipac_seats,
        party_of=lambda person: person.get("party"),
        source="TrackAIPAC",
        seat_text=lambda person: person.get("seat"),
    )
