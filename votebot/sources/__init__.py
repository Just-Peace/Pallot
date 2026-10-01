"""External data sources. Each module talks to one service through HttpCache (or, for
TrackAIPAC and the Texas Ethics Commission, a package that keeps a bundled snapshot) and
can build SourceCards for candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..models import Fact, SourceCard, Tone


@dataclass
class CardSet:
    """What a source adds to a ballot: cards keyed by candidate key and by race key (a race
    card compares the candidates), plus lines for the ballot's notes and warnings."""

    candidates: dict[str, SourceCard] = field(default_factory=dict)
    races: dict[str, SourceCard] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class RefreshFailed(Exception):
    """A Refresh that changed nothing; its message is the whole sentence for Settings."""


class KeptSource(Protocol):
    """A source kept in files rather than HttpCache rows (the SBOE and precinct maps, the
    bundled snapshots). Settings asks it for its row's state and actions (admin.py), so a new
    one only needs its SourceInfo."""

    @property
    def busy(self) -> bool:
        """A download running, which Refresh and Clear must wait for."""

    def notice(self) -> tuple[str, Tone] | None:
        """One line for Settings: a download under way, a failure, or where its data stands."""

    def details(self) -> list[Fact]: ...

    def size(self) -> int:
        """Bytes on disk."""

    def refresh_size(self) -> int | None:
        """Bytes a Refresh may download, for the confirm prompt's {size}; None if unknown."""

    async def refresh(self) -> str:
        """What a Refresh did, as a sentence; RefreshFailed when it changed nothing."""

    def clear(self) -> str:
        """Throw away what's kept and say what happens next, as a sentence."""
