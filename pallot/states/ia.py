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
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from . import (
    MONTH_DAY_YEAR, WITHDRAWN, Filing, ManualList, Office, legislator, party, pdf_lines, require, statewide, us_house,
    us_senate,
)

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
