"""The shapes the API returns, and the ballot request it accepts."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

Tone = Literal["neutral", "info", "good", "warn"]

# Display order of race groups on the ballot (labels live in the frontend).
GROUPS = ("federal", "state", "legislature", "judicial", "county", "precinct", "local")


class Badge(BaseModel):
    text: str
    tone: Tone = "neutral"
    url: str | None = None  # makes the badge a link to the source's page
    hint: str | None = None  # tooltip explaining the badge


class Fact(BaseModel):
    label: str
    value: str
    url: str | None = None


class Link(BaseModel):
    label: str
    url: str


class Match(BaseModel):
    """How a source's record was tied to this candidate, for sources matched by name."""

    confidence: Literal["exact", "likely"]
    method: str
    note: str | None = None


class SourceCard(BaseModel):
    """One source's information about one candidate. The frontend renders every card the
    same way, so a new source only has to produce these."""

    source: str
    label: str
    description: str | None = None
    url: str | None = None
    image: str | None = None  # a candidate photo, if the source has one
    as_of: str | None = None
    match: Match | None = None
    badges: list[Badge] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)


class Candidate(BaseModel):
    key: str  # stable across refreshes: "sos:<election>:<candidate>" or "bp:<candidate>"
    name: str
    ballot_name: str | None = None
    party: str | None = None  # D, R, L, G, I, W …
    party_name: str | None = None
    incumbent: bool = False
    write_in: bool = False
    ballot_position: int | None = None
    photo_url: str | None = None
    cards: list[SourceCard] = Field(default_factory=list)


class Race(BaseModel):
    key: str  # "sos:<election>:<office>" or "bp:<race>"
    name: str
    group: str
    seats: int = 1
    unexpired: bool = False
    seat: str | None = None  # "TX-10" / "TX-SEN" for congressional races
    election_id: int | None = None
    election_name: str | None = None
    source: str
    url: str | None = None
    candidates: list[Candidate] = Field(default_factory=list)


class MaybeSection(BaseModel):
    """Races that may or may not be on this voter's ballot, with why."""

    id: str
    title: str
    explanation: str
    races: list[Race]


class Measure(BaseModel):
    key: str
    title: str
    summary: str | None = None
    url: str | None = None
    district: str | None = None


class Location(BaseModel):
    input_address: str
    matched_address: str | None
    lat: float
    lon: float
    state: str | None = None  # postal code, "TX"
    state_name: str | None = None
    county: str | None
    city: str | None
    school_district: str | None
    geocoder: Literal["census", "nominatim"]
    approximate: bool = False


class Districts(BaseModel):
    county_id: int | None = None
    cd: int | None = None
    sd: int | None = None
    hd: int | None = None
    sboe: int | None = None
    commissioner: int | None = None
    jp: int | None = None
    constable: int | None = None
    precinct_source: str | None = None  # "you" or "ballotpedia"


class ElectionRef(BaseModel):
    id: int | None = None
    name: str
    type: str | None = None
    date: str | None = None
    party: str | None = None


class SourceUse(BaseModel):
    id: str
    label: str
    status: Literal["used", "off", "error", "stale", "unused"]
    as_of: str | None = None
    message: str | None = None


class Meta(BaseModel):
    external_calls: int
    cache_hits: int
    elapsed_ms: int


class Ballot(BaseModel):
    election_date: str | None
    elections: list[ElectionRef]
    location: Location
    districts: Districts
    races: list[Race]
    maybe: list[MaybeSection]
    measures: list[Measure]
    notes: list[str]
    warnings: list[str]
    sources: list[SourceUse]
    meta: Meta


class PrecinctInput(BaseModel):
    commissioner: int | None = Field(default=None, ge=1, le=99)
    jp: int | None = Field(default=None, ge=1, le=99)
    constable: int | None = Field(default=None, ge=1, le=99)


class BallotRequest(BaseModel):
    address: str = Field(min_length=5, max_length=200)
    election_date: dt.date | None = None
    party: Literal["D", "R"] | None = None
    precincts: PrecinctInput | None = None


class ElectionDate(BaseModel):
    date: str
    elections: list[ElectionRef]
    has_primaries: bool


class CacheStatus(BaseModel):
    entries: int
    bytes: int
    expired: int
    oldest: str | None
    newest: str | None


class SourceStatus(BaseModel):
    id: str
    label: str
    description: str
    toggleable: bool
    enabled: bool
    busy: bool
    cache: CacheStatus
    details: list[Fact]
    refresh_label: str
    clear_label: str


class SourcesOverview(BaseModel):
    sources: list[SourceStatus]
    total_bytes: int


class SourceToggle(BaseModel):
    enabled: bool


class ActionResult(BaseModel):
    message: str
