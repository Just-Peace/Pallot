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


class Share(BaseModel):
    """One part of a Breakdown. ``amount`` is None when the source has no figure for it."""

    label: str
    amount: float | None = None
    count: int | None = None
    note: str | None = None
    tone: Tone | None = None
    tag: str | None = None  # a word shown as a badge in the row's tone ("for", "against")
    candidate_key: str | None = None  # in a race comparison, whose row this is (for the party colour)


class Breakdown(BaseModel):
    """Money split into parts, drawn as labelled bars. With a ``total`` the bars are shares
    of it (and show a %); without one they are scaled to the largest part. In "percent"
    the amounts are percentages of one whole (a poll), drawn as a single stacked bar."""

    title: str
    parts: list[Share] = Field(default_factory=list)
    total: float | None = None
    note: str | None = None
    unit: Literal["dollars", "percent"] = "dollars"


class CompareValue(BaseModel):
    """One candidate's figure in a comparison row; ``amount`` is None when the source has no
    figure for them (0 means it has one, and it's nothing)."""

    candidate_key: str
    amount: float | None = None
    count: int | None = None


class CompareRow(BaseModel):
    """A category every candidate shares ("Individuals"), with a bar per candidate."""

    label: str
    values: list[CompareValue]
    counted: str | None = None  # what the counts count, when not the section's


class CompareEntry(Share):
    """A named donor or spender in one candidate's column."""

    shared_with: list[str] = Field(default_factory=list)  # other candidates whose column has this name
    match_key: str | None = None  # the same for this name in every column it's in (set when shared)


class CompareSection(BaseModel):
    """One breakdown with the race's candidates side by side: grouped bars (``rows``) for the
    categories they share, or a column per candidate (``columns``) for named donors and
    spenders. ``totals`` holds each candidate's whole that the rows are shares of."""

    title: str
    note: str | None = None
    counted: str = "donation"  # what the counts count, singular
    rows: list[CompareRow] = Field(default_factory=list)
    totals: dict[str, float] = Field(default_factory=dict)
    columns: dict[str, list[CompareEntry]] = Field(default_factory=dict)


class Comparison(BaseModel):
    """A race's candidates compared by one money source (on the race's SourceCard)."""

    candidates: list[str]  # keys of the race's candidates this source has, in ballot order
    as_of: dict[str, str] = Field(default_factory=dict)  # candidate key -> their reports' end date
    sections: list[CompareSection] = Field(default_factory=list)


class SourceCard(BaseModel):
    """One source's information about one candidate (or, in Race.cards, about a race). The
    frontend renders every card the same way, so a new source only has to produce these."""

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
    breakdowns: list[Breakdown] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    comparison: Comparison | None = None  # race cards only: the candidates side by side


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
    cards: list[SourceCard] = Field(default_factory=list)  # race-level cards, e.g. money raised by each candidate


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


class KeyDates(BaseModel):
    """One election's deadlines (ISO dates), from the Texas SOS's Important Election Dates page."""

    election: str  # the page's name for it: "Uniform Election Date", "Primary Runoff Election"
    election_day: str
    register_by: str | None = None
    mail_apply_by: str | None = None  # the application must arrive (not be postmarked) by then
    early_voting_start: str | None = None
    early_voting_end: str | None = None
    source_url: str


class SourceUse(BaseModel):
    """How one lookup used a source ("stale": it served a copy it couldn't refresh)."""

    id: str
    label: str
    status: Literal["used", "off", "error", "stale", "unused"]
    as_of: str | None = None  # the oldest data it served
    calls: int = 0  # external requests it made (0: everything came from the cache)
    message: str | None = None


class Meta(BaseModel):
    external_calls: int
    cache_hits: int
    elapsed_ms: int


class LastLookup(Meta):
    """The latest ballot lookup since VoteBot started, for the Settings page."""

    at: str


class Ballot(BaseModel):
    election_date: str | None
    elections: list[ElectionRef]
    key_dates: KeyDates | None = None  # none when the source is off, or has no election on this date
    location: Location
    districts: Districts
    races: list[Race]
    maybe: list[MaybeSection]
    measures: list[Measure]
    notes: list[str]
    warnings: list[str]
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


class AddressSuggestion(BaseModel):
    label: str  # "1100 Congress Avenue, Austin, TX 78701"
    street_only: bool  # only the street is known there: the house number is the one typed


class SuggestResult(BaseModel):
    enabled: bool  # suggestions are on in Settings
    suggestions: list[AddressSuggestion]


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
    resettable: bool  # comes with a bundled snapshot: "clear" resets to it
    enabled: bool
    busy: bool
    cache: CacheStatus
    details: list[Fact]
    refresh_label: str
    clear_label: str
    refresh_confirm: str | None = None  # asked before refreshing, when a refresh sends or downloads a lot
    notice: str | None = None  # one line shown under the description, e.g. what the source is missing
    notice_tone: Tone = "info"
    last_use: SourceUse | None = None  # in the last lookup


class SourcesOverview(BaseModel):
    sources: list[SourceStatus]
    total_bytes: int
    last_lookup: LastLookup | None = None


class SourceToggle(BaseModel):
    enabled: bool


class ActionResult(BaseModel):
    message: str
