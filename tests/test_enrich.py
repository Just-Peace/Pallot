"""enrich.run: every source is asked at once, and their cards come back in the order of the
tabs in Details, whichever answers first."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from pallot import enrich
from pallot.models import Candidate, Race, SourceCard
from pallot.sources import CardSet, fec, polls

pytestmark = pytest.mark.anyio


def senate() -> Race:
    return Race(key="sos:1:1", name="U.S. Senator", group="federal", source="sos", seat="TX-SEN",
                candidates=[Candidate(key="sos:1:1:0", name="Jane Doe")])


def cards_from(source: str, races: list[Race]) -> CardSet:
    return CardSet(candidates={c.key: SourceCard(source=source, label=source) for r in races for c in r.candidates})


async def run(races: list[Race]) -> enrich.Outcome:
    return await enrich.run(
        SimpleNamespace(fec=None, polls=None), races, elections={}, ballot_rows={}, bp_ballot=None, sos_lookups=None,
        use_trackaipac=False, use_fec=True, use_polls=True,
    )


async def test_sources_are_asked_at_once_and_cards_keep_their_order(monkeypatch):
    started = {fec.SOURCE: asyncio.Event(), polls.SOURCE: asyncio.Event()}

    def fake(source: str, other: str):
        async def cards(_svc, races, _day):
            started[source].set()
            await asyncio.wait_for(started[other].wait(), 2)  # times out unless the other one is running too
            if source == fec.SOURCE:
                await asyncio.sleep(0.02)  # the FEC answers last, but its tab still comes first
            return cards_from(source, races)
        return cards

    monkeypatch.setattr(fec, "cards", fake(fec.SOURCE, polls.SOURCE))
    monkeypatch.setattr(polls, "cards", fake(polls.SOURCE, fec.SOURCE))
    race = senate()
    outcome = await run([race])
    assert [card.source for card in race.candidates[0].cards] == [fec.SOURCE, polls.SOURCE]
    assert (outcome.errors, outcome.warnings) == ({}, [])


async def test_a_source_that_cant_answer_is_a_warning(monkeypatch):
    async def fec_cards(_svc, races, _day):
        return cards_from(fec.SOURCE, races)

    async def polls_down(*_args):
        raise polls.PollsUnavailable("HTTP 403")

    monkeypatch.setattr(fec, "cards", fec_cards)
    monkeypatch.setattr(polls, "cards", polls_down)
    race = senate()
    outcome = await run([race])
    assert [card.source for card in race.candidates[0].cards] == [fec.SOURCE]
    assert outcome.errors == {polls.SOURCE: "HTTP 403"}
    assert outcome.warnings == ["Couldn't load polls from FiftyPlusOne (HTTP 403)."]


async def test_an_unexpected_error_still_fails_the_lookup(monkeypatch):
    async def broken(*_args):
        raise RuntimeError("bug")

    monkeypatch.setattr(fec, "cards", broken)
    monkeypatch.setattr(polls, "cards", broken)
    with pytest.raises(RuntimeError):
        await run([senate()])
