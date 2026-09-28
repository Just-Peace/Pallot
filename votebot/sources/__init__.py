"""External data sources. Each module talks to one service through HttpCache (or, for
TrackAIPAC and the Texas Ethics Commission, a package that keeps a bundled snapshot) and
can build SourceCards for candidates."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import SourceCard


@dataclass
class CardSet:
    """What a source adds to a ballot: cards keyed by candidate key and by race key (a race
    card compares the candidates), plus lines for the ballot's notes and warnings."""

    candidates: dict[str, SourceCard] = field(default_factory=dict)
    races: dict[str, SourceCard] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
