"""Virginia: the Department of Elections' candidate lists for a November election, each a page
with a table (a spreadsheet's rows): office, district, party, name as on the ballot, and, on
the newer ones, whether they hold the seat. Its Candidates & Referendums page links the
election's lists, named for its day and what they cover ("november-3-2026-gen-elect-federal-
offices", "november-4-2025-gen-elect-house-of-del"); the names change from year to year, so the
lists are found on that page by their links, never by a name worked out ahead.

The list of all offices is read, a row per candidate in each locality the race reaches (so a
statewide candidate's rows repeat): it alone also has a special election's race on the same day
(2026's for House of Delegates District 20). Where the page links none, every list but the local
offices' is. That's Congress in an even year; in an odd year, the Legislature (the House of
Delegates every odd year, the Senate of Virginia every four, 2027's next) and the statewide
offices (Governor, Lieutenant Governor and Attorney General, 2029's next). A page whose heading
gives only the year ("2023 November General Election - General Assembly Candidates") is that
year's general election. Each page is streamed to disk and kept as its filings alone, so the
cache and the bundle never hold the candidates' emails, phones or addresses. Local offices
(boards of supervisors, city councils, sheriffs, school boards) aren't read: Virginia doesn't
print their candidates' parties (Va. Code 24.2-613), and their districts aren't any the Census
knows.

Virginia's key dates, for its general election (Va. Code 24.2-101: the Tuesday after the first
Monday of November, every year): registration records close for the ten days before (24.2-416), so
the last day is the eleventh day before, then voters register in person at the general registrar's
office or the polling place through Election Day and vote a provisional ballot (24.2-420.1); early
voting in person runs from the forty-fifth day before (24.2-701.1(A); the Department of Elections
opens it on the Friday, the forty-sixth day) through 5 p.m. on the Saturday before; any voter can
vote absentee by mail, the application reaching the general registrar by 5 p.m. on the eleventh day
before (24.2-701(C)), and the ballot must be postmarked by Election Day and reach the registrar by
noon on the third day after (24.2-709(B)); polls are open 6 a.m. to 7 p.m. (24.2-603).
"""

from __future__ import annotations

import datetime as dt
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

from ..http_cache import RequestSpec
from . import (
    MONTH_DAY_YEAR, Filing, Office, Rows, StateList, decoded, legislator, party, party_rank, require,
    statewide, us_house, us_senate,
)
from .dates import Counts, Guide, first_tuesday_after_first_monday

PAGE = "https://www.elections.virginia.gov/casting-a-ballot/candidate-list/"
# The columns read, by their headings: a list has the office, district, party and name, and may have the incumbent.
COLUMNS = {
    "office": ("Office Title",), "district": ("District",),
    "party": ("Candidate Party", "Political Party Descr"), "name": ("Candidate Name",), "incumbent": ("Incumbent",),
}
# Of a list with a reach in a year it's all up (a special election fills one seat): one can go without a candidate.
MINIMUM = {"cd": 11, "sd": 35, "hd": 90}
STATEWIDE = ("Governor", "Lieutenant Governor", "Attorney General")
_TITLE = re.compile(r"<title>[^<]*Candidates &(?:amp;)? Referendums", re.I)
_LINK = re.compile(r"""href=["']([^"']*/candidate-list/november-(\d{1,2})-(\d{4})-gen-elect-([a-z0-9-]+?)/?)["']""",
                   re.I)
_HEADING = re.compile(rf"<h1[^>]*>\s*(?:({MONTH_DAY_YEAR})|(\d{{4}}) November General Election)", re.I)
_NUMBER = re.compile(r"(\d+)(?:st|nd|rd|th)?(?: District)?", re.I)


def links(text: str) -> dict[str, Any]:
    """The Candidates & Referendums page as kept: each general election's lists, by its ISO day
    and what the list covers ({"2026-11-03": {"federal-offices": url}}); ValueError for a page
    that isn't it."""
    if not _TITLE.search(text):
        raise ValueError("not the Department of Elections' Candidates & Referendums page")
    found: dict[str, dict[str, str]] = {}
    for href, day, year, kind in _LINK.findall(text):
        try:
            when = dt.date(int(year), 11, int(day)).isoformat()
        except ValueError:
            continue
        found.setdefault(when, {}).setdefault(kind.lower(), urljoin(PAGE, unescape(href)))
    return {"links": found}


def read(kinds: dict[str, str]) -> list[str]:
    """Which of an election's lists to read: the one of all offices, or without it every list
    but the local offices'."""
    whole = [url for kind, url in kinds.items() if kind.startswith("all-")]
    return whole[:1] or [url for kind, url in kinds.items() if "local" not in kind]


def _race(office: str, district: str) -> tuple[Office, int] | None:
    """The race an office title and district name, and where it comes on the ballot; None for a
    local office."""
    number = _NUMBER.fullmatch(district.strip())
    if office == "Member, United States Senate":
        return us_senate("VA"), 0
    if office in STATEWIDE:
        return statewide(office), 20 + STATEWIDE.index(office)
    if not number:
        return None
    n = int(number.group(1))
    if office == "Member, House of Representatives":
        return us_house("VA", n), n
    if office == "Member, Senate of Virginia":
        return legislator("sd", n), 100 + n
    if office == "Member, House of Delegates":
        return legislator("hd", n, office=f"House of Delegates District {n}"), 200 + n
    return None


def parse_page(text: str) -> list[Filing]:
    """Every candidate for Congress, the statewide offices and the Legislature on one list, each
    once (the list of all offices repeats them per locality); ValueError for a page that isn't a
    list (no election day or no column headings) or isn't all of one (MINIMUM)."""
    heading = _HEADING.search(text)
    reader = Rows(cells=("td", "th"))
    reader.feed(text)
    header = next((i for i, row in enumerate(reader.rows) if "Office Title" in row and "Candidate Name" in row), None)
    if not heading or header is None:
        raise ValueError("no election date or column headings")
    day = (dt.datetime.strptime(heading.group(1), "%B %d, %Y").date() if heading.group(1)
           else first_tuesday_after_first_monday(int(heading.group(2)), 11)).isoformat()
    names = reader.rows[header]
    at = {key: next((names.index(n) for n in options if n in names), None) for key, options in COLUMNS.items()}
    if any(at[key] is None for key in ("office", "district", "party", "name")):
        raise ValueError(f"not the columns it reads: {names}")
    filings, seen, listed = [], set(), {}
    for row in reader.rows[header + 1:]:
        if len(row) < len(names) or any("withdr" in cell.lower() for cell in row):
            continue
        found = _race(row[at["office"]], row[at["district"]])
        name = row[at["name"]]
        if found is None or not name:
            continue
        race, place = found
        if (race.office_id, name) in seen:
            continue
        seen.add((race.office_id, name))
        listed[race.office_id] = listed.get(race.office_id, 0) + 1
        code, party_name = party(row[at["party"]])
        incumbent = at["incumbent"] is not None and row[at["incumbent"]].strip().lower() == "yes"
        filings.append(race.filing(
            day=day, name=name, party=code, party_name=party_name, incumbent=incumbent,
            order=place * 1_000 + party_rank(code, party_name) * 100 + listed[race.office_id],
        ))
    year = int(day[:4])
    regular = {"cd": year % 2 == 0, "hd": year % 2 == 1, "sd": year % 4 == 3}
    return require(filings, {reach: least for reach, least in MINIMUM.items()
                             if regular[reach] and any(f.reach == reach for f in filings)})


class VaList(StateList):
    state = "VA"
    source = "state_va"
    label = "Virginia Department of Elections"
    page = PAGE
    description = ("Virginia's official lists of the candidates for Congress, Governor and the other statewide offices, "
                   "and the General Assembly, from its Department of Elections.")
    max_bytes = 16 << 20
    index_key = "links"
    scope_note = ("Your county's or city's races (board of supervisors, city council, sheriff, school board and the "
                  "like) and any questions aren't shown: your general registrar's sample ballot has them.")

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", PAGE)

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        text = decoded(raw)
        return None if _HEADING.search(text) else links(text)

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        urls = read(index["links"].get(day.isoformat(), {}))
        return [RequestSpec("GET", url) for url in urls] or None

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        return parse_page(decoded(raw) if isinstance(raw, bytes) else raw if isinstance(raw, str) else "")


GUIDE = Guide(
    name="Virginia",
    source="Virginia Department of Elections",
    url="https://www.elections.virginia.gov/",
    computed=True,
    registration_url="https://vote.elections.virginia.gov/Registration/Eligibility",
    mail_url="https://vote.elections.virginia.gov/VoterInformation",
    register="The last day to register to vote in {election} in Virginia. After it, you can still register in "
             "person at your general registrar's office or your polling place, through Election Day, and vote a "
             "provisional ballot.",
    mail_summary="Absentee ballot application due",
    mail="If you vote absentee by mail in {election}, your application must reach your general registrar by 5 p.m. "
         "today. Your ballot must be postmarked by Election Day and reach the registrar by noon on the third day "
         "after. Any voter can vote absentee; how to apply:",
    early_where="Your general registrar's office, and any satellite sites your locality opens; the registrar lists "
                "the places and hours. Early voting ends at 5 p.m. on the Saturday before Election Day.",
    credit="Dates worked out from the Code of Virginia; more from the Virginia Department of Elections",
    poll_hours="6 a.m. – 7 p.m.",
    check_url="https://vote.elections.virginia.gov/VoterInformation",
    check_hint="Virginia's Citizen Portal (Department of Elections): your registration and your polling place",
    where_url="https://vote.elections.virginia.gov/VoterInformation",
    where_hint="The Citizen Portal: your polling place; your general registrar lists its early voting places",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote absentee by mail, no reason needed. Your ballot must be postmarked "
                     "by Election Day and reach your general registrar by noon on the third day after.",
    mail_deadline="Your application must reach your general registrar by 5 p.m. on ",
    local_office="Your general registrar",
    late_registration="After that, register in person at your general registrar's office or polling place through "
                      "Election Day, and vote a provisional ballot",
)
RULE = Counts(11, 11, 46, 3, every_year=True).rule("VA")
