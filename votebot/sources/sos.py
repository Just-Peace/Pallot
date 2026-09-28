"""Texas Secretary of State candidate data (goelect.txelections.civixapps.com).

This is the API behind the state's public "Candidate Ballot Order" and "Candidate
Information" pages; it needs no key. It sends Cache-Control: no-store, so every call goes
through HttpCache with our own lifetimes.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

from ..config import Ttls
from ..http_cache import Cached, HttpCache, RequestSpec, UpstreamError
from ..models import Candidate, Fact, Link, SourceCard
from ..offices import clean_office_name
from ..text import display_office, iso_utc, web_url

SOURCE = "sos"
LABEL = "Texas SOS"
DESCRIPTION = "Official candidate filings and ballot order from the Texas Secretary of State."
HOST = "https://goelect.txelections.civixapps.com"
CBP = f"{HOST}/api-ivis-cbp/api/cbp"
SYSTEM = f"{HOST}/api-ivis-system/api/system"
BALLOT_ORDER_PAGE = f"{HOST}/ivis-cbp-ui/candidate-ballot-order"
CANDIDATE_PAGE = f"{HOST}/ivis-cbp-ui/candidate-information"

_GONE = {"R", "WDE", "DI"}  # declaration status: rejected, withdrew, declared ineligible


@dataclass(frozen=True)
class Election:
    id: int
    name: str
    type: str | None  # GE general, P primary, RU primary runoff, S special, SR special runoff
    day: dt.date | None

    @property
    def party(self) -> str | None:
        """ "D"/"R" for a party primary or its runoff; None for every other election."""
        if self.type not in ("P", "RU"):
            return None
        name = self.name.upper()
        return "D" if "DEMOCRATIC" in name else "R" if "REPUBLICAN" in name else None


@dataclass(frozen=True)
class Lookups:
    parties: dict[str, str]
    filing: dict[str, str]
    declaration: dict[str, str]


def _date(text: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat((text or "")[:10])
    except ValueError:
        return None


def still_running(row: dict[str, Any]) -> bool:
    return row.get("cdDeclarationStatus") not in _GONE


class Sos:
    def __init__(self, cache: HttpCache, ttl: Ttls, today: Callable[[], dt.date] = dt.date.today):
        self.cache = cache
        self.ttl = ttl
        self.today = today
        self._indexes: dict[int, tuple[float, dict[int, dict[str, Any]]]] = {}

    async def _get(self, url: str, ttl: float) -> Cached:
        return await self.cache.get_json(SOURCE, RequestSpec("GET", url), ttl=ttl)

    async def _post(self, url: str, body: dict[str, Any], ttl: float, empty_ttl: float) -> Cached:
        return await self.cache.get_json(SOURCE, RequestSpec("POST", url, json=body), ttl=ttl, empty_ttl=empty_ttl)

    def _lifetime(self, election: Election, normal: float) -> float:
        return self.ttl.past_election if election.day and election.day < self.today() else normal

    async def elections(self, year: int) -> list[Election]:
        ttl = self.ttl.past_election if year < self.today().year else self.ttl.sos_elections
        got = await self._get(f"{CBP}/getElectionsByYear/{year}", ttl)
        return [
            Election(row["idElection"], " ".join((row.get("txElectionName") or "").split()),
                     row.get("cdElectionType"), _date(row.get("dtElectionDate")))
            for row in got.value or []
            if row.get("idElection")
        ]

    async def upcoming(self) -> dict[dt.date, list[Election]]:
        """Elections on each date from today on, soonest first."""
        today = self.today()
        per_year = await asyncio.gather(self.elections(today.year), self.elections(today.year + 1))
        by_day: dict[dt.date, list[Election]] = defaultdict(list)
        for election in (e for year in per_year for e in year):
            if election.day and election.day >= today:
                by_day[election.day].append(election)
        return dict(sorted(by_day.items()))

    async def counties(self) -> dict[str, int]:
        """County name in capitals ("TRAVIS") -> the SOS county id."""
        got = await self._get(f"{SYSTEM}/getAllRegions", self.ttl.sos_reference)
        return {row["txName"].upper(): row["idRegion"] for row in got.value or [] if row.get("txName") and row.get("idRegion")}

    async def county_id(self, name: str | None, fips: str | None) -> int | None:
        counties = await self.counties()
        if name:
            wanted = name.upper().removesuffix(" COUNTY").replace(" ", "")
            for county, county_id in counties.items():
                if county.replace(" ", "") == wanted:  # "DE WITT" vs "DeWitt"
                    return county_id
        if fips and fips.isdigit():  # SOS numbers counties alphabetically, as Texas's odd FIPS codes do
            guess = (int(fips) + 1) // 2
            if guess in counties.values():
                return guess
        return None

    async def lookups(self) -> Lookups:
        parties, filing, declaration = await asyncio.gather(
            self._get(f"{CBP}/getPoliticalParties", self.ttl.sos_reference),
            self._get(f"{CBP}/getCandidateStatus", self.ttl.sos_reference),
            self._get(f"{CBP}/getDeclarationStatus", self.ttl.sos_reference),
        )

        def table(got: Cached) -> dict[str, str]:
            return {row["txKey"]: " ".join((row.get("txVal") or "").split()) for row in got.value or [] if row.get("txKey")}

        return Lookups(table(parties), table(filing), table(declaration))

    async def ballot_order(self, election: Election, county_id: int) -> Cached:
        """Every race touching the county, candidates in ballot order (empty for some specials)."""
        body = {"electionYear": election.day.year if election.day else None, "electionId": election.id,
                "countyId": county_id, "source": "TX"}
        ttl = self._lifetime(election, self.ttl.sos_ballot_order)
        return await self._post(f"{CBP}/getCandidateBallotOrder", body, ttl, min(ttl, self.ttl.sos_empty))

    async def candidates(self, election: Election) -> Cached:
        """Every candidate statewide in this election, in one call (~2.6 MB for a general)."""
        body = {"electionYear": election.day.year if election.day else None, "electionId": election.id}
        ttl = self._lifetime(election, self.ttl.sos_candidates)
        return await self._post(f"{CBP}/findQualifiedCandidates", body, ttl, min(ttl, self.ttl.sos_empty))

    def index(self, election_id: int, cached: Cached) -> dict[int, dict[str, Any]]:
        """idCandidate -> row of a statewide list, built once per fetched copy."""
        hit = self._indexes.get(election_id)
        if hit and hit[0] == cached.fetched_at:
            return hit[1]
        index = {row["idCandidate"]: row for row in cached.value or [] if row.get("idCandidate")}
        self._indexes[election_id] = (cached.fetched_at, index)
        return index


def _filed(text: str | None) -> str | None:
    day = _date(text)
    return f"{day:%b} {day.day}, {day.year}" if day else None


def card(row: dict[str, Any], lookups: Lookups, fetched_at: float | None) -> SourceCard:
    code = row.get("cdParty") or ""
    counties = {row["txCountyName"].upper()} if row.get("txCountyName") else set()
    office, unexpired = clean_office_name(row.get("txOfficeName") or "", counties)
    address = row.get("mailingAddress") or {}
    city = ", ".join(x for x in ((address.get("txCity") or "").title(), address.get("cdState")) if x)
    website = web_url(row.get("txWebsiteUrl"))
    email = (row.get("txEmail") or "").strip() or None
    facts = [
        Fact(label="Name on ballot", value=row.get("txFullNameBallot") or ""),
        Fact(label="Party", value=lookups.parties.get(code, code).title()),
        Fact(label="Office", value=display_office(office) + (" (unexpired term)" if unexpired else "")),
        Fact(label="Occupation", value=display_office((row.get("txOccupation") or "").strip())),
        Fact(label="Incumbent", value="Yes" if row.get("flIncmbntGen") else ""),
        Fact(label="Filing status", value=lookups.filing.get(row.get("cdFilingStatus") or "", "")),
        Fact(label="Application", value=lookups.declaration.get(row.get("cdDeclarationStatus") or "", "").capitalize()),
        Fact(label="Filed", value=_filed(row.get("dtFiled")) or ""),
        Fact(label="Mailing city", value=city),
        Fact(label="Email", value=email or "", url=f"mailto:{email}" if email else None),
        Fact(label="Website", value=website or "", url=website),
    ]
    links = [
        Link(label="Candidate information (Texas SOS)", url=CANDIDATE_PAGE),
        Link(label="Ballot order (Texas SOS)", url=BALLOT_ORDER_PAGE),
    ]
    if website:
        links.insert(0, Link(label="Campaign website", url=website))
    return SourceCard(
        source=SOURCE,
        label=LABEL,
        description=DESCRIPTION,
        url=CANDIDATE_PAGE,
        as_of=iso_utc(fetched_at),
        facts=[f for f in facts if f.value],
        links=links,
    )


async def cards(
    sos: Sos, elections: dict[int, Election], candidates: list[Candidate], ballot_rows: dict[str, dict[str, Any]]
) -> dict[str, SourceCard]:
    """A card per state-listed candidate, from the (cached) statewide list of their election,
    falling back to what the ballot-order row had."""
    wanted: dict[int, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        if not candidate.key.startswith(f"{SOURCE}:"):
            continue
        election_id = int(candidate.key.split(":")[1])
        if election_id in elections:
            wanted[election_id].append(candidate)
    if not wanted:
        return {}
    lookups = await sos.lookups()
    lists = await asyncio.gather(*(sos.candidates(elections[e]) for e in wanted), return_exceptions=True)
    out = {}
    for election_id, got in zip(wanted, lists):
        if isinstance(got, UpstreamError):
            got = None
        elif isinstance(got, BaseException):
            raise got
        index = sos.index(election_id, got) if got else {}
        for candidate in wanted[election_id]:
            candidate_id = int(candidate.key.rsplit(":", 1)[1])
            row = {**ballot_rows.get(candidate.key, {}), **index.get(candidate_id, {})}
            if row:
                out[candidate.key] = card(row, lookups, got.fetched_at if got else None)
    return out
