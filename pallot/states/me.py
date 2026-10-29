"""Maine: the Secretary of State's general election candidate list, a spreadsheet (.xlsx), and its
declared write-in candidates, a PDF, both linked from its Upcoming Elections page. Their file names
are chosen by hand ("2026 General Candidate List - FINAL.xlsx", "Nov26 Declared Write in List -
Updated 10.15.26.pdf"), so they're found on that page by their links, never by a name worked out
ahead. maine.gov answers 403 to a script's user agent and 200 to a browser's, with no challenge, so
all three are asked with a browser's headers, as FiftyPlusOne is.

The sheet is named for the election's day ("November 3, 2026"), a row per candidate: the office's
abbreviation (US, CG, GOV, SS, SR, then the county offices), the district, the county, the party
(D, R, or a non-party candidate's own word: "Unenrolled", "Independent"), the date filed, the name
in parts and the town they live in. The write-ins' PDF has a line per candidate: the office, the
district, the county, the party in words, the name, the town and the towns the office covers.
Only the name, office, district, party and whether it's a write-in are kept: each file is streamed
to disk and kept as its filings, so the cache and the bundle hold nothing else. A primary winner
who withdrew is taken off the list (the page says so, and 2026's withdrawals PDF names no one still
on it), so the withdrawals aren't read. The county offices aren't placed: their districts aren't
any the Census knows (county commissioners, two counties' registries of deeds), and a sheriff or
judge of probate would need the county's code read, so they're left out.

Maine's races for U.S. Senate and House are ranked-choice in a general election with three
candidates or more, two of them on the ballot (21-A M.R.S. §1(27-C), §723-A); its Governor's and
the Legislature's aren't.

Maine's key dates, for its general election (every other November, the Tuesday after the first
Monday: 21-A M.R.S. §1(19), 2 U.S.C. §7), checked on legislature.maine.gov on 2026-10-28: a
registration by mail or online must reach the registrar by the 21st day before (§121-A(1)), and a
voter can register in person at the town office through Election Day, at the polls on the day
itself (§121-A(1)(D), §122(4)); any voter can vote absentee (§751), asking the town clerk by the
third business day before, the Thursday (§753-B(2)(D)), which is also the last day to vote
absentee in person at the town office, and the ballot must reach the clerk before the polls close
(§755); polls close at 8 p.m., and each town opens them between 6 and 10 a.m. (§626). No holiday
falls between that Thursday and Election Day.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any
from urllib.parse import unquote, urljoin

from ..http_cache import RequestSpec
from ..models import Race
from . import (
    MONTH_DAY_YEAR, Filing, Office, StateList, filings_json, legislator, party, pdf_lines, require, sheet_rows,
    statewide, us_house, us_senate,
)
from .dates import Counts, Guide

PAGE = "https://www.maine.gov/sos/elections-voting/upcoming-elections"
HEADERS = {  # maine.gov answers 403 to anything that doesn't look like a browser
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36",
    "accept-language": "en-US,en;q=0.8",
}
COLUMNS = ("Office", "Dist", "County", "Party", "Date Filed", "Last Name", "First Name", "Middle Name", "Suffix")
MINIMUM = {"cd": 2, "sd": 30, "hd": 140}  # nearly every district: one can go without a candidate
COUNTY_OFFICES = frozenset({"CC", "CT", "DA", "JP", "RD", "RP", "SH", "KBC", "ACC"})
_TITLE = re.compile(r"<title>\s*Upcoming Elections\b", re.I)
_LINK = re.compile(r"""href=["']([^"']+\.(?:xlsx|pdf))["']""", re.I)
_LIST = re.compile(r"(\d{4}) General Candidate List\b[^/]*\.xlsx$", re.I)
_WRITE_INS = re.compile(r"Declared Write[\s-]*in List[^/]*\.pdf$", re.I)
_WRITE_INS_DAY = re.compile(rf"for the ({MONTH_DAY_YEAR}) General Election")
_WRITE_IN = re.compile(r"\s*(US|CG|GOV|SS|SR)\s+(?:(\d+)\s+)?(\S.*)")
_CODES = {"D": "DEMOCRATIC", "R": "REPUBLICAN", "G": "GREEN", "L": "LIBERTARIAN"}


def links(text: str) -> dict[str, Any]:
    """The Upcoming Elections page as kept: its links to the general election candidate list, by
    year, and to the declared write-in candidates; ValueError for a page that isn't it."""
    if not _TITLE.search(text):
        raise ValueError("not the Secretary of State's Upcoming Elections page")
    found: dict[str, str] = {}
    write_ins: list[str] = []
    for href in _LINK.findall(text):
        url = urljoin(PAGE, href)
        year = _LIST.search(unquote(url))
        if year:
            found.setdefault(year.group(1), url)
        elif _WRITE_INS.search(unquote(url)) and url not in write_ins:
            write_ins.append(url)
    return {"links": found, "write_ins": write_ins}


def _race(code: str, district: str) -> Office | None:
    """The race an office's abbreviation and district name; None for a county office. ValueError
    for an office the list never had."""
    if code == "US":
        return us_senate("ME")
    if code == "GOV":
        return statewide("Governor")
    if code in ("CG", "SS", "SR"):
        if not district.isdigit():
            raise ValueError(f"no district for {code}: {district!r}")
        number = int(district)
        return us_house("ME", number) if code == "CG" else legislator("sd" if code == "SS" else "hd", number)
    if code in COUNTY_OFFICES:
        return None
    raise ValueError(f"an office it doesn't know: {code}")


def parse_rows(sheet: str, rows: list[list[str]]) -> list[Filing]:
    """Every candidate for Congress, Governor and the Legislature on the list; ValueError for a
    sheet that isn't the list (its name isn't the election's day, its columns, an office it
    doesn't know, a row without a name) or isn't all of it (MINIMUM)."""
    try:
        day = dt.datetime.strptime(" ".join(sheet.split()), "%B %d, %Y").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"not the general election's list: its sheet is {sheet!r}") from exc
    if not rows or tuple(rows[0][:len(COLUMNS)]) != COLUMNS:
        raise ValueError("not the list of general election candidates")
    filings = []
    for index, row in enumerate(rows[1:]):
        cells = [*row, *[""] * (len(COLUMNS) - len(row))]
        if not any(cells):
            continue
        race = _race(cells[0].upper(), cells[1])
        if race is None:
            continue
        last, first, middle, suffix = cells[5:9]
        if not last or not first:
            raise ValueError(f"a row without a name: {cells[:4]}")
        code, party_name = party(_CODES.get(cells[3].upper(), cells[3]))
        filings.append(race.filing(
            day=day, name=" ".join(part for part in (first, middle, last, suffix) if part), party=code,
            party_name=party_name, order=index,
        ))
    return require(filings, MINIMUM)


def write_ins(lines: list[str]) -> list[Filing]:
    """The declared write-in candidates for Congress, Governor and the Legislature, from pdf_lines'
    layout of their list: a line's office, its district, then its party (which can be blank), name,
    town and the towns the office covers, apart by runs of spaces. ValueError for a file that isn't
    the list, or a candidate's line it can't read."""
    text = " ".join(" ".join(lines).split())
    day = _WRITE_INS_DAY.search(text)
    if "Declared Write-in Candidates" not in text or day is None:
        raise ValueError("not the list of declared write-in candidates")
    day = dt.datetime.strptime(day.group(1), "%B %d, %Y").date().isoformat()
    filings = []
    for index, line in enumerate(lines):
        found = _WRITE_IN.fullmatch(line)
        if not found:
            continue
        cells = re.split(r"\s{2,}", found.group(3).strip())
        if len(cells) < 3:
            raise ValueError(f"a write-in it can't read: {' '.join(line.split())[:60]}")
        label, name = (cells[0], cells[1]) if len(cells) > 3 else ("", cells[0])
        code, party_name = party(label)
        filings.append(_race(found.group(1), found.group(2) or "").filing(
            day=day, name=name, party=code, party_name=party_name, write_in=True, order=100_000 + index,
        ))
    return filings


class MeList(StateList):
    state = "ME"
    source = "state_me"
    label = "Maine Secretary of State"
    page = PAGE
    description = ("Maine's list of the candidates for Congress, Governor and the Legislature, from its Secretary of "
                   "State.")
    max_bytes = 8 << 20
    index_key = "links"
    scope_note = ("Your county's races (sheriff, district attorney, judge of probate and the like) and any questions "
                  "aren't shown: your town clerk's sample ballot has them.")

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", PAGE, headers=HEADERS)

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        """The page's links; the write-ins kept beside an empty index, so a year whose list has none
        for these offices still reads as an answer."""
        if raw.startswith(b"PK"):
            return None
        if raw.startswith(b"%PDF"):
            return {**filings_json(write_ins(pdf_lines(raw))), "links": {}}
        return links(raw.decode("utf-8", "replace"))

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        url = index["links"].get(str(day.year))
        if not url:
            return None
        return [RequestSpec("GET", link, headers=HEADERS) for link in (url, *index.get("write_ins", ()))]

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, bytes):
            raise ValueError("not a spreadsheet or a PDF")
        return write_ins(pdf_lines(raw)) if raw.startswith(b"%PDF") else parse_rows(*sheet_rows(raw))

    @classmethod
    def ranked_choice(cls, race: Race) -> bool:
        """U.S. Senate and House, with three candidates or more, two of them on the ballot (21-A
        M.R.S. §1(27-C)); never Governor or the Legislature."""
        printed = sum(not candidate.write_in for candidate in race.candidates)
        return race.group == "federal" and printed >= 2 and len(race.candidates) >= 3


GUIDE = Guide(
    name="Maine",
    source="Maine Secretary of State",
    url="https://www.maine.gov/sos/elections-voting",
    computed=True,
    registration_url="https://registertovote.sos.maine.gov/",
    mail_url="https://absenteeballotrequest.sos.maine.gov/",
    register="The last day for your registration online or by mail to reach your town for {election} in Maine. After "
             "it, you can still register in person at your town office, or at your polling place on Election Day.",
    mail_summary="Absentee ballot request due",
    mail="If you vote absentee in {election}, ask your town clerk for your ballot by today. Your ballot must reach the "
         "clerk by 8 p.m. on Election Day; one that arrives later isn't counted. Any voter can vote absentee; how to "
         "ask:",
    early_where="Your town office: vote absentee in person there through the Thursday before Election Day. Your town "
                "clerk sets the hours.",
    credit="Dates worked out from Maine's election law; more from the Maine Secretary of State",
    poll_hours="8 p.m.",
    check_url="https://www.maine.gov/sos/elections-voting/find-a-municipal-clerk-or-registrar",
    check_hint="Every town's clerk and registrar (Maine Secretary of State); yours can tell you whether you're "
               "registered",
    where_url=PAGE,
    where_hint="Maine Secretary of State: its Voting Place Report lists every town's polling place",
    mail_label="How to ask",
    mail_eligibility="Any registered voter can vote absentee, no reason needed. Your ballot must reach your town clerk "
                     "by 8 p.m. on Election Day.",
    mail_deadline="Ask your town clerk for your ballot by ",
    local_office="Your town clerk",
    late_registration="After that, register in person at your town office, or at your polling place on Election Day",
    hours_set_by="your town",
)
RULE = Counts(21, 5, None, 5).rule("ME")
