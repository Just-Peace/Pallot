"""Montana: the Secretary of State's candidate list (candidatefiling.mt.gov), its CandidateList.aspx
grid (grid.py). The page's election dropdown has every election under an id ("FEDERAL GENERAL 2026
(11/03/2026) (General)" under 450002987); the page without one shows the newest primary. The list
is the grid's Export to CSV, a button that posts the page back for that election through
``__doPostBack``, so the postback names it as its ``__EVENTTARGET``. A plain script gets a 200.

A row per candidate: the status (Filed or Withdrawn; only Filed is kept), the district type
("Statewide", "Congressional", "Senate", "House", "Public Service Commission", "Supreme Court
Justice", "Judicial"), the district ("1ST CONGRESSIONAL", "SENATE DISTRICT 9"), the race ("STATE
SENATOR DISTRICT 9"), the term type (Regular, Unexpired) and length, the name in capitals, the
incumbent's after a "*", the candidate's address, email or website and phone, the filing date, the
party (DEM, REP, LIB, IND, NON for none) and a ballot order, mostly empty. A declared write-in is
marked only by "WRITE-IN" (or "WRITE IN") where the list has the email and website, the one thing
read from that column. Only the name, office, district, party, incumbent and write-in are kept: the
list is kept as its filings, so the cache and the bundle hold nothing else.

Its races in 2026 are the U.S. Senate, the U.S. House (two districts), the Public Service
Commission's districts up (each is 20 State House districts, MCA 69-1-104, so a voter's is found
by their State House district), a seat on the Supreme Court, about half the State Senate's 50
districts and all 100 of the State House. The district court judges are elected in judicial
districts the list doesn't place, and county races file with the county: they're left out with a
ballot note.

Montana's key dates, for its general election (the Tuesday after the first Monday of November in an
even year, 2 U.S.C. §7), checked on 2026-10-29 against the Montana Code Annotated 2025
(mca.legmt.gov): regular registration closes 30 days before (MCA 13-2-301(1)(a)), a Sunday, so the
last day moves to the next business day (1-1-307; Sundays and Columbus Day are legal holidays,
1-1-216), a Monday; a form postmarked by then still counts. After it, a voter can still register
late in person at the county election office and vote there, as late as Election Day (13-2-304).
Its hours are left to the county office: 2025's SB 490 (ch. 409) set them for a federal election,
and a court has stopped part of it, so the Secretary of State's own page lists them with notes on
what's barred. Any voter can vote absentee, no reason needed (13-13-201): the application must be
in before noon the day before (13-13-211), and the ballot must reach the election office or a
polling place in the county by 8 p.m. on Election Day (13-13-201(3)). Absentee ballots are
available to vote in person at the election office from 30 days before, the Sunday, so in effect
the Monday after, and mailed from 25 days before (13-13-205). Polls are open 7 a.m. to 8 p.m., or
from noon in a polling place with fewer than 400 voters who vote there in person (13-1-106), the
whole state in one time zone. 2026: Oct 5, Nov 2, Oct 5 – Nov 2, the first two as on the
Secretary of State's 2026 Voter Calendar (votemt.gov), which also has absentee ballots mailed Oct 9.
"""

from __future__ import annotations

import dataclasses
import re

from . import Office, legislator, us_house, us_senate
from .dates import Counts, Guide, Roll, columbus_day
from .grid import GridList, GridRow, titled

PAGE = "https://candidatefiling.mt.gov/candidatefiling/CandidateList.aspx"
EXPORT = {"__EVENTTARGET": "ctl00$ContentPlaceHolder1$grdCandidates$ctl00$ctl02$ctl00$ExportToCsvButton",
          "__EVENTARGUMENT": ""}
# The Public Service Commission's districts, each 20 State House districts (MCA 69-1-104).
PSC: dict[int, tuple[int, ...]] = {
    1: (19, 20, 21, 22, 23, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 38, 43, 44, 45),
    2: (39, 40, 41, 42, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 61, 62),
    3: (37, 60, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 77, 78, 79, 85, 86),
    4: (1, 2, 6, 8, 9, 10, 12, 13, 14, 87, 88, 89, 90, 93, 94, 95, 96, 97, 98, 100),
    5: (3, 4, 5, 7, 11, 15, 16, 17, 18, 24, 25, 76, 80, 81, 82, 83, 84, 91, 92, 99),
}
WEB = "EMAIL/WEB ADDRESS"  # the column a declared write-in is marked in
_NUMBER = re.compile(r"(\d+)(?:ST|ND|RD|TH)?\b", re.I)
_SEAT = re.compile(r"SUPREME COURT JUSTICE #\s*(\d+)", re.I)
_PSC = re.compile(r"PUBLIC SERVICE COMMISSIONER,? DISTRICT (\d+)", re.I)
_MARKED_WRITE_IN = re.compile(r"\bWRITE[- ]?IN\b", re.I)


def _number(row: GridRow) -> int:
    found = _NUMBER.search(row.district)
    if not found:
        raise ValueError(f"no district for {row.race}: {row.district!r}")
    return int(found.group(1))


class MtList(GridList):
    state = "MT"
    source = "state_mt"
    label = "Montana Secretary of State"
    page = PAGE
    form = EXPORT
    kept = ("FILED",)
    parties = {"IND": "Independent"}
    minimum = {"cd": 2, "sd": 20, "hd": 90}  # nearly every House district; about half the Senate's up
    description = ("Montana's official list of the candidates for Congress, the Public Service Commission, the Supreme "
                   "Court and the Legislature, from its Secretary of State.")
    scope_note = ("The district court judges, your county's offices and any ballot issues aren't shown: your county "
                  "election office's sample ballot has them.")

    @classmethod
    def office(cls, row: GridRow) -> Office | None:
        """The race of a row, its term unexpired where the list says so; None for a district court
        judge's. ValueError for an office it doesn't know."""
        found = cls._office(row)
        if found and row.cells.get("TERM TYPE", "").upper() == "UNEXPIRED":
            return dataclasses.replace(found, unexpired=True)
        return found

    @classmethod
    def _office(cls, row: GridRow) -> Office | None:
        kind, race = row.district_type.upper(), " ".join(row.race.split()).upper()
        if kind == "STATEWIDE" and race == "UNITED STATES SENATOR":
            return us_senate("MT")
        if kind == "CONGRESSIONAL" and race == "UNITED STATES REPRESENTATIVE":
            return us_house("MT", _number(row))
        if kind == "SENATE" and race.startswith("STATE SENATOR"):
            return legislator("sd", _number(row))
        if kind == "HOUSE" and race.startswith("STATE REPRESENTATIVE"):
            return legislator("hd", _number(row))
        if kind == "PUBLIC SERVICE COMMISSION" and (found := _PSC.fullmatch(race)):
            district = int(found.group(1))
            if district not in PSC:
                raise ValueError(f"no Public Service Commission district {district}")
            return Office(f"PUBLIC SERVICE COMMISSIONER {district}", f"Public Service Commissioner District {district}",
                          "PUBLIC SERVICE COMMISSIONER", "state", "hd", ",".join(str(n) for n in PSC[district]))
        if kind == "SUPREME COURT JUSTICE" and (found := _SEAT.fullmatch(race)):
            seat = found.group(1)
            return Office(f"SUPREME COURT {seat}", f"Supreme Court Justice No. {seat}", "SUPREME COURT", "judicial",
                          "state")
        if kind == "JUDICIAL":
            return None
        raise ValueError(f"an office it doesn't know: {row.race}")

    @classmethod
    def marked(cls, row: GridRow) -> tuple[str, bool, bool]:
        """The name without the incumbent's "*"; a write-in's where the email and website column says so."""
        name = row.name.strip()
        return name.lstrip("*").strip(), bool(_MARKED_WRITE_IN.search(row.cells.get(WEB, ""))), name.startswith("*")

    @classmethod
    def named(cls, name: str) -> str:
        return titled(name)


GUIDE = Guide(
    name="Montana",
    source="Montana Secretary of State",
    url="https://sosmt.gov/elections/",
    computed=True,
    registration_url="https://votemt.gov/voter-registration/",
    mail_url="https://votemt.gov/voter-registration/",
    register="The last day of regular registration for {election} in Montana: a form mailed today, postmarked, still "
             "counts. After it, you can still register late, and vote, in person at your county election office, as "
             "late as Election Day.",
    mail_summary="Absentee ballot application due",
    mail="If you vote absentee in {election}, your application must reach your county election office before noon "
         "today. Your ballot must reach the office, or a polling place in your county, by 8 p.m. on Election Day; one "
         "that arrives later isn't counted. Any voter can vote absentee; how to apply:",
    early_where="Your county election office, where you can vote an absentee ballot in person through noon the day "
                "before Election Day.",
    credit="Dates worked out from Montana's election law; more from the Montana Secretary of State",
    poll_hours="8 p.m.",
    check_url="https://voterportal.mt.gov/WhereToVote.aspx",
    check_hint="My Voter Page (Montana Secretary of State): your registration, your polling place and your absentee "
               "ballot",
    where_url="https://voterportal.mt.gov/WhereToVote.aspx",
    where_hint="My Voter Page (Montana Secretary of State): your polling place and your county election office",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote absentee, no reason needed. Your ballot must reach your county "
                     "election office, or a polling place in your county, by 8 p.m. on Election Day.",
    mail_deadline="Apply to your county election office before noon on ",
    local_office="Your county election office",
    polls_text="Polls are open 7 a.m. to 8 p.m.; a polling place with fewer than 400 voters may open at noon instead. If "
               "you're in line at 8, you can vote.",
    late_registration="After that, register late in person at your county election office, as late as Election Day",
    hours_set_by="your county",
)
RULE = Counts(30, 1, 29, 1, roll=Roll(holidays=lambda year: (columbus_day(year),))).rule("MT")
