"""Assemble one voter's ballot from the enabled sources.

The Census gives the county and districts, the SBOE map adds the State Board of
Education district, and the Texas Legislative Council's precinct map the election precinct,
whose county's records may settle the commissioner and JP precincts, whichever ballot source is
on. Official path: the county's Texas SOS
ballot order is filtered down to those districts. Ballotpedia adds city/school races, races the state doesn't list
at all, its notes on races and the voter's precincts, or supplies the whole ballot when the state source is off.
Then every candidate gets a card from each enabled source (enrich.py).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import time
import zipfile
from dataclasses import dataclass, field
from typing import Any, Callable

from . import enrich
from .config import Config
from .http_cache import CallStats, HttpCache, UpstreamError, track_calls
from .matching import NameIndex
from .models import (
    GROUPS, Ballot, BallotRequest, Candidate, CountySource, Districts, ElectionDate, ElectionPrecinct, ElectionRef,
    KeyDates, LastLookup, Location, MaybeSection, Measure, Meta, PrecinctSource, Race, RaceNote, SourceUse,
)
from .offices import DISTRICT_KINDS, KIND_LABELS, PRECINCT_KINDS, OfficeScope, classify
from .settings import Settings
from .sources import ballotpedia as ballotpedia_source
from .sources import county_precincts as county_precincts_source
from .sources import election_precincts as election_precincts_source
from .sources import key_dates as key_dates_source
from .sources import sos as sos_source
from .sources.ballotpedia import Ballotpedia, BallotpediaUnavailable, BpBallot, BpRace
from .sources.census import TEXAS_FIPS, Census, Place
from .sources.county_precincts import CountyPrecincts
from .sources.election_precincts import ElectionPrecincts, StillDownloading
from .sources.fec import Fec
from .sources.key_dates import Deadlines, KeyDatesPage
from .sources.nominatim import Nominatim
from .sources.osm_tiles import Tiles
from .sources.polls import Polls
from .sources.sboe import SboeMap
from .sources.sos import Election, Lookups, Sos, find_county, still_running
from .sources.suggestions import Suggestions
from .sources.tec import Tec
from .sources.tigerweb import Tigerweb
from .sources.trackaipac import TrackAipac
from .text import display_office, display_person, display_time, iso_utc

MAYBE_SECTIONS = {
    "precinct": (
        "Depends on your commissioner or JP precinct",
        "These races are only on some ballots in {county} County. Your commissioner and justice of the peace "
        "precincts are printed on your voter registration certificate; enter them under \"Your districts\" at the top "
        "of your ballot to narrow this list.",
    ),
    "unconfirmed": (
        "Couldn't confirm",
        "VoteBot couldn't work out which of these districts your address is in, so check your county's sample ballot.",
    ),
    "special": (
        "Special districts (MUDs, water and utility districts)",
        "Ballotpedia lists these for your area, but you only vote in one if your home is inside that district. "
        "Check your county's sample ballot.",
    ),
}


class BallotError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Services:
    config: Config
    settings: Settings
    cache: HttpCache
    census: Census
    nominatim: Nominatim
    suggestions: Suggestions
    sboe: SboeMap
    election_precincts: ElectionPrecincts
    county_precincts: CountyPrecincts
    sos: Sos
    ballotpedia: Ballotpedia
    trackaipac: TrackAipac
    fec: Fec
    tec: Tec
    polls: Polls
    key_dates: KeyDatesPage
    tigerweb: Tigerweb
    tiles: Tiles
    today: Callable[[], dt.date] = dt.date.today
    last_lookup: LastLookup | None = None  # the latest ballot, and how it used each source (Settings shows both)
    last_uses: dict[str, SourceUse] = field(default_factory=dict)


@dataclass
class SosData:
    county_id: int
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

    return KeyDates(
        election=found.name,
        election_day=found.day.isoformat(),
        register_by=iso(found.register_by),
        mail_apply_by=iso(found.mail_apply_by),
        early_voting_start=iso(found.early_start),
        early_voting_end=iso(found.early_end),
        source_url=key_dates_source.URL,
    )


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


async def locate(svc: Services, address: str) -> tuple[Place, Location]:
    try:
        place = await svc.census.geocode(address)
        geocoder, approximate, label = "census", False, place.matched_address if place else None
        if place is None:
            point = await svc.nominatim.locate(address)
            if point is None:
                raise BallotError(422, "VoteBot couldn't find that address. Include the street, city and ZIP code.")
            place = await svc.census.at(point.lat, point.lon)
            if place is None:
                raise BallotError(422, "That address doesn't seem to be in the United States.")
            geocoder, approximate, label = "nominatim", point.approximate, point.label
    except UpstreamError as exc:
        if exc.until:
            raise BallotError(502, f"The address lookup is paused until {display_time(exc.until)} after refusing a "
                                   "request. Addresses already looked up still work.") from exc
        raise BallotError(502, f"The address lookup service isn't responding ({exc}). Try again in a minute.") from exc
    if place.state_fips != TEXAS_FIPS:
        raise BallotError(422, "VoteBot only covers Texas addresses for now.")
    location = Location(
        input_address=address,
        matched_address=label,
        lat=place.lat,
        lon=place.lon,
        state=place.state,
        state_name=place.state_name,
        county=place.county,
        city=place.city,
        school_district=place.school_district,
        geocoder=geocoder,
        approximate=approximate,
    )
    return place, location


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


def _adds_to_state_ballot(race: BpRace, state_names: NameIndex) -> bool:
    """A Ballotpedia race the state's ballot doesn't have: a city, school or special-district
    race, or one with candidates on the ballot, none of whom the state lists."""
    if race.group in ("local", "special"):
        return True
    printed = [c for c in race.candidates if not c.write_in]
    return bool(printed) and not any(state_names.find(c.name)[0] for c in printed)


def _notes(race: BpRace) -> list[RaceNote]:
    return [RaceNote(text=note.text, url=note.url, source=ballotpedia_source.LABEL) for note in race.notes]


def _sort_key(row: dict[str, Any], name: str) -> tuple[int, int, int, str]:
    return (
        row.get("nbOfficeTypeOrder") or 99,
        row.get("nbSortOrder") or 999,
        row.get("nbSecondarySortOrder") or 999,
        name,
    )


async def build_ballot(svc: Services, request: BallotRequest) -> Ballot:
    return await _Builder(svc, request, track_calls()).run()


async def _nothing() -> None:
    return None


class _Builder:
    def __init__(self, svc: Services, request: BallotRequest, calls: CallStats):
        self.svc = svc
        self.request = request
        self.calls = calls
        self.started = time.monotonic()
        self.use_sos = svc.settings.enabled("sos")
        self.use_bp = svc.settings.enabled("ballotpedia")
        self.use_tap = svc.settings.enabled("trackaipac")
        self.use_fec = svc.settings.enabled("fec")
        self.use_tec = svc.settings.enabled("tec")
        self.use_polls = svc.settings.enabled("polls")
        self.use_key_dates = svc.settings.enabled(key_dates_source.SOURCE)
        self.use_election_precincts = svc.settings.enabled(election_precincts_source.SOURCE)
        self.use_county_precincts = self.use_election_precincts and svc.settings.enabled(county_precincts_source.SOURCE)
        self.notes: list[str] = []
        self.warnings: list[str] = []
        self.errors: dict[str, str] = {}
        self.ballot_rows: dict[str, dict[str, Any]] = {}  # candidate key -> its SOS row
        self.scopes: dict[str, OfficeScope] = {}  # SOS race key -> what its office covers
        self.included: set[tuple[str, int | None]] = set()  # (kind, number) of SOS races kept
        self.unlisted: set[str] = set()  # SOS race keys with only write-ins, so not on the county's ballot order
        self.state_names = NameIndex()  # everyone the state lists for the day, kept or not
        self.maybe: dict[str, list[Race]] = {key: [] for key in MAYBE_SECTIONS}

    async def run(self) -> Ballot:
        if not (self.use_sos or self.use_bp):
            raise BallotError(400, "No ballot source is turned on. Turn on Texas SOS or Ballotpedia in Settings.")
        place, location = await locate(self.svc, self.request.address)
        if location.approximate:
            self.warnings.append(
                f"VoteBot could only place this address approximately ({location.matched_address}), "
                "so double-check \"Your districts\" at the top of your ballot."
            )

        elections, day = await self._elections()
        sos_data, bp_ballot, deadlines, sboe, found_precincts = await asyncio.gather(
            self._sos(elections, place) if elections else _nothing(),
            self._ballotpedia(place, day) if self.use_bp else _nothing(),
            self._key_dates() if self.use_key_dates else _nothing(),
            self._sboe(place),
            self._precinct_and_county(place, location) if self.use_election_precincts else _nothing(),
        )
        election_precinct, county = found_precincts or (None, None)
        if sos_data is None and not (bp_ballot and bp_ballot.races):
            if "sos" in self.errors and (until := self.svc.cache.paused_until("sos")):
                raise BallotError(502, f"Texas SOS is paused until {display_time(until)} after refusing a request, "
                                       "and nothing is cached yet for this address.")
            if "sos" in self.errors:
                raise BallotError(502, f"Texas SOS isn't responding and nothing is cached yet ({self.errors['sos']}).")
            raise BallotError(404, " ".join(self.warnings) or "No ballot data found for this address.")
        if self.use_sos and sos_data is None:
            self.warnings.append("Texas SOS data isn't available, so this ballot comes from Ballotpedia only.")

        precincts, precinct_sources = self._precincts(bp_ballot, county)
        entered = self.request.districts.model_dump(exclude_unset=True) if self.request.districts else {}
        found = {"cd": place.cd, "sd": place.sd, "hd": place.hd, "sboe": sboe}
        districts = Districts(
            county_id=sos_data.county_id if sos_data else None,
            **{**found, **entered},
            entered=[kind for kind in DISTRICT_KINDS if kind in entered],
            election_precinct=election_precinct,
            city_council=bp_ballot.city_council if bp_ballot else None,
            precinct_sources=precinct_sources,
            county_source=CountySource(county=county.county.name, method=county.county.method)
            if county and county.numbers else None,
            **precincts,
        )

        if sos_data:
            races = self._sos_races(sos_data, districts)
            if bp_ballot:
                races += self._bp_races(bp_ballot, self.state_names)
            self._district_notes(districts, [e for e, _ in sos_data.orders])
        else:
            races = self._bp_races(bp_ballot, None) if bp_ballot else []

        maybe = [
            MaybeSection(
                id=key,
                title=MAYBE_SECTIONS[key][0],
                explanation=MAYBE_SECTIONS[key][1].format(county=place.county or "your"),
                races=found,
            )
            for key, found in self.maybe.items()
            if found
        ]
        every_race = races + [race for section in maybe for race in section.races]
        bp_counterparts = ballotpedia_source.counterparts(bp_ballot, every_race) if bp_ballot else {}
        for race in every_race:
            if own := bp_counterparts.get(race.key):
                race.notes = _notes(own)
        ballot_day = day or (bp_ballot.day if bp_ballot else None)
        found = next((d for d in deadlines or () if d.day == ballot_day), None)
        outcome = await enrich.run(
            self.svc,
            every_race,
            elections={e.id: e for e, _ in sos_data.orders} if sos_data else {},
            ballot_rows=self.ballot_rows,
            bp_ballot=bp_ballot,
            sos_lookups=sos_data.lookups if sos_data else None,
            use_trackaipac=self.use_tap,
            use_fec=self.use_fec,
            use_tec=self.use_tec,
            use_polls=self.use_polls,
            day=ballot_day,
            scopes=self.scopes,
            county=place.county,
            bp_counterparts=bp_counterparts,
        )
        self.warnings += outcome.warnings
        self.notes += outcome.notes
        self.errors.update(outcome.errors)

        if sos_data:
            used = {race.election_id for race in every_race}
            refs = [election_ref(e) for e, _ in sos_data.orders if e.id in used]
        else:
            refs = [ElectionRef(name="Ballotpedia sample ballot", date=ballot_day.isoformat() if ballot_day else None)]
        meta = Meta(
            external_calls=self.calls.external_calls,
            cache_hits=self.calls.cache_hits,
            elapsed_ms=int((time.monotonic() - self.started) * 1000),
        )
        self.svc.last_lookup = LastLookup(at=iso_utc(time.time()), **meta.model_dump())
        self.svc.last_uses = {use.id: use for use in self._sources(location)}
        return Ballot(
            election_date=ballot_day.isoformat() if ballot_day else None,
            elections=refs,
            key_dates=key_dates_of(found) if found else None,
            location=location,
            districts=districts,
            races=races,
            maybe=maybe,
            measures=[
                Measure(key=f"bp:{m.id}", title=m.title, summary=m.summary, url=m.url, district=m.district)
                for m in (bp_ballot.measures if bp_ballot else ())
            ],
            notes=self.notes,
            warnings=self.warnings,
            meta=meta,
        )

    # -- gathering -----------------------------------------------------------------

    async def _elections(self) -> tuple[list[Election], dt.date | None]:
        requested = self.request.election_date
        if not self.use_sos:
            return [], requested
        try:
            upcoming = await self.svc.sos.upcoming()
        except UpstreamError as exc:
            self.errors["sos"] = str(exc)
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

    async def _sos(self, elections: list[Election], place: Place) -> SosData | None:
        sos = self.svc.sos
        try:
            counties, lookups = await asyncio.gather(sos.counties(), sos.lookups())
            county_id = find_county(counties, place.county, place.county_fips)
            if county_id is None:
                self.warnings.append(f"Texas SOS doesn't list {place.county} County.")
                return None
            orders = await asyncio.gather(*(self._rows(e, county_id, place.county) for e in elections))
        except UpstreamError as exc:
            self.errors["sos"] = str(exc)
            return None
        return SosData(county_id, set(counties), lookups, list(zip(elections, orders)))

    async def _rows(self, election: Election, county_id: int, county: str | None) -> list[dict[str, Any]]:
        """The county's ballot order, plus the declared write-ins from the statewide candidate
        list (_declared_write_ins), with the races that have only write-ins noted in ``unlisted``;
        when the ballot order is empty (special elections), that list trimmed to
        the races it can place (_placeable). It names no county for judicial, DA or county
        races, so those are left out, with a note, rather than shown to every county. Everyone
        in either list goes in ``state_names``, so Ballotpedia's races that the state has, even
        for another district, aren't added again."""
        order, statewide = await asyncio.gather(
            self.svc.sos.ballot_order(election, county_id), self.svc.sos.candidates(election), return_exceptions=True
        )
        if isinstance(order, BaseException):
            raise order
        rows = order.value or []
        if isinstance(statewide, UpstreamError) and rows:
            self.notes.append("Couldn't load the Texas Secretary of State's list of declared write-in candidates, so "
                              "they aren't listed; your county's sample ballot names them.")
            self._remember_names(rows)
            return rows
        if isinstance(statewide, BaseException):
            raise statewide
        running = [r for r in statewide.value or [] if still_running(r)]
        if rows:
            listed = {row.get("idOffice") for row in rows}
            write_ins = _declared_write_ins(rows, running, county)
            self.unlisted |= {f"sos:{election.id}:{r['idOffice']}" for r in write_ins if r.get("idOffice") not in listed}
            rows = rows + write_ins
            self._remember_names(rows)
            return rows
        self._remember_names(running)
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

    def _remember_names(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self.state_names.add(display_person(row.get("txFullNameBallot") or ""), row.get("idOffice"))

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
        county = await self._county(place, codes) if self.use_county_precincts and codes else None
        return precinct, county

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
            self.errors[election_precincts_source.SOURCE] = str(exc).removeprefix(f"{election_precincts_source.SOURCE}: ")
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

    async def _county(self, place: Place, codes: tuple[str, ...]) -> county_precincts_source.Found | None:
        """What the county's records say for those precincts; None, with a note, when they can't be read."""
        try:
            return await self.svc.county_precincts.at(int(place.county_fips or 0), codes)
        except (UpstreamError, OSError, ValueError) as exc:
            self.errors[county_precincts_source.SOURCE] = str(exc).removeprefix(f"{county_precincts_source.SOURCE}: ")
            self.notes.append(f"Couldn't read {place.county or 'your'} County's records of its election precincts, so they "
                              "don't give your commissioner and JP precincts this time.")
            return None

    async def _ballotpedia(self, place: Place, day: dt.date | None) -> BpBallot | None:
        try:
            ballot = await self.svc.ballotpedia.ballot(place.lat, place.lon, day)
        except BallotpediaUnavailable as exc:
            self.errors["ballotpedia"] = str(exc)
            self.warnings.append(f"Ballotpedia isn't available ({exc}), so city and school races aren't shown.")
            return None
        if not ballot.races and day:
            self.notes.append(f"Ballotpedia has nothing for {day:%b %d, %Y} at this address yet.")
        return ballot

    async def _key_dates(self) -> list[Deadlines]:
        try:
            return await self.svc.key_dates.deadlines()
        except UpstreamError as exc:
            self.errors[key_dates_source.SOURCE] = str(exc).removeprefix(f"{key_dates_source.SOURCE}: ")
            self.notes.append("Couldn't load the key dates (registration, early voting) from the Texas Secretary of "
                              "State; see VoteTexas.gov.")
            return []

    # -- building races ----------------------------------------------------------------

    def _precincts(
        self, bp_ballot: BpBallot | None, county: county_precincts_source.Found | None
    ) -> tuple[dict[str, int | None], dict[str, PrecinctSource]]:
        """Each precinct's number, and who gave it: the voter, then the county's records, then
        Ballotpedia. A note when the county's records and Ballotpedia differ, or when the
        county's records couldn't settle one that nothing else gives."""
        given = _jp_is_constable(self.request.precincts.model_dump(exclude_unset=True) if self.request.precincts else {})
        from_county = _jp_is_constable(dict(county.numbers) if county else {})
        from_bp = _jp_is_constable(dict(bp_ballot.precincts) if bp_ballot else {})
        numbers: dict[str, int | None] = {}
        sources: dict[str, PrecinctSource] = {}
        for kind in PRECINCT_KINDS:
            for source, found in (("you", given), ("county", from_county), ("ballotpedia", from_bp)):
                if kind in found:
                    numbers[kind], sources[kind] = found[kind], source
                    break
            else:
                numbers[kind] = None
        if county:
            name = county.county.name
            for kind, what in county_precincts_source.KIND_NAMES.items():
                theirs = from_bp.get(kind)
                if sources.get(kind) == "county" and theirs is not None and theirs != from_county[kind]:
                    self.notes.append(f"Ballotpedia puts this address in {what} precinct {theirs}, but {name} County's "
                                      f"records say {from_county[kind]}, which this ballot uses. Your voter registration "
                                      "certificate says which.")
                if kind in county.unsettled and numbers[kind] is None and kind not in given:
                    self.notes.append(f"{county.unsettled[kind]}, so VoteBot doesn't guess your {what} precinct; it's "
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
            ballot_name=row.get("txFullNameBallot"),
            party=code,
            party_name=(lookups.parties.get(code or "") or "").title() or None,
            incumbent=bool(row.get("flIncmbntGen")),
            write_in=write_in,
            ballot_position=row.get("nbBallotOrder"),
        )

    def _bp_races(self, ballot: BpBallot, state_names: NameIndex | None) -> list[Race]:
        """Ballotpedia's races: all of them without the state's ballot. With it, the city, school
        and special-district races, and any other race none of whose candidates the state lists
        (an appraisal district's board). Special districts always go to the "may be on your
        ballot" list."""
        races = []
        for bp_race in ballot.races:
            if state_names is not None and not _adds_to_state_ballot(bp_race, state_names):
                continue
            race = Race(
                key=f"bp:{bp_race.id}",
                name=bp_race.office,
                group="local" if bp_race.group == "special" else bp_race.group,
                seats=bp_race.seats,
                seat=bp_race.seat,
                source="ballotpedia",
                url=bp_race.url,
                candidates=[
                    Candidate(
                        key=f"bp:{c.id}",
                        name=c.name,
                        party=c.party,
                        party_name=c.party_name,
                        incumbent=c.incumbent,
                        write_in=c.write_in,
                        photo_url=c.photo,
                    )
                    for c in bp_race.candidates
                ],
            )
            (self.maybe["special"] if bp_race.group == "special" else races).append(race)
        return sorted(races, key=lambda r: GROUPS.index(r.group))

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

    def _sources(self, location: Location) -> list[SourceUse]:
        """How this lookup used each source, for the Settings page."""

        def status(source_id: str, label: str, on: bool, tags: tuple[str, ...]) -> SourceUse:
            if not on:
                return SourceUse(id=source_id, label=label, status="off")
            calls = sum(self.calls.calls.get(t, 0) for t in tags)
            if source_id in self.errors:
                return SourceUse(id=source_id, label=label, status="error", calls=calls, message=self.errors[source_id])
            used = [self.calls.oldest[t] for t in tags if t in self.calls.oldest]
            if not used:
                return SourceUse(id=source_id, label=label, status="unused", calls=calls)
            stale = any(t in self.calls.stale_sources for t in tags)
            return SourceUse(
                id=source_id, label=label, status="stale" if stale else "used", as_of=iso_utc(min(used)), calls=calls
            )

        def snapshot(source_id: str, label: str, on: bool, document: Callable[[], dict[str, Any]]) -> SourceUse:
            if not on:
                return SourceUse(id=source_id, label=label, status="off")
            taken = document().get("snapshot")
            return SourceUse(
                id=source_id,
                label=label,
                status="used" if taken else "unused",
                as_of=taken,
                message=None if taken else f"no {label} data yet; refresh it in Settings",
            )

        geocoding = status("geocoding", "Address lookup", True, ("census", "nominatim", "sboe"))
        geocoding.message = "OpenStreetMap + US Census" if location.geocoder == "nominatim" else "US Census"
        return [
            geocoding,
            status("sos", "Texas SOS", self.use_sos, ("sos",)),
            status(key_dates_source.SOURCE, key_dates_source.LABEL, self.use_key_dates, (key_dates_source.SOURCE,)),
            status("ballotpedia", "Ballotpedia", self.use_bp, ("ballotpedia",)),
            snapshot("trackaipac", "TrackAIPAC", self.use_tap, self.svc.trackaipac.document),
            status("fec", "FEC", self.use_fec, ("fec",)),
            snapshot("tec", "Texas Ethics Commission", self.use_tec, self.svc.tec.document),
            status("polls", "Polls", self.use_polls, ("polls",)),
            status(election_precincts_source.SOURCE, election_precincts_source.LABEL, self.use_election_precincts,
                   (election_precincts_source.SOURCE,)),
            status(county_precincts_source.SOURCE, county_precincts_source.LABEL, self.use_county_precincts,
                   (county_precincts_source.SOURCE,)),
        ]
