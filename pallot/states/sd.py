"""South Dakota: the Secretary of State's candidate list (vip.sdsos.gov), its candidatelist.aspx grid
(grid.py). The grid has no election dropdown, and the page without an election sends you away, so
its id comes from the Secretary of State's Upcoming Elections page, whose menu links the year's
list under "2026 Election Information" ("candidatelist.aspx?eid=774"). The list is the grid's
Export to CSV, a button that posts the page back for that election through ``__doPostBack``, so
the postback names it as its ``__EVENTTARGET``. A plain script gets a 200.

A row per candidate: the contest ("State Representative"), the name as the ballot prints it (a
ticket's two joined by "&", a withdrawn candidate's ending "(Withdrawn 8/4/2026 12:00:00 AM)",
left out), the party (REP, DEM, LIB, IND, NON for none), the filing date, the district or county
("District 26A", "Mellette", empty for a statewide race), the ballot order and the candidate's
mailing address. It has no status, incumbent or write-in column. Only the name, office, district
and party are kept: the list is kept as its filings, so the cache and the bundle hold nothing else.

Its races in 2026 are the U.S. Senate, the U.S. House (one seat, at large), Governor and
Lieutenant Governor (one ticket), the other statewide offices, the Public Utilities Commission
and the whole Legislature: each of its 35 districts elects one Senator and two Representatives,
but for House districts 26 and 28, each split into two districts of one Representative (26A and
26B, 28A and 28B, as the Census names them too). The county offices, conservation and water
development districts and city races on the list are left out with a ballot note.

South Dakota's key dates, for its general election (the Tuesday after the first Monday of
November in an even year, SDCL 12-2-2), checked on 2026-10-29 against the South Dakota Codified
Laws (sdlegislature.gov) and the Secretary of State's 2026 election calendar: registration must
reach the county auditor by 5 p.m. local time 15 days before (12-4-5), with no registering after
it; any voter can vote absentee, no reason needed (12-19-1), from 46 days before (12-19-1.2), in
person at the county auditor's office or by mail; a voter can apply in person until 5 p.m. the day
before (12-19-2.1), the calendar's last day to ask for an absentee ballot, and a ballot that
reaches the polling place or the auditor after the polls close isn't counted (12-19-12). Polls are
open 7 a.m. to 7 p.m. local time (12-2-3), the same hours in its Central and Mountain halves.
2026: Oct 19, Nov 2, Sep 18 – Nov 2, as on the calendar.
"""

from __future__ import annotations

import dataclasses
import html
import re
from typing import Any

from . import Office, decoded, legislator, statewide, us_house, us_senate
from .dates import Counts, Guide
from .grid import GridList, GridRow

INDEX = "https://sdsos.gov/elections-voting/upcoming-elections/default.aspx"
PAGE = "https://vip.sdsos.gov/candidatelist.aspx"
VIP = "https://vip.sdsos.gov/VIPLogin.aspx"
EXPORT = {"__EVENTTARGET": "ctl00$MainContent$grdCandidates$ctl00$ctl02$ctl00$ExportToCsvButton",
          "__EVENTARGUMENT": ""}
STATEWIDE = ("Secretary of State", "Attorney General", "State Auditor", "State Treasurer",
             "Commissioner of School and Public Lands", "Public Utilities Commissioner")
SINGLE = frozenset({"26A", "26B", "28A", "28B"})  # the House districts of one Representative
_LINK = re.compile(r"""candidatelist\.aspx\?eid=(\d+)""", re.I)
_YEAR = re.compile(r"\b(\d{4}) Election Information\b", re.I)
_DISTRICT = re.compile(r"District 0*(\d+[AB]?)", re.I)
_WITHDRAWN = re.compile(r"\(Withdrawn\b", re.I)


def _district(row: GridRow) -> str:
    found = _DISTRICT.fullmatch(row.district.strip())
    if not found:
        raise ValueError(f"no district for {row.race}: {row.district!r}")
    return found.group(1).upper()


class SdList(GridList):
    state = "SD"
    source = "state_sd"
    label = "South Dakota Secretary of State"
    page = PAGE
    index = INDEX
    election = "eid"
    form = EXPORT
    parties = {"IND": "Independent"}
    minimum = {"cd": 1, "sd": 30, "hd": 35}  # nearly every district: all of them are up
    description = ("South Dakota's official list of the candidates for Congress, the statewide offices and the "
                   "Legislature, from its Secretary of State.")
    scope_note = ("Your county's offices, its conservation and water development districts, city races and any ballot "
                  "questions aren't shown: your county auditor's sample ballot has them.")

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        """The Upcoming Elections page's list for each year: the grid's id in each link to it, by
        the year of the "2026 Election Information" its menu lists it under; None for the CSV;
        ValueError for a page without a link to it."""
        text = decoded(raw)
        if not text.lstrip().startswith("<"):
            return None
        found: dict[str, str] = {}
        links = list(_LINK.finditer(text))
        if not links:
            raise ValueError("no link to a candidate list")
        for link in links:
            before = html.unescape(re.sub(r"<[^>]+>", " ", text[:link.start()]))
            years = _YEAR.findall(before)
            if years:
                found.setdefault(years[-1], link.group(1))
        return {"elections": found}

    @classmethod
    def office(cls, row: GridRow) -> Office | None:
        """The race of a row; None for a withdrawn candidate's and a local office's."""
        if _WITHDRAWN.search(row.name):
            return None
        race = " ".join(row.race.split())
        if race == "United States Senator":
            return us_senate("SD")
        if race == "United States Representative":
            return us_house("SD", 0, "US HOUSE")
        if race == "Governor and Lieutenant Governor":
            return statewide(race, "GOVERNOR")
        if race in STATEWIDE:
            return statewide(race)
        if race == "State Senator":
            return legislator("sd", _district(row))
        if race == "State Representative":
            district = _district(row)
            return dataclasses.replace(legislator("hd", district), seats=1 if district in SINGLE else 2)
        return None

    @classmethod
    def named(cls, name: str) -> str:
        """A ticket's two names joined by "and", as the ballot shows them."""
        return " and ".join(part.strip() for part in name.split("&"))


GUIDE = Guide(
    name="South Dakota",
    source="South Dakota Secretary of State",
    url="https://sdsos.gov/elections-voting/default.aspx",
    computed=True,
    registration_url="https://sdsos.gov/elections-voting/voting/register-to-vote/default.aspx",
    mail_url="https://sdsos.gov/elections-voting/voting/absentee-voting.aspx",
    register="The last day to register to vote in {election} in South Dakota: your form must reach your county "
             "auditor by 5 p.m. local time today. There's no registering after it.",
    mail_summary="Last day to ask for an absentee ballot",
    mail="If you vote absentee in {election}, today is the last day to ask for your ballot: your request must reach "
         "your county auditor by 5 p.m., and you can still apply and vote in person at the auditor's office until "
         "then. Your ballot must reach the auditor, or your polling place, before the polls close on Election Day; one "
         "that arrives later isn't counted. Any voter can vote absentee; how to apply:",
    early_where="Your county auditor's office: vote absentee in person there from 46 days before Election Day through "
                "5 p.m. the day before.",
    credit="Dates worked out from South Dakota's election law; more from the South Dakota Secretary of State",
    poll_hours="7 a.m. – 7 p.m.",
    check_url=VIP,
    check_hint="Voter Information Portal (South Dakota Secretary of State): your registration, your polling place and "
               "your absentee ballot",
    where_url=VIP,
    where_hint="Voter Information Portal (South Dakota Secretary of State): your polling place and your county auditor",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote absentee, no reason needed. Your ballot must reach your county "
                     "auditor, or your polling place, before the polls close on Election Day.",
    mail_deadline="Your request must reach your county auditor by 5 p.m. on ",
    local_office="Your county auditor",
    local_time=True,
)
RULE = Counts(15, 1, 46, 1).rule("SD")
