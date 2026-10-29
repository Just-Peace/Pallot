"""North Carolina: the State Board of Elections' candidate list, one CSV on S3 for the year's
elections (layout: https://s3.amazonaws.com/dl.ncsbe.gov/Elections/layout_candidate_listing.txt).

It has every contest in the state, one row per candidate per county the contest reaches, for the
primary and the general; a general's rows carry its November date. It has no withdrawn
candidates, write-ins or incumbents. A contest's reach comes from its name and the counties it
has rows in: a judicial or district attorney's district is the counties it's listed in, a county
office the one county, a town's the town.

North Carolina's key dates, for its general election (G.S. 163-1: the Tuesday after the first Monday
of November in an even year): registration closes the twenty-fifth day before (163-82.6(d)), then
voters register and vote the same day at an early voting site (163-82.6B), but not on Election Day;
early voting runs from the third Thursday before through 3 p.m. on the last Saturday before
(163-227.2(b)); any voter can vote absentee, the request reaching the county board by 5 p.m. on the
second Tuesday before (163-230.1(a)), and the ballot must reach the board by 7:30 p.m. on Election
Day (163-231(b)); polls are open 6:30 a.m. to 7:30 p.m. (163-166.01).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from typing import Any

from ..http_cache import RequestSpec
from ..sources.fec import race_name
from ..text import display_office
from . import Filing, Office, StateList, party, party_rank
from .dates import Counts, Guide

URL = "https://s3.amazonaws.com/dl.ncsbe.gov/Elections/{year}/Candidate%20Filing/Candidate_Listing_{year}.csv"
COLUMNS = ("election_dt", "county_name", "contest_name", "name_on_ballot", "party_candidate", "is_unexpired",
           "is_partisan", "vote_for")

_PART = re.compile(r"\b(?:DISTRICT|DIST|SEAT|WARD|AREA|ZONE|TOWNSHIP|PRECINCT)\b(?!\s*AT-LARGE)|\((?:NORTH|SOUTH|EAST|WEST)\)")


def _kind(contest: str, county: str) -> Office:
    """A contest's race, its id the contest, from its name and a county it has rows in."""
    def race(group: str, reach: str, family: str, district: str | None = None, city: str | None = None) -> Office:
        return Office(contest, _office(contest, reach, district), family, group, reach, district, city=city)

    if contest == "US SENATE":
        return race("federal", "state", "US SENATE")
    if found := re.fullmatch(r"US HOUSE OF REPRESENTATIVES DISTRICT (\d+)", contest):
        return race("federal", "cd", "US HOUSE", str(int(found.group(1))))
    if found := re.fullmatch(r"NC STATE SENATE DISTRICT (\d+)", contest):
        return race("legislature", "sd", "NC STATE SENATE", str(int(found.group(1))))
    if found := re.fullmatch(r"NC HOUSE OF REPRESENTATIVES DISTRICT (\d+)", contest):
        return race("legislature", "hd", "NC HOUSE", str(int(found.group(1))))
    if contest.startswith(("NC SUPREME COURT", "NC COURT OF APPEALS")):
        return race("judicial", "state", contest)
    if found := re.match(r"(NC SUPERIOR COURT JUDGE|NC DISTRICT COURT JUDGE|DISTRICT ATTORNEY) DISTRICT (\w+)", contest):
        return race("judicial", "counties", found.group(1), found.group(2))
    if found := re.match(r"(?:CITY|TOWN|VILLAGE) OF (.+)", contest):
        return race("local", "part_city" if _PART.search(contest) else "city", contest, city=found.group(1))
    if contest.startswith(f"{county} COUNTY ") or contest.startswith(f"{county} SOIL AND WATER CONSERVATION"):
        part = _PART.search(contest.removeprefix(f"{county} SOIL AND WATER CONSERVATION DISTRICT"))
        return race("county", "part_county" if part else "county", contest)
    return race("local", "part_county", contest)


def _office(contest: str, reach: str, district: str | None) -> str:
    if reach == "cd" or contest == "US SENATE":
        return race_name("NC", int(district) if district else None)
    return re.sub(r"\b(District|Seat) 0+(?=\d)", r"\1 ", re.sub(r"^Nc ", "NC ", display_office(contest)))


def _rank(group: str, reach: str) -> int:
    """Where a race comes on the ballot, within its group: the Senate before the House, and so on."""
    return {"state": 0, "cd": 1, "sd": 0, "hd": 1, "counties": 2, "county": 3, "city": 4}.get(reach, 5)


class NcList(StateList):
    state = "NC"
    source = "state_nc"
    label = "NC State Board of Elections"
    page = "https://www.ncsbe.gov/results-data/candidate-lists"
    description = "North Carolina's official list of the candidates on its ballot, from the State Board of Elections."

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", URL.format(year=day.year), as_text=True)

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        reader = csv.DictReader(io.StringIO(raw if isinstance(raw, str) else ""))
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or ())]
        if missing:
            raise ValueError(f"no {', '.join(missing)} column")
        merged: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in reader:
            try:
                day = dt.datetime.strptime(row["election_dt"].strip(), "%m/%d/%Y").date()
            except ValueError:
                continue
            contest, name = " ".join(row["contest_name"].upper().split()), " ".join(row["name_on_ballot"].split())
            if day.month != 11 or not contest or not name:
                continue
            key = (day.isoformat(), contest, name)
            county = " ".join(row["county_name"].upper().split())
            if key in merged:
                merged[key]["counties"].add(county)
                continue
            partisan = row["is_partisan"].strip().upper() == "TRUE"
            merged[key] = {"row": row, "county": county, "counties": {county}, "partisan": partisan}
        position = {contest: i for i, contest in enumerate(sorted({key[1] for key in merged}))}
        filings = []
        for (day, contest, name), found in merged.items():
            race = _kind(contest, found["county"])
            code, party_name = party(found["row"]["party_candidate"]) if found["partisan"] else (None, None)
            seats = found["row"]["vote_for"].strip()
            filings.append(race.filing(
                day=day, name=name, party=code, party_name=party_name, counties=tuple(sorted(found["counties"])),
                seats=int(seats) if seats.isdigit() and int(seats) > 0 else 1,
                unexpired=found["row"]["is_unexpired"].strip().upper() == "TRUE" or "(UNEXPIRED)" in contest,
                order=(_rank(race.group, race.reach) * 10_000 + position[contest]) * 10
                + party_rank(code, party_name),
            ))
        return filings


GUIDE = Guide(
    name="North Carolina",
    source="North Carolina State Board of Elections",
    url="https://www.ncsbe.gov/",
    computed=True,
    registration_url="https://www.ncsbe.gov/registering/how-register",
    mail_url="https://votebymail.ncsbe.gov/",
    register="The last day to register to vote in {election} in North Carolina, online, by mail (postmarked today) "
             "or in person. After it, you can still register and vote the same day at an early voting site, until "
             "early voting ends; not on Election Day.",
    mail_summary="Absentee ballot request due",
    mail="If you vote absentee in {election}, your request must reach your county board of elections by 5 p.m. "
         "today. Your ballot must reach the board by 7:30 p.m. on Election Day; one that arrives later isn't "
         "counted. Any voter can vote absentee; how to ask:",
    early_where="Your county board of elections lists the places and hours. Early voting ends at 3 p.m. on the last "
                "day.",
    credit="Dates worked out from North Carolina's election law; more from the North Carolina State Board of Elections",
    poll_hours="6:30 a.m. – 7:30 p.m.",
    check_url="https://vt.ncsbe.gov/RegLkup/",
    check_hint="North Carolina's voter search (State Board of Elections): your registration, your polling place and "
               "your sample ballot",
    where_url="https://vt.ncsbe.gov/RegLkup/",
    where_hint="The voter search: your polling place; your county board of elections lists its early voting sites",
    mail_label="How to ask",
    mail_eligibility="Any registered voter can vote absentee by mail, no reason needed. Your ballot must reach your "
                     "county board of elections by 7:30 p.m. on Election Day.",
    mail_deadline="Your request must reach your county board by 5 p.m. on ",
    local_office="Your county board of elections",
    late_registration="After that, register and vote the same day at an early voting site, until early voting ends",
)
RULE = Counts(25, 14, 19, 3).rule("NC")
