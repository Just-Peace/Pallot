"""New Jersey: the Division of Elections' official lists of the general election's candidates
for U.S. Senate and U.S. House, two PDFs linked from its election information page for the year.
The House list's file name carries the date it was last changed, so both are found on that page
by their links, never by a name worked out ahead.

Each candidate's first line is their name, an asterisk after an incumbent's, their mailing
address and their party or slogan, then the same once for each county with the party in
capitals. Only the first line is read, and only the name, party, district and incumbent kept:
the address never leaves the parser, so the cache and the bundle hold the parsed filings and the
page's two links alone. A House district starts with its heading ("First Congressional District:
BURLINGTON (part) - …  Counties"), sometimes wrapped onto a second line, and each list ends with
its totals, whose count of candidates the list read must match.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any
from urllib.parse import urljoin

from ..http_cache import RequestSpec
from ..text import display_person
from . import _ORDINALS, Filing, StateList, party, pdf_lines, require, us_house, us_senate

BASE = "https://www.nj.gov/state/elections/"
URL = BASE + "election-information-{year}.shtml"
MINIMUM = {"cd": 12}  # a House list with fewer districts isn't the whole list
_LINK = re.compile(r"""href=["']([^"']*/(\d{4})-official-general-candidates-us-(senate|house)(?:-\d+)?\.pdf)["']""", re.I)
_TITLE = re.compile(r"<title>[^<]*\b(\d{4}) Election Information", re.I)
_DAY = re.compile(r"GENERALELECTION(\d{2}/\d{2}/\d{4})")
_HEADING = re.compile(r"(\w+) Congressional District:", re.I)
_TOTAL = re.compile(r"Total Candidates\s+(\d+)")
_PAGE = re.compile(r"\d{2}/\d{2}/\d{4}\s.*Official List|Name\s{2,}Address\s{2,}Party")
_NAMES = {"INDEPENDENT": "Independent"}


def links(text: str) -> dict[str, Any]:
    """The election information page as kept: its year and the links to its official lists of
    general-election candidates; ValueError for a page that isn't it."""
    title = _TITLE.search(text)
    if not title:
        raise ValueError("not the Division of Elections' election information page")
    found = {kind.lower(): urljoin(BASE, href) for href, year, kind in _LINK.findall(text) if year == title.group(1)}
    return {"year": int(title.group(1)), "links": found}


def parse_lines(lines: list[str]) -> list[Filing]:
    """Every candidate on one of the lists, from pdf_lines' layout; ValueError for a file that
    isn't one, a House list without every district, or one whose count isn't its total's."""
    day = next((found.group(1) for line in lines if (found := _DAY.search(re.sub(r"\s", "", line)))), None)
    if day is None:
        raise ValueError("no general election date")
    day = dt.datetime.strptime(day, "%m/%d/%Y").date().isoformat()
    senate = any("Candidates for US Senate" in line for line in lines)
    house = any("Candidates for House of Representatives" in line for line in lines)
    if senate == house:
        raise ValueError("not the list of candidates for U.S. Senate or House")
    filings: list[Filing] = []
    district, wrapped, totals, total, listed = None, False, False, None, 0
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
            number = _ORDINALS.get(found.group(1).upper())
            if number is None:
                raise ValueError(f"no district {found.group(1)}")
            district, wrapped, listed = number, not text.endswith("Counties"), 0
            continue
        cells = re.split(r"\s{2,}", line.strip())
        if house and district is None or len(cells) < 2:
            raise ValueError(f"a line it can't read: {text[:60]}")
        name, label = cells[0], " ".join(cells[-1].split())
        code, party_name = party(label, _NAMES)
        listed += 1
        race = us_house("NJ", district) if house else us_senate("NJ")
        filings.append(race.filing(
            day=day, name=display_person(" ".join(name.rstrip("*").split())), party=code, party_name=party_name,
            incumbent=name.endswith("*"), order=(district or 0) * 100 + listed,
        ))
    if not total or total != len(filings):
        raise ValueError(f"{len(filings)} candidates, not the {total or 'no'} its totals say")
    return require(filings, MINIMUM) if house else filings


class NjList(StateList):
    state = "NJ"
    source = "state_nj"
    label = "New Jersey Division of Elections"
    page = "https://www.nj.gov/state/elections/election-information.shtml"
    description = "New Jersey's official lists of the candidates for U.S. Senate and House, from its Division of Elections."
    max_bytes = 16 << 20
    index_key = "links"

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", URL.format(year=day.year))

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        return None if raw.startswith(b"%PDF") else links(raw.decode("utf-8", "replace"))

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        found = index["links"]
        if "house" not in found:
            return None
        return [RequestSpec("GET", found[kind]) for kind in ("senate", "house") if kind in found]

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, bytes):
            raise ValueError("not a PDF")
        return parse_lines(pdf_lines(raw))
