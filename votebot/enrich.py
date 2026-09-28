"""Attach every enabled source's cards to the ballot's candidates and races.

Each source builds SourceCards keyed by candidate (the money sources also build one per
race, comparing its candidates); a new source only needs its own cards() added here. The
frontend renders any card the same way.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .http_cache import UpstreamError
from .models import Race
from .offices import OfficeScope
from .sources import CardSet, ballotpedia, fec, sos, tec, trackaipac
from .sources.ballotpedia import BpBallot
from .sources.sos import Election

if TYPE_CHECKING:
    from .ballot import Services


@dataclass
class Outcome:
    """What enrichment adds besides the cards: lines for the ballot, and which sources failed."""

    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)  # source id -> why it failed


async def run(
    svc: Services,
    races: list[Race],
    *,
    elections: dict[int, Election],
    ballot_rows: dict[str, dict[str, Any]],
    bp_ballot: BpBallot | None,
    use_sos: bool,
    use_trackaipac: bool,
    use_fec: bool = False,
    use_tec: bool = False,
    day: dt.date | None = None,
    scopes: dict[str, OfficeScope] | None = None,
    county: str | None = None,
) -> Outcome:
    """Add cards in place; say what failed."""
    candidates = [c for race in races for c in race.candidates]
    outcome = Outcome()
    per_source: list[CardSet] = []
    if use_sos and elections:
        try:
            per_source.append(CardSet(candidates=await sos.cards(svc.sos, elections, candidates, ballot_rows)))
        except UpstreamError as exc:
            outcome.warnings.append(f"Couldn't load Texas SOS candidate details ({exc}).")
    if bp_ballot is not None:
        per_source.append(CardSet(candidates=ballotpedia.cards(bp_ballot, races)))
    if use_trackaipac:
        per_source.append(CardSet(candidates=trackaipac.cards(svc.trackaipac, races)))
    if use_fec:
        try:
            per_source.append(await fec.cards(svc.fec, races, day))
        except fec.FecUnavailable as exc:
            outcome.errors[fec.SOURCE] = str(exc)
            outcome.warnings.append(f"Couldn't load FEC campaign finance ({exc}).")
    if use_tec:
        per_source.append(tec.cards(svc.tec, races, scopes or {}, county))

    for cards in per_source:
        outcome.notes += cards.notes
        outcome.warnings += cards.warnings
        for candidate in candidates:
            card = cards.candidates.get(candidate.key)
            if card:
                candidate.cards.append(card)
                if card.image and not candidate.photo_url:
                    candidate.photo_url = card.image
        for race in races:
            if race_card := cards.races.get(race.key):
                race.cards.append(race_card)
    return outcome
