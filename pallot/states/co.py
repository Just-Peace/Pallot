"""Colorado: the Secretary of State's official list of the candidates in a general election, one
spreadsheet (.xlsx) a row per candidate: name, office, district ("State" for a statewide one, a
number, a county's name or an RTD letter), party and whether they're a write-in. The sheet's name
carries the year ("2026GeneralElectionCandidates"); the election is that November's.

The Governor and Lieutenant Governor are a ticket, listed as a row each, the running mate's after
the Governor's: they're one race here. The State Board of Education and the CU Regents are elected
by congressional district, or at large. The RTD's districts don't follow any the Census knows, so
they're only counted. The judges stand for retention, each a yes-or-no question of their own: the
Supreme Court and the Court of Appeals statewide, a district court judge in the counties of their
judicial district, a county court judge in their county.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from .. import counties
from ..http_cache import RequestSpec
from ..sources.fec import race_name
from . import Filing, StateList, ordinal, party, sheet_rows
from .key_dates import first_tuesday_after_first_monday

URL = "https://www.coloradosos.gov/pubs/elections/vote/files/{year}/{year}GeneralCandidateListOfficial.xlsx"
COLUMNS = ("Candidate Name", "Office", "District", "Party", "Write In?")
HOUSE_RACES = 8  # a list with fewer U.S. House races isn't the whole list
_SHEET = re.compile(r"(\d{4})\s*General", re.I)
_STATEWIDE = {"Secretary of State": "Secretary of State", "State Treasurer": "State Treasurer",
              "Attorney General": "Attorney General"}
_BOARDS = {"State Board of Education": "State Board of Education",
           "University of Colorado Board of Regents": "University of Colorado Regent"}
_JUDICIAL = {  # C.R.S. 13-5-102 to 13-5-124, with the 23rd since 2025
    1: ("Gilpin", "Jefferson"), 2: ("Denver",), 3: ("Huerfano", "Las Animas"), 4: ("El Paso", "Teller"),
    5: ("Clear Creek", "Eagle", "Lake", "Summit"), 6: ("Archuleta", "La Plata", "San Juan"),
    7: ("Delta", "Gunnison", "Hinsdale", "Montrose", "Ouray", "San Miguel"), 8: ("Jackson", "Larimer"),
    9: ("Garfield", "Pitkin", "Rio Blanco"), 10: ("Pueblo",), 11: ("Chaffee", "Custer", "Fremont", "Park"),
    12: ("Alamosa", "Conejos", "Costilla", "Mineral", "Rio Grande", "Saguache"),
    13: ("Kit Carson", "Logan", "Morgan", "Phillips", "Sedgwick", "Washington", "Yuma"),
    14: ("Grand", "Moffat", "Routt"), 15: ("Baca", "Cheyenne", "Kiowa", "Prowers"), 16: ("Bent", "Crowley", "Otero"),
    17: ("Adams", "Broomfield"), 18: ("Arapahoe",), 19: ("Weld",), 20: ("Boulder",), 21: ("Mesa",),
    22: ("Dolores", "Montezuma"), 23: ("Douglas", "Elbert", "Lincoln"),
}
_DENVER_COURTS = (("Juvenile", "Denver Juvenile Court"), ("Probate", "Denver Probate Court"))


def _county(name: str) -> str:
    found = counties.find("CO", name)
    if found is None:
        raise ValueError(f"no county {name!r}")
    return found.name.upper()


def _number(district: str, office: str) -> int:
    if not district.isdigit():
        raise ValueError(f"{office} district {district!r} isn't a number")
    return int(district)


def _race(office: str, district: str, name: str) -> tuple[str, str, str, str, str | None, str, tuple[str, ...]] | None:
    """(race id, family, group, reach, district, shown, counties) of a row's office; None for one
    that isn't a race on the ballot here (the Lieutenant Governor, the Governor's running mate)."""
    statewide = district.upper() in ("STATE", "AT LARGE", "AT-LARGE", "")
    if office == "US Senate":
        return "US SENATE", "US SENATE", "federal", "state", None, race_name("CO", None), ()
    if office == "US House of Representatives":
        seat = _number(district, office)
        return f"US HOUSE {seat}", "US HOUSE", "federal", "cd", str(seat), race_name("CO", seat), ()
    if office == "Governor":
        return "GOVERNOR", "GOVERNOR", "state", "state", None, "Governor and Lieutenant Governor", ()
    if office == "Lt. Governor":
        return None
    if office in _STATEWIDE:
        return office.upper(), office.upper(), "state", "state", None, _STATEWIDE[office], ()
    if office in _BOARDS:
        family = office.upper()
        if statewide:
            return f"{family} AT LARGE", family, "state", "state", None, f"{_BOARDS[office]} At Large", ()
        seat = _number(district, office)
        return f"{family} {seat}", family, "state", "cd", str(seat), f"{_BOARDS[office]} District {seat}", ()
    if office == "State Senate":
        seat = _number(district, office)
        return f"STATE SENATE {seat}", "STATE SENATE", "legislature", "sd", str(seat), f"State Senator District {seat}", ()
    if office == "State House of Representatives":
        seat = _number(district, office)
        return (f"STATE HOUSE {seat}", "STATE HOUSE", "legislature", "hd", str(seat),
                f"State Representative District {seat}", ())
    if office == "RTD Board of Directors":
        return (f"RTD {district.upper()}", "RTD", "local", "unplaced", district.upper(),
                f"RTD Board of Directors District {district.upper()}", ())
    return _court(office, district, name)


def _court(office: str, district: str, name: str) -> tuple[str, str, str, str, str | None, str, tuple[str, ...]]:
    """A judge's retention question, a race of its own; ValueError for an office it doesn't know."""
    key = name.upper()
    if office == "Colorado Supreme Court":
        return (f"SUPREME COURT {key}", "SUPREME COURT", "judicial", "state", None,
                f"Retain {name}, Justice of the Colorado Supreme Court", ())
    if office == "Colorado Court of Appeals":
        return (f"COURT OF APPEALS {key}", "COURT OF APPEALS", "judicial", "state", None,
                f"Retain {name}, Judge of the Colorado Court of Appeals", ())
    if re.match(r"Dist[ri]+ct Court\b", office):
        for word, court in _DENVER_COURTS:
            if word in office:
                family = court.upper()
                return (f"{family} {key}", family, "judicial", "county", None, f"Retain {name}, Judge of the {court}",
                        (_county("Denver"),))
        number = _number(district, office)
        if number not in _JUDICIAL:
            raise ValueError(f"no judicial district {number}")
        return (f"DISTRICT COURT {number} {key}", "DISTRICT COURT", "judicial", "counties", str(number),
                f"Retain {name}, District Court Judge, {ordinal(number)} Judicial District",
                tuple(sorted(_county(county) for county in _JUDICIAL[number])))
    if office in ("County Court", "Associate County Court"):
        county = _county(district)
        family = office.upper()
        return (f"{family} {county} {key}", family, "judicial", "county", None,
                f"Retain {name}, {county.title()} {office} Judge", (county,))
    raise ValueError(f"an office it doesn't know: {office!r}")


def _rows(raw: Any) -> tuple[str, list[list[str]]]:
    """The election's ISO date and the candidates' rows, under the column headings."""
    if not isinstance(raw, bytes):
        raise ValueError("not a spreadsheet")
    sheet, rows = sheet_rows(raw)
    year = _SHEET.match(sheet)
    if not year or not rows or tuple(rows[0][:len(COLUMNS)]) != COLUMNS:
        raise ValueError("not the general election's list of candidates")
    day = first_tuesday_after_first_monday(int(year.group(1)), 11).isoformat()
    return day, [row + [""] * (len(COLUMNS) - len(row)) for row in rows[1:]]


def parse_rows(day: str, rows: list[list[str]]) -> list[Filing]:
    """Every candidate in the list's rows, the Lieutenant Governors on their Governor's ticket;
    ValueError for a list whose tickets don't pair or that's short of the U.S. House races."""
    rows = [row for row in rows if row[0] and row[1] and row[0].lower() != "end of data"]
    governors = [row for row in rows if row[1] == "Governor"]
    mates = [row for row in rows if row[1] == "Lt. Governor"]
    if len(governors) != len(mates) or any(g[3] != m[3] for g, m in zip(governors, mates)):
        raise ValueError("its Governors and Lieutenant Governors don't pair into tickets by party")
    tickets = {id(g): m for g, m in zip(governors, mates)}
    filings = []
    for index, row in enumerate(rows):
        name, office, district, label, write_in = (cell.strip() for cell in row[:len(COLUMNS)])
        race = _race(office, district, name)
        if race is None:
            continue
        office_id, family, group, reach, seat, shown, where = race
        if mate := tickets.get(id(row)):
            name = f"{name} and {mate[0].strip()}"
        code, party_name = party(label)
        filings.append(Filing(
            day=day, office_id=office_id, office=shown, family=family, group=group, reach=reach, district=seat,
            name=name, party=code, party_name=party_name, counties=where, write_in=write_in.upper() == "Y",
            incumbent=group == "judicial", retention=group == "judicial", order=index,
        ))
    house = {f.district for f in filings if f.reach == "cd" and f.group == "federal"}
    if len(house) < HOUSE_RACES:
        raise ValueError(f"{len(house)} U.S. House races, not {HOUSE_RACES}")
    return filings


class CoList(StateList):
    state = "CO"
    source = "state_co"
    label = "Colorado Secretary of State"
    page = "https://www.coloradosos.gov/pubs/elections/main.html"
    description = "Colorado's official list of the candidates on its ballot, from its Secretary of State."
    max_bytes = 4 << 20

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", URL.format(year=day.year))

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        return parse_rows(*_rows(raw))
