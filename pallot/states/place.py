"""A state's list made into the voter's races: which of its races are on the ballot at an address.

A race reaching the whole state is always there; Congress and the Legislature by the Census's
districts, as is a board elected by several of the Legislature's districts (Kansas's State Board of
Education) or a seat elected by several (New Hampshire's floterial House districts); a county's or a town's when the address is in it. A race on only part of a county or
town (a commissioner's district, a ward), or a judicial district when another district of the
same office also reaches the county or only part of the county is in it, can't be told from the address, so it's "unconfirmed":
the ballot leaves it out unless asked, as Texas's precinct races. A race the list doesn't say
where it is ("unplaced") is only counted.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from ..models import GROUPS, Candidate, Districts, Location, Race
from ..offices import OfficeScope
from . import Filing, district_key


@dataclass
class Placed:
    races: list[Race] = field(default_factory=list)  # on the ballot
    unconfirmed: list[Race] = field(default_factory=list)  # may be: on part of the county or town
    unplaced: list[Filing] = field(default_factory=list)  # the races the list doesn't say where they are, by their first filing
    scopes: dict[str, OfficeScope] = field(default_factory=dict)  # the Legislature's races, for the seat holders


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _city_of(filing: Filing, city: str | None) -> bool:
    """Whether a town's race is the voter's town: its name, as the list begins it, starts with the town's."""
    return bool(city and filing.city and (filing.city == city or filing.city.startswith(f"{city} ")))


def where(filing: Filing, districts: Districts, county: str | None, city: str | None, split: set[str]) -> str:
    """ "include", "skip" or "unconfirmed" for a race (by its first filing). ``split``: the
    families of judicial offices with more than one district reaching the voter's county."""
    reach = filing.reach
    if reach == "state":
        return "include"
    if reach == "cd":
        return "include" if districts.cd is not None and filing.district == str(districts.cd) else "skip"
    if reach in ("sd", "hd"):
        mine = getattr(districts, reach)
        if mine is None:
            return "unconfirmed"
        mine = district_key(mine)
        return "include" if any(district_key(part) == mine for part in (filing.district or "").split(",")) else "skip"
    if reach == "counties" and county and f"{county}*" in filing.counties:
        return "unconfirmed"
    if reach == "unplaced" or not county or county not in filing.counties:
        return "skip"
    if reach == "counties":
        return "unconfirmed" if filing.family in split else "include"
    if reach == "county":
        return "include"
    if reach == "part_county":
        return "unconfirmed"
    if reach in ("city", "part_city"):
        if not _city_of(filing, city):
            return "skip"
        return "include" if reach == "city" else "unconfirmed"
    return "skip"


def races(filings: list[Filing], location: Location, districts: Districts, *, state: str, source: str,
          url: str) -> Placed:
    """The list's races at ``location``, each with its candidates in the list's order, the races
    in ballot order (GROUPS, then the list's)."""
    by_race: dict[str, list[Filing]] = defaultdict(list)
    for filing in filings:
        by_race[filing.office_id].append(filing)
    county = (location.county or "").upper() or None
    city = (location.city or "").upper() or None
    reaching: dict[str, set[str | None]] = defaultdict(set)
    for found in by_race.values():
        first = found[0]
        if first.reach == "counties" and county in first.counties:
            reaching[first.family].add(first.district)
    split = {family for family, seen in reaching.items() if len(seen) > 1}

    placed = Placed()
    ordered = sorted(by_race.values(), key=lambda found: (GROUPS.index(found[0].group), min(f.order for f in found)))
    for found in ordered:
        first = found[0]
        if first.reach == "unplaced":
            placed.unplaced.append(first)
            continue
        verdict = where(first, districts, county, city, split)
        if verdict == "skip":
            continue
        key = f"{source}:{_slug(first.office_id)}"
        race = Race(
            key=key,
            name=first.office,
            group=first.group,
            seats=max(f.seats for f in found),
            unexpired=first.unexpired,
            retention=first.retention,
            seat=(None if first.group != "federal" else f"{state}-SEN" if first.reach == "state"
                  else f"{state}-{int(first.district):02d}" if first.reach == "cd" and first.district else None),
            source=source,
            url=url,
            candidates=[
                Candidate(key=f"{key}:{_slug(f.name)}", name=f.name, party=f.party, party_name=f.party_name,
                          incumbent=f.incumbent, write_in=f.write_in)
                for f in sorted(found, key=lambda f: (f.order, f.name))
            ],
        )
        if first.reach in ("sd", "hd") and first.group == "legislature" and first.district:
            seat = first.district.split(",")[0]  # a district placed by others too (a floterial) is its own first
            placed.scopes[key] = OfficeScope(first.reach, district_key(seat), first.unexpired, first.office.upper())
        (placed.races if verdict == "include" else placed.unconfirmed).append(race)
    return placed
