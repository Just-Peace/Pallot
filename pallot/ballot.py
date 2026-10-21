"""Assemble one voter's ballot from the enabled sources.

The Census gives the county and districts, at the address or, for a voter card, at points inside its
precinct on the precinct map (locate_card), the SBOE map adds the State Board of
Education district, and the Texas Legislative Council's precinct map the election precinct,
whose county's records may settle the commissioner and JP precincts. The county's Texas SOS
ballot order is filtered down to those districts. Then every candidate gets a card from each
enabled source (enrich.py).

Another state with an adapter for its official list (states/) gets every race on that list
that the address, or a voter card's county and districts, places (states/place.py). A state
without one, or whose list can't be had, gets only the races for Congress, from the people who
filed with the FEC, each unverified.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import zipfile
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from bundles.store import Seeded

from . import counties, coverage, enrich
from .config import Config
from .http_cache import CallStats, HttpCache, UpstreamError, track_calls
from .models import (
    GROUPS, Ballot, BallotRequest, Candidate, CountySource, Districts, ElectionDate, ElectionPrecinct, ElectionRef,
    KeyDates, LeftOut, Location, MaybeSection, PrecinctSource, Race,
)
from .offices import DISTRICT_KINDS, KIND_LABELS, PRECINCT_KINDS, OfficeScope, classify
from .settings import Sources
from .sources import county_precincts as county_precincts_source
from .sources import election_precincts as election_precincts_source
from .sources import fec as fec_source
from .sources import google as google_source
from .sources import ca_key_dates as ca_key_dates_source
from .sources import key_dates as key_dates_source
from .sources import sos as sos_source
from .sources.census import TEXAS_FIPS, Census, Place
from .sources.county_precincts import CountyPrecincts
from .sources.election_precincts import ElectionPrecincts, StillDownloading
from .sources.endorsement_feeds import EndorsementSource
from .sources.fec import Fec
from .sources.google import Google
from .sources.ca_key_dates import CaKeyDatesPage
from .sources.key_dates import Deadlines, KeyDatesPage
from .sources.nominatim import Nominatim
from .sources.osm_tiles import Tiles
from .sources.officeholders import Officeholders
from .sources.wikidata import Wikidata
from .sources.polls import Polls
from .sources.sboe import SboeMap
from .sources.sos import Election, Lookups, Sos, find_county, still_running
from .sources.suggestions import Suggestions
from .sources.tec import Tec
from .sources.tigerweb import Tigerweb
from .sources.trackaipac import TrackAipac
from .sources.voteforpeace import VoteForPeace
from .states import StateList
from .states import key_dates as state_key_dates
from .states import place as state_place
from .text import display_office, display_person, display_time

log = logging.getLogger("uvicorn.error")

MAYBE_SECTIONS = {
    "precinct": (
        "Depends on your commissioner or JP precinct",
        "These races are only on some ballots in {county} County. Your commissioner and justice of the peace "
        "precincts are printed on your voter registration certificate; enter them under \"Your districts\" at the top "
        "of your ballot to narrow this list.",
    ),
    "unconfirmed": (
        "Couldn't confirm",
        "Pallot couldn't work out which of these districts you're in, so check your county's sample ballot.",
    ),
}
WAITING_ORDER = (*DISTRICT_KINDS, "commissioner", "jp", "precinct_other")
SOS_OFF = "Texas ballots come from Texas SOS, which is turned off. Turn it on in Settings."


class BallotError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Services:
    config: Config
    sources: Sources  # the defaults; a request's own come from Sources.chosen()
    cache: HttpCache
    census: Census
    nominatim: Nominatim
    google: Google
    suggestions: Suggestions
    sboe: SboeMap
    election_precincts: ElectionPrecincts
    county_precincts: CountyPrecincts
    sos: Sos
    trackaipac: TrackAipac
    voteforpeace: VoteForPeace
    endorsements: list[EndorsementSource]  # the frozen lists found at startup and the live feeds, by label
    fec: Fec
    tec: Tec
    polls: Polls
    officeholders: Officeholders
    wikidata: Wikidata
    key_dates: KeyDatesPage
    ca_key_dates: CaKeyDatesPage
    tigerweb: Tigerweb
    tiles: Tiles
    states: dict[str, StateList] = field(default_factory=dict)  # the official lists of states other than Texas, by postal code
    today: Callable[[], dt.date] = dt.date.today
    bundles: dict[str, Seeded] = field(default_factory=dict)  # what came with Pallot, by bundle (Settings)


@dataclass
class SosData:
    county_names: set[str]
    lookups: Lookups
    orders: list[tuple[Election, list[dict[str, Any]]]]


def election_ref(election: Election) -> ElectionRef:
    return ElectionRef(
        id=election.id,
        name=display_office(election.name),
        type=election.type,
        date=election.day.isoformat() if election.day else None,
        party=election.party,
    )


def key_dates_of(found: Deadlines) -> KeyDates:
    def iso(day: dt.date | None) -> str | None:
        return day.isoformat() if day else None

    guide = state_key_dates.GUIDES[found.state]
    return KeyDates(
        election=found.name,
        election_day=found.day.isoformat(),
        register_by=iso(found.register_by),
        mail_apply_by=iso(found.mail_apply_by),
        early_voting_start=iso(found.early_start),
        early_voting_end=iso(found.early_end),
        source=guide.source,
        source_url=guide.url,
        computed=guide.computed,
    )


def computed_key_dates(state: str | None, day: dt.date) -> KeyDates | None:
    found = state_key_dates.computed(state, day)
    return key_dates_of(found) if found else None


async def election_dates(sos: Sos) -> list[ElectionDate]:
    upcoming = await sos.upcoming()
    return [
        ElectionDate(
            date=day.isoformat(),
            elections=[election_ref(e) for e in elections],
            has_primaries=any(e.party for e in elections),
        )
        for day, elections in upcoming.items()
    ]


async def locate(svc: Services, address: str, sources: Sources) -> tuple[Place, Location]:
    """The address's place: the Census geocoder's, else (a point to ask the Census about) Nominatim's,
    else Google's when it has a key and the voter has it on."""
    try:
        place = await svc.census.geocode(address)
        geocoder, approximate, label = "census", False, place.matched_address if place else None
        if place is None:
            geocoder = "nominatim"
            point = await svc.nominatim.locate(address)
            if point is None and svc.google.keyed and sources.enabled(google_source.SOURCE):
                geocoder = "google"
                point = await svc.google.locate(address)
            if point is None:
                raise BallotError(422, "Pallot couldn't find that address. Check the street, city and ZIP code, or "
                                       "look up by your voter card.")
            place = await svc.census.at(point.lat, point.lon)
            if place is None:
                raise BallotError(422, "That address doesn't seem to be in the United States.")
            approximate, label = point.approximate, point.label
    except UpstreamError as exc:
        if exc.until:
            raise BallotError(502, f"The address lookup is paused until {display_time(exc.until)} after refusing a "
                                   "request. Addresses already looked up still work.") from exc
        log.warning("%s", exc)
        raise BallotError(502, "The address lookup isn't answering right now. Try again in a minute.") from exc
    if place.state not in coverage.STATES:
        raise BallotError(422, "Pallot covers addresses in the 50 states and DC.")
    location = Location(
        matched_address=label,
        lat=place.lat,
        lon=place.lon,
        state=place.state,
        state_name=coverage.NAMES[place.state],
        county=place.county,
        city=place.city,
        school_district=place.school_district,
        geocoder=geocoder,
        approximate=approximate,
        county_name=place.county_name,
    )
    return place, location


@dataclass
class CardPlace:
    """Where a voter card's precinct is: the Census's place at a point inside it, and the precinct
    on the map; or, when the map can't place it, only the county, with a note or a warning saying
    why."""

    county: str  # as Texas names it: "Travis"
    county_fips: str  # "453", as Place has it
    location: Location
    place: Place | None = None
    precinct: ElectionPrecinct | None = None
    note: str | None = None
    warning: str | None = None


def _shared(places: list[Place]) -> Place:
    """The first place, keeping only the districts, city and school district every one of them has."""
    first = places[0]
    keep = {
        attr: getattr(first, attr) if len({getattr(p, attr) for p in places}) == 1 else None
        for attr in ("cd", "sd", "hd", "city", "school_district")
    }
    return replace(first, **keep, matched_address=None, block_point=None)


async def locate_card(svc: Services, request: BallotRequest, sources: Sources) -> CardPlace:
    """A voter card's state and county, and for a Texas precinct, as locate() places an address:
    points inside it from the Texas Legislative Council's precinct map, and the Census's districts
    there, kept where every point agrees. No address or geocoder is involved. Without a precinct,
    the map (turned off, still downloading, unreadable) or the precinct on it, or outside Texas,
    only the county, so the ballot has the statewide and county races and the districts the voter
    typed."""
    state = request.state or "TX"
    states = counties.state_names()
    if state not in states:
        raise BallotError(422, "Pallot covers the 50 states and DC.")
    typed = (request.county or "").strip()
    known = counties.find(state, typed)
    if known is None:
        raise BallotError(422, f"{states[state]} has no county called “{typed}”. Check the spelling on your voter "
                               "registration card.")
    name, fips = known.name, known.fips

    def location(place: Place | None) -> Location:
        return Location(
            matched_address=None, lat=place.lat if place else None, lon=place.lon if place else None,
            state=state, state_name=states[state], county=name, county_name=known.full_name,
            city=place.city if place else None, school_district=place.school_district if place else None,
            geocoder=None, source="voter_card",
        )

    card = CardPlace(county=name, county_fips=f"{fips:03d}", location=location(None))
    if state != "TX":
        return card
    precinct = request.precinct
    fallback = (f"so this ballot has the statewide and {known.full_name} races, and any districts you enter under "
                "\"More districts\".")
    if not precinct:
        card.note = f"Without your precinct number, Pallot can't find your districts, {fallback}"
        return card
    if not sources.enabled(election_precincts_source.SOURCE):
        card.note = (f"\"Election precincts\" is off, so Pallot can't find your districts from your precinct, {fallback} "
                     f"[Turn it on in Settings](settings.html#toggle-{election_precincts_source.SOURCE}).")
        return card
    try:
        on_map = await svc.election_precincts.card(fips, precinct)
    except StillDownloading as exc:
        card.note = (f"Pallot finds your districts on its precinct map, which is still downloading ({exc.size / 1_048_576:.0f} "
                     f"MB, the first time only), {fallback} Reload the page in a minute.")
        return card
    except (UpstreamError, OSError, ValueError, zipfile.BadZipFile) as exc:
        log.warning("%s: %s", election_precincts_source.SOURCE, str(exc).removeprefix(f"{election_precincts_source.SOURCE}: "))
        card.warning = f"Couldn't load the Texas Legislative Council's precinct map, {fallback}"
        return card
    if on_map is None:
        card.warning = (f"The Texas Legislative Council's precinct map has no precinct {precinct} in {name} County, "
                        f"{fallback} Check the number on your voter registration certificate.")
        return card
    found, points = on_map
    card.precinct = ElectionPrecinct(
        name=found.name, code=found.code, county=found.county, map_label=found.label, primary_map=found.primary
    )
    if not points:
        card.note = f"Precinct {found.name} is too small to find on the precinct map, {fallback}"
        return card
    try:
        places = [p for p in await asyncio.gather(*(svc.census.at(lat, lon) for lat, lon in points)) if p is not None]
    except UpstreamError as exc:
        if exc.until:
            raise BallotError(502, f"The US Census is paused until {display_time(exc.until)} after refusing a request. "
                                   "Precincts already looked up still work.") from exc
        log.warning("%s", exc)
        raise BallotError(502, "The US Census isn't answering right now. Try again in a minute.") from exc
    places = [p for p in places if p.state_fips == TEXAS_FIPS and p.county_fips == card.county_fips]
    if not places:
        card.warning = f"The US Census doesn't place precinct {found.name} in {name} County, {fallback}"
        return card
    card.place = _shared(places)
    card.location = location(card.place)
    return card


def placement(scope: OfficeScope, districts: Districts) -> str:
    """ "include", "skip" (another district's race), or the maybe-section it belongs in."""
    if scope.kind in DISTRICT_KINDS or scope.kind in PRECINCT_KINDS:
        mine = getattr(districts, scope.kind)
        if mine is None:
            return "unconfirmed" if scope.kind in DISTRICT_KINDS else "precinct"
        return "include" if mine == scope.number else "skip"
    if scope.kind == "precinct_other":
        return "precinct"
    return "include"


def _placeable(row: dict[str, Any]) -> bool:
    """A statewide-list race whose reach is known without a county: federal, statewide, or
    a district the voter's address gives (U.S. House, Legislature, SBOE), which placement()
    then checks."""
    office_type = row.get("cdOfficeType")
    if office_type in ("FD", "SW"):
        return True
    return office_type == "SR" and classify(row.get("txOfficeName") or "", office_type).kind in DISTRICT_KINDS


def _declared_write_ins(rows: list[dict[str, Any]], running: list[dict[str, Any]], county: str | None) -> list[dict[str, Any]]:
    """The statewide list's declared write-ins, since the county's ballot order lists only the
    printed names: a county office's only from this county, and another's for a race on the ballot
    order or, when it has only write-ins and so no ballot-order row, one _placeable places. A
    district judge or DA with only write-ins names no county, so it's left out. The list has no
    nbOfficeTypeOrder; it's taken from the ballot order, so such a race sorts into its place."""
    offices = {row.get("idOffice") for row in rows}
    printed = {row.get("idCandidate") for row in rows}
    type_order = {row.get("cdOfficeType"): row.get("nbOfficeTypeOrder") for row in rows}
    wanted = (county or "").upper()

    def kept(r: dict[str, Any]) -> bool:
        if r.get("txCountyName"):
            return r["txCountyName"].upper() == wanted
        return r.get("idOffice") in offices or _placeable(r)

    return [
        {**r, "nbOfficeTypeOrder": r.get("nbOfficeTypeOrder") or type_order.get(r.get("cdOfficeType"))}
        for r in running
        if r.get("cdParty") == "W" and r.get("idCandidate") not in printed and kept(r)
    ]


def _jp_is_constable(precincts: dict[str, int | None]) -> dict[str, int | None]:
    filled = dict(precincts)
    for kind, twin in (("jp", "constable"), ("constable", "jp")):
        if kind in filled and twin not in filled:
            filled[twin] = filled[kind]
    return filled


def _sort_key(row: dict[str, Any], name: str) -> tuple[int, int, int, str]:
    return (
        row.get("nbOfficeTypeOrder") or 99,
        row.get("nbSortOrder") or 999,
        row.get("nbSecondarySortOrder") or 999,
        name,
    )


async def start_ballot(svc: Services, request: BallotRequest, sources: Sources | None = None) -> _Builder:
    """A builder whose ``ballot`` has its races but no cards yet; ``finish()`` adds them. Every
    BallotError is raised here, before any card is asked for."""
    builder = _Builder(svc, request, track_calls(), sources or svc.sources)
    await builder.races()
    return builder


async def _nothing() -> None:
    return None


class _Builder:
    def __init__(self, svc: Services, request: BallotRequest, calls: CallStats, sources: Sources):
        self.svc = svc
        self.request = request
        self.calls = calls
        self.sources = sources
        self.use_sos = sources.enabled(sos_source.SOURCE)
        self.use_key_dates = sources.enabled(key_dates_source.SOURCE)
        self.use_election_precincts = sources.enabled(election_precincts_source.SOURCE)
        self.use_county_precincts = self.use_election_precincts and sources.enabled(county_precincts_source.SOURCE)
        self.notes: list[str] = []
        self.warnings: list[str] = []
        self.sos_error: str | None = None  # why Texas SOS didn't answer, for the error when there's no ballot
        self.ballot_rows: dict[str, dict[str, Any]] = {}  # candidate key -> its SOS row
        self.scopes: dict[str, OfficeScope] = {}  # SOS race key -> what its office covers
        self.included: set[tuple[str, int | None]] = set()  # (kind, number) of SOS races kept
        self.unlisted: set[str] = set()  # SOS race keys with only write-ins, so not on the county's ballot order
        self.maybe: dict[str, list[Race]] = {key: [] for key in MAYBE_SECTIONS}
        self.waiting: Counter[str] = Counter()  # the left-out races, by what would settle them (WAITING_ORDER)
        self.where = "address" if not request.voter_card else "precinct" if request.precinct else "county"
        self.ballot: Ballot  # set by races(), for finish()
        self.every_race: list[Race] = []
        self.context = enrich.Context()

    async def races(self) -> Ballot:
        """The ballot without cards, kept in ``self.ballot`` for ``finish()``. A state Pallot has
        only the FEC's filers for (coverage.py) takes _from_fec instead."""
        card: CardPlace | None = None
        if self.request.address:
            place, location = await locate(self.svc, self.request.address, self.sources)
            cover = coverage.of(location.state)
            if cover.ballot == "list":
                return await self._from_list(location, Districts(cd=place.cd, sd=place.sd, hd=place.hd), cover)
            if cover.ballot == "fec":
                return await self._from_fec(location, place.cd, cover)
            if not self.use_sos:
                raise BallotError(400, SOS_OFF)
            county_name, county_fips = place.county, place.county_fips
        else:
            card = await locate_card(self.svc, self.request, self.sources)
            place, location = card.place, card.location
            cover = coverage.of(location.state)
            if cover.ballot != "state":
                districts = self._card_districts(location.state, cover)
                if cover.ballot == "list":
                    return await self._from_list(location, districts, cover)
                return await self._from_fec(location, districts.cd, cover)
            if not self.use_sos:
                raise BallotError(400, SOS_OFF)
            county_name, county_fips = card.county, card.county_fips
            self.notes += [card.note] if card.note else []
            self.warnings += [card.warning] if card.warning else []

        elections, day = await self._elections()
        if card:
            precinct_search = self._card_precincts(card)
        elif self.use_election_precincts and place:
            precinct_search = self._precinct_and_county(place, location)
        else:
            precinct_search = _nothing()
        sos_data, deadlines, sboe, found_precincts = await asyncio.gather(
            self._sos(elections, county_name, county_fips) if elections else _nothing(),
            self._key_dates() if self.use_key_dates else _nothing(),
            self._sboe(place) if place else _nothing(),
            precinct_search,
        )
        election_precinct, county = found_precincts or (None, None)
        if sos_data is None:
            if self.sos_error and (until := self.svc.cache.paused_until("sos")):
                raise BallotError(502, f"Texas SOS is paused until {display_time(until)} after refusing a request, "
                                       f"and nothing is cached yet for this {self.where}.")
            if self.sos_error:
                raise BallotError(502, f"Texas SOS isn't answering right now, and nothing is kept yet for this {self.where}. "
                                       "Try again in a minute.")
            raise BallotError(404, " ".join(self.warnings) or f"No ballot data found for this {self.where}.")

        precincts, precinct_sources = self._precincts(county)
        entered = self.request.districts.model_dump(exclude_unset=True) if self.request.districts else {}
        found = {"cd": place.cd if place else None, "sd": place.sd if place else None,
                 "hd": place.hd if place else None, "sboe": sboe}
        districts = Districts(
            **{**found, **entered},
            entered=[kind for kind in DISTRICT_KINDS if kind in entered],
            election_precinct=election_precinct,
            precinct_sources=precinct_sources,
            county_source=CountySource(county=county.county.name, method=county.county.method)
            if county and county.numbers else None,
            **precincts,
        )

        races = self._sos_races(sos_data, districts)
        self._district_notes(districts, [e for e, _ in sos_data.orders])

        shown = self.request.all_races
        maybe = [
            MaybeSection(
                id=key,
                title=MAYBE_SECTIONS[key][0],
                explanation=MAYBE_SECTIONS[key][1].format(county=location.county or "your"),
                races=found,
            )
            for key, found in self.maybe.items()
            if found and shown
        ]
        every_race = races + [race for section in maybe for race in section.races]
        found = next((d for d in deadlines or () if d.day == day), None)
        self.context = enrich.Context(
            elections={e.id: e for e, _ in sos_data.orders},
            ballot_rows=self.ballot_rows,
            sos_lookups=sos_data.lookups,
            day=day,
            scopes=self.scopes,
            county=location.county,
            city=location.city,
            state=location.state,
        )
        self.every_race = every_race

        used = {race.election_id for race in every_race}
        self.ballot = Ballot(
            election_date=day.isoformat() if day else None,
            elections=[election_ref(e) for e, _ in sos_data.orders if e.id in used],
            key_dates=key_dates_of(found) if found else None,
            location=location,
            districts=districts,
            races=races,
            maybe=maybe,
            notes=list(self.notes),
            warnings=list(self.warnings),
            left_out=self._left_out(shown),
            coverage=coverage.of(location.state).info(),
        )
        return self.ballot

    def _card_districts(self, state: str, cover: coverage.Coverage) -> Districts:
        """A voter card's districts outside Texas: the ones the voter typed that the state's
        coverage shows, and an at-large state's one U.S. House seat."""
        typed = self.request.districts.model_dump(exclude_unset=True) if self.request.districts else {}
        entered = {kind: number for kind, number in typed.items() if kind in cover.districts and number is not None}
        cd = entered.get("cd", 0 if state in coverage.AT_LARGE else None)
        return Districts(**{**entered, "cd": cd}, entered=list(entered))

    async def _from_list(self, location: Location, districts: Districts, cover: coverage.Coverage) -> Ballot:
        """The races on the state's official list that the address or voter card places
        (states/place.py), the ones it can't settle left out unless asked for, as Texas's precinct
        races. With the list off, not yet out, or not to be had, the FEC's races for Congress
        instead, saying why."""
        lists = self.svc.states.get(location.state)
        if lists is None:
            return await self._from_fec(location, districts.cd, coverage.FEDERAL)
        day = fec_source.general_day(self.svc.today())
        when = f"{day:%b} {day.day}, {day.year}"
        if not self.sources.enabled(lists.source):
            self.notes.append(f"The list of candidates from the {lists.label} is turned off, so this ballot has only "
                              f"the races for Congress. [Turn it on in Settings](settings.html#toggle-{lists.source}).")
            return await self._from_fec(location, districts.cd, coverage.FEDERAL)
        try:
            filings = await lists.filings(day)
        except UpstreamError as exc:
            log.warning("%s", exc)
            self.warnings.append(f"Couldn't load the list of candidates from the {lists.label}, so this ballot has "
                                 "only the races for Congress.")
            return await self._from_fec(location, districts.cd, coverage.FEDERAL)
        if not filings:
            self.notes.append(f"The {lists.label} hasn't published its list of candidates for {when} yet, so this "
                              "ballot has only the races for Congress.")
            return await self._from_fec(location, districts.cd, coverage.FEDERAL)
        requested = self.request.election_date
        if requested and requested != day:
            self.warnings.append(f"Pallot has only the general election on {when} here; showing it.")
        if location.source == "voter_card":
            self.notes.append(f"Without your address, this ballot has the statewide and {location.county_name} races, "
                              "and those of any districts you enter under \"More districts\". Your town's races "
                              "aren't shown: your county's sample ballot has them.")
        found = state_place.races(filings, location, districts, state=lists.state, source=lists.source, url=lists.page)
        if not (found.races or found.unconfirmed):
            raise BallotError(404, f"The {lists.label} lists no races for this {self.where}.")
        if found.unplaced:
            one = len(found.unplaced) == 1
            what = ("court" if any(f.group == "judicial" for f in found.unplaced)
                    else " and ".join(sorted({f.family for f in found.unplaced})))
            self.notes.append(f"The {lists.label} also lists {len(found.unplaced)} {what} "
                              f"{'race' if one else 'races'} without saying which counties "
                              f"{'it covers' if one else 'they cover'}, so "
                              f"{'it isn' if one else 'they aren'}'t shown: your county's sample "
                              "ballot has yours.")
        shown = self.request.all_races
        count = len(found.unconfirmed)
        maybe = [MaybeSection(id="unconfirmed", title=MAYBE_SECTIONS["unconfirmed"][0],
                              explanation="These races are on the ballot in only part of your county or town, and "
                                          "Pallot can't tell from your address whether yours is one. Your county's "
                                          "sample ballot says.",
                              races=found.unconfirmed)] if count and shown else []
        left_out = LeftOut(
            races=count, missing=[], shown=shown,
            lines=[f"{count} {'race is' if count == 1 else 'races are'} on the ballot in only part of your county or "
                   "town, and Pallot can't tell whether yours is one."],
        ) if count else None
        self.every_race = found.races + [race for section in maybe for race in section.races]
        self.context = enrich.Context(day=day, scopes=found.scopes, county=location.county, city=location.city,
                                      state=location.state)
        self.ballot = Ballot(
            election_date=day.isoformat(),
            elections=[ElectionRef(name=f"{day.year} General Election", type="GE", date=day.isoformat())],
            key_dates=await self._state_key_dates(location.state, day),
            location=location,
            districts=districts,
            races=found.races,
            maybe=maybe,
            notes=list(self.notes),
            warnings=list(self.warnings),
            left_out=left_out,
            coverage=cover.info(),
        )
        return self.ballot

    async def _from_fec(self, location: Location, cd: int | None, cover: coverage.Coverage) -> Ballot:
        """The races for Congress from the FEC's filers (fec.ballot_races), for a state without
        its own list: the Senate race when the FEC lists one this cycle, and the House race of
        district ``cd``. No state source or precincts; key dates only where they're worked out by
        rule (states/key_dates.py), or California's from its SOS (_state_key_dates)."""
        if not self.sources.enabled(fec_source.SOURCE):
            raise BallotError(400, "Outside Texas, Pallot's races come from the FEC, which is turned off. Turn on "
                                   "the FEC in Settings.")
        fec = self.svc.fec
        day = fec_source.general_day(self.svc.today())
        requested = self.request.election_date
        if requested and requested != day:
            self.warnings.append(f"Outside Texas, Pallot has only the general election on {day:%b %d, %Y}; showing it.")
        state = location.state
        cycle = fec_source.cycle_of(day)
        try:
            senate = (state, 0) in await fec.elections(cycle, "senate")
        except UpstreamError as exc:
            log.warning("%s", exc)
            self.warnings.append("Couldn't load the FEC's list of this year's Senate races, so the U.S. Senate race "
                                 "isn't shown.")
            senate = False
        if cd is None and location.source == "voter_card":
            self.notes.append("Enter your U.S. House district under \"More districts\" to see its race.")
        elif cd is None:
            self.warnings.append("Couldn't tell your U.S. House district from your address, so its race isn't shown.")
        try:
            races = await fec_source.ballot_races(fec, state, cd, senate, day)
        except UpstreamError as exc:
            if exc.until:
                raise BallotError(502, f"The FEC is paused until {display_time(exc.until)} after refusing a request, and "
                                       f"nothing is kept yet for this {self.where}.") from exc
            log.warning("%s", exc)
            raise BallotError(502, f"The FEC isn't answering right now, and nothing is kept yet for this {self.where}. "
                                   "Try again in a minute.") from exc
        if not races:
            raise BallotError(404, " ".join(self.warnings) or f"No ballot data found for this {self.where}.")
        self.context = enrich.Context(day=day, county=location.county, city=location.city, state=location.state)
        self.every_race = races
        self.ballot = Ballot(
            election_date=day.isoformat(),
            elections=[ElectionRef(name=f"{day.year} General Election", type="GE", date=day.isoformat())],
            key_dates=await self._state_key_dates(location.state, day),
            location=location,
            districts=Districts(cd=cd),
            races=races,
            maybe=[],
            notes=list(self.notes),
            warnings=list(self.warnings),
            coverage=cover.info(),
        )
        return self.ballot

    async def finish(self) -> Ballot:
        """Adds every source's cards to ``self.ballot`` (in place), and logs what the lookup cost."""
        outcome = await enrich.run(self.svc, self.every_race, self.sources, self.context)
        self.warnings += outcome.warnings
        self.notes += outcome.notes
        self.ballot.notes = self.notes
        self.ballot.warnings = self.warnings
        self.calls.log("lookup")
        return self.ballot

    # -- gathering -----------------------------------------------------------------

    async def _elections(self) -> tuple[list[Election], dt.date | None]:
        requested = self.request.election_date
        try:
            upcoming = await self.svc.sos.upcoming()
        except UpstreamError as exc:
            self.sos_error = str(exc)
            log.warning("%s", exc)
            return [], requested
        if not upcoming:
            self.warnings.append("Texas SOS doesn't list any upcoming elections.")
            return [], requested
        day = requested if requested in upcoming else next(iter(upcoming))
        if requested and requested != day:
            self.warnings.append(f"Texas SOS lists no election on {requested:%b %d, %Y}; showing {day:%b %d, %Y}.")
        on_day = upcoming[day]
        chosen = [e for e in on_day if not e.party]
        primaries = [e for e in on_day if e.party]
        if primaries:
            if self.request.party:
                chosen += [e for e in primaries if e.party == self.request.party]
            else:
                self.warnings.append("This date has party primaries. Choose Democratic or Republican to see those races.")
        return chosen, day

    async def _sos(self, elections: list[Election], county: str | None, county_fips: str | None) -> SosData | None:
        sos = self.svc.sos
        try:
            listed, lookups = await asyncio.gather(sos.counties(), sos.lookups())
            county_id = find_county(listed, county, county_fips)
            if county_id is None:
                self.warnings.append(f"Texas SOS doesn't list {county} County.")
                return None
            orders = await asyncio.gather(*(self._rows(e, county_id, county) for e in elections))
        except UpstreamError as exc:
            self.sos_error = str(exc)
            log.warning("%s", exc)
            return None
        return SosData(set(listed), lookups, list(zip(elections, orders)))

    async def _rows(self, election: Election, county_id: int, county: str | None) -> list[dict[str, Any]]:
        """The county's ballot order, plus the declared write-ins from the statewide candidate
        list (_declared_write_ins), with the races that have only write-ins noted in ``unlisted``;
        when the ballot order is empty (special elections), that list trimmed to
        the races it can place (_placeable). It names no county for judicial, DA or county
        races, so those are left out, with a note, rather than shown to every county."""
        order, statewide = await asyncio.gather(
            self.svc.sos.ballot_order(election, county_id), self.svc.sos.candidates(election), return_exceptions=True
        )
        if isinstance(order, BaseException):
            raise order
        rows = order.value or []
        if isinstance(statewide, UpstreamError) and rows:
            self.notes.append("Couldn't load the Texas Secretary of State's list of declared write-in candidates, so "
                              "they aren't listed; your county's sample ballot names them.")
            return rows
        if isinstance(statewide, BaseException):
            raise statewide
        running = [r for r in statewide.value or [] if still_running(r)]
        if rows:
            listed = {row.get("idOffice") for row in rows}
            write_ins = _declared_write_ins(rows, running, county)
            self.unlisted |= {f"sos:{election.id}:{r['idOffice']}" for r in write_ins if r.get("idOffice") not in listed}
            return rows + write_ins
        wanted = (county or "").upper()
        kept = [r for r in running if _placeable(r) or (r.get("txCountyName") or "").upper() == wanted]
        if len(kept) < len(running):
            where = f"{county} County" if county else "your county"
            self.notes.append(
                f"Texas SOS has no {where} ballot for the {display_office(election.name)}. Its statewide list doesn't "
                "say which counties judicial, district attorney and county races cover, so those aren't listed; "
                "check your county's sample ballot."
            )
        return kept

    async def _sboe(self, place: Place) -> int | None:
        try:
            return await self.svc.sboe.district_at(place.lat, place.lon)
        except (UpstreamError, ValueError, OSError, zipfile.BadZipFile):
            self.warnings.append("Couldn't load the State Board of Education map, so your SBOE district isn't known.")
            return None

    async def _precinct_and_county(
        self, place: Place, location: Location
    ) -> tuple[ElectionPrecinct | None, county_precincts_source.Found | None]:
        precinct, codes = await self._election_precinct(place, location)
        county = await self._county(place.county, place.county_fips, codes) if self.use_county_precincts and codes else None
        return precinct, county

    async def _card_precincts(
        self, card: CardPlace
    ) -> tuple[ElectionPrecinct | None, county_precincts_source.Found | None]:
        """The voter card's precinct, found on the map by locate_card(), and what its county's
        records say for it."""
        precinct = card.precinct
        if not (precinct and self.use_county_precincts):
            return precinct, None
        return precinct, await self._county(card.county, card.county_fips, (precinct.code,))

    async def _election_precinct(self, place: Place, location: Location) -> tuple[ElectionPrecinct | None, tuple[str, ...]]:
        """The precinct from the Texas Legislative Council's map, and the codes of the precincts the
        address may be in, for its county's records: the one found, or two near a line. No
        precinct, with a note saying why, for an approximate address (OpenStreetMap's street,
        where the block's point would agree with it and look certain), one near a precinct line,
        or while the first map downloads."""
        if location.approximate:
            self.notes.append("Your address could only be placed approximately, so your election precinct isn't "
                              "shown; it's on your voter registration certificate.")
            return None, ()
        if not place.county_fips:
            return None, ()
        try:
            answer = await self.svc.election_precincts.at(int(place.county_fips), (place.lat, place.lon), place.block_point)
        except StillDownloading as exc:
            self.notes.append(f"Your election precinct will show once its map has downloaded ({exc.size / 1_048_576:.0f} "
                              "MB, the first time only). Reload the page in a minute.")
            return None, ()
        except (UpstreamError, OSError, ValueError, zipfile.BadZipFile) as exc:
            log.warning("%s: %s", election_precincts_source.SOURCE, str(exc).removeprefix(f"{election_precincts_source.SOURCE}: "))
            self.warnings.append("Couldn't load the Texas Legislative Council's precinct map, so your election precinct "
                                 "isn't shown; it's on your voter registration certificate.")
            return None, ()
        found = answer.found
        if found is None:
            if answer.reason == "between":
                first, second = answer.between
                self.notes.append(f"Your address is near the line between election precincts {first} and {second}, and "
                                  "the map can't tell which side it's on; your voter registration certificate says which.")
            else:
                self.notes.append("Your address isn't inside one election precinct on the Texas Legislative Council's "
                                  "map; your voter registration certificate has it.")
            return None, answer.codes
        precinct = ElectionPrecinct(
            name=found.name, code=found.code, county=found.county, map_label=found.label, primary_map=found.primary
        )
        return precinct, answer.codes

    async def _county(
        self, name: str | None, fips: str | None, codes: tuple[str, ...]
    ) -> county_precincts_source.Found | None:
        """What the county's records say for those precincts; None, with a note, when they can't be read."""
        try:
            return await self.svc.county_precincts.at(int(fips or 0), codes)
        except (UpstreamError, OSError, ValueError) as exc:
            log.warning("%s: %s", county_precincts_source.SOURCE, str(exc).removeprefix(f"{county_precincts_source.SOURCE}: "))
            self.notes.append(f"Couldn't read {name or 'your'} County's records of its election precincts, so they "
                              "don't give your commissioner and JP precincts this time.")
            return None

    async def _state_key_dates(self, state: str, day: dt.date) -> KeyDates | None:
        """Another state's dates for the election on ``day``: California's from its SOS's page
        while that source is on, a state's whose deadlines are counts of days worked out by rule."""
        if state != "CA":
            return computed_key_dates(state, day)
        if not self.sources.enabled(ca_key_dates_source.SOURCE):
            return None
        try:
            found = await self.svc.ca_key_dates.on(day)
        except UpstreamError as exc:
            log.warning("%s", exc)
            self.notes.append("Couldn't load the key dates (registration, mail ballots) from the California Secretary "
                              "of State; see sos.ca.gov.")
            return None
        return key_dates_of(found) if found else None

    async def _key_dates(self) -> list[Deadlines]:
        try:
            return await self.svc.key_dates.deadlines()
        except UpstreamError as exc:
            log.warning("%s", exc)
            self.notes.append("Couldn't load the key dates (registration, early voting) from the Texas Secretary of "
                              "State; see VoteTexas.gov.")
            return []

    # -- building races ----------------------------------------------------------------

    def _precincts(
        self, county: county_precincts_source.Found | None
    ) -> tuple[dict[str, int | None], dict[str, PrecinctSource]]:
        """Each precinct's number, and who gave it: the voter, then the county's records. A note
        when the county's records couldn't settle one the voter didn't give."""
        given = _jp_is_constable(self.request.precincts.model_dump(exclude_unset=True) if self.request.precincts else {})
        from_county = _jp_is_constable(dict(county.numbers) if county else {})
        numbers: dict[str, int | None] = {}
        sources: dict[str, PrecinctSource] = {}
        for kind in PRECINCT_KINDS:
            for source, found in (("you", given), ("county", from_county)):
                if kind in found:
                    numbers[kind], sources[kind] = found[kind], source
                    break
            else:
                numbers[kind] = None
        if county:
            for kind, what in county_precincts_source.KIND_NAMES.items():
                if kind in county.unsettled and numbers[kind] is None and kind not in given:
                    self.notes.append(f"{county.unsettled[kind]}, so Pallot doesn't guess your {what} precinct; it's "
                                      "on your voter registration certificate.")
        return numbers, sources

    def _sos_races(self, data: SosData, districts: Districts) -> list[Race]:
        entries: list[tuple[tuple[int, int, int, str], Race]] = []
        for election, rows in data.orders:
            offices: dict[int, list[dict[str, Any]]] = {}
            for row in rows:
                offices.setdefault(row["idOffice"], []).append(row)
            for office_id, office_rows in offices.items():
                first = office_rows[0]
                scope = classify(first.get("txOfficeName") or "", first.get("cdOfficeType"), data.county_names)
                where = placement(scope, districts)
                if where == "skip" or (where == "unconfirmed" and f"sos:{election.id}:{office_id}" in self.unlisted):
                    continue
                ordered = sorted(
                    office_rows,
                    key=lambda r: (r.get("nbBallotOrder") is None, r.get("nbBallotOrder") or 0, r.get("txLastNameBallot") or ""),
                )
                self.scopes[f"sos:{election.id}:{office_id}"] = scope
                race = Race(
                    key=f"sos:{election.id}:{office_id}",
                    name=display_office(scope.name),
                    group=scope.group,
                    unexpired=scope.unexpired,
                    seat=scope.seat,
                    election_id=election.id,
                    election_name=display_office(election.name),
                    source=sos_source.SOURCE,
                    url=sos_source.BALLOT_ORDER_PAGE,
                    candidates=[self._sos_candidate(election, row, data.lookups) for row in ordered],
                )
                if where == "include":
                    self.included.add((scope.kind, scope.number))
                    entries.append((_sort_key(first, scope.name), race))
                else:
                    self.maybe[where].append(race)
                    self.waiting["jp" if scope.kind == "constable" else scope.kind] += 1
        entries.sort(key=lambda e: (GROUPS.index(e[1].group), e[0]))
        return [race for _, race in entries]

    def _sos_candidate(self, election: Election, row: dict[str, Any], lookups: Lookups) -> Candidate:
        key = f"sos:{election.id}:{row['idCandidate']}"
        self.ballot_rows[key] = row
        write_in = row.get("cdParty") == "W"  # the state's "W" marks a write-in, not a party
        code = None if write_in else row.get("cdParty")
        return Candidate(
            key=key,
            name=display_person(row.get("txFullNameBallot") or ""),
            party=code,
            party_name=(lookups.parties.get(code or "") or "").title() or None,
            incumbent=bool(row.get("flIncmbntGen")),
            write_in=write_in,
        )

    def _left_out(self, shown: bool) -> LeftOut | None:
        """What the races the districts and precincts don't settle are waiting for, a line each."""
        if not self.waiting:
            return None
        lines, missing = [], []
        for kind in WAITING_ORDER:
            count = self.waiting.get(kind, 0)
            if not count:
                continue
            races = f"{count} {'race depends' if count == 1 else 'races depend'}"
            if kind in KIND_LABELS:
                missing.append(kind)
                unit = "district" if kind in DISTRICT_KINDS else "precinct"
                lines.append(f"Your {KIND_LABELS[kind]} {unit} isn't known: {races} on it.")
            else:
                lines.append(f"{races} on a county precinct Pallot can't tell from your {self.where}.")
        return LeftOut(races=sum(self.waiting.values()), missing=missing, lines=lines, shown=shown)

    def _district_notes(self, districts: Districts, elections: list[Election]) -> None:
        """Say which of the voter's districts have no race here: State Senate and SBOE seats
        that aren't up (shown in Your districts), and U.S. House and State House races that
        should be in a general election but weren't found (a warning)."""
        districts.not_up = [
            kind for kind in ("sd", "sboe") if getattr(districts, kind) and (kind, getattr(districts, kind)) not in self.included
        ]
        if any(e.type == "GE" for e in elections):
            for kind in ("cd", "hd"):  # every one of these seats is up in a general election
                number = getattr(districts, kind)
                if number and (kind, number) not in self.included:
                    self.warnings.append(
                        f"Couldn't find the {KIND_LABELS[kind]} District {number} race on your county's ballot. "
                        "Double-check with your county elections office."
                    )
