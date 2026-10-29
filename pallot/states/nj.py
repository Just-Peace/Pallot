"""New Jersey: the Division of Elections' official lists of the general election's candidates,
PDFs linked from its election information page for the year: U.S. Senate and U.S. House in an
even year; the State Senate and the General Assembly in an odd one. The Legislature's 40
districts each elect a senator and two members of the General Assembly; the Assembly is up every
odd year, the Senate in the years ending 1, 3 and 7 (N.J. Const. art. IV, §2), and a Senate list
in another odd year is a special election's (2025's, for the 35th district). A file name may
carry the date it was last changed, so the lists are found on that page by their links, never by
a name worked out ahead.

Each candidate's first line is their name, an asterisk after an incumbent's, their mailing
address and their party or slogan, then the same once for each county with the party in
capitals. A long name wraps onto the lines under it, and an Assembly candidate's running mate
follows in brackets ("(bracketed with …)"). Only the name, party, district and incumbent are
kept: the address never leaves the parser, so the cache and the bundle hold the parsed filings
and the page's links alone. A district starts with its heading ("First Congressional District:
BURLINGTON (part) - …  Counties", "Twenty-First Legislative District: …"), sometimes wrapped onto
a second line, and each list ends with its totals: a count for each party or slogan, which tells
where a party ends an address it runs into, and the count of candidates the list read must match.

New Jersey's key dates, for its general election (N.J.S.A. 19:2-3: the Tuesday after the first
Monday of November): registration closes the twenty-first day before (19:31-6.3); early voting in
person runs from the tenth day before through the second day before (19:15A-1); any voter can vote
by mail, applying by mail so the county clerk has it by the seventh day before, or in person at the
clerk's office until 3 p.m. the day before (19:63-3), and a mailed ballot must be postmarked by
Election Day and reach the county board of elections within 144 hours after the polls close
(19:63-22); polls are open 6 a.m. to 8 p.m. (19:15-2).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import re
from typing import Any
from urllib.parse import urljoin

from ..http_cache import RequestSpec
from ..text import display_person
from . import _ORDINALS, Filing, Office, StateList, legislator, party, pdf_lines, require, us_house, us_senate
from .dates import Counts, Guide

BASE = "https://www.nj.gov/state/elections/"
URL = BASE + "election-information-{year}.shtml"
# Each list by its title, under the name it's kept by (its file's, without "us-"), in ballot order.
LISTS = {
    "Candidates for US Senate": "senate", "Candidates for House of Representatives": "house",
    "Candidates for State Senate": "state-senate", "Candidates for General Assembly": "general-assembly",
}
MINIMUM = {"cd": 12, "sd": 40, "hd": 40}  # of a list in a year its seats are all up: fewer districts isn't the whole list
_LINK = re.compile(r"""href=["']([^"']*/(\d{4})-official-general-candidates-(us-senate|us-house|state-senate|"""
                   r"""general-assembly)(?:-\d+)?\.pdf)["']""", re.I)
_TITLE = re.compile(r"<title>[^<]*\b(\d{4}) Election Information", re.I)
_DAY = re.compile(r"GENERALELECTION(\d{2}/\d{2}/\d{4})")
_HEADING = re.compile(r"([\w-]+) (Congressional|Legislative) District:", re.I)
_TENS = {"TWENTY": 20, "THIRTY": 30}
_UNITS = {**_ORDINALS, "THIRTIETH": 30, "FORTIETH": 40}
_TOTAL = re.compile(r"Total Candidates\s+(\d+)")
_COUNT = re.compile(r"(\S.*?)\s{2,}\d+$")
_PAGE = re.compile(r"\d{2}/\d{2}/\d{4}\s.*Official List|Name\s{2,}Address\s{2,}Party")
_NAMES = {"INDEPENDENT": "Independent"}


def links(text: str) -> dict[str, Any]:
    """The election information page as kept: its year and the links to its official lists of
    general-election candidates; ValueError for a page that isn't it."""
    title = _TITLE.search(text)
    if not title:
        raise ValueError("not the Division of Elections' election information page")
    found = {kind.lower().removeprefix("us-"): urljoin(BASE, href)
             for href, year, kind in _LINK.findall(text) if year == title.group(1)}
    return {"year": int(title.group(1)), "links": found}


def _district(word: str) -> int:
    """A heading's district, "Twelfth" or "Twenty-First"; ValueError for a word that isn't one."""
    tens, _, unit = word.upper().rpartition("-")
    number = _UNITS.get(unit)
    if number is None or tens and (tens not in _TENS or number > 9):
        raise ValueError(f"no district {word}")
    return _TENS.get(tens, 0) + number


def _race(kind: str, district: int | None) -> Office:
    if kind == "senate":
        return us_senate("NJ")
    if district is None:
        raise ValueError("a candidate before the first district")
    if kind == "house":
        return us_house("NJ", district)
    if kind == "state-senate":
        return legislator("sd", district)
    return dataclasses.replace(legislator("hd", district, office=f"General Assembly District {district}"), seats=2)


def _labels(lines: list[str]) -> list[str]:
    """The parties and slogans a list's totals count, longest first."""
    start = next((i for i, line in enumerate(lines) if line.lstrip().startswith("Candidate Totals")), len(lines))
    found = {" ".join(count.group(1).split()) for line in lines[start:] if not _PAGE.search(line)
             and (count := _COUNT.match(line.strip())) and not count.group(1).startswith("Total Candidates")}
    return sorted(found, key=len, reverse=True)


def parse_lines(lines: list[str]) -> list[Filing]:
    """Every candidate on one of the lists, from pdf_lines' layout; ValueError for a file that
    isn't one, a list without every district in a year they're all up, or one whose count isn't
    its total's."""
    day = next((found.group(1) for line in lines if (found := _DAY.search(re.sub(r"\s", "", line)))), None)
    if day is None:
        raise ValueError("no general election date")
    day = dt.datetime.strptime(day, "%m/%d/%Y").date().isoformat()
    kinds = {kind for title, kind in LISTS.items() if any(title in line for line in lines)}
    if len(kinds) != 1:
        raise ValueError("not a list of candidates for U.S. Senate or House, State Senate or General Assembly")
    kind, labels = kinds.pop(), _labels(lines)
    place = list(LISTS.values()).index(kind) * 10_000
    filings: list[Filing] = []
    district, wrapped, bracket, totals, total, listed = None, False, False, False, None, 0
    for line in lines:
        text = " ".join(line.split())
        if not text or line[0].isspace() or _PAGE.search(line):
            continue
        if wrapped:
            wrapped = not text.endswith("Counties")
            continue
        if found := _TOTAL.match(text):
            total = int(found.group(1))
            continue
        totals = totals or text.startswith("Candidate Totals")
        if totals:
            continue
        if found := _HEADING.match(text):
            district, wrapped, bracket, listed = _district(found.group(1)), not text.endswith("Counties"), False, 0
            continue
        cells = re.split(r"\s{2,}", line.strip())
        if bracket or text.startswith("("):
            bracket = ")" not in cells[0]
            continue
        label = next((label for label in labels if text.endswith(label)), None)
        if label is None:
            if not listed:
                raise ValueError(f"a line it can't read: {text[:60]}")
            last = filings[-1]
            filings[-1] = dataclasses.replace(last, name=last.name + ("" if last.name.endswith("-") else " ") + cells[0])
            continue
        code, party_name = party(label, _NAMES)
        listed += 1
        filings.append(_race(kind, district).filing(
            day=day, name=cells[0], party=code, party_name=party_name, order=place + (district or 0) * 100 + listed,
        ))
    if not total or total != len(filings):
        raise ValueError(f"{len(filings)} candidates, not the {total or 'no'} its totals say")
    filings = [dataclasses.replace(f, name=display_person(" ".join(f.name.rstrip("* ").split())),
                                   incumbent=f.name.rstrip().endswith("*")) for f in filings]
    year = int(day[:4])
    regular = {"cd": year % 2 == 0, "hd": year % 2 == 1, "sd": year % 10 in (1, 3, 7)}
    return require(filings, {reach: least for reach, least in MINIMUM.items()
                             if regular[reach] and any(f.reach == reach for f in filings)})


class NjList(StateList):
    state = "NJ"
    source = "state_nj"
    label = "New Jersey Division of Elections"
    page = "https://www.nj.gov/state/elections/election-information.shtml"
    description = ("New Jersey's official lists of the candidates for U.S. Senate and House, the State Senate and the "
                   "General Assembly, from its Division of Elections.")
    max_bytes = 16 << 20
    index_key = "links"

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", URL.format(year=day.year))

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        return None if raw.startswith(b"%PDF") else links(raw.decode("utf-8", "replace"))

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        """The year's lists, once the one always up that year is out: the House's in an even year,
        the General Assembly's in an odd one."""
        found = index["links"]
        if ("house" if day.year % 2 == 0 else "general-assembly") not in found:
            return None
        return [RequestSpec("GET", found[kind]) for kind in LISTS.values() if kind in found]

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, bytes):
            raise ValueError("not a PDF")
        return parse_lines(pdf_lines(raw))


GUIDE = Guide(
    name="New Jersey",
    source="New Jersey Division of Elections",
    url="https://www.nj.gov/state/elections/",
    computed=True,
    registration_url="https://voter.svrs.nj.gov/register",
    mail_url="https://www.nj.gov/state/elections/vote-by-mail.shtml",
    register="The last day to register to vote in {election} in New Jersey, online, by mail or in person. There's no "
             "registration on Election Day.",
    mail_summary="Mail-in ballot application due by mail",
    mail="If you vote by mail in {election}, an application sent by mail must reach your county clerk today. In "
         "person, you can apply at the clerk's office until 3 p.m. the day before Election Day. Your ballot must be "
         "postmarked by Election Day and reach your county board of elections within six days, or be dropped in a "
         "drop box by 8 p.m. on Election Day. Any voter can vote by mail; how to apply:",
    early_where="Your county lists the places. Early voting is open 10 a.m. to 8 p.m. Monday to Saturday, and 10 a.m. "
                "to 6 p.m. on Sunday.",
    credit="Dates worked out from New Jersey's election law; more from the New Jersey Division of Elections",
    poll_hours="6 a.m. – 8 p.m.",
    check_url="https://voter.svrs.nj.gov/registration-check",
    check_hint="New Jersey's voter registration check (Division of Elections)",
    where_url="https://voter.svrs.nj.gov/polling-place-search",
    where_hint="New Jersey's polling place search; your county lists its early voting places",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote by mail, no reason needed. Your ballot must be postmarked by "
                     "Election Day and reach your county within six days, or be dropped in a drop box by 8 p.m. on "
                     "Election Day.",
    mail_deadline="An application sent by mail must reach your county clerk by ",
    local_office="Your county clerk",
)
RULE = Counts(21, 7, 10, 2, every_year=True).rule("NJ")
