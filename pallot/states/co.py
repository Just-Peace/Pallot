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

Colorado's key dates, for its general election (C.R.S. 1-4-201: the Tuesday after the first Monday
of November in an even year): every active voter is mailed a ballot, sent from the twenty-second day
before (1-7.5-107(3)); registering online or by mail by the eighth day before still gets one
(1-2-201(3)), and after that a voter registers and votes in person at a voter service and polling
center through Election Day (1-2-217.7); the centers open the fifteenth day before (1-5-102.9); a
ballot must reach the county clerk by 7 p.m. on Election Day (1-7.5-107(4)); polls and centers are
open 7 a.m. to 7 p.m. on Election Day.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from .. import counties
from ..http_cache import RequestSpec
from . import (
    Filing, Office, StateList, legislator, ordinal, party, require, sheet_rows, statewide, us_house, us_senate,
)
from .dates import Counts, Guide, first_tuesday_after_first_monday

URL = "https://www.coloradosos.gov/pubs/elections/vote/files/{year}/{year}GeneralCandidateListOfficial.xlsx"
COLUMNS = ("Candidate Name", "Office", "District", "Party", "Write In?")
MINIMUM = {"cd": 8}  # a list with fewer U.S. House races isn't the whole list
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


def _race(office: str, district: str, name: str) -> Office | None:
    """A row's race; None for one that isn't a race on the ballot here (the Lieutenant Governor,
    the Governor's running mate)."""
    at_large = district.upper() in ("STATE", "AT LARGE", "AT-LARGE", "")
    if office == "US Senate":
        return us_senate("CO")
    if office == "US House of Representatives":
        return us_house("CO", _number(district, office))
    if office == "Governor":
        return statewide("Governor and Lieutenant Governor", "GOVERNOR")
    if office == "Lt. Governor":
        return None
    if office in _STATEWIDE:
        return statewide(_STATEWIDE[office], office.upper())
    if office in _BOARDS:
        family = office.upper()
        if at_large:
            return Office(f"{family} AT LARGE", f"{_BOARDS[office]} At Large", family, "state", "state")
        seat = _number(district, office)
        return Office(f"{family} {seat}", f"{_BOARDS[office]} District {seat}", family, "state", "cd", str(seat))
    if office == "State Senate":
        return legislator("sd", _number(district, office))
    if office == "State House of Representatives":
        return legislator("hd", _number(district, office))
    if office == "RTD Board of Directors":
        seat = district.upper()
        return Office(f"RTD {seat}", f"RTD Board of Directors District {seat}", "RTD", "local", "unplaced", seat)
    return _court(office, district, name)


def _court(office: str, district: str, name: str) -> Office:
    """A judge's retention question, a race of its own; ValueError for an office it doesn't know."""
    key = name.upper()

    def retain(office_id: str, shown: str, family: str, reach: str, seat: str | None = None,
               where: tuple[str, ...] = ()) -> Office:
        return Office(office_id, f"Retain {name}, {shown}", family, "judicial", reach, seat, where, incumbent=True,
                      retention=True)

    if office == "Colorado Supreme Court":
        return retain(f"SUPREME COURT {key}", "Justice of the Colorado Supreme Court", "SUPREME COURT", "state")
    if office == "Colorado Court of Appeals":
        return retain(f"COURT OF APPEALS {key}", "Judge of the Colorado Court of Appeals", "COURT OF APPEALS", "state")
    if re.match(r"Dist[ri]+ct Court\b", office):
        for word, court in _DENVER_COURTS:
            if word in office:
                return retain(f"{court.upper()} {key}", f"Judge of the {court}", court.upper(), "county",
                              where=(_county("Denver"),))
        number = _number(district, office)
        if number not in _JUDICIAL:
            raise ValueError(f"no judicial district {number}")
        return retain(f"DISTRICT COURT {number} {key}", f"District Court Judge, {ordinal(number)} Judicial District",
                      "DISTRICT COURT", "counties", str(number),
                      tuple(sorted(_county(county) for county in _JUDICIAL[number])))
    if office in ("County Court", "Associate County Court"):
        county = _county(district)
        return retain(f"{office.upper()} {county} {key}", f"{county.title()} {office} Judge", office.upper(), "county",
                      where=(county,))
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
        if mate := tickets.get(id(row)):
            name = f"{name} and {mate[0].strip()}"
        code, party_name = party(label)
        filings.append(race.filing(day=day, name=name, party=code, party_name=party_name,
                                   write_in=write_in.upper() == "Y", order=index))
    return require(filings, MINIMUM)


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


GUIDE = Guide(
    name="Colorado",
    source="Colorado Secretary of State",
    url="https://www.coloradosos.gov/pubs/elections/main.html",
    computed=True,
    registration_url="https://www.govotecolorado.gov/",
    mail_url="https://www.govotecolorado.gov/",
    register="The last day to register online or by mail for {election} in Colorado and still be mailed a ballot. "
             "After it, you can still register and vote in person at a voter service and polling center, through "
             "Election Day.",
    mail_summary="Mail ballots go out",
    mail="Every active voter in Colorado is mailed a ballot for {election}. Your county clerk must have it back by "
         "7 p.m. on Election Day, by mail or in a drop box or at a voter service and polling center; a postmark "
         "doesn't count. More:",
    early_where="Your county clerk lists the voter service and polling centers and their hours; you can register and "
                "vote there in person.",
    credit="Dates worked out from Colorado's election law; more from the Colorado Secretary of State",
    poll_hours="7 a.m. – 7 p.m.",
    check_url="https://www.govotecolorado.gov/",
    check_hint="GoVoteColorado (Colorado Secretary of State): your registration, your ballot's status and where to vote",
    where_url="https://www.govotecolorado.gov/",
    where_hint="GoVoteColorado: your county's voter service and polling centers and drop boxes",
    mail_label="Track your ballot",
    mail_eligibility="Every active voter is mailed a ballot, from 22 days before Election Day. It must reach your county "
                     "clerk by 7 p.m. on Election Day, by mail, in a drop box or at a voter service and polling center; "
                     "a postmark doesn't count.",
    local_office="Your county clerk",
    polls_text="Voter service and polling centers are open 7 a.m. to 7 p.m. on Election Day; if you're in line at 7, "
               "you can vote.",
    late_registration="After that, register and vote in person at a voter service and polling center through "
                      "Election Day",
)
RULE = Counts(8, None, 15, 1).rule("CO")  # every voter is mailed a ballot
