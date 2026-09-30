"""Each Texas election's key dates (the last day to register, early voting, the last day to
apply to vote by mail), from the Texas Secretary of State's "Important Election Dates" page.

The page is plain HTML with one table per election, read through HttpCache as text and
parsed here. Earlier years' tables are still in it, inside HTML comments, which HTMLParser
skips. Labels vary from table to table ("First Day of Early Voting" or "... by Personal
Appearance"), so a row is known by how its label starts. A date cell gives the first full
date in it: some add a footnote, a note or a time after it.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from html.parser import HTMLParser

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec

SOURCE = "key_dates"
LABEL = "Key dates"
DESCRIPTION = (
    "The last day to register, early voting and the mail-ballot deadline of each Texas election, from the Texas "
    "Secretary of State's Important Election Dates page. VoteBot reads the whole page, so nothing about you is sent."
)
URL = "https://www.sos.state.tx.us/elections/voter/important-election-dates.shtml"
REGISTRATION_URL = "https://goelect.txelections.civixapps.com/ivis-mvp-ui/#/login"  # My Voter Portal
MAIL_APPLY_URL = "https://www.sos.state.tx.us/elections/voter/reqabbm.shtml"
REFUSALS = (403, 429)  # answers that pause the page for Ttls.key_dates_backoff

_DATE = re.compile(r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,\s+([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})")


@dataclass(frozen=True)
class Deadlines:
    day: dt.date  # Election Day
    name: str  # the page's name for the election: "Uniform Election Date", "Primary Runoff"
    register_by: dt.date | None = None
    mail_apply_by: dt.date | None = None  # the application must arrive (not be postmarked) by then
    early_start: dt.date | None = None
    early_end: dt.date | None = None


def first_date(text: str) -> dt.date | None:
    """The first "Monday, October 5, 2026" in the text."""
    match = _DATE.search(text)
    if not match:
        return None
    try:
        return dt.datetime.strptime(" ".join(match.groups()), "%B %d %Y").date()
    except ValueError:
        return None


def _field(label: str) -> str | None:
    """Which deadline a row's label (whitespace collapsed, lower case) gives, if any. Only the
    start counts: "Last Day for Candidates ... to Register to Vote" and "First day to apply
    for a ballot by mail" are other deadlines."""
    if label.startswith("last day to register to vote"):
        return "register_by"
    if label.startswith("first day of early voting"):
        return "early_start"
    if label.startswith("last day of early voting"):
        return "early_end"
    if label.startswith("last day to apply") and "mail" in label:
        return "mail_apply_by"
    return None


class _Tables(HTMLParser):
    """The text of each election table (class "norm-5px"): its summary attribute and its rows'
    cells, whitespace collapsed. Comments, and so the tables inside them, are skipped."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[tuple[str, list[list[str]]]] = []
        self._rows: list[list[str]] | None = None  # inside an election table
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        found = dict(attrs)
        if tag == "table" and "norm-5px" in (found.get("class") or "").split():
            self._rows = []
            self.tables.append((" ".join((found.get("summary") or "").split()), self._rows))
        elif self._rows is None:
            return
        elif tag == "tr":
            self._rows.append([])
        elif tag in ("td", "th"):
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self._rows is None:
            return
        if tag in ("td", "th") and self._cell is not None:
            if self._rows:
                self._rows[-1].append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "table":
            self._rows = self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def parse(html: str) -> list[Deadlines]:
    """Every election table on the page. A table's title ("Tuesday, November 3, 2026 -
    Uniform Election Date") is its summary attribute, or else its heading row."""
    reader = _Tables()
    reader.feed(html)
    reader.close()
    found = []
    for summary, rows in reader.tables:
        title = next((text for text in (summary, *(row[0] for row in rows if len(row) == 1)) if _DATE.search(text)), None)
        day = first_date(title or "")
        if title is None or day is None:
            continue
        dates: dict[str, dt.date | None] = {}
        for label, value, *_ in (row for row in rows if len(row) >= 2):
            field = _field(label.lower())
            if field and dates.get(field) is None:
                dates[field] = first_date(value)
        name = title[_DATE.search(title).end():].strip(" -–—:") or "Election"
        found.append(Deadlines(day, name, **dates))
    return found


class KeyDatesPage:
    def __init__(self, cache: HttpCache, ttl: Ttls):
        self.cache = cache
        self.ttl = ttl
        self._parsed: tuple[float, list[Deadlines]] | None = None
        cache.pause_on(SOURCE, REFUSALS, ttl.key_dates_backoff)

    async def deadlines(self) -> list[Deadlines]:
        """Every election on the page, parsed once per fetched copy. UpstreamError when the
        page can't be had and nothing is cached."""
        got = await self.cache.get_text(SOURCE, RequestSpec("GET", URL), ttl=self.ttl.key_dates)
        if self._parsed is None or self._parsed[0] != got.fetched_at:
            self._parsed = (got.fetched_at, parse(got.value or ""))
        return self._parsed[1]

    async def on(self, day: dt.date) -> Deadlines | None:
        return next((found for found in await self.deadlines() if found.day == day), None)
