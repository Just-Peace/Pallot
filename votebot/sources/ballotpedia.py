"""Ballotpedia's sample-ballot data, from the endpoint behind its own lookup widget.

Unofficial: the endpoint only answers requests that carry Ballotpedia's own origin
header, and Ballotpedia's terms forbid commercial scraping, so this is for personal use
and can be switched off in Settings. It adds what the state doesn't track (city council,
school board, special districts) and pins down the voter's commissioner/JP/constable
precincts. Ballotpedia lists special districts (MUDs, water districts) for a whole county,
so those are only ever shown as "may be on your ballot".
"""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec, UpstreamError
from ..matching import NameIndex, match_unique
from ..models import Badge, Fact, Link, Match, Race, SourceCard
from ..text import iso_utc

SOURCE = "ballotpedia"
LABEL = "Ballotpedia"
DESCRIPTION = "Ballotpedia's sample ballot: local races, precincts and candidate profiles (unofficial endpoint, personal use)."
URL = "https://api4.ballotpedia.org/myvote_redistricting_with_historical"
ORIGIN = "https://sblv3.ballotpedia.org"
BACKOFF_FLAG = "ballotpedia:blocked"

PARTY_CODES = {
    "Republican Party": "R",
    "Democratic Party": "D",
    "Libertarian Party": "L",
    "Green Party": "G",
    "Independent": "I",
}
_SPECIAL_OFFICE_TYPES = {"Utility", "Water"}
_SPECIAL_WORDS = (
    "utility district", "water control", "improvement district", "management district", "water district",
    "water supply", "emergency services district", "hospital district", "drainage district", "navigation district",
    "levee", "groundwater", "conservation district",
)
_NOT_RUNNING = ("withdrew", "disqualified", "lost")


class BallotpediaUnavailable(Exception):
    """Ballotpedia refused or failed, or we're pausing after it refused."""


@dataclass(frozen=True)
class BpCandidate:
    id: int
    name: str
    party: str | None
    party_name: str | None
    incumbent: bool
    write_in: bool
    status: str | None
    url: str | None
    photo: str | None
    survey: bool


@dataclass(frozen=True)
class BpRace:
    id: int
    office: str
    office_type: str | None
    district_type: str
    district_name: str
    group: str  # a ballot group, or "special" for special districts
    seats: int
    url: str | None
    candidates: tuple[BpCandidate, ...]

    @property
    def seat(self) -> str | None:
        if self.office.startswith("U.S. Senate"):
            return "TX-SEN"
        if self.district_type == "Congress":
            number = re.search(r"District (\d+)", self.district_name)
            return f"TX-{int(number.group(1)):02d}" if number else None
        return None


@dataclass(frozen=True)
class BpMeasure:
    id: int | str
    title: str
    summary: str | None
    url: str | None
    district: str


@dataclass(frozen=True)
class BpBallot:
    day: dt.date | None
    complete: bool
    races: tuple[BpRace, ...]
    measures: tuple[BpMeasure, ...]
    precincts: dict[str, int]
    fetched_at: float
    stale: bool


def _date(text: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat((text or "")[:10])
    except ValueError:
        return None


def _group(district_type: str, office: dict[str, Any], name: str) -> str:
    lowered = name.lower()
    if (
        district_type == "Special District"
        or office.get("type") in _SPECIAL_OFFICE_TYPES
        or any(word in lowered for word in _SPECIAL_WORDS)
    ):
        return "special"
    if district_type == "Congress" or office.get("level") == "Federal":
        return "federal"
    if district_type == "State":
        return "state"
    if district_type.startswith("State Legislative") or district_type == "State subdivision":
        return "legislature"
    if district_type == "Judicial District":
        return "judicial"
    if district_type == "County":
        return "county"
    if district_type == "County subdivision":
        return "precinct"
    return "local"  # cities, city council districts, school districts


def precincts_in(district_name: str) -> dict[str, int]:
    """ "Travis County Constable-Justice of the Peace District 5" -> {"jp": 5, "constable": 5}."""
    name = district_name.lower()
    numbers = re.findall(r"\d+", name)
    if not numbers:
        return {}
    number = int(numbers[-1])
    found = {}
    if "commission" in name:
        found["commissioner"] = number
    if "justice of the peace" in name:
        found["jp"] = number
    if "constable" in name:
        found["constable"] = number
    return found


def _candidate(raw: dict[str, Any]) -> BpCandidate | None:
    status = raw.get("status") or ""
    if any(word in status.lower() for word in _NOT_RUNNING) and not raw.get("withdrew_still_on_ballot"):
        return None
    person = raw.get("person") or {}
    parties = [p.get("name") for p in raw.get("party_affiliation") or [] if p.get("name")]
    party_name = parties[0] if parties else None
    return BpCandidate(
        id=raw["id"],
        name=person.get("name") or "Unknown",
        party=PARTY_CODES.get(party_name or ""),
        party_name=party_name,
        incumbent=bool(raw.get("is_incumbent")),
        write_in=bool(raw.get("is_write_in")),
        status="Withdrew (still on the ballot)" if raw.get("withdrew_still_on_ballot") else status or None,
        url=person.get("url"),
        photo=((person.get("image") or {}).get("thumbnail")),
        survey=bool(raw.get("survey_exists")),
    )


def _race(raw: dict[str, Any], district_type: str, district_name: str) -> BpRace:
    office = raw.get("office") or {}
    name = office.get("name") or district_name
    candidates = tuple(c for c in (_candidate(r) for r in raw.get("candidates") or []) if c)
    return BpRace(
        id=raw["id"],
        office=name,
        office_type=office.get("type"),
        district_type=district_type,
        district_name=district_name,
        group=_group(district_type, office, name),
        seats=int(raw.get("number_of_seats_override") or raw.get("number_of_seats") or 1),
        url=raw.get("url") or office.get("url"),
        candidates=tuple(sorted(candidates, key=lambda c: c.write_in)),
    )


def _measure(raw: dict[str, Any], district_name: str) -> BpMeasure:
    return BpMeasure(
        id=raw.get("id") or raw.get("name") or district_name,
        title=raw.get("name") or raw.get("title") or "Ballot measure",
        summary=raw.get("summary") or raw.get("text"),
        url=raw.get("url"),
        district=district_name,
    )


def parse(payload: dict[str, Any], day: dt.date | None, fetched_at: float, stale: bool) -> BpBallot:
    elections = ((payload or {}).get("data") or {}).get("elections") or []
    dated = [(e, _date(e.get("date"))) for e in elections]
    if day:
        chosen = next((e for e, d in dated if d == day), None)
    else:
        upcoming = sorted((d, i) for i, (_, d) in enumerate(dated) if d)
        chosen = dated[upcoming[0][1]][0] if upcoming else (elections[0] if elections else None)
    if chosen is None:
        return BpBallot(day, False, (), (), {}, fetched_at, stale)
    races: list[BpRace] = []
    measures: list[BpMeasure] = []
    precincts: dict[str, int] = {}
    for district in chosen.get("districts") or []:
        district_type = district.get("type") or ""
        district_name = district.get("name") or ""
        if district_type == "County subdivision":
            precincts.update(precincts_in(district_name))
        races += [_race(r, district_type, district_name) for r in district.get("races") or []]
        measures += [_measure(m, district_name) for m in district.get("ballot_measures") or []]
    return BpBallot(
        _date(chosen.get("date")), bool(chosen.get("candidate_lists_complete")),
        tuple(races), tuple(measures), precincts, fetched_at, stale,
    )


class Ballotpedia:
    def __init__(self, cache: HttpCache, ttl: Ttls):
        self.cache = cache
        self.ttl = ttl

    def paused_until(self) -> float | None:
        return self.cache.flag_until(BACKOFF_FLAG)

    async def ballot(self, lat: float, lon: float, day: dt.date | None = None) -> BpBallot:
        until = self.paused_until()
        if until:
            raise BallotpediaUnavailable(f"paused until {iso_utc(until)} after Ballotpedia refused a request")
        spec = RequestSpec(
            "GET",
            URL,
            params={"long": f"{lon:.5f}", "lat": f"{lat:.5f}", "include_volunteer": "true"},
            headers={"Origin": ORIGIN, "Accept": "application/json"},
        )
        try:
            got = await self.cache.get_json(SOURCE, spec, ttl=self.ttl.ballotpedia)
        except UpstreamError as exc:
            if exc.status in (401, 403, 429):
                self.cache.set_flag(BACKOFF_FLAG, SOURCE, self.ttl.ballotpedia_backoff)
            raise BallotpediaUnavailable(str(exc)) from exc
        return parse(got.value, day, got.fetched_at, got.stale)


def card(candidate: BpCandidate, race: BpRace, fetched_at: float, match: Match | None) -> SourceCard:
    facts = [
        Fact(label="Name", value=candidate.name),
        Fact(label="Party", value=candidate.party_name or ""),
        Fact(label="Race", value=race.office),
        Fact(label="Status", value=candidate.status or ""),
        Fact(label="Incumbent", value="Yes" if candidate.incumbent else "No"),
        Fact(label="Write-in", value="Yes" if candidate.write_in else ""),
    ]
    links = [Link(label="Ballotpedia profile", url=candidate.url)] if candidate.url else []
    if race.url:
        links.append(Link(label="This race on Ballotpedia", url=race.url))
    return SourceCard(
        source=SOURCE,
        label=LABEL,
        description=DESCRIPTION,
        url=candidate.url or race.url,
        image=candidate.photo,
        as_of=iso_utc(fetched_at),
        match=match,
        badges=[Badge(text="Ballotpedia survey", tone="info")] if candidate.survey else [],
        facts=[f for f in facts if f.value],
        links=links,
    )


def cards(ballot: BpBallot, races: list[Race]) -> dict[str, SourceCard]:
    """Cards for Ballotpedia's own candidates, and for state-listed candidates matched by
    name (within the same kind of race first, then anywhere on this ballot)."""
    by_id = {c.id: (c, r) for r in ballot.races for c in r.candidates}
    per_group: dict[str, NameIndex] = defaultdict(NameIndex)
    everyone = NameIndex()
    for race in ballot.races:
        for candidate in race.candidates:
            per_group[race.group].add(candidate.name, (candidate, race))
            everyone.add(candidate.name, (candidate, race))
    out = {}
    for race in races:
        for candidate in race.candidates:
            if candidate.key.startswith("bp:"):
                hit = by_id.get(int(candidate.key.split(":", 1)[1]))
                if hit:
                    out[candidate.key] = card(hit[0], hit[1], ballot.fetched_at, None)
                continue
            found = match_unique(per_group[race.group], candidate.name) or match_unique(everyone, candidate.name)
            if found:
                (bp_candidate, bp_race), match = found
                out[candidate.key] = card(bp_candidate, bp_race, ballot.fetched_at, match)
    return out
