"""California: the Secretary of State's Official Certified List of Candidates for a general
election, a PDF of about 40 pages (14 MB, mostly its cover's seal), open to scripts on the SOS's
CDN. Each race is a centred heading, then its candidates one to a line, name and party apart,
an asterisk after an incumbent's name, and their ballot designation on the line under.

Its State Senate races are half the districts (one year the odd ones, the next the even). The
Board of Equalization's four districts aren't said by county, so they're left out. Then come
the courts' retention questions, from another tool whose layout splits words: the Supreme Court
for the whole state, and each Court of Appeal district with the counties it covers. They're read
from the file's text order instead, each question a race of its own with the justice as its one
candidate, as Florida's are: "Retain" a sitting justice, "Elect" a judge the Governor appointed
to the court, as the question words it ("Shall Superior Court Judge … be elected").
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from .. import counties
from ..http_cache import RequestSpec
from ..text import display_person
from . import _ORDINALS, Filing, Office, StateList, party, pdf_lines, require, statewide, us_house, us_senate

URL = "https://elections.cdn.sos.ca.gov/statewide-elections/{year}-general/cert-list-candidates.pdf"
MINIMUM = {"cd": 52}  # a list with fewer U.S. House races isn't the whole list
STATEWIDE = ("Governor", "Lieutenant Governor", "Secretary of State", "Controller", "Treasurer", "Attorney General",
              "Insurance Commissioner", "Superintendent of Public Instruction")
_DISTRICTS = (
    (re.compile(r"United States Representative District (\d+)"), "federal", "cd", "US HOUSE"),
    (re.compile(r"State Senate District (\d+)"), "legislature", "sd", "STATE SENATE"),
    (re.compile(r"State Assembly Member District (\d+)"), "legislature", "hd", "STATE ASSEMBLY"),
    (re.compile(r"Board of Equalization Member District (\d+)"), "state", "unplaced", "Board of Equalization"),
)
_NO_PARTY = ("NO PARTY PREFERENCE", "NON-PARTISAN", "NONPARTISAN")
_DAY = re.compile(r"General Election - (\w+ \d{1,2}, \d{4})")
_CANDIDATE = re.compile(r"(\S.*?\S)\s{3,}(\S.*)")
_HEADING = 20  # a heading is centred, its line starting this many spaces in or more; a candidate's starts nearer
_PAGE = re.compile(r"General Election|Official Certified List|\d{1,2}/\d{1,2}/\d{4}$|Page \d+ of \d+$|\* ?Incumbent$")
_SUPREME = re.compile(r"Supreme Court\s*-\s*For all", re.I)
_APPEAL = re.compile(r"Court of Appeal\s*[-–]\s*(\w+) Appellate District", re.I)
_TITLE = re.compile(r"Court of Appeal, (\w+) District(?:, Division (\w+))?", re.I)
_DIVISIONS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9}
_QUESTION = re.compile(r"Shall (.*?)\s*\b((?:[A-Z][A-Z.'’-]*\s+)*[A-Z][A-Z.'’-]*) be elected\b")


def _race(heading: str) -> Office | None:
    """A candidates' heading's race; None for one it doesn't know."""
    if heading in STATEWIDE:
        return statewide(heading)
    if heading.startswith("United States Senator"):
        return us_senate("CA", heading.upper())
    for pattern, group, reach, family in _DISTRICTS:
        if found := pattern.fullmatch(heading):
            number = int(found.group(1))
            if reach == "cd":
                return us_house("CA", number, heading.upper())
            return Office(heading.upper(), heading, family, group, reach, str(number))
    return None


def _candidates(lines: list[str]) -> tuple[str | None, list[Filing]]:
    """The election's day and the candidates, from the layout's lines, up to the courts."""
    day, filings, race = None, [], None
    races, listed = 0, 0
    for line in lines:
        text = " ".join(line.split())
        if not text:
            continue
        if found := _DAY.search(text):
            day = day or dt.datetime.strptime(found.group(1), "%B %d, %Y").date().isoformat()
            continue
        if _PAGE.search(text):
            continue
        if _SUPREME.search(text) or _APPEAL.search(text):
            break
        indent = len(line) - len(line.lstrip())
        candidate = _CANDIDATE.fullmatch(line.strip())
        if indent >= _HEADING and not candidate:
            races, listed, race = races + 1, 0, _race(text)
            continue
        if race is None or not candidate or not indent or day is None:
            continue
        listed += 1
        name, label = candidate.group(1).strip(), " ".join(candidate.group(2).split())
        code, party_name = (None, None) if label.upper() in _NO_PARTY else party(label)
        filings.append(race.filing(
            day=day, name=" ".join(name.rstrip("*").split()), party=code, party_name=party_name,
            incumbent=name.endswith("*"), order=races * 100 + listed,
        ))
    return day, filings


def _county_line(text: str) -> tuple[str, ...] | None:
    """The counties a line names, matched with spaces ignored ("S  olano"); None unless it's all counties."""
    found = [counties.find("CA", part) for part in text.split(",") if part.strip()]
    return tuple(county.name.upper() for county in found) if found and all(found) else None


def _district(title: str) -> tuple[int, int]:
    """(appellate district, division) a question's title names: (0, 0) for the Supreme Court's."""
    if "Supreme Court" in title:
        return 0, 0
    found = _TITLE.search(title)
    number = _ORDINALS.get(found.group(1).upper()) if found else None
    if number is None:
        raise ValueError(f"no court in {title[:60]}")
    return number, _DIVISIONS.get((found.group(2) or "").upper(), 0)


def _retention(lines: list[str], day: str, start: int) -> list[Filing]:
    """The courts' retention questions, from the file's text order: a page's heading of an
    appellate district can come first in it, so a question's court is the one its title names,
    and the questions are put in the ballot's order (the Supreme Court, then each district's)."""
    where: dict[int, list[str]] = {}
    asked: list[tuple[str, str]] = []  # (title, question)
    courts, heading, title, question = False, None, None, None
    for raw in lines:
        text = " ".join(raw.split())
        if not text or _PAGE.search(text) and not question:
            continue
        if _SUPREME.search(text):
            courts, heading = True, None
            continue
        if found := _APPEAL.search(text):
            heading = _ORDINALS.get(found.group(1).upper())
            if heading is None:
                raise ValueError(f"no appellate district {found.group(1)}")
            courts = True
            where.setdefault(heading, [])
            continue
        if not courts:
            continue
        if text.startswith("•"):
            title, heading = text.lstrip("• ").removeprefix("For ").strip(), None
            continue
        if question is not None or text.startswith("Shall "):
            question = f"{question} {text}" if question else text
            if text.endswith("?"):
                if not title:
                    raise ValueError(f"a retention question without its office: {question[:60]}")
                asked.append((title, question))
                question = None
            continue
        if heading and (named := _county_line(text)):
            where[heading].extend(named)
    ranked = sorted(enumerate(asked), key=lambda item: (*_district(item[1][0]), item[0]))
    filings = []
    for rank, (_, (title, question)) in enumerate(ranked):
        found = _QUESTION.search(question)
        if not found:
            raise ValueError(f"a retention question it can't read: {question[:60]}")
        name = display_person(" ".join(found.group(2).split()))
        number = _district(title)[0]
        if number and not where.get(number):
            raise ValueError(f"no counties for appellate district {number}")
        family, district = ("COURT OF APPEAL", str(number)) if number else ("SUPREME COURT", None)
        sitting = "Justice" in found.group(1)
        race = Office(" ".join(filter(None, (family, district, name.upper()))),
                      f"{'Retain' if sitting else 'Elect'} {name}, {title}", family, "judicial",
                      "counties" if district else "state", district, tuple(sorted(where.get(number, ()))),
                      incumbent=sitting, retention=True)
        filings.append(race.filing(day=day, name=name, order=(start + rank) * 100))
    return filings


def parse_lines(layout: list[str], plain: list[str]) -> list[Filing]:
    """Every candidate in the list: the races' from ``layout`` (pdf_lines' columns), the courts'
    retention from ``plain`` (its text order); ValueError for a file that isn't the whole list."""
    day, filings = _candidates(layout)
    if day is None:
        raise ValueError("no general election date")
    require(filings, MINIMUM)
    return filings + _retention(plain, day, max((f.order // 100 for f in filings), default=0) + 1)


class CaList(StateList):
    state = "CA"
    source = "state_ca"
    label = "California Secretary of State"
    page = "https://www.sos.ca.gov/elections/upcoming-elections"
    description = "California's official list of the candidates on its ballot, from its Secretary of State."
    max_bytes = 64 << 20

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", URL.format(year=day.year))

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, bytes):
            raise ValueError("not a PDF")
        return parse_lines(pdf_lines(raw), pdf_lines(raw, layout=False))
