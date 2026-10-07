"""Ballotpedia's sample-ballot data, from the endpoint behind its own lookup widget.

Unofficial: the endpoint only answers requests that carry Ballotpedia's own origin
header, and Ballotpedia's terms forbid commercial scraping, so this is for personal use
and can be switched off in Settings. It adds what the state doesn't track (city council,
school board, special districts, appraisal district boards), its notes on races, and pins
down the voter's commissioner/JP/constable precincts, though only those with a race on this
ballot. Ballotpedia lists special districts (MUDs, water districts) for a whole county, so
those are only ever shown as "may be on your ballot".
"""

from __future__ import annotations

import datetime as dt
import html
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec, UpstreamError
from ..matching import NameIndex, match_person, match_unique
from ..models import Badge, Fact, Link, Match, Race, SourceCard
from ..text import display_time, iso_utc, parse_date
from . import CardSet

SOURCE = "ballotpedia"
LABEL = "Ballotpedia"
DESCRIPTION = (
    "Ballotpedia's sample ballot: local races and others the state doesn't list, notes on races, precincts and "
    "candidate profiles (unofficial endpoint, personal use)."
)
URL = "https://api4.ballotpedia.org/myvote_redistricting_with_historical"
ORIGIN = "https://sblv3.ballotpedia.org"
REFUSALS = (401, 403, 429)  # answers that pause Ballotpedia for Ttls.ballotpedia_backoff

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
_KINDS = (("commission", "commissioner"), ("justice of the peace", "jp"), ("constable", "constable"))
_LINK = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_HREF = re.compile(r"""\bhref\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_CLICK_HERE = re.compile(r"^\s*(click here|learn more|read more)\b", re.IGNORECASE)


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
class BpNote:
    text: str
    url: str | None = None


@dataclass(frozen=True)
class BpRace:
    id: int
    office: str
    district_type: str
    district_name: str
    group: str  # a ballot group, or "special" for special districts
    seats: int
    url: str | None
    candidates: tuple[BpCandidate, ...]
    notes: tuple[BpNote, ...] = ()

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
    races: tuple[BpRace, ...]
    measures: tuple[BpMeasure, ...]
    precincts: dict[str, int]
    fetched_at: float
    city_council: str | None = None


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


def _kinds(text: str) -> set[str]:
    lowered = text.lower()
    return {kind for word, kind in _KINDS if word in lowered}


def precincts_in(district_name: str, offices: Iterable[str] = ()) -> dict[str, int]:
    """ "Travis County Constable-Justice of the Peace District 5" -> {"jp": 5, "constable": 5}. A
    name that doesn't say which kind ("Fort Bend County Precinct 1") takes it from the offices
    of the races in it ("Fort Bend County Justice of the Peace, Precinct 1-Place 2" -> jp)."""
    numbers = re.findall(r"\d+", district_name)
    if not numbers:
        return {}
    kinds = _kinds(district_name) or set().union(*(_kinds(office) for office in offices))
    return {kind: int(numbers[-1]) for kind in kinds}


def council_district_in(district_name: str) -> str | None:
    name = district_name.strip()
    match = re.search(r"\bcouncil\s+(\S.*)$", name, re.IGNORECASE)
    return match.group(1) if match else name or None


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


def _note(raw: Any) -> BpNote | None:
    """One of Ballotpedia's disclaimers, as plain text and the first web link in it. Its HTML
    is never passed on: tags are dropped, and so is a "Click here to learn more" link's text."""
    text = raw.get("text") if isinstance(raw, dict) else raw
    if not isinstance(text, str):
        return None
    url = None

    def link(found: re.Match[str]) -> str:
        nonlocal url
        href = _HREF.search(found.group(1))
        if href and url is None and href.group(1).startswith(("https://", "http://")):
            url = html.unescape(href.group(1))
        inner = _TAG.sub("", found.group(2))
        return "" if _CLICK_HERE.match(html.unescape(inner)) else inner

    plain = " ".join(html.unescape(_TAG.sub(" ", _LINK.sub(link, text))).split())
    return BpNote(plain, url) if plain else None


def _notes(*lists: Any) -> tuple[BpNote, ...]:
    found = (_note(raw) for items in lists for raw in items or ())
    return tuple(dict.fromkeys(note for note in found if note))


def _race(raw: dict[str, Any], district: dict[str, Any]) -> BpRace:
    district_type = district.get("type") or ""
    district_name = district.get("name") or ""
    office = raw.get("office") or {}
    name = office.get("name") or district_name
    candidates = tuple(c for c in (_candidate(r) for r in raw.get("candidates") or []) if c)
    return BpRace(
        id=raw["id"],
        office=name,
        district_type=district_type,
        district_name=district_name,
        group=_group(district_type, office, name),
        seats=int(raw.get("number_of_seats_override") or raw.get("number_of_seats") or 1),
        url=raw.get("url") or office.get("url"),
        candidates=tuple(sorted(candidates, key=lambda c: c.write_in)),
        notes=_notes(raw.get("race_disclaimers"), raw.get("stage_disclaimers"), district.get("disclaimers"),
                     district.get("permanent_disclaimers")),
    )


def _measure(raw: dict[str, Any], district_name: str) -> BpMeasure:
    return BpMeasure(
        id=raw.get("id") or raw.get("name") or district_name,
        title=raw.get("name") or raw.get("title") or "Ballot measure",
        summary=raw.get("summary") or raw.get("text"),
        url=raw.get("url"),
        district=district_name,
    )


def parse(payload: dict[str, Any], day: dt.date | None, fetched_at: float, today: dt.date | None = None) -> BpBallot:
    """The ballot of the election on ``day``; without one, the earliest on or after ``today``,
    or the latest when every election listed is past."""
    elections = ((payload or {}).get("data") or {}).get("elections") or []
    dated = [(e, parse_date(e.get("date"))) for e in elections]
    if day:
        chosen = next((e for e, d in dated if d == day), None)
    else:
        today = today or dt.date.today()
        dates = sorted((d, i) for i, (_, d) in enumerate(dated) if d)
        coming = [(d, i) for d, i in dates if d >= today]
        pick = coming[0] if coming else (dates[-1] if dates else None)
        chosen = dated[pick[1]][0] if pick else (elections[0] if elections else None)
    if chosen is None:
        return BpBallot(day, (), (), {}, fetched_at)
    races: list[BpRace] = []
    measures: list[BpMeasure] = []
    precincts: dict[str, int] = {}
    city_council: str | None = None
    for district in chosen.get("districts") or []:
        district_type = district.get("type") or ""
        district_name = district.get("name") or ""
        if district_type == "County subdivision":
            offices = ((r.get("office") or {}).get("name") or "" for r in district.get("races") or [])
            precincts.update(precincts_in(district_name, offices))
        elif district_type == "City-town subdivision":
            city_council = city_council or council_district_in(district_name)
        races += [_race(r, district) for r in district.get("races") or []]
        measures += [_measure(m, district_name) for m in district.get("ballot_measures") or []]
    return BpBallot(parse_date(chosen.get("date")), tuple(races), tuple(measures), precincts, fetched_at, city_council)


class Ballotpedia:
    def __init__(self, cache: HttpCache, ttl: Ttls, today: Callable[[], dt.date] = dt.date.today):
        self.cache = cache
        self.ttl = ttl
        self.today = today
        cache.pause_on(SOURCE, REFUSALS, ttl.ballotpedia_backoff)

    async def ballot(self, lat: float, lon: float, day: dt.date | None = None) -> BpBallot:
        """The sample ballot at this point (from cache, also while paused if we have it)."""
        spec = RequestSpec(
            "GET",
            URL,
            params={"long": f"{lon:.5f}", "lat": f"{lat:.5f}", "include_volunteer": "true"},
            headers={"Origin": ORIGIN, "Accept": "application/json"},
        )
        try:
            got = await self.cache.get_json(SOURCE, spec, ttl=self.ttl.ballotpedia)
        except UpstreamError as exc:
            if exc.until:
                raise BallotpediaUnavailable(f"paused until {display_time(exc.until)} after Ballotpedia refused a request") from exc
            raise BallotpediaUnavailable(str(exc)) from exc
        return parse(got.value, day, got.fetched_at, self.today())


def card(candidate: BpCandidate, race: BpRace, fetched_at: float, match: Match | None) -> SourceCard:
    facts = [
        Fact(label="Name", value=candidate.name),
        Fact(label="Party", value=candidate.party_name or ""),
        Fact(label="Race", value=race.office),
        Fact(label="Status", value=candidate.status or ""),
        Fact(label="Incumbent", value="Yes" if candidate.incumbent else "No"),
        Fact(label="Write-in", value="Yes" if candidate.write_in else ""),
        Fact(label="Candidate survey", value="Answered (see the profile)" if candidate.survey else ""),
    ]
    links = [Link(label="Ballotpedia profile", url=candidate.url)] if candidate.url else []
    if race.url:
        links.append(Link(label="This race on Ballotpedia", url=race.url))
    return SourceCard(
        source=SOURCE,
        kind="profile",
        label=LABEL,
        description=DESCRIPTION,
        url=candidate.url or race.url,
        image=candidate.photo,
        as_of=iso_utc(fetched_at),
        match=match,
        badges=[Badge(text="Ballotpedia profile", tone="info", url=candidate.url)] if candidate.url else [],
        facts=[f for f in facts if f.value],
        links=links,
    )


def counterparts(ballot: BpBallot, races: list[Race]) -> dict[str, BpRace]:
    """Each race's own race on Ballotpedia's ballot (by race key): its own for Ballotpedia's
    races, and for the state's, the one its candidates are found in by name, when every
    candidate found is in the same one."""
    by_id = {race.id: race for race in ballot.races}
    printed = NameIndex()
    for race in ballot.races:
        for candidate in race.candidates:
            if not candidate.write_in:
                printed.add(candidate.name, race)
    out = {}
    for race in races:
        if race.key.startswith("bp:"):
            if own := by_id.get(int(race.key.split(":", 1)[1])):
                out[race.key] = own
            continue
        found = {hit[0].id: hit[0] for c in race.candidates if not c.write_in and (hit := match_unique(printed, c.name))}
        if len(found) == 1:
            out[race.key] = next(iter(found.values()))
    return out


def cards(ballot: BpBallot, races: list[Race], same: dict[str, BpRace] | None = None) -> CardSet:
    """Cards for Ballotpedia's own candidates, and for state-listed candidates matched by name:
    within the race's own race on Ballotpedia (``same``, from counterparts()), with the party
    to confirm, else within the same kind of race, then anywhere on this ballot. A candidate
    matched exactly in its own race whom Ballotpedia calls the incumbent goes in ``incumbents``."""
    same = same or {}
    by_id = {c.id: (c, r) for r in ballot.races for c in r.candidates}
    per_group: dict[str, NameIndex] = defaultdict(NameIndex)
    everyone = NameIndex()
    for race in ballot.races:
        for candidate in race.candidates:
            per_group[race.group].add(candidate.name, (candidate, race))
            everyone.add(candidate.name, (candidate, race))
    out = CardSet()
    for race in races:
        own = same.get(race.key)
        for candidate in race.candidates:
            if candidate.key.startswith("bp:"):
                hit = by_id.get(int(candidate.key.split(":", 1)[1]))
                if hit:
                    out.candidates[candidate.key] = card(hit[0], hit[1], ballot.fetched_at, None)
                continue
            if own:
                found = match_person(
                    everyone, candidate.name, candidate.party, own.office,
                    seats_of=lambda hit: {hit[1].office},
                    party_of=lambda hit: hit[0].party,
                    source=LABEL,
                    seat_text=lambda hit: hit[1].office,
                    name_of=lambda hit: hit[0].name,
                )
            else:
                found = match_unique(per_group[race.group], candidate.name) or match_unique(everyone, candidate.name)
            if found:
                (bp_candidate, bp_race), match = found
                out.candidates[candidate.key] = card(bp_candidate, bp_race, ballot.fetched_at, match)
                if own and bp_candidate.incumbent and match.confidence == "exact":
                    out.incumbents.add(candidate.key)
    return out
