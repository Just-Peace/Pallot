"""Virginia: the Department of Elections' list of the candidates for federal offices in a
November election, one page with a table (a spreadsheet's rows): office, district, party,
name as on the ballot, and whether they hold the seat.

Its state and local candidates are on another, much larger page; Virginia elects its
Legislature and governor in odd years, so a federal year's list is the federal one.

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
from typing import Any

from ..http_cache import RequestSpec
from . import Filing, Rows, StateList, party, party_rank, us_house, us_senate
from .dates import Counts, Guide

URL = "https://www.elections.virginia.gov/casting-a-ballot/candidate-list/november-{day}-{year}-gen-elect-federal-offices/"
COLUMNS = ("Office Title", "District", "Candidate Party", "Candidate Name", "Incumbent")
_DAY = re.compile(r"<h1>\s*(November \d{1,2}, \d{4})")


class VaList(StateList):
    state = "VA"
    source = "state_va"
    label = "Virginia Department of Elections"
    page = "https://www.elections.virginia.gov/casting-a-ballot/candidate-list/"
    description = "Virginia's official list of the candidates for Congress, from its Department of Elections."

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", URL.format(day=day.day, year=day.year), as_text=True)

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        text = raw if isinstance(raw, str) else ""
        found = _DAY.search(text)
        reader = Rows()
        reader.feed(text)
        header = next((i for i, row in enumerate(reader.rows) if tuple(row[:len(COLUMNS)]) == COLUMNS), None)
        if not found or header is None:
            raise ValueError("no election date or column headings")
        day = dt.datetime.strptime(found.group(1), "%B %d, %Y").date().isoformat()
        filings = []
        for index, row in enumerate(reader.rows[header + 1:]):
            if len(row) < len(COLUMNS) or any("withdr" in cell.lower() for cell in row):
                continue
            office, district, label, name, incumbent = row[:len(COLUMNS)]
            number = re.fullmatch(r"(\d+)\w\w District", district)
            if office == "Member, United States Senate":
                race = us_senate("VA")
            elif office == "Member, House of Representatives" and number:
                race = us_house("VA", int(number.group(1)))
            else:
                continue
            code, party_name = party(label)
            filings.append(race.filing(
                day=day, name=name, party=code, party_name=party_name, incumbent=incumbent.strip().lower() == "yes",
                order=(0 if race.reach == "state" else 1 + int(race.district or 0)) * 1_000
                + party_rank(code, party_name) * 100 + index,
            ))
        return filings


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
