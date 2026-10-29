"""Indiana (``in`` is a Python keyword, hence the underscore): the Election Division's general
election candidate list, a spreadsheet (.xlsx) linked from its home page as "2026 General Election
Candidate List" under a name that carries the time it was made
("Candidate_List_Abbreviated_20260922_011251PM.xlsx"), so it's found on that page by its link, never
by a name worked out ahead. A plain script gets a 200 from both.

The sheet's heading names the election ("2026 GENERAL ELECTION - 11/3/2026 11:59:00 PM"), then
each office category ("OFFICE CATEGORY:", "STATE SENATOR") is followed by its candidates, a row
each: the name on the ballot, the party ("Republican", "( )" for none, "Write-In (Independent)" for
a declared write-in), the office's title, which holds the district ("State Senator, District 01",
"United States Representative, Eighth District", "Allen County Sheriff"), and the day they filed.
It has no incumbent, withdrawn or contact columns; the cache and the bundle keep its filings alone.

Placed: Congress, the statewide offices, the State Senate and State House, the county offices
elected countywide (auditor, recorder, treasurer, sheriff, coroner, surveyor, assessor and the
circuit court clerk), the prosecuting attorney of the county (or counties: "Dearborn & Ohio") of
each judicial circuit, and the circuit and superior courts' judges, each court one county's. County
commissioners and council members are named by district, so they're unconfirmed. Townships, cities,
towns, school boards, small claims courts and special districts are left out with a ballot note. An
office category it doesn't know is refused, so a new one is seen rather than dropped.

Indiana's key dates, for its general election (the first Tuesday after the first Monday in
November of an even year, IC 3-10-2-1), checked against the Election Division's absentee voting
page on 2026-10-29: registration closes on the 29th day before, in person, by mail or online by
11:59 p.m. (IC 3-7-13-10, -11; IC 3-7-26.7-5), and there's no registering after it; an application
to vote absentee by mail must be received by 11:59 p.m. on the 12th day before (IC 3-11-4-3(a)(4)),
and only a voter with a reason the law allows can vote by mail: away from the county all 12 hours
the polls are open, disabled, 65 or older, working all 12 hours, confined by illness or caring for
someone who is, and the like (IC 3-11-10-24); the ballot must reach the county election board by
6 p.m. on Election Day (IC 3-11.5-4-3). Anyone can vote absentee in person at the county's office
from the 28th day before until noon on the day before (IC 3-11-10-26). Polls are open 6 a.m. to
6 p.m. local time (IC 3-11-8-8), in the Eastern and Central counties alike.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from typing import Any
from urllib.parse import urljoin

from ..http_cache import RequestSpec
from . import _ORDINALS, Filing, Office, StateList, legislator, party, require, sheet_rows, statewide, us_house, us_senate
from .dates import Counts, Guide, only_if

PAGE = "https://www.in.gov/sos/elections/"
COLUMNS = ("BALLOT NAME", "PARTY", "OFFICE TITLE", "FILED DATE")
MINIMUM = {"cd": 9, "sd": 20, "hd": 90}  # nearly every district up: one can go without a candidate
STATEWIDE = {
    "SECRETARY OF STATE", "STATE COMPTROLLER (AUDITOR OF STATE)", "TREASURER OF STATE", "ATTORNEY GENERAL",
    "GOVERNOR", "GOVERNOR AND LIEUTENANT GOVERNOR", "SUPERINTENDENT OF PUBLIC INSTRUCTION",
}
COUNTYWIDE = {
    "CLERK OF THE CIRCUIT COURT", "COUNTY AUDITOR", "COUNTY RECORDER", "COUNTY TREASURER", "COUNTY SHERIFF",
    "COUNTY CORONER", "COUNTY SURVEYOR", "COUNTY ASSESSOR",
}
_TITLE = re.compile(r"<title>\s*Election Division\b", re.I)
_ANCHOR = re.compile(r"<a\s[^>]*href=\"([^\"]+\.xlsx)\"[^>]*>(.*?)</a>", re.I | re.S)
_LIST = re.compile(r"(\d{4}) (?:Municipal )?General Election Candidate List\b", re.I)
_ELECTION = re.compile(r"GENERAL ELECTION - (\d{1,2}/\d{1,2}/\d{4})", re.I)
_LOCAL = re.compile(r"TOWNSHIP|\bTOWN\b|\bCITY\b|MAYOR|SCHOOL|SMALL CLAIMS|^OTHER$")
_CONGRESS = re.compile(r"United States Representative, (\w+) District", re.I)
_LEGISLATURE = re.compile(r"State (Senator|Representative), District (\d+)", re.I)
_COUNTY = re.compile(r"(.+?) County (.+)", re.I)
_PART = re.compile(r"(.+?) County (Commissioner|Council)\b.*", re.I)
_PROSECUTOR = re.compile(r"Prosecuting Attorney of (.+?) Count(?:y|ies), (\d+)", re.I)  # "Judical" too
_COURT = re.compile(r"Judge of the (.+?) (Circuit|Superior) Court\b", re.I)
_WRITE_IN = re.compile(r"Write-In \((.*)\)", re.I)
_NO_PARTY = {"( )", "NON PARTISAN", "OTHER"}


def links(text: str) -> dict[str, Any]:
    """The Election Division's home page as kept: its links to each year's general election
    candidate list; ValueError for a page that isn't it."""
    if not _TITLE.search(text):
        raise ValueError("not the Election Division's home page")
    found: dict[str, str] = {}
    for href, label in _ANCHOR.findall(text):
        year = _LIST.search(" ".join(html.unescape(re.sub(r"<[^>]+>", " ", label)).split()))
        if year:
            found.setdefault(year.group(1), urljoin(PAGE, html.unescape(href)))
    return {"links": found}


def _counties(text: str) -> tuple[str, ...]:
    """"Dearborn & Ohio" -> ("DEARBORN", "OHIO")."""
    return tuple(part.strip().upper() for part in re.split(r"\s*(?:&|\band\b)\s*", text) if part.strip())


def _race(category: str, title: str) -> Office | None:
    """The race of a row's office category and title; None for an office left out. ValueError for
    a category it doesn't know, or a title it can't read."""
    upper = title.upper()
    if category == "PRESIDENT" or _LOCAL.search(category):
        return None
    if category in ("US SENATOR", "UNITED STATES SENATOR"):
        return us_senate("IN", upper)
    if category == "US REPRESENTATIVE":
        found = _CONGRESS.fullmatch(title)
        number = _ORDINALS.get(found.group(1).upper()) if found else None
        if number is None:
            raise ValueError(f"a district it can't read: {title}")
        return us_house("IN", number, upper)
    if category in ("STATE SENATOR", "STATE REPRESENTATIVE"):
        found = _LEGISLATURE.fullmatch(title)
        if not found:
            raise ValueError(f"a district it can't read: {title}")
        return legislator("sd" if category == "STATE SENATOR" else "hd", int(found.group(2)), upper)
    if category in STATEWIDE:
        return statewide(title, upper)
    if category in COUNTYWIDE:
        found = _COUNTY.fullmatch(title)
        if not found:
            raise ValueError(f"a county it can't read: {title}")
        return Office(upper, title, category, "county", "county", counties=(found.group(1).upper(),))
    if category in ("COUNTY COMMISSIONER", "COUNTY COUNCIL MEMBER"):
        found = _PART.fullmatch(title)
        if not found:
            raise ValueError(f"a county it can't read: {title}")
        whole = "AT LARGE" in upper
        district = None if whole else re.sub(r"(?i)^.*?,\s*(?:District\s*)?", "", title) or None
        return Office(upper, title, category, "county", "county" if whole else "part_county", district,
                      counties=(found.group(1).upper(),))
    if category == "PROSECUTING ATTORNEY":
        found = _PROSECUTOR.match(title)
        if not found:
            raise ValueError(f"a circuit it can't read: {title}")
        return Office(upper, title, category, "county", "county", found.group(2), counties=_counties(found.group(1)))
    if category in ("JUDGE, CIRCUIT COURT", "JUDGE, SUPERIOR COURT"):
        found = _COURT.match(title)
        if not found:
            raise ValueError(f"a court it can't read: {title}")
        return Office(upper, title, f"{found.group(2).upper()} COURT JUDGE", "judicial", "county",
                      counties=_counties(found.group(1)))
    raise ValueError(f"an office it doesn't know: {category}")


def parse_rows(rows: list[list[str]]) -> list[Filing]:
    """Every candidate the list places; ValueError for a sheet that isn't the list (no election in
    its heading, its columns, an office it doesn't know, a row without a name) or isn't all of it
    (MINIMUM, in a year with Congress on the ballot)."""
    heading = " ".join(cell for row in rows[:6] for cell in row)
    election = _ELECTION.search(heading)
    if not election or "Candidate List" not in heading:
        raise ValueError("not the general election's candidate list")
    day = dt.datetime.strptime(election.group(1), "%m/%d/%Y").date().isoformat()
    filings: list[Filing] = []
    category = None
    for index, row in enumerate(rows):
        cells = [*row, *[""] * (len(COLUMNS) - len(row))]
        if cells[0] == "OFFICE CATEGORY:":
            category = " ".join(cells[1].upper().split())
            continue
        if tuple(cells[:len(COLUMNS)]) == COLUMNS or category is None or not any(cells[:3]):
            continue
        name, label, title = cells[0], cells[1], cells[2]
        if not name or not title:
            raise ValueError(f"a row without a name or office: {cells[:3]}")
        race = _race(category, title)
        if race is None:
            continue
        write_in = _WRITE_IN.fullmatch(label)
        label = write_in.group(1) if write_in else label
        code, party_name = (None, None) if label.upper() in _NO_PARTY else party(label)
        filings.append(race.filing(day=day, name=name, party=code, party_name=party_name, write_in=bool(write_in),
                                   order=index + (100_000 if write_in else 0)))
    if category is None:
        raise ValueError("not the list of general election candidates")
    return require(filings, MINIMUM) if any(f.group == "federal" for f in filings) else filings


class InList(StateList):
    state = "IN"
    source = "state_in"
    label = "Indiana Election Division"
    page = PAGE
    description = ("Indiana's official list of the candidates for Congress, its statewide offices, the General "
                   "Assembly, its county offices and courts, from its Election Division.")
    max_bytes = 8 << 20
    index_key = "links"
    scope_note = ("Township, city, town, school board and small claims court races, any judges standing for retention "
                  "and any questions aren't shown: your county election board's sample ballot has them.")

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", PAGE)

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        return None if raw.startswith(b"PK") else links(raw.decode("utf-8", "replace"))

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        url = index["links"].get(str(day.year))
        return [RequestSpec("GET", url)] if url else None

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, bytes):
            raise ValueError("not a spreadsheet")
        return parse_rows(sheet_rows(raw)[1])


GUIDE = Guide(
    name="Indiana",
    source="Indiana Election Division",
    url=PAGE,
    computed=True,
    registration_url="https://indianavoters.in.gov/",
    mail_url="https://indianavoters.in.gov/",
    register="The last day to register to vote in {election} in Indiana, in person, by mail or online by 11:59 p.m. "
             "There's no registering after it.",
    mail_summary="Absentee ballot application due",
    mail="If you vote absentee by mail in {election}, your application must reach your county election board by "
         "11:59 p.m. today: received, not postmarked. Your ballot must reach the board by 6 p.m. on Election Day. Who "
         "can vote by mail, and how to apply:",
    early_where="Your county election board's office, and any other sites your county opens: vote absentee in person "
                "there until noon on the day before Election Day, and on the two Saturdays before. Your county sets the "
                "hours.",
    credit="Dates worked out from Indiana's election law; more from the Indiana Election Division",
    poll_hours="6 a.m. – 6 p.m.",
    local_time=True,
    check_url="https://indianavoters.in.gov/",
    check_hint="Indiana Voters (Indiana Election Division): your registration, your polling place and your absentee "
               "ballot",
    where_url="https://indianavoters.in.gov/",
    where_hint="Indiana Voters: your polling place, and your county's places for voting early",
    mail_label="How to apply",
    mail_eligibility=only_if("you're 65 or older", "disabled", "away from your county all 12 hours the polls are open",
                             "working all 12 hours the polls are open",
                             "confined by illness or injury, or caring for someone who is",
                             "another reason Indiana's law allows")
    + " Your ballot must reach your county election board by 6 p.m. on Election Day.",
    mail_deadline="Your application must reach your county election board by 11:59 p.m. on ",
)
RULE = Counts(29, 12, 28, 1).rule("IN")
