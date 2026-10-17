"""Attach every enabled source's cards to the ballot's candidates and races.

Each source builds SourceCards keyed by candidate (the money sources and polls also build
one per race, comparing its candidates); a new source only needs its cards() added to JOBS. The
frontend renders any card the same way, in the order they're attached: JOBS' order is the order
of the tabs in Details and of the badges on a candidate's row, with the endorsement lists last.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from . import coverage
from .http_cache import UpstreamError
from .models import Race, SourceCard
from .offices import OfficeScope
from .settings import Sources
from .sources import (
    CardSet, SeatInfo, ballotpedia, fec, officeholders, polls, sos, tec, trackaipac, voteforpeace, wikidata,
)
from .sources.ballotpedia import BpBallot, BpRace
from .sources.endorsement_feeds import EndorsementFeed
from .sources.sos import Election, Lookups

if TYPE_CHECKING:
    from .ballot import Services

log = logging.getLogger("uvicorn.error")

UNAVAILABLE = {  # what the voter reads when a source's UpstreamError leaves its cards out
    fec.SOURCE: "The FEC isn't answering right now, so campaign money for federal races isn't shown.",
    polls.SOURCE: "FiftyPlusOne isn't answering right now, so polls aren't shown.",
    officeholders.SOURCE: "The lists of seat holders aren't answering right now, so who holds each seat isn't shown.",
    wikidata.SOURCE: "Wikidata isn't answering right now, so its profiles aren't shown.",
    ballotpedia.SOURCE: "Ballotpedia isn't answering right now, so city and school races aren't shown.",
}


@dataclass
class Context:
    """What the ballot found that the sources' cards need. ``sos_lookups`` is None when the ballot
    didn't come from Texas SOS; ``counterparts`` gives each race's own race on Ballotpedia's
    ballot (ballotpedia.counterparts)."""

    elections: dict[int, Election] = field(default_factory=dict)
    ballot_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    sos_lookups: Lookups | None = None
    bp_ballot: BpBallot | None = None
    counterparts: dict[str, BpRace] = field(default_factory=dict)
    day: dt.date | None = None
    scopes: dict[str, OfficeScope] = field(default_factory=dict)
    county: str | None = None
    city: str | None = None
    state: str | None = None


@dataclass
class Outcome:
    """What enrichment adds besides the cards: lines for the ballot."""

    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


async def _candidate_cards(found: Awaitable[dict[str, SourceCard]]) -> CardSet:
    return CardSet(candidates=await found)


def _sos(svc: Services, races: list[Race], ctx: Context, _sources: Sources) -> Awaitable[CardSet] | None:
    if not (ctx.sos_lookups and ctx.elections):
        return None
    candidates = [c for race in races for c in race.candidates]
    return _candidate_cards(sos.cards(svc.sos, ctx.elections, candidates, ctx.ballot_rows, ctx.sos_lookups))


def _ballotpedia(_svc: Services, races: list[Race], ctx: Context, _sources: Sources) -> Awaitable[CardSet] | None:
    if ctx.bp_ballot is None:
        return None
    return asyncio.to_thread(ballotpedia.cards, ctx.bp_ballot, races, ctx.counterparts)


Job = Callable[["Services", list[Race], Context, Sources], "Awaitable[CardSet] | None"]
JOBS: dict[str, Job] = {  # each source's cards, None when it has nothing to ask
    fec.SOURCE: lambda svc, races, ctx, _: fec.cards(svc.fec, races, ctx.day),
    tec.SOURCE: lambda svc, races, ctx, _: asyncio.to_thread(tec.cards, svc.tec, races, ctx.scopes, ctx.county, ctx.bp_ballot),
    sos.SOURCE: _sos,
    polls.SOURCE: lambda svc, races, ctx, _: polls.cards(svc.polls, races, ctx.day),
    wikidata.SOURCE: lambda svc, races, ctx, sources: wikidata.cards(
        svc.wikidata, races, ctx.scopes, ctx.county, ctx.bp_ballot, sources.enabled(ballotpedia.SOURCE)),
    ballotpedia.SOURCE: _ballotpedia,
    trackaipac.SOURCE: lambda svc, races, ctx, _: asyncio.to_thread(
        lambda: CardSet(candidates=trackaipac.cards(svc.trackaipac, races, ctx.state or "TX"))),
    voteforpeace.SOURCE: lambda svc, races, ctx, _: asyncio.to_thread(
        voteforpeace.cards, svc.voteforpeace, races, ctx.scopes, ctx.county, ctx.bp_ballot, ctx.city, ctx.state or "TX"),
    officeholders.SOURCE: lambda svc, races, ctx, _: officeholders.cards(
        svc.officeholders, races, ctx.scopes, ctx.county, ctx.bp_ballot, ctx.day, ctx.state or "TX"),
}


async def run(svc: Services, races: list[Race], sources: Sources, ctx: Context) -> Outcome:
    """Add cards in place; say what failed. Every source the voter has on is asked at once (the
    ones without I/O in a thread), and nothing touches the races until they've all answered. A
    source that only knows some states (coverage.ONLY_IN) isn't asked about another's ballot."""
    jobs: dict[str, Awaitable[CardSet]] = {}
    for source, job in JOBS.items():
        if not coverage.works_in(source, ctx.state):
            continue
        if sources.enabled(source) and (asked := job(svc, races, ctx, sources)) is not None:
            jobs[source] = asked
    lists = [found for found in svc.endorsements if sources.enabled(found.source)]
    for found in lists:
        jobs[found.source] = found.lookup(races, ctx.scopes, ctx.county, ctx.bp_ballot, ctx.state or "TX", ctx.city)
    unavailable = {**UNAVAILABLE, **{f.source: f.unavailable for f in lists if isinstance(f, EndorsementFeed)}}
    answers = dict(zip(jobs, await asyncio.gather(*jobs.values(), return_exceptions=True)))

    outcome = Outcome()
    seats: dict[str, SeatInfo] = {}
    candidates = [c for race in races for c in race.candidates]
    for source, cards in answers.items():
        if isinstance(cards, UpstreamError) and source in unavailable:
            log.warning("%s", cards)
            outcome.warnings.append(unavailable[source])
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
        seats.update(cards.seats)
    for race in races:
        if info := seats.get(race.key):
            _set_seat(race, info)
    return outcome


def _set_seat(race: Race, info: SeatInfo) -> None:
    """The race's holder, once every source has said who's the incumbent: a seat isn't open
    while any candidate is, and the incumbent doesn't also "hold it for their party"."""
    race.holder = info.holder
    race.open_seat = info.open and not any(c.incumbent for c in race.candidates)
    for candidate in race.candidates:
        candidate.party_holds_seat = candidate.key in info.party_holds and not candidate.incumbent
