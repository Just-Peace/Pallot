"""North Dakota: the Secretary of State's Contest/Candidate List (vip.sos.nd.gov), its candidatelist.aspx
grid (grid.py). The grid has no election dropdown, so its id comes from the Secretary of State's
Candidate page, whose link to it says "View candidates and contests on the ballot for the 2026
General Election" ("candidatelist.aspx?eid=348"). The page for that election shows only its
filters; a postback of its Search button with every filter on "All" answers the whole list as one
HTML table (``table``, no pager). Its Export List button works only from that answer's own form,
a second postback, so the table is read instead. A plain script gets a 200.

A row per candidate: the contest ("State Representative"), the term's length, the district
("District 03", empty for a statewide race), the county ("STATE" for a race beyond one), the name
as the ballot prints it, the party (Republican, Democratic-NPL, "independent nomination",
Nonpartisan), and the candidate's mailing address, email, website and phone. It has no status,
incumbent or write-in column. Only the name, office, district and party are kept: the list is kept
as its filings, so the cache and the bundle hold nothing else.

Its races in 2026 are the U.S. House (one seat, at large), the statewide offices up, and the
Legislature: each of its 47 districts elects one Senator and two Representatives for four years,
the odd-numbered districts in 2026 (NDCC 54-03-01.15), plus an unexpired House seat in 20, 26 and 42
(one Representative each). District 9 is one district again since the court order of 2024-01-08,
as the Census's 2026 map names it ("9"); the House subdistricts 4A and 4B aren't up. The Public
Service Commission has two races in 2026, a six-year term and an unexpired one, under one contest
the list doesn't split, so they're left out with a ballot note, with the Supreme Court, the district
judges, the county offices and the soil conservation districts.

North Dakota's key dates, for its general election (the Tuesday after the first Monday of November
in an even year, NDCC 16.1-13-01), checked on 2026-10-29 against the North Dakota Century Code
(ndlegis.gov) and the Secretary of State's Absentee Voting page: North Dakota has no voter
registration; a voter shows an ID with their North Dakota address at the polls (16.1-01-04.1). Any
voter can vote absentee, no reason needed (16.1-07-01); the ballots are ready 40 days before
(16.1-07-04), to be voted in person at the county auditor's office or by mail. A voter can apply
any time in the year, but no ballot is issued on Election Day but in an emergency (16.1-07-05),
so the day before is the last; the ballot must reach the county auditor before the polls close
(16.1-07-09), a postmark doesn't count, and polling places don't take it. A county may open early
voting sites in the 15 days before (16.1-07-15). Polls open between 7 and 9 a.m. and close between
7 and 9 p.m., as each county or city sets for a precinct (16.1-01-03). 2026: Nov 2, Sep 24 – Nov 2.
"""

from __future__ import annotations

import dataclasses
import re

from . import Office, legislator, party, statewide, us_house
from .dates import Counts, Guide
from .grid import GridList, GridRow

INDEX = "https://www.sos.nd.gov/elections/candidate"
PAGE = "https://vip.sos.nd.gov/candidatelist.aspx"
SEARCH = {"ctl00$ContentPlaceHolder1$ddlJursdiction": "AL", "ctl00$ContentPlaceHolder1$ddlDistrict": "0",
          "ctl00$ContentPlaceHolder1$ddlContest": "0", "ctl00$ContentPlaceHolder1$ddlCandidate": "0",
          "ctl00$ContentPlaceHolder1$btnSearch": "Search"}
STATEWIDE = ("Secretary of State", "Attorney General", "Agriculture Commissioner", "Tax Commissioner",
             "Superintendent of Public Instruction")
PARTIES = {"DEMOCRATIC-NPL": ("D", None), "INDEPENDENT NOMINATION": (None, "Independent")}
_DISTRICT = re.compile(r"District 0*(\d+)", re.I)


def _district(row: GridRow) -> int:
    found = _DISTRICT.fullmatch(row.district.strip())
    if not found:
        raise ValueError(f"no district for {row.race}: {row.district!r}")
    return int(found.group(1))


class NdList(GridList):
    state = "ND"
    source = "state_nd"
    label = "North Dakota Secretary of State"
    page = PAGE
    index = INDEX
    election = "eid"
    form = SEARCH
    table = True
    minimum = {"cd": 1, "sd": 20, "hd": 20}  # nearly every odd-numbered district: they're up
    description = ("North Dakota's official list of the candidates for Congress, the statewide offices and the "
                   "Legislature, from its Secretary of State.")
    scope_note = ("The Public Service Commission's two races, the Supreme Court and district judges, your county's "
                  "offices, its soil conservation district and any ballot measures aren't shown: your county auditor's "
                  "sample ballot has them.")

    @classmethod
    def office(cls, row: GridRow) -> Office | None:
        """The race of a row; None for one the ballot leaves out (the Public Service Commission's,
        a judge's, a county's)."""
        race = " ".join(row.race.split())
        if race == "Representative in Congress":
            return us_house("ND", 0, "US HOUSE")
        if race in STATEWIDE:
            return statewide(race)
        if race == "State Senator":
            return legislator("sd", _district(row))
        if race == "State Representative":
            district = _district(row)
            if district % 2:
                return dataclasses.replace(legislator("hd", district), seats=2)
            return dataclasses.replace(legislator("hd", district), unexpired=True)
        return None

    @classmethod
    def affiliation(cls, row: GridRow) -> tuple[str | None, str | None]:
        """Democratic-NPL is the Democrats' party; an independent nomination is no party's."""
        return PARTIES.get(" ".join(row.party.split()).upper()) or party(row.party)


GUIDE = Guide(
    name="North Dakota",
    source="North Dakota Secretary of State",
    url="https://www.sos.nd.gov/elections",
    computed=True,
    registration_url="https://www.sos.nd.gov/elections/voter/voting-north-dakota/forms-voter-id",
    mail_url="https://vip.sos.nd.gov/absentee/Default.aspx",
    register="",
    mail_summary="Last day to get an absentee ballot",
    mail="If you vote absentee in {election}, today is the last day to get your ballot: no ballot is issued on "
         "Election Day. Your ballot must reach your county auditor before the polls close on Election Day; a postmark "
         "doesn't count, and polling places don't take it. Any voter can vote absentee; apply online:",
    early_where="Your county auditor's office, where you can vote an absentee ballot in person from 40 days before "
                "Election Day; many counties also open early voting sites in the 15 days before.",
    credit="Dates worked out from North Dakota's election law; more from the North Dakota Secretary of State",
    poll_hours="7–9 p.m.",
    check_url="https://www.sos.nd.gov/elections/voter/voting-north-dakota/forms-voter-id",
    check_hint="North Dakota has no voter registration: bring an ID with your North Dakota address to the polls. Forms "
               "of voter ID (North Dakota Secretary of State)",
    where_url="https://vip.sos.nd.gov/WhereToVote.aspx",
    where_hint="My Voting Information (North Dakota Secretary of State): your polling place, early voting sites and "
               "your county auditor",
    mail_label="Apply for an absentee ballot",
    mail_eligibility="Any voter can vote absentee, no reason needed. Your ballot must reach your county auditor before "
                     "the polls close on Election Day; polling places don't take it.",
    mail_deadline="No ballot is issued on Election Day: get yours by ",
    local_office="Your county auditor",
    polls_text="Polls open between 7 and 9 a.m. and close between 7 and 9 p.m., as your county or city sets for your "
               "polling place; if you're in line at closing time, you can vote. North Dakota has no voter registration: "
               "bring an ID with your North Dakota address.",
    hours_set_by="your county or city",
    check_label="Voter ID",
    check_short="ID",
)
RULE = Counts(None, 1, 40, 1).rule("ND")
