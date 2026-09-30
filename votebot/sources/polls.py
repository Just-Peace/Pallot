"""Public polls of Texas's U.S. Senate, U.S. House and Governor races, from FiftyPlusOne
(fiftyplusone.news).

Its API lists every poll of one kind of race nationwide, at most 500 to a page and with no
way to ask for one state, so we page through the lists the ballot needs and keep Texas's.
Every page goes through HttpCache for a day. The site refuses clients that don't look like
a browser (403), so requests carry a browser's User-Agent; a refusal pauses it for an hour.

A candidate's number is the median of their share across each pollster's latest poll of
this matchup. A question about another matchup (Cornyn instead of Paxton) is left out, and
a poll asked of both likely and registered voters counts once, as likely voters.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re
import statistics
from dataclasses import dataclass
from typing import Any, Callable

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec, UpstreamError
from ..matching import NameIndex, last_name
from ..models import Breakdown, Candidate, Fact, Link, Race, Share, SourceCard
from ..text import display_date, display_time, web_url
from . import CardSet

SOURCE = "polls"
LABEL = "Polls"
SITE_LABEL = "FiftyPlusOne"
DESCRIPTION = (
    "Public polls of Texas's races for U.S. Senate, U.S. House and Governor, from FiftyPlusOne (fiftyplusone.news). "
    "VoteBot downloads its nationwide poll lists, so nothing about you is sent."
)
API = "https://fiftyplusone.news/api/polls"
SITE = "https://fiftyplusone.news"
HEADERS = {  # the site answers 403 to anything that doesn't look like a browser
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36",
    "accept-language": "en-US,en;q=0.8",
}
REFUSALS = (403, 429)  # answers that pause FiftyPlusOne for Ttls.polls_backoff
PAGE = 500  # the most the API sends at once, whatever limit is asked for
STATE = "Texas"
SENATE, HOUSE, GOVERNOR = KINDS = ("senate_general", "house_general", "governor_general")
_OFFICES = {SENATE: "U.S. Senate", HOUSE: "U.S. House", GOVERNOR: "Governor"}
_POPULATIONS = {"lv": "likely voters", "rv": "registered voters", "v": "voters", "a": "adults"}  # best first
_RANK = {code: i for i, code in enumerate(_POPULATIONS)}


class PollsUnavailable(Exception):
    """FiftyPlusOne couldn't be asked (refused, paused, down) and nothing was cached."""


class Polls:
    def __init__(self, cache: HttpCache, ttl: Ttls, today: Callable[[], dt.date] = dt.date.today):
        self.cache = cache
        self.ttl = ttl
        self.today = today
        cache.pause_on(SOURCE, REFUSALS, ttl.polls_backoff)

    async def _page(self, kind: str, offset: int) -> list[dict[str, Any]]:
        params = {"offset": str(offset), "limit": str(PAGE), "filterValue": kind, "sortBy": "created_at", "dir": "DESC"}
        try:
            got = await self.cache.get_json(SOURCE, RequestSpec("GET", API, params=params, headers=HEADERS), ttl=self.ttl.polls)
        except UpstreamError as exc:
            if exc.until:
                raise PollsUnavailable(f"paused until {display_time(exc.until)} after FiftyPlusOne refused a request") from exc
            raise PollsUnavailable(str(exc).removeprefix(f"{SOURCE}: ")) from exc
        return list((got.value or {}).get("data") or [])

    async def polls(self, kind: str) -> list[dict[str, Any]]:
        """Every Texas poll of this kind of race. Pages are read until one comes back short
        (or brings nothing new, should the API ever ignore the offset)."""
        found: dict[str, dict[str, Any]] = {}
        offset = 0
        while True:
            page = await self._page(kind, offset)
            new = [row for row in page if str(row.get("poll_id")) not in found]
            for row in new:
                found[str(row.get("poll_id"))] = row
            if len(page) < PAGE or not new:
                break
            offset += PAGE
        return [row for row in found.values() if row.get("state") == STATE]


# -- which polls count ------------------------------------------------------------------


def kind_of(race: Race) -> str | None:
    """Which of FiftyPlusOne's lists has polls of this race, if any."""
    if race.seat == "TX-SEN":
        return SENATE
    if race.seat:
        return HOUSE
    if re.match(r"governor\b", race.name, re.I):
        return GOVERNOR
    return None


def _about(question: dict[str, Any], kind: str, race: Race) -> bool:
    if question.get("office_type") != _OFFICES[kind]:
        return False
    if kind != HOUSE:
        return True
    district = re.search(r"\d+", question.get("seat_name") or "")
    return bool(district) and int(district.group()) == int((race.seat or "").partition("-")[2])


def _matcher(race: Race) -> Callable[[str], str | None]:
    """A poll's name for someone -> the key of the ballot candidate it is, if exactly one."""
    index = NameIndex()
    for candidate in race.candidates:
        index.add(candidate.name, candidate.key)

    def key_of(name: str) -> str | None:
        found = list(dict.fromkeys(index.find(name)[0]))
        if len(found) != 1:  # nobody by that name: a last name only one of them has will do
            found = list(dict.fromkeys(index.by_last.get(last_name(name), [])))
        return found[0] if len(found) == 1 else None

    return key_of


@dataclass(frozen=True)
class Reading:
    """One poll's answer to one question about the race: each ballot candidate's percent."""

    poll_id: str
    pollster_id: str
    pollster: str
    url: str | None
    end: str
    population: str
    shares: dict[str, float]  # candidate key -> percent, largest first


def _reading(poll: dict[str, Any], question: dict[str, Any], key_of: Callable[[str], str | None]) -> Reading | None:
    """The question's answers as a Reading, or None when its two leading answers aren't both
    on this ballot (a matchup that won't happen)."""
    answers = sorted(
        (a for a in question.get("answers") or [] if (a.get("candidate") or {}).get("name") and isinstance(a.get("pct"), (int, float))),
        key=lambda a: -a["pct"],
    )
    keys = [key_of(a["candidate"]["name"]) for a in answers]
    if len(keys) < 2 or None in keys[:2] or keys[0] == keys[1]:
        return None
    shares: dict[str, float] = {}
    for answer, key in zip(answers, keys):
        if key and key not in shares:
            shares[key] = float(answer["pct"])
    pollster = poll.get("pollster") or {}
    return Reading(
        poll_id=str(poll.get("poll_id")),
        pollster_id=str(poll.get("pollster_id") or pollster.get("pollster_id") or pollster.get("name")),
        pollster=pollster.get("display_name") or pollster.get("name") or "Unnamed pollster",
        url=web_url(poll.get("url") or question.get("url")),
        end=poll.get("end_date") or "",
        population=question.get("population") or "",
        shares=shares,
    )


def readings(rows: list[dict[str, Any]], kind: str, race: Race, cycle: int) -> list[Reading]:
    """Each pollster's latest poll of this race's matchup, newest first. Of a poll's
    questions, the one asked of likely voters wins, then the one with more of the ballot."""
    key_of = _matcher(race)
    best: dict[str, tuple[tuple[int, int], Reading]] = {}  # poll id -> (rank, its reading)
    for poll in rows:
        for question in poll.get("questions") or []:
            if question.get("stage") != "general" or question.get("cycle") != cycle or not _about(question, kind, race):
                continue
            reading = _reading(poll, question, key_of)
            if reading is None:
                continue
            rank = (_RANK.get(reading.population, len(_RANK)), -len(reading.shares))
            if reading.poll_id not in best or rank < best[reading.poll_id][0]:
                best[reading.poll_id] = (rank, reading)
    latest: dict[str, Reading] = {}
    for _, reading in best.values():
        if reading.pollster_id not in latest or reading.end > latest[reading.pollster_id].end:
            latest[reading.pollster_id] = reading
    return sorted(latest.values(), key=lambda r: r.end, reverse=True)


def medians(race: Race, kept: list[Reading]) -> dict[str, float]:
    """Each candidate's median percent across the polls that asked about them."""
    out = {}
    for candidate in race.candidates:
        values = [r.shares[candidate.key] for r in kept if candidate.key in r.shares]
        if values:
            out[candidate.key] = statistics.median(values)
    return out


# -- cards ------------------------------------------------------------------------------


def _pct(value: float) -> str:
    return f"{round(value, 1):g}%"


def _span(kept: list[Reading]) -> str:
    first, last = display_date(kept[-1].end), display_date(kept[0].end)
    return f"{first} – {last}" if first != last else last or ""


def _method(kept: list[Reading]) -> str:
    if len(kept) == 1:
        return f"One poll so far: {kept[0].pollster}, {display_date(kept[0].end)}."
    return (f"The median of each pollster's latest poll: {len(kept)} polls, {_span(kept)}. "
            "Likely voters where a poll asked them.")


def race_card(race: Race, kept: list[Reading], middle: dict[str, float]) -> SourceCard:
    """The race's poll bar: each candidate's median, in ballot order."""
    parts = [
        Share(label=c.name, amount=round(middle[c.key], 1), candidate_key=c.key) if c.key in middle
        else Share(label=c.name, note="not in these polls", candidate_key=c.key)
        for c in race.candidates
    ]
    return SourceCard(
        source=SOURCE,
        label=SITE_LABEL,
        description="Each candidate's median share in recent public polls, from FiftyPlusOne.",
        url=SITE,
        as_of=kept[0].end or None,
        breakdowns=[Breakdown(title="Polls", unit="percent", parts=parts, note=_method(kept))],
    )


def candidate_card(candidate: Candidate, race: Race, kept: list[Reading], median: float) -> SourceCard:
    """The Polls tab: the median, then each poll it's taken from."""
    names = {c.key: c.name for c in race.candidates}
    theirs = [r for r in kept if candidate.key in r.shares]
    facts = [Fact(label="Median", value=f"{_pct(median)} across {len(theirs)} poll{'s' if len(theirs) != 1 else ''}")]
    for r in theirs:
        others = ", ".join(f"{names[key]} {_pct(share)}" for key, share in r.shares.items() if key != candidate.key)
        value = " · ".join(filter(None, (
            _pct(r.shares[candidate.key]), others, display_date(r.end), _POPULATIONS.get(r.population, r.population),
        )))
        facts.append(Fact(label=r.pollster, value=value, url=r.url))
    return SourceCard(
        source=SOURCE,
        label=LABEL,
        description=f"Public polls of this race, from FiftyPlusOne. {_method(kept)}",
        url=SITE,
        as_of=kept[0].end or None,
        facts=facts,
        links=[Link(label="FiftyPlusOne", url=SITE)],
    )


async def cards(polls: Polls, races: list[Race], day: dt.date | None) -> CardSet:
    """A poll bar for each race FiftyPlusOne has polls of, and a Polls tab for its
    candidates. Raises PollsUnavailable if none of the lists could be loaded."""
    out = CardSet()
    wanted = {race.key: kind for race in races if (kind := kind_of(race))}
    if not wanted:
        return out
    cycle = (day or polls.today()).year
    kinds = sorted(set(wanted.values()))
    lists: dict[str, list[dict[str, Any]]] = {}
    failures: list[PollsUnavailable] = []
    for kind, got in zip(kinds, await asyncio.gather(*(polls.polls(k) for k in kinds), return_exceptions=True)):
        if isinstance(got, PollsUnavailable):
            failures.append(got)
        elif isinstance(got, BaseException):
            raise got
        else:
            lists[kind] = got
    if failures and not lists:
        raise failures[0]
    if failures:
        out.warnings.append(f"Some polls couldn't be loaded from FiftyPlusOne ({failures[0]}).")

    for race in races:
        kind = wanted.get(race.key)
        if kind not in lists:
            continue
        kept = readings(lists[kind], kind, race, cycle)
        if not kept:
            continue
        middle = medians(race, kept)
        out.races[race.key] = race_card(race, kept, middle)
        for candidate in race.candidates:
            if candidate.key in middle:
                out.candidates[candidate.key] = candidate_card(candidate, race, kept, middle[candidate.key])
    return out
