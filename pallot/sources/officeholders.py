"""Who holds each seat now, and their party: Congress from the congress-legislators project's
current members (public domain), a state's Legislature from Open States' current people (CC0).

Each is one public file, fetched whole through HttpCache for a week, and only when the ballot
has a race of that body, so nothing about the voter is sent. A race whose holder isn't among
its candidates is an open seat; the holder's party's other candidates "hold the seat" for their
party; and a candidate who is the holder by full name (or first and last name) is the
incumbent, even where the state's filing doesn't say. A likely match (a first initial only, as
Troy and Trever Nehls share) claims none of it. Statewide offices, the SBOE, courts and local
races aren't covered.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import logging
from dataclasses import dataclass
from typing import Any

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec, UpstreamError
from ..matching import FIRST_LAST, FULL, NameIndex
from ..models import Race, SeatHolder
from ..offices import OfficeScope
from . import CardSet, SeatInfo
from .ballotpedia import BpBallot
from .tec import bp_seat, tec_seat

log = logging.getLogger("uvicorn.error")

SOURCE = "officeholders"
LABEL = "Seat holders"
DESCRIPTION = (
    "Who holds each U.S. Congress and state Legislature seat now, from congress-legislators and Open States."
)
CONGRESS = "https://unitedstates.github.io/congress-legislators/legislators-current.json"
LEGISLATURE = "https://data.openstates.org/people/current/{state}.csv"
# States that redrew their U.S. House map mid-decade -> when the first Congress elected under the
# new map starts (a term that began before it was won under the district's old lines), and the words.
REDRAWN = {"TX": (dt.date(2027, 1, 3), "Texas redrew its U.S. House map in 2025")}
_CHAMBERS = {"upper": "STATESEN", "lower": "STATEREP"}
_PARTIES = (("REPUBLICAN", "R", "Republican"), ("DEMOCRAT", "D", "Democrat"), ("LIBERTARIAN", "L", "Libertarian"),
            ("GREEN", "G", "Green"), ("INDEPENDENT", "I", "Independent"))


@dataclass
class Holder:
    seat: str  # "TX-SEN", "TX-07", "STATESEN:9"
    name: str
    names: list[str]  # every spelling to look for on the ballot (a nickname too)
    party: str | None  # D, R, L, G, I
    party_name: str | None
    started: dt.date | None = None  # when their current term began
    ends: dt.date | None = None  # when it ends (a senator's)
    fec_ids: tuple[str, ...] = ()  # their FEC candidate IDs, as ballot_races keys candidates ("fec:<id>")


def _party(text: str | None) -> tuple[str | None, str | None]:
    upper = (text or "").upper()
    return next(((code, name) for word, code, name in _PARTIES if word in upper), (None, (text or "").strip() or None))


def _date(text: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(text or "")
    except ValueError:
        return None


def congress_holders(members: list[dict[str, Any]], state: str | None) -> list[Holder]:
    """The state's members of Congress (every state's with None), each at their current term's seat."""
    out = []
    for member in members:
        term = (member.get("terms") or [{}])[-1]
        if (state and term.get("state") != state) or not term.get("state") or term.get("type") not in ("sen", "rep"):
            continue
        if term["type"] == "rep" and not isinstance(term.get("district"), int):
            continue
        name = member.get("name") or {}
        full = name.get("official_full") or " ".join(filter(None, (name.get("first"), name.get("last"))))
        names = [full]
        if name.get("nickname") and name.get("last"):
            names.append(f"{name['nickname']} {name['last']}")
        code, party_name = _party(term.get("party"))
        where = term["state"]
        out.append(Holder(
            seat=f"{where}-SEN" if term["type"] == "sen" else f"{where}-{term['district']:02d}",
            name=full, names=names, party=code, party_name=party_name,
            started=_date(term.get("start")), ends=_date(term.get("end")),
            fec_ids=tuple((member.get("id") or {}).get("fec") or ()),
        ))
    return out


def legislature_holders(text: str) -> list[Holder]:
    """A Legislature's members, at "STATESEN:9" or "STATEREP:26" (numbered districts only)."""
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        chamber, district = _CHAMBERS.get(row.get("current_chamber") or ""), (row.get("current_district") or "").strip()
        if not chamber or not district.isdigit() or not row.get("name"):
            continue
        names = [row["name"]]
        if row.get("given_name") and row.get("family_name"):
            names.append(f"{row['given_name']} {row['family_name']}")
        code, party_name = _party(row.get("current_party"))
        out.append(Holder(seat=f"{chamber}:{int(district)}", name=row["name"], names=names, party=code, party_name=party_name))
    return out


class Officeholders:
    def __init__(self, cache: HttpCache, ttl: Ttls):
        self.cache = cache
        self.ttl = ttl
        cache.pause_on(SOURCE, ttl.officeholders_backoff)

    async def _get(self, url: str, *, text: bool) -> Any:
        spec = RequestSpec("GET", url)
        got = await (self.cache.get_text if text else self.cache.get_json)(SOURCE, spec, ttl=self.ttl.officeholders)
        return got.value

    async def congress(self) -> list[Holder]:
        return congress_holders(list(await self._get(CONGRESS, text=False) or []), state=None)

    async def legislature(self, state: str) -> list[Holder]:
        return legislature_holders(await self._get(LEGISLATURE.format(state=state.lower()), text=True) or "")


def _seat_of(race: Race, scope: OfficeScope | None, bp_ballot: BpBallot | None, county: str | None) -> str | None:
    if race.seat:
        return race.seat
    bp_race = next((r for r in bp_ballot.races if f"bp:{r.id}" == race.key), None) if bp_ballot else None
    seat = tec_seat(scope, county) if scope else bp_seat(bp_race, county) if bp_race else None
    return seat if seat and seat.split(":")[0] in _CHAMBERS.values() else None


def _senator_up(holders: list[Holder], day: dt.date) -> Holder | None:
    """The senator whose seat is up: the one whose term ends after the election and by the January
    after it, an appointee's (whose seat a special election fills) included."""
    return next((h for h in holders if h.ends and day <= h.ends < dt.date(day.year + 1, 2, 1)), None)


def _hint(holder: Holder, seat: str) -> str:
    who = f"Held by {holder.name}" + (f", a {holder.party_name}" if holder.party_name else "")
    redrawn = REDRAWN.get(seat.partition("-")[0])
    if redrawn and not seat.endswith("-SEN") and holder.started and holder.started < redrawn[0]:
        who += f", elected under the district's lines before {redrawn[1]}"
    return who


def seat_info(race: Race, holder: Holder | None, seat: str) -> tuple[SeatInfo, str | None]:
    """The race's SeatInfo and the key of the candidate who is the holder (None if nobody
    surely is). A candidate from the FEC's list is the holder by FEC ID, since its legal names
    ("T. Jonathan Ossoff") aren't the ones people go by. A likely match of the holder makes no
    claim at all."""
    if holder is None:
        return SeatInfo(holder=None, open=True), None
    info = SeatHolder(name=holder.name, party=holder.party, party_name=holder.party_name, hint=_hint(holder, seat))
    found = {c.key for c in race.candidates if c.key.startswith("fec:") and c.key.removeprefix("fec:") in holder.fec_ids}
    likely = False
    if not found:
        index = NameIndex()
        for candidate in race.candidates:
            index.add(candidate.name, candidate.key)
        for name in holder.names:
            keys, how = index.find(name)
            if how in (FULL, FIRST_LAST) and len(set(keys)) == 1:
                found |= set(keys)
            elif keys:
                likely = True
    if len(found) != 1:
        if likely or found:
            return SeatInfo(holder=info, open=False), None
        parties = {c.party for c in race.candidates if not c.write_in and c.party}
        other_primary = len(parties) == 1 and holder.party not in parties and len(race.candidates) > 1
        party_holds = {c.key for c in race.candidates if holder.party and c.party == holder.party}
        return SeatInfo(holder=info, open=not other_primary, party_holds=party_holds), None
    [key] = found
    party_holds = {c.key for c in race.candidates if holder.party and c.party == holder.party and c.key != key}
    return SeatInfo(holder=info, open=False, party_holds=party_holds), key


async def cards(
    svc: Officeholders, races: list[Race], scopes: dict[str, OfficeScope], county: str | None,
    bp_ballot: BpBallot | None, day: dt.date | None, state: str,
) -> CardSet:
    """Each covered race's seat (CardSet.seats) and the candidates who hold it (incumbents). A
    list is fetched only when the ballot has a race it covers. Raises UpstreamError
    if a list was needed and none could be had."""
    out = CardSet()
    seats = {race.key: seat for race in races if (seat := _seat_of(race, scopes.get(race.key), bp_ballot, county))}
    if not seats:
        return out
    wanted = {"congress": any("-" in s for s in seats.values()), "legislature": any(":" in s for s in seats.values())}
    got: dict[str, list[Holder]] = {}
    failures: list[UpstreamError] = []
    for name, wants in wanted.items():
        if not wants:
            continue
        try:
            got[name] = await (svc.congress() if name == "congress" else svc.legislature(state))
        except UpstreamError as exc:
            failures.append(exc)
    if failures and not got:
        raise failures[0]
    if failures:
        log.warning("%s", failures[0])
        out.warnings.append("A list of seat holders isn't answering right now, so some seats' holders aren't shown.")
    by_seat: dict[str, list[Holder]] = {}
    for holders in got.values():
        for holder in holders:
            by_seat.setdefault(holder.seat, []).append(holder)
    covered = {"congress": "-", "legislature": ":"}
    day = day or dt.date.today()
    for race in races:
        seat = seats.get(race.key)
        if not seat or not any(mark in seat for name, mark in covered.items() if name in got):
            continue
        found = by_seat.get(seat, [])
        holder = _senator_up(found, day) if seat.endswith("-SEN") else (found[0] if len(found) == 1 else None)
        if seat.endswith("-SEN") and holder is None and found:
            continue  # no senator's term ends after this election: no claim
        if len(found) > 1 and not seat.endswith("-SEN"):
            continue  # two members for one seat: the list is mid-change
        info, key = seat_info(race, holder, seat)
        out.seats[race.key] = info
        if key:
            out.incumbents.add(key)
    return out
