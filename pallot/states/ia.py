"""Iowa: the Secretary of State's Candidate List for a general election, a PDF made from a
spreadsheet, saved by hand (manual/state_ia), since sos.iowa.gov answers scripts with
Cloudflare's challenge and Pallot never asks it.

Its columns are For the Office Of…, Party, Ballot Name(s), Address, Phone, Email and Filing
Date. The office is printed only on a race's first row, and the rows under it are the same
race's; a party that has no candidate has "--" for a name. Only the office, party and name are
read: the address, phone and email are never kept. Each page repeats the title, the column
headings and a footer about the filing period, which are skipped.

The list has Congress, the statewide offices and the Legislature. The Governor and Lieutenant
Governor are elected as a ticket, but the list names them as two offices, and so does Pallot.

Iowa's key dates, for its general election (Iowa Code 39.1: the first Tuesday after the first Monday
of November in an even year), checked on legis.iowa.gov (Iowa Code 2026) on 2026-10-24:
pre-registration closes at 5 p.m. fifteen days before (48A.9), then voters register at the polls on
Election Day with ID and proof of residence (48A.7A); any voter can vote absentee, the written
application reaching the county auditor by 5 p.m. on that same day (53.2(1)(b)), and the ballot must
reach the auditor before the polls close (53.17); absentee voting in person at the auditor's office
starts twenty days before (53.10) and goes on any day but Election Day (53.2(1)(a)); polls are open
7 a.m. to 8 p.m. (49.73).
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from . import (
    MONTH_DAY_YEAR, WITHDRAWN, Filing, ManualList, Office, legislator, party, pdf_lines, require, statewide, us_house,
    us_senate,
)
from .dates import Counts, Guide

STATEWIDE = ("Governor", "Lieutenant Governor", "Secretary of State", "Auditor of State", "Treasurer of State",
             "Secretary of Agriculture", "Attorney General")
MINIMUM = {"cd": 4, "hd": 100}
_TITLE = re.compile(rf"\b({MONTH_DAY_YEAR}) General Election\b")
_DATE = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")
_NOISE = re.compile(r"\s*(?:For change requests\b|or \d{3}-\d{3}-\d{4}|Candidate List\b|For the Office Of\b|"
                    r"Filing period\b|Ballot vacancies\b|\w+ \d{1,2}, \d{4} General Election\b)")
_PARTIES = {"NO PARTY": None}


def _kind(office: str) -> Office:
    """The race an office names; ValueError for one the list never had."""
    upper = office.upper()
    if upper == "UNITED STATES SENATOR":
        return us_senate("IA", upper)
    if found := re.fullmatch(r"UNITED STATES REPRESENTATIVE DISTRICT (\d+)", upper):
        return us_house("IA", int(found.group(1)), upper)
    for pattern, reach in ((r"STATE SENATOR DISTRICT (\d+)", "sd"), (r"STATE REPRESENTATIVE DISTRICT (\d+)", "hd")):
        if found := re.fullmatch(pattern, upper):
            return legislator(reach, int(found.group(1)), upper)
    for name in STATEWIDE:
        if upper == name.upper():
            return statewide(name, upper)
    raise ValueError(f"an office it doesn't know: {office}")


def parse_lines(lines: list[str]) -> list[Filing]:
    """Every candidate on the list, from pdf_lines' layout; ValueError for a file that isn't the
    list (no title, a row it can't split into its columns, an office it doesn't know) or isn't all
    of it (MINIMUM)."""
    title = next((found.group(1) for line in lines if (found := _TITLE.search(line))), None)
    if title is None:
        raise ValueError("no general election's title")
    day = dt.datetime.strptime(title, "%B %d, %Y").date().isoformat()
    filings: list[Filing] = []
    race: Office | None = None
    for index, line in enumerate(lines):
        if not line.strip() or _NOISE.match(line):
            continue
        cells = re.split(r"\s{3,}", line.strip())
        if not line[0].isspace():
            race = _kind(cells.pop(0))
        if race is None or len(cells) < 2:
            raise ValueError(f"a row it can't split into the list's columns: {' '.join(line.split())[:80]}")
        label, name = " ".join(cells[0].split()), " ".join(cells[1].split())
        if name == "--":
            continue
        if len(cells) < 3 or not _DATE.fullmatch(cells[-1]) or _DATE.search(label) or any(c.isdigit() for c in name):
            raise ValueError(f"a row it can't split into the list's columns: {' '.join(line.split())[:80]}")
        if WITHDRAWN.search(line):
            continue
        code, party_name = (_PARTIES[label.upper()], None) if label.upper() in _PARTIES else party(label)
        filings.append(race.filing(day=day, name=name, party=code, party_name=party_name, order=index))
    return require(filings, MINIMUM)


class IaList(ManualList):
    state = "IA"
    source = "state_ia"
    label = "Iowa Secretary of State"
    page = "https://sos.iowa.gov/general-election"
    description = ("Iowa's official list of the candidates for Congress, its statewide offices and the Legislature, "
                   "from its Secretary of State, imported by hand.")
    folder = "manual/state_ia"
    binary = True
    challenge = ("Just a moment...", "challenges.cloudflare.com", "cf-browser-verification")

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, bytes):
            raise ValueError("not a PDF")
        return parse_lines(pdf_lines(raw))


GUIDE = Guide(
    name="Iowa",
    source="Iowa Secretary of State",
    url="https://sos.iowa.gov/general-election",
    computed=True,
    registration_url="https://sos.iowa.gov/elections-voting",
    mail_url="https://sos.iowa.gov/elections-voting",
    register="The last day to pre-register for {election} in Iowa, by 5 p.m. After it, you can still register at "
             "your polling place on Election Day, with ID and proof of where you live.",
    mail_summary="Absentee ballot request due",
    mail="If you vote absentee in {election}, your request must reach your county auditor by 5 p.m. today. Your "
         "ballot must reach the auditor before the polls close at 8 p.m. on Election Day; one that arrives later "
         "isn't counted. Any voter can vote absentee; how to ask:",
    early_where="Your county auditor's office, and any satellite sites your county opens; the auditor lists the "
                "places and hours.",
    credit="Dates worked out from Iowa's election law; more from the Iowa Secretary of State",
    poll_hours="7 a.m. – 8 p.m.",
    check_url="https://sos.iowa.gov/elections-voting",
    check_hint="Iowa Secretary of State: check your registration and find your polling place",
    where_url="https://sos.iowa.gov/elections-voting",
    where_hint="Iowa Secretary of State: your polling place, and your county auditor's office for voting early",
    mail_label="How to ask",
    mail_eligibility="Any registered voter can vote absentee by mail, no reason needed. Your ballot must reach your "
                     "county auditor before the polls close at 8 p.m. on Election Day.",
    mail_deadline="Your request must reach your county auditor by 5 p.m. on ",
    local_office="Your county auditor",
    late_registration="After that, register at your polling place on Election Day, with ID and proof of where you live",
)
RULE = Counts(15, 15, 20, 1).rule("IA")
