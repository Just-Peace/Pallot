"""Wisconsin: the Elections Commission's "All Contests and Candidates" CSV for a general election,
saved by hand (manual/state_wi), since elections.wi.gov answers scripts with Cloudflare's
challenge and Pallot never asks it.

Each row is a candidate in a contest, read by its column names: the election, the name on the
ballot, the party, the jurisdiction that runs the contest ("STATE OF WISCONSIN", "DANE COUNTY",
"CITY OF VERONA - DANE COUNTY"), the contest, its district, and the contest's and candidate's
ballot positions, which give the order. Referendums have rows of their own with no candidate:
the ballot has no measures, so they're left out, as are contests no one filed for.

The statewide offices, Congress, the State Senate and the Assembly come under the state. A county's
contest whose district is the whole county (sheriff, clerk of circuit court, coroner) reaches the
whole county, and a city's or village's whose district is the whole of it, the whole place;
anything else within a county (a supervisory district, a joint municipal court, a town) only part
of it, so those are unconfirmed. A city spanning counties ("- MULTIPLE COUNTIES") isn't placed.

Wisconsin's key dates, for its general election (Wis. Stat. 5.02(5): the Tuesday after the first
Monday of November in an even year): registration by mail or online closes the third Wednesday
before (6.28(1)), then it's in person at the municipal clerk's office until 5 p.m. the Friday before
(6.29(2)(a)), or at the polling place on Election Day (6.55(2)); any voter can vote absentee, asking
by mail or online by 5 p.m. the fifth day before, or in person at the clerk's office from the
fourteenth day before through the Sunday before (6.86(1)(b)), and the ballot must reach the polling
place by 8 p.m. on Election Day (6.87(6)); polls are open 7 a.m. to 8 p.m. (6.78(1m)).
"""

from __future__ import annotations

import csv
import dataclasses
import functools
import io
import re
from typing import Any

from . import Filing, ManualList, Office, legislator, party, us_house
from .dates import Counts, Guide, first_tuesday_after_first_monday

COLUMNS = ("Election", "IsReferendum", "Name On Ballot", "Political Party", "Jurisdiction", "Contest", "District",
           "Contest Ballot Position", "Candidate Ballot Position")
STATEWIDE = {
    "GOVERNOR / LIEUTENANT GOVERNOR": "Governor / Lieutenant Governor", "ATTORNEY GENERAL": "Attorney General",
    "SECRETARY OF STATE": "Secretary of State", "STATE TREASURER": "State Treasurer",
}
LEGISLATURE = (
    (r"STATE SENATOR DISTRICT (\d+)", "sd", "STATE SENATE", "State Senate"),
    (r"REPRESENTATIVE TO THE ASSEMBLY DISTRICT (\d+)", "hd", "STATE ASSEMBLY", "State Assembly"),
)
_ELECTION = re.compile(r"(\d{4}) General Election", re.I)
_CONGRESS = re.compile(r"REPRESENTATIVE IN CONGRESS DISTRICT (\d+)")
_COUNTY = re.compile(r"(.+) COUNTY")
_MUNICIPALITY = re.compile(r"(CITY|VILLAGE|TOWN) OF (.+?) - (.+)")
_JUDICIAL = re.compile(r"\bJUDGE\b|\bJUSTICE\b")
_PARTIES = {"WISCONSIN GREEN": ("G", None), "INDEPENDENT": (None, None)}


def _text(value: str | None) -> str:
    return " ".join((value or "").split())


def _number(value: str | None) -> int:
    text = _text(value)
    return int(text) if text.isdigit() else 0


def _kind(jurisdiction: str, contest: str, district: str) -> Office:
    """The race of a row's contest."""
    where, upper, area = jurisdiction.upper(), contest.upper(), district.upper()
    group = "judicial" if _JUDICIAL.search(upper) else "local"
    if where == "STATE OF WISCONSIN":
        if found := _CONGRESS.fullmatch(upper):
            return us_house("WI", int(found.group(1)), upper)
        for pattern, reach, family, label in LEGISLATURE:
            if found := re.fullmatch(pattern, upper):
                number = int(found.group(1))
                return dataclasses.replace(legislator(reach, number, upper, f"{label} District {number}"), family=family)
        if area == "WISCONSIN":
            return Office(upper, STATEWIDE.get(upper, contest), upper, "judicial" if group == "judicial" else "state",
                          "state")
        return Office(upper, contest, upper, "state", "unplaced")
    race = functools.partial(Office, f"{upper} ({where})", contest, upper, group)
    if found := _MUNICIPALITY.fullmatch(where):
        kind, name, county = found.groups()
        if not (counted := _COUNTY.fullmatch(county)):
            return race("unplaced")
        counties = (counted.group(1),)
        if kind == "TOWN":
            return race("part_county", counties=counties)
        whole = area == f"{kind} OF {name}"
        return race("city" if whole else "part_city", city=name, counties=counties)
    if found := _COUNTY.fullmatch(where):
        county = found.group(1)
        if area == where:
            return Office(f"{upper} ({where})", contest, re.sub(rf"^{re.escape(county)}(?: COUNTY)? ", "", upper),
                          "judicial" if group == "judicial" else "county", "county", counties=(county,))
        return race("part_county", counties=(county,))
    return race("unplaced")


def parse_rows(text: str) -> list[Filing]:
    """Every candidate in the CSV; ValueError for a file that isn't the list (its columns missing,
    no general election's candidates)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = [name for name in COLUMNS if name not in (reader.fieldnames or ())]
    if missing:
        raise ValueError(f"no {', '.join(missing)} column{'s' if len(missing) > 1 else ''}")
    filings: list[Filing] = []
    for row in reader:
        found = _ELECTION.fullmatch(_text(row["Election"]))
        name = _text(row["Name On Ballot"])
        if not found or _text(row["IsReferendum"]) or not name:
            continue
        day = first_tuesday_after_first_monday(int(found.group(1)), 11).isoformat()
        race = _kind(_text(row["Jurisdiction"]), _text(row["Contest"]), _text(row["District"]))
        label = _text(row["Political Party"])
        code, party_name = _PARTIES.get(label.upper()) or party(label)
        filings.append(race.filing(day=day, name=name, party=code, party_name=party_name,
                                   order=_number(row["Contest Ballot Position"]) * 100
                                   + _number(row["Candidate Ballot Position"])))
    if not filings:
        raise ValueError("no candidates")
    return filings


class WiList(ManualList):
    state = "WI"
    source = "state_wi"
    label = "Wisconsin Elections Commission"
    page = "https://elections.wi.gov/candidates"
    description = ("Wisconsin's official list of the candidates on its ballot, from Congress to its counties, from its "
                   "Elections Commission, imported by hand.")
    folder = "manual/state_wi"
    challenge = ("Just a moment...", "challenges.cloudflare.com", "cf-browser-verification")

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, str):
            raise ValueError("not a CSV")
        return parse_rows(raw)


GUIDE = Guide(
    name="Wisconsin",
    source="Wisconsin Elections Commission",
    url="https://elections.wi.gov/",
    computed=True,
    registration_url="https://myvote.wi.gov/",
    mail_url="https://myvote.wi.gov/",
    register="The last day to register online or by mail for {election} in Wisconsin. After it, you can still "
             "register in person at your municipal clerk's office until 5 p.m. on the Friday before, or at your "
             "polling place on Election Day, with proof of residence.",
    mail_summary="Absentee ballot request due",
    mail="If you vote absentee in {election}, a request made online or by mail must reach your municipal clerk by "
         "5 p.m. today. Your ballot must reach your polling place or clerk by 8 p.m. on Election Day; one that "
         "arrives later isn't counted. Any voter can vote absentee; how to ask:",
    early_where="Your municipal clerk sets the places and hours, and may start later than the first day allowed.",
    credit="Dates worked out from Wisconsin's election law; more from the Wisconsin Elections Commission",
    poll_hours="7 a.m. – 8 p.m.",
    check_url="https://myvote.wi.gov/",
    check_hint="MyVote Wisconsin (Wisconsin Elections Commission): your registration, your polling place and your "
               "ballot",
    where_url="https://myvote.wi.gov/",
    where_hint="MyVote Wisconsin: your polling place, and your municipal clerk's office for voting early",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote absentee by mail, no reason needed. Your ballot must reach your "
                     "polling place or clerk by 8 p.m. on Election Day.",
    mail_deadline="Mailed or online requests must reach your clerk by 5 p.m. on ",
    local_office="Your municipal clerk",
    late_registration="After that, register in person at your clerk's office until the Friday before, or at your "
                      "polling place on Election Day",
)
RULE = Counts(20, 5, 14, 2).rule("WI")
