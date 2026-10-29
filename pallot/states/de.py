"""Delaware: the Department of Elections' general election candidate list, a spreadsheet (.xlsx)
named for its year since 2008 (candidates/candidatelist/genl_fcddt_2026.xlsx), and its declared
write-in candidates beside it (genl_wcddt_2026.xlsx), so both are asked by their names, with no
page to find them on first. A plain script gets a 200 from both.

A row per candidate: the county ("Statewide" for a statewide race), the office, which holds the
district ("State Senator District 1", "New Castle County Council District 6"), the date withdrawn,
the name on the ballot, the party ("Democratic", "Republican", "Ind Pty of DE"; the write-ins' sheet
has no party column), the name in parts, the date filed, the candidate's addresses, website, emails
and phones, and the status: "Qualified", or "Withdrawn" (and a write-in's "Provisional"), left out.
Neither sheet names the election, so a filing is dated by the year it was asked for. Only the
name, office, district, party and whether it's a write-in are kept: each sheet is kept as its
filings, so the cache and the bundle hold nothing else.

Its races in 2026 are the U.S. Senate, the U.S. House (one seat, at large), Attorney General,
Auditor of Accounts and State Treasurer, the State Senate's seats up (11 of 21) and the whole
State House (41). Its three counties' offices elected countywide (sheriff, recorder of deeds,
register of wills, Kent's Levy Court at large) are placed by county; a council or Levy Court seat
elected by district is unconfirmed. An office it doesn't know is refused, so a new one is seen
rather than dropped.

Delaware's key dates, for its general election (the Tuesday after the first Monday of November in
an even year, Del. Const. art. V §1), checked on 2026-10-29 against the Delaware Code (Title 15,
delcode.delaware.gov) and the Department's 2026 election calendar: registration closes at
11:59 p.m. on the fourth Saturday before, the 24th day (§2036 as the Department applies it: the
Delaware Supreme Court struck down same-day registration and no-excuse voting by mail in Albence
v. Higgin, 2022, so the Code's Election Day registration isn't in force), and there's no
registering after it; voting absentee needs one of the reasons the law gives (§5502: public
service or living abroad, the armed forces, work, caring for someone sick or disabled, being sick
or disabled, away on vacation, one's religion), since a constitutional amendment for voting by mail
without a reason has passed only its first leg (2026); an absentee ballot can be asked for until
noon on the day before (§5503(a)) and must reach the county's Department office before the polls
close (§5508(b)). Anyone can vote early in person, on at least 10 days through the Saturday and
Sunday before (§5402): the Department's 2026 calendar opens it the 12th day before and ends it the
2nd, with no voting on Sunday, October 25. Polls are open 7 a.m. to 8 p.m. (§4931, §4947). 2026:
Oct 10, Nov 2, Oct 22 – Nov 1, as on the calendar.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import re
from typing import Any

from ..http_cache import RequestSpec
from . import Filing, Office, StateList, filings_json, legislator, party, require, sheet_rows, statewide, us_house, us_senate
from .dates import Counts, Guide, only_if

SITE = "https://elections.delaware.gov"
LISTS = f"{SITE}/candidates/candidatelist/"
PAGE = f"{LISTS}genl_fcddt_2026.html"
COLUMNS = ("Office", "BallotName", "DisplayedStatus")  # read by name: the write-ins' sheet has no Party
MINIMUM = {"cd": 1, "sd": 9, "hd": 38}  # nearly every district up: one can go without a candidate
STATEWIDE = frozenset({"Governor", "Lieutenant Governor", "Insurance Commissioner", "Attorney General",
                       "Auditor of Accounts", "State Treasurer"})
PARTIES = {"IND PTY OF DE": "Independent Party of Delaware"}
_LEGISLATURE = re.compile(r"State (Senator|Representative) District (\d+)", re.I)
_COUNTY = re.compile(r"(New Castle|Kent|Sussex) County (.+)", re.I)
_PART = re.compile(r"(.+?) District (\d+)", re.I)
_NO_PARTY = {"NON-PARTISAN", "NONPARTISAN", "NON PARTISAN", "UNAFFILIATED"}


def _race(office: str) -> Office:
    """The race of a row's office. ValueError for an office it doesn't know."""
    if office == "U.S. Senator":
        return us_senate("DE")
    if office == "Representative in Congress":
        return us_house("DE", 0, "US HOUSE")
    if office in STATEWIDE:
        return statewide(office)
    found = _LEGISLATURE.fullmatch(office)
    if found:
        return legislator("sd" if found.group(1).lower() == "senator" else "hd", int(found.group(2)))
    found = _COUNTY.fullmatch(office)
    if found:
        county, title = found.group(1).upper(), found.group(2)
        part = _PART.fullmatch(title)
        title = title.removesuffix(" At-Large")
        family = f"COUNTY {(part.group(1) if part else title).upper()}"
        if part:
            return Office(office.upper(), office, family, "county", "part_county", part.group(2), counties=(county,))
        return Office(office.upper(), office, family, "county", "county", counties=(county,))
    raise ValueError(f"an office it doesn't know: {office}")


def parse_rows(rows: list[list[str]]) -> list[Filing]:
    """Every qualified candidate on a sheet, the general election's list or its write-ins' (no
    Party column), undated (DeList.on); ValueError for a sheet that isn't one (its columns, an
    office it doesn't know, a row without a name) or a list short of its districts (MINIMUM, in a
    year with Congress on the ballot)."""
    heading = rows[0] if rows else []
    if not all(column in heading for column in COLUMNS):
        raise ValueError("not the list of general election candidates")
    at = {column: heading.index(column) for column in (*COLUMNS, "Party") if column in heading}
    write_in = "Party" not in at
    filings = []
    for index, row in enumerate(rows[1:]):
        cells = [*row, *[""] * (len(heading) - len(row))]
        if not any(cells):
            continue
        office, name = cells[at["Office"]], cells[at["BallotName"]]
        if not office or not name:
            raise ValueError(f"a row without a name or office: {cells[:4]}")
        race = _race(office)
        if cells[at["DisplayedStatus"]] != "Qualified":
            continue
        label = "" if write_in else cells[at["Party"]]
        code, party_name = (None, None) if label.upper() in _NO_PARTY else party(label, PARTIES)
        filings.append(race.filing(day="", name=name, party=code, party_name=party_name, write_in=write_in,
                                   order=index + (100_000 if write_in else 0)))
    if write_in or not any(f.group == "federal" for f in filings):
        return filings
    return require(filings, MINIMUM)


class DeList(StateList):
    state = "DE"
    source = "state_de"
    label = "Delaware Department of Elections"
    page = PAGE
    description = ("Delaware's official list of the candidates for Congress, its statewide offices, the General "
                   "Assembly and its county offices, from its Department of Elections.")
    max_bytes = 4 << 20
    index_key = "links"
    scope_note = ("County council and Levy Court seats elected by district, school board and town races, and any "
                  "questions aren't shown: your county's Department of Elections office has your sample ballot.")

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", f"{LISTS}genl_fcddt_{day.year}.xlsx")

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        """Either sheet as kept: its filings beside an empty index, so a year whose write-ins are
        all withdrawn still reads as an answer."""
        return {**filings_json(cls.parse(raw)), "links": {}}

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        """The year's write-ins, named as the list is."""
        return [RequestSpec("GET", f"{LISTS}genl_wcddt_{day.year}.xlsx")]

    def on(self, value: Any, day: dt.date) -> list[Filing]:
        """The filings in a stored answer, dated ``day``: the sheet asked for is that year's."""
        return [dataclasses.replace(f, day=day.isoformat()) if not f.day else f
                for f in self.read(value) if not f.day or f.day == day.isoformat()]

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, bytes):
            raise ValueError("not a spreadsheet")
        return parse_rows(sheet_rows(raw)[1])


GUIDE = Guide(
    name="Delaware",
    source="Delaware Department of Elections",
    url=SITE,
    computed=True,
    registration_url="https://ivote.de.gov/",
    mail_url="https://ivote.de.gov/",
    register="The last day to register to vote in {election} in Delaware, in person, by mail or online by 11:59 p.m. "
             "There's no registering after it.",
    mail_summary="Absentee ballot request due",
    mail="If you vote absentee in {election}, ask your county's Department of Elections office for your ballot by noon "
         "today. Your ballot must reach that office by 8 p.m. on Election Day; one that arrives later isn't counted. "
         "Who can vote absentee, and how to ask:",
    early_where="Your county's early voting sites, open to every voter, no reason needed: the Department of Elections "
                "lists them and their hours.",
    credit="Dates worked out from Delaware's election law; more from the Delaware Department of Elections",
    poll_hours="7 a.m. – 8 p.m.",
    check_url="https://ivote.de.gov/",
    check_hint="iVote (Delaware Department of Elections): your registration, your polling place and your absentee ballot",
    where_url="https://ivote.de.gov/",
    where_hint="iVote (Delaware Department of Elections): your polling place and your county's early voting sites",
    mail_label="How to ask",
    mail_eligibility=only_if("you're sick or disabled", "away on vacation",
                             "kept away by your work or by caring for someone sick or disabled",
                             "in the armed forces, in public service or living abroad", "kept away by your religion")
    + " Your ballot must reach your county's Department of Elections office by 8 p.m. on Election Day.",
    mail_deadline="Ask your county's Department of Elections office by noon on ",
)
RULE = Counts(24, 1, 12, 2).rule("DE")
