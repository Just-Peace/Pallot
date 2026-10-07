"""Who holds each seat now, and their party: Congress from the congress-legislators project's
current members (public domain), the Texas Legislature from Open States' current people (CC0).

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
from dataclasses import dataclass
from typing import Any

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec, UpstreamError
from ..matching import FIRST_LAST, FULL, NameIndex
from ..models import Race, SeatHolder
from ..offices import OfficeScope
from ..text import display_time
from . import CardSet, SeatInfo
from .ballotpedia import BpBallot
from .tec import bp_seat, tec_seat

SOURCE = "officeholders"
LABEL = "Seat holders"
DESCRIPTION = (
    "Who holds each U.S. Senate, U.S. House and Texas Legislature seat now, and their party, from the "
    "congress-legislators project and Open States. Pallot downloads both whole lists, so nothing about you is sent."
)
CONGRESS = "https://unitedstates.github.io/congress-legislators/legislators-current.json"
LEGISLATURE = "https://data.openstates.org/people/current/tx.csv"
REFUSALS = (403, 429)  # answers that pause both files for Ttls.officeholders_backoff
STATE = "TX"
# Texas redrew its U.S. House map in 2025: a term that began before the first Congress elected
# under it was won under the district's old lines.
REDRAWN = dt.date(2027, 1, 3)
_CHAMBERS = {"upper": "STATESEN", "lower": "STATEREP"}
_PARTIES = (("REPUBLICAN", "R", "Republican"), ("DEMOCRAT", "D", "Democrat"), ("LIBERTARIAN", "L", "Libertarian"),
            ("GREEN", "G", "Green"), ("INDEPENDENT", "I", "Independent"))


class OfficeholdersUnavailable(Exception):
    """Neither list could be fetched (refused, paused, down) and nothing was cached."""


@dataclass
class Holder:
    seat: str  # "TX-SEN", "TX-07", "STATESEN:9"
    name: str
    names: list[str]  # every spelling to look for on the ballot (a nickname too)
    party: str | None  # D, R, L, G, I
    party_name: str | None
    started: dt.date | None = None  # when their current term began
    ends: dt.date | None = None  # when it ends (a senator's)


def _party(text: str | None) -> tuple[str | None, str | None]:
    upper = (text or "").upper()
    return next(((code, name) for word, code, name in _PARTIES if word in upper), (None, (text or "").strip() or None))


def _date(text: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(text or "")
    except ValueError:
        return None


def congress_holders(members: list[dict[str, Any]], state: str = STATE) -> list[Holder]:
    """The state's members of Congress, each at their current term's seat."""
    out = []
    for member in members:
        term = (member.get("terms") or [{}])[-1]
        if term.get("state") != state or term.get("type") not in ("sen", "rep"):
            continue
        if term["type"] == "rep" and not isinstance(term.get("district"), int):
            continue
        name = member.get("name") or {}
        full = name.get("official_full") or " ".join(filter(None, (name.get("first"), name.get("last"))))
        names = [full]
        if name.get("nickname") and name.get("last"):
            names.append(f"{name['nickname']} {name['last']}")
        code, party_name = _party(term.get("party"))
        out.append(Holder(
            seat=f"{state}-SEN" if term["type"] == "sen" else f"{state}-{term['district']:02d}",
            name=full, names=names, party=code, party_name=party_name,
            started=_date(term.get("start")), ends=_date(term.get("end")),
        ))
    return out


def legislature_holders(text: str) -> list[Holder]:
    """The Texas Legislature's members, at "STATESEN:9" or "STATEREP:26"."""
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
        cache.pause_on(SOURCE, REFUSALS, ttl.officeholders_backoff)

    async def _get(self, url: str, *, text: bool) -> Any:
        spec = RequestSpec("GET", url)
        try:
            got = await (self.cache.get_text if text else self.cache.get_json)(SOURCE, spec, ttl=self.ttl.officeholders)
        except UpstreamError as exc:
            if exc.until:
                raise OfficeholdersUnavailable(f"paused until {display_time(exc.until)} after a list was refused") from exc
            raise OfficeholdersUnavailable(str(exc).removeprefix(f"{SOURCE}: ")) from exc
        return got.value

    async def congress(self) -> list[Holder]:
        return congress_holders(list(await self._get(CONGRESS, text=False) or []))

    async def legislature(self) -> list[Holder]:
        return legislature_holders(await self._get(LEGISLATURE, text=True) or "")


def _seat_of(race: Race, scope: OfficeScope | None, bp_ballot: BpBallot | None, county: str | None) -> str | None:
    if race.seat:
        return race.seat
    bp_race = next((r for r in bp_ballot.races if f"bp:{r.id}" == race.key), None) if bp_ballot else None
    seat = tec_seat(scope, county) if scope else bp_seat(bp_race, county) if bp_race else None
    return seat if seat and seat.split(":")[0] in _CHAMBERS.values() else None


def _senator_up(holders: list[Holder], day: dt.date) -> Holder | None:
    """The senator whose seat is up: the one whose term ends in the January after the election."""
    return next((h for h in holders if h.ends and h.ends.year == day.year + 1), None)


def _hint(holder: Holder, seat: str) -> str:
    who = f"Held by {holder.name}" + (f", a {holder.party_name}" if holder.party_name else "")
    if not seat.endswith("-SEN") and "-" in seat and holder.started and holder.started < REDRAWN:
        who += ", elected under the district's lines before Texas redrew its U.S. House map in 2025"
    return who


def seat_info(race: Race, holder: Holder | None, seat: str) -> tuple[SeatInfo, str | None]:
    """The race's SeatInfo and the key of the candidate who is the holder (None if nobody
    surely is). A likely match of the holder makes no claim at all."""
    if holder is None:
        return SeatInfo(holder=None, open=True), None
    index = NameIndex()
    for candidate in race.candidates:
        index.add(candidate.name, candidate.key)
    found: set[str] = set()
    likely = False
    for name in holder.names:
        keys, how = index.find(name)
        if how in (FULL, FIRST_LAST) and len(set(keys)) == 1:
            found |= set(keys)
        elif keys:
            likely = True
    info = SeatHolder(name=holder.name, party=holder.party, party_name=holder.party_name, hint=_hint(holder, seat))
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
    bp_ballot: BpBallot | None, day: dt.date | None,
) -> CardSet:
    """Each covered race's seat (CardSet.seats) and the candidates who hold it (incumbents). A
    list is fetched only when the ballot has a race it covers. Raises OfficeholdersUnavailable
    if a list was needed and none could be had."""
    out = CardSet()
    seats = {race.key: seat for race in races if (seat := _seat_of(race, scopes.get(race.key), bp_ballot, county))}
    if not seats:
        return out
    wanted = {"congress": any("-" in s for s in seats.values()), "legislature": any(":" in s for s in seats.values())}
    got: dict[str, list[Holder]] = {}
    failures: list[OfficeholdersUnavailable] = []
    for name, wants in wanted.items():
        if not wants:
            continue
        try:
            got[name] = await (svc.congress() if name == "congress" else svc.legislature())
        except OfficeholdersUnavailable as exc:
            failures.append(exc)
    if failures and not got:
        raise failures[0]
    if failures:
        out.warnings.append(f"Some seats' holders aren't shown ({failures[0]}).")
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
