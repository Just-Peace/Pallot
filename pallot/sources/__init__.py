"""External data sources. Each module talks to one service through HttpCache (or, for
TrackAIPAC, Vote for Peace and the Texas Ethics Commission, a package that keeps a bundled snapshot) and
can build SourceCards for candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..models import Fact, SourceCard, Tone


@dataclass
class CardSet:
    """What a source adds to a ballot: cards keyed by candidate key and by race key (a race
    card compares the candidates), the candidates it says hold the seat (on an exact match),
    plus lines for the ballot's notes and warnings."""

    candidates: dict[str, SourceCard] = field(default_factory=dict)
    races: dict[str, SourceCard] = field(default_factory=dict)
    incumbents: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def arcgis_error(answer: Any) -> str | None:
    """Why an ArcGIS server's answer is an error, or None for a good one: it answers an error
    with a 200 and an ``error`` body (HttpCache.check_answers)."""
    error = answer.get("error") if isinstance(answer, dict) else None
    if error is None:
        return None
    if not isinstance(error, dict):
        return f"error: {error}"
    code, message = error.get("code"), error.get("message") or "no message"
    return f"error {code}: {message}" if code else f"error: {message}"


class RefreshFailed(Exception):
    """A refresh that changed nothing; its message is the whole sentence pallot-cache prints."""


class KeptSource(Protocol):
    """A source kept in files rather than HttpCache rows (the SBOE and precinct maps, the
    bundled snapshots). Settings asks it for its row's state (admin.py), and pallot-cache
    (maintain.py) to check, refresh and clear it, so a new one only needs its SourceInfo."""

    @property
    def busy(self) -> bool:
        """A download running in this process (Settings says so)."""

    def notice(self) -> tuple[str, Tone] | None:
        """One line for Settings: a download under way, a failure, or where its data stands."""

    def details(self) -> list[Fact]: ...

    def size(self) -> int:
        """Bytes on disk."""

    def stale(self) -> str | None:
        """Why a soft refresh (pallot-cache refresh) should fetch it now, or None: a map not
        downloaded yet, or one the portal lists a newer one of. A snapshot is never stale."""

    async def refresh(self) -> str:
        """What a refresh did, as a sentence; RefreshFailed when it changed nothing."""

    def clear(self) -> str:
        """Throw away what's kept and say what happens next, as a sentence."""
