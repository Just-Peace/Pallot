"""The shapes the API returns, and the ballot request it accepts."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Tone = Literal["neutral", "info", "good", "warn"]
CardKind = Literal["money", "polls", "filing", "profile", "endorsement"]

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
    url: str | None = None  # where the part comes from (a poll's page)
    versus: str | None = None  # whom the tag measures against (a poll's closest rival)


class Breakdown(BaseModel):
    """Money split into parts, drawn as labelled bars. With a ``total`` the bars are shares
    of it (and show a %); without one they are scaled to the largest part. In "percent"
    the amounts are percentages of one whole (a poll), drawn as a single stacked bar; in
    "points" each part is a percentage of its own whole (one poll each), a bar of 0-100
    apiece, with ``mark`` drawn as a line across them (the median)."""

    title: str
    parts: list[Share] = Field(default_factory=list)
    total: float | None = None
    note: str | None = None
    unit: Literal["dollars", "percent", "points"] = "dollars"
    mark: float | None = None
    count: int | None = None  # how many it's worked out from (a poll bar's polls)


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
    kind: CardKind  # the page places the card's badges and its race card by this
    label: str
    description: str | None = None
    url: str | None = None
    image: str | None = None  # a candidate photo, if the source has one
    as_of: str | None = None
    match: Match | None = None
    badges: list[Badge] = Field(default_factory=list)
    highlights: list[Badge] = Field(default_factory=list)  # a money card's Funding chips (sources/highlights.py)
    facts: list[Fact] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)
    breakdowns: list[Breakdown] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    comparison: Comparison | None = None  # race cards only: the candidates side by side
    # What Pick by rule tests, by id, shared by sources that mean the same thing ("raised" from
    # the FEC and the TEC): figures in dollars (a poll's in percent), and the source's lists the
    # candidate is on ("endorsed").
    figures: dict[str, float] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)


class Candidate(BaseModel):
    key: str  # stable across refreshes: "sos:<election>:<candidate>" or "fec:<FEC candidate ID>"
    name: str
    party: str | None = None  # D, R, L, G, I …
    party_name: str | None = None
    incumbent: bool = False
    party_holds_seat: bool = False  # of the seat holder's party, but not the holder (Race.holder)
    write_in: bool = False
    unverified: bool = False  # filed to run (the FEC), but no official list says they're on this ballot
    photo_url: str | None = None
    cards: list[SourceCard] = Field(default_factory=list)


class RaceNote(BaseModel):
    """A source's note on a race, as plain text, e.g. the FEC's on who its list of filers leaves out."""

    text: str
    url: str | None = None
    source: str  # the source's label, "FEC"


class SeatHolder(BaseModel):
    """Who holds a race's seat now (officeholders.py)."""

    name: str
    party: str | None = None
    party_name: str | None = None
    hint: str  # "Held by John Cornyn, a Republican", with any caveat


class Race(BaseModel):
    key: str  # "sos:<election>:<office>" or "fec:<cycle>:<seat>"
    name: str
    group: str
    seats: int = 1
    unexpired: bool = False
    ranked_choice: bool = False  # the voter ranks the candidates 1st, 2nd, 3rd… (Alaska) instead of picking
    seat: str | None = None  # "TX-10" / "TX-SEN" for congressional races
    holder: SeatHolder | None = None  # who holds the seat now, where the seat holders source covers it
    open_seat: bool = False  # the holder isn't running here, or the seat is vacant
    election_id: int | None = None
    election_name: str | None = None
    source: str
    url: str | None = None
    candidates: list[Candidate] = Field(default_factory=list)
    cards: list[SourceCard] = Field(default_factory=list)  # race-level cards, e.g. money raised by each candidate
    notes: list[RaceNote] = Field(default_factory=list)


class MaybeSection(BaseModel):
    """Races that may or may not be on this voter's ballot, with why."""

    id: str
    title: str
    explanation: str
    races: list[Race]


class Location(BaseModel):
    matched_address: str | None
    lat: float | None  # None: a voter card's precinct the precinct map couldn't place
    lon: float | None
    state: str  # postal code, "TX"
    state_name: str  # "Texas"
    county: str | None
    city: str | None
    school_district: str | None
    geocoder: Literal["census", "nominatim", "google"] | None  # None: found from a voter card
    county_name: str | None = None  # the Census's full name: "Travis County", "Orleans Parish"
    approximate: bool = False
    source: Literal["address", "voter_card"] = "address"  # a voter card's point is one inside its precinct


class ElectionPrecinct(BaseModel):
    """The voter's election precinct (the "Pct" on a voter registration certificate), from the
    Texas Legislative Council's precinct map."""

    name: str  # as the voter reads it: "300"
    code: str  # as the map writes it ("0300"): asks for the outline, with ``county``
    county: int  # the county's FIPS code
    map_label: str  # the map's: "2026 Primary Election Voting Precincts"
    primary_map: bool  # a primary's map, which normally carries over to the general


PrecinctSource = Literal["you", "county"]


class CountySource(BaseModel):
    """The county whose records gave commissioner and JP precincts: its list of its election
    precincts ("table"), or its maps of its commissioner and JP precincts, laid over the voter's
    election precinct ("maps")."""

    county: str  # "Harris"
    method: Literal["table", "maps"]


class Districts(BaseModel):
    cd: int | None = None
    sd: int | str | None = None  # a name where the state names its districts ("Third Suffolk")
    hd: int | str | None = None
    sboe: int | None = None
    election_precinct: ElectionPrecinct | None = None
    commissioner: int | None = None
    jp: int | None = None
    constable: int | None = None
    precinct_sources: dict[str, PrecinctSource] = Field(default_factory=dict)  # "commissioner", "jp", "constable" -> who gave it
    county_source: CountySource | None = None  # when the county's records gave any, even ones the voter then changed
    not_up: list[str] = Field(default_factory=list)  # the voter's districts ("sd", "sboe") whose seat isn't on this ballot
    entered: list[str] = Field(default_factory=list)  # the districts ("cd", "sd", "hd", "sboe") the voter gave


class ElectionRef(BaseModel):
    id: int | None = None
    name: str
    type: str | None = None
    date: str | None = None
    party: str | None = None


class KeyDates(BaseModel):
    """One election's deadlines (ISO dates): Texas's from its SOS's Important Election Dates page,
    other states' worked out from their election law (states/key_dates.py)."""

    election: str  # the page's name for it: "Uniform Election Date", "Primary Runoff Election"
    election_day: str
    register_by: str | None = None
    mail_apply_by: str | None = None  # the application must arrive (not be postmarked) by then
    early_voting_start: str | None = None
    early_voting_end: str | None = None
    source: str  # "Texas Secretary of State"
    source_url: str
    computed: bool = False  # worked out by rule, so the source explains the rules rather than lists the dates


class Outline(BaseModel):
    """One district's shape for the map: rings of (lon, lat), outer rings and holes alike."""

    kind: Literal["cd", "sd", "hd", "sboe", "election_precinct"]  # as in Districts
    number: int | str  # the district's number, or the precinct's name ("300")
    rings: list[list[tuple[float, float]]]


class DistrictOutlines(BaseModel):
    outlines: list[Outline]  # in the order asked: U.S. House, State Senate, State House, SBOE, election precinct
    notes: list[str]  # outlines that are off or couldn't be had
    street_map: bool  # whether the street map (/api/tiles) is on


class LeftOut(BaseModel):
    """Races the voter's districts and precincts don't settle. They're left off the ballot, with no
    cards fetched, unless the request asks for them (``all_races``)."""

    races: int
    missing: list[str]  # the districts and precincts ("cd", "jp") whose numbers would settle some of them
    lines: list[str]  # a sentence each: "Your Justice of the Peace precinct isn't known: 6 races depend on it."
    shown: bool  # asked for, so they're in Ballot.maybe


class SourceRef(BaseModel):
    id: str
    label: str


class Coverage(BaseModel):
    """How much of the voter's state's ballot Pallot has (coverage.py), which the page draws by."""

    ballot: Literal["state", "list", "fec"] = "state"  # Texas SOS's ballot, another state's official list, or the FEC's filers (unverified)
    districts: list[str] = ["cd", "sd", "hd", "sboe"]  # the district kinds found and shown
    precincts: bool = True  # election, commissioner and JP precincts
    outlines: bool = True  # the districts' map
    labels: dict[str, str] = {}  # a district kind's name in this state where it isn't the usual one: {"hd": "State Assembly"}


class Ballot(BaseModel):
    election_date: str | None
    elections: list[ElectionRef]
    key_dates: KeyDates | None = None  # none when the source is off, or has no election on this date
    location: Location
    districts: Districts
    races: list[Race]
    maybe: list[MaybeSection]
    notes: list[str]
    warnings: list[str]
    left_out: LeftOut | None = None
    sources_off: list[SourceRef] = []  # the sources Pick by rule's conditions use that this request has off
    street_map: bool = True  # the street map (/api/tiles) is on for this request
    coverage: Coverage = Coverage()


class PrecinctInput(BaseModel):
    commissioner: int | None = Field(default=None, ge=1, le=4)
    jp: int | None = Field(default=None, ge=1, le=99)
    constable: int | None = Field(default=None, ge=1, le=99)


class DistrictInput(BaseModel):
    """District numbers the voter gives, which win over the ones found from the address. The
    highest is any state's: California's 52 House seats, Minnesota's 67 senators, New Hampshire's
    400 representatives."""

    cd: int | None = Field(default=None, ge=1, le=52)
    sd: int | None = Field(default=None, ge=1, le=67)
    hd: int | None = Field(default=None, ge=1, le=400)
    sboe: int | None = Field(default=None, ge=1, le=15)


class BallotRequest(BaseModel):
    """An address, or the state, county and (optional) precinct number on a voter registration
    card. A card without a state is Texas's."""

    address: str | None = Field(default=None, min_length=5, max_length=200)
    state: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    county: str | None = Field(default=None, min_length=2, max_length=40)
    precinct: str | None = Field(default=None, min_length=1, max_length=8)
    election_date: dt.date | None = None
    party: Literal["D", "R"] | None = None
    precincts: PrecinctInput | None = None
    districts: DistrictInput | None = None
    all_races: bool = False  # also the races the districts and precincts don't settle ("Show these races anyway")

    @field_validator("precinct", mode="before")
    @classmethod
    def _precinct_as_text(cls, value: object) -> object:
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
        return (value.strip() or None) if isinstance(value, str) else value

    @field_validator("state", mode="before")
    @classmethod
    def _state_upper(cls, value: object) -> object:
        return (value.strip().upper() or None) if isinstance(value, str) else value

    @model_validator(mode="after")
    def _address_or_card(self) -> BallotRequest:
        if not self.address and not self.county:
            raise ValueError("Enter an address, or the state and county on your voter registration card.")
        if not self.address and not self.state:
            self.state = "TX"
        return self

    @property
    def voter_card(self) -> bool:
        return not self.address


class CardState(BaseModel):
    """A state on the voter card: its counties, for the County box's suggestions, and the
    districts its coverage shows, for the district boxes."""

    code: str  # "TX"
    name: str  # "Texas"
    counties: list[str]  # the Census's names: "Travis County", "Orleans Parish"
    districts: list[str]  # "cd", "sd", "hd", "sboe"
    precincts: bool  # commissioner and JP precincts too
    labels: dict[str, str] = {}  # its own name for a district kind (Coverage.labels)


class EntryConfig(BaseModel):
    """What the entry card offers: GET /api/config."""

    default_entry: Literal["address", "voter_card"]  # the tab a first visit starts on
    voter_card: bool  # the voter card tab shows
    states: list[CardState]  # by name, for the State box


class ElectionDate(BaseModel):
    date: str
    elections: list[ElectionRef]
    has_primaries: bool


class AddressSuggestion(BaseModel):
    label: str  # "1100 Congress Ave, Austin, TX 78701"


class SuggestResult(BaseModel):
    enabled: bool  # suggestions are on, as this voter has them in Settings
    suggestions: list[AddressSuggestion]


class SourceStatus(BaseModel):
    """A source's row in Settings: its switch, one sentence, and one line of fine print. What the
    server keeps for it is pallot-cache check's, on the host."""

    id: str
    label: str
    description: str
    group: str  # the id of the SourceGroupInfo it's drawn under
    toggleable: bool
    enabled: bool  # for this voter: their choice in this browser, or else Pallot's default
    busy: bool  # a download running (the precinct map, for a lookup)
    counts: list[str] = []  # what it holds: "101 Texas candidates", "1,020 in 27 states"
    updated: str | None = None  # ISO date or time its data dates from
    frozen: bool = False  # comes with Pallot as captured, never fetched (an endorsement list): "captured", not "updated"
    notice: str | None = None  # a short line only when the voter should know: a pause, a failure, a missing key
    notice_tone: Tone = "info"


class SourceGroupInfo(BaseModel):
    """A heading in Settings' Sources, with the sources whose ``group`` is its id under it."""

    id: str
    title: str
    description: str
    toggle_all: bool  # offers "Turn all on" and "Turn all off"


class SourcesOverview(BaseModel):
    groups: list[SourceGroupInfo]  # in the order Settings draws them
    sources: list[SourceStatus]


class EndorsementListInfo(BaseModel):
    """An organization's endorsement list that came with Pallot, or that Pallot fetches (``live``)."""

    source: str
    label: str  # "JVP Action"
    organization: str  # "Jewish Voice for Peace Action"
    url: str
    captured: str | None  # ISO date: when it was copied, or a live list's copy kept was fetched (None: not yet)
    description: str
    live: bool = False
    enabled: bool  # for this voter
