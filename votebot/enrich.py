"""Attach every enabled source's cards to the ballot's candidates and races.

Each source builds SourceCards keyed by candidate (the money sources and polls also build
one per race, comparing its candidates); a new source only needs its own cards() added here. The
frontend renders any card the same way, in the order they're attached: CARD_ORDER is the order
of the tabs in Details and of the badges on a candidate's row.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable

from .models import Race, SourceCard
from .offices import OfficeScope
from .sources import CardSet, ballotpedia, fec, polls, sos, tec, trackaipac, voteforpeace
from .sources.ballotpedia import BpBallot, BpRace
from .sources.sos import Election, Lookups

if TYPE_CHECKING:
    from .ballot import Services

CARD_ORDER = (
    fec.SOURCE, tec.SOURCE, sos.SOURCE, polls.SOURCE, ballotpedia.SOURCE, trackaipac.SOURCE, voteforpeace.SOURCE,
)
UNAVAILABLE: dict[str, tuple[type[Exception], str]] = {
    fec.SOURCE: (fec.FecUnavailable, "Couldn't load FEC campaign finance ({})."),
    polls.SOURCE: (polls.PollsUnavailable, "Couldn't load polls from FiftyPlusOne ({})."),
}


@dataclass
class Outcome:
    """What enrichment adds besides the cards: lines for the ballot, and which sources failed."""

    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)  # source id -> why it failed


async def _candidate_cards(found: Awaitable[dict[str, SourceCard]]) -> CardSet:
    return CardSet(candidates=await found)


async def run(
    svc: Services,
    races: list[Race],
    *,
    elections: dict[int, Election],
    ballot_rows: dict[str, dict[str, Any]],
    bp_ballot: BpBallot | None,
    sos_lookups: Lookups | None,
    use_trackaipac: bool,
    use_voteforpeace: bool = False,
    use_fec: bool = False,
    use_tec: bool = False,
    use_polls: bool = False,
    day: dt.date | None = None,
    scopes: dict[str, OfficeScope] | None = None,
    county: str | None = None,
    bp_counterparts: dict[str, BpRace] | None = None,
) -> Outcome:
    """Add cards in place; say what failed. ``sos_lookups`` is None when the ballot didn't
    come from Texas SOS; ``bp_counterparts`` gives each race's own race on Ballotpedia's
    ballot (ballotpedia.counterparts). Every source is asked at once (the ones without I/O
    in a thread), and nothing touches the races until they've all answered."""
    candidates = [c for race in races for c in race.candidates]
    jobs: dict[str, Awaitable[CardSet]] = {}
    if sos_lookups and elections:
        jobs[sos.SOURCE] = _candidate_cards(sos.cards(svc.sos, elections, candidates, ballot_rows, sos_lookups))
    if bp_ballot is not None:
        jobs[ballotpedia.SOURCE] = asyncio.to_thread(ballotpedia.cards, bp_ballot, races, bp_counterparts)
    if use_trackaipac:
        jobs[trackaipac.SOURCE] = asyncio.to_thread(lambda: CardSet(candidates=trackaipac.cards(svc.trackaipac, races)))
    if use_voteforpeace:
        jobs[voteforpeace.SOURCE] = asyncio.to_thread(
            voteforpeace.cards, svc.voteforpeace, races, scopes or {}, county, bp_ballot
        )
    if use_fec:
        jobs[fec.SOURCE] = fec.cards(svc.fec, races, day)
    if use_tec:
        jobs[tec.SOURCE] = asyncio.to_thread(tec.cards, svc.tec, races, scopes or {}, county, bp_ballot)
    if use_polls:
        jobs[polls.SOURCE] = polls.cards(svc.polls, races, day)
    answers = dict(zip(jobs, await asyncio.gather(*jobs.values(), return_exceptions=True)))

    outcome = Outcome()
    for source in CARD_ORDER:
        if source not in answers:
            continue
        cards = answers[source]
        if source in UNAVAILABLE and isinstance(cards, UNAVAILABLE[source][0]):
            outcome.errors[source] = str(cards)
            outcome.warnings.append(UNAVAILABLE[source][1].format(cards))
            continue
        if isinstance(cards, BaseException):
            raise cards
        outcome.notes += cards.notes
        outcome.warnings += cards.warnings
        for candidate in candidates:
            card = cards.candidates.get(candidate.key)
            if card:
                candidate.cards.append(card)
                if card.image and not candidate.photo_url:
                    candidate.photo_url = card.image
            if candidate.key in cards.incumbents:
                candidate.incumbent = True
        for race in races:
            if race_card := cards.races.get(race.key):
                race.cards.append(race_card)
    return outcome
