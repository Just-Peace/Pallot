"""Attach every enabled source's cards to the ballot's candidates.

Each source builds SourceCards keyed by candidate; a new source only needs its own
cards() added here. The frontend renders any card the same way.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .http_cache import UpstreamError
from .models import Race, SourceCard
from .sources import ballotpedia, sos, trackaipac
from .sources.ballotpedia import BpBallot
from .sources.sos import Election

if TYPE_CHECKING:
    from .ballot import Services


async def run(
    svc: Services,
    races: list[Race],
    *,
    elections: dict[int, Election],
    ballot_rows: dict[str, dict[str, Any]],
    bp_ballot: BpBallot | None,
    use_sos: bool,
    use_trackaipac: bool,
) -> list[str]:
    """Add cards in place; return warnings for sources that failed."""
    candidates = [c for race in races for c in race.candidates]
    warnings: list[str] = []
    per_source: list[dict[str, SourceCard]] = []
    if use_sos and elections:
        try:
            per_source.append(await sos.cards(svc.sos, elections, candidates, ballot_rows))
        except UpstreamError as exc:
            warnings.append(f"Couldn't load Texas SOS candidate details ({exc}).")
    if bp_ballot is not None:
        per_source.append(ballotpedia.cards(bp_ballot, races))
    if use_trackaipac:
        per_source.append(trackaipac.cards(svc.trackaipac, races))

    for cards in per_source:
        for candidate in candidates:
            card = cards.get(candidate.key)
            if card:
                candidate.cards.append(card)
                if card.image and not candidate.photo_url:
                    candidate.photo_url = card.image
    return warnings
