"""Minnesota: the general election's ballot as the Secretary of State's election results files set
it up (electionresultsfiles.sos.mn.gov/<yyyymmdd>/), one semicolon-separated text file per kind of
office, posted before Election Day with every candidate on the ballot. Its candidate filings site
(candidates.sos.mn.gov) and its results pages sit behind a captcha for scripts, and the filings
keep every candidate who filed, primary losers too; the results files answer a plain script with no
challenge, and hold only the ballot's nominees. On 2026-10-29 every one of their 420 candidates was
among those who filed (the filings page, saved by hand), with no race holding two of one party's.

The House's file (ushouse.txt) is asked first; the others (FILES) follow it. A row per candidate in
a race: the state, the county and precinct (empty statewide), the office's id and name ("State
Representative District 1A"), the district, the candidate's order code, name, suffix and
incumbent code (empty in 2026), the party's abbreviation ("DFL", "R", "IND"; "WI" for the race's
write-in line, which isn't a candidate), and the votes counted so far. The files carry no address,
phone or email, and no election date: their folder names the day, so their filings are dated by
the election asked for. Each file is kept as its filings alone.

Placed in 2026: the U.S. Senate, the U.S. House (eight districts), Governor and Lieutenant Governor
(one ticket), Secretary of State, State Auditor, Attorney General, the State Senate (all 67
districts) and the State House (all 134, numbered with a letter, "1A", as the Census numbers them),
by party in each race. The judges (Supreme Court, Court of Appeals, District Courts), county and
city races and the ballot questions are in other files, which aren't read: the ballot's note says so.
An office it doesn't know in the files it reads is refused, so a new one is seen rather than dropped.

Minnesota's key dates, for its general election (the first Tuesday after the first Monday of
November in even years, Minn. Stat. §204D.03), checked on revisor.mn.gov on 2026-10-29: registering
before Election Day closes 21 days before, at 5 p.m. by mail or in person and at 11:59 p.m. online
(§201.061 subd. 1); after that, a voter registers at the polling place on Election Day, with proof
of residence (§201.061 subd. 3). Any voter can vote absentee (§203B.02), asking any time up to the
day before (§203B.04 subd. 1), and in person at the county auditor's office and the places it names
during the 46 days before, through the day before (§203B.081 subd. 1). A ballot brought in person
must reach the auditor or clerk by 5 p.m. on Election Day, and one mailed by 8 p.m. (§203B.08 subds.
1, 3). Polls are open 7 a.m. to 8 p.m. (§204C.05 subd. 1); a small town may open them as late as 10
a.m. (subd. 1a). 2026: register by Oct 13, absentee in person Sep 18 – Nov 2, ask by Nov 2.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import re
from typing import Any

from ..http_cache import RequestSpec, UpstreamError
from . import (
    Filing, Office, StateList, decoded, filings_json, legislator, party_rank, require, statewide, us_house, us_senate,
)
from .dates import Counts, Guide

BASE = "https://electionresultsfiles.sos.mn.gov"
INDEX = "ushouse.txt"  # asked first: every even year has its U.S. House races
FILES = ("ussenate.txt", "governor.txt", "secofstate.txt", "auditor.txt", "attorneygen.txt", "stsenate.txt",
         "LegislativeByDistrict.txt")  # 2026's other races' files, by name, as the Secretary of State names them
MINIMUM = {"cd": 8, "sd": 60, "hd": 120}  # nearly every district: one can go without a candidate
CODES = {"DFL": "D", "R": "R", "LIB": "L", "GP": "G"}
NAMES = {"IND": "Independent", "FI": "Forward Independence", "UNI": "United New Independence",
         "LMN": "Legal Marijuana Now", "GLC": "Grassroots - Legalize Cannabis", "SWP": "Socialist Workers"}
STATEWIDE = ("Secretary of State", "State Auditor", "Attorney General")  # after Governor, in ballot order
_HOUSE = re.compile(r"U\.S\. Representative District (\d+)")
_LEGISLATURE = re.compile(r"State (Senator|Representative) District (\d+[A-Z]?)")


def _race(office: str) -> tuple[int, Office]:
    """A row's race, and where its kind comes on the ballot; ValueError for one it doesn't know."""
    if office == "U.S. Senator":
        return 0, us_senate("MN")
    if found := _HOUSE.fullmatch(office):
        return 1, us_house("MN", int(found.group(1)))
    if office == "Governor & Lt Governor":
        return 2, statewide("Governor and Lieutenant Governor", "GOVERNOR")
    if office in STATEWIDE:
        return 3 + STATEWIDE.index(office), statewide(office)
    if found := _LEGISLATURE.fullmatch(office):
        senate = found.group(1) == "Senator"
        return (6, legislator("sd", int(found.group(2)))) if senate else (7, legislator("hd", found.group(2)))
    raise ValueError(f"an office it doesn't know: {office}")


def candidates(text: str) -> list[Filing]:
    """Every candidate in one of the results files, undated (MnList.on dates them with the
    election asked), by race in the file's order and by party in each; ValueError for a file that
    isn't one (a page, too few fields) or with an office it doesn't know."""
    rows = [line.split(";") for line in text.splitlines() if line.strip()]
    if not rows or any(len(cells) < 11 or cells[0] != "MN" for cells in rows):
        raise ValueError("not one of the Secretary of State's results files")
    filings: list[Filing] = []
    starts: dict[str, int] = {}
    for cells in rows:
        label = cells[10].strip().upper()
        if label == "WI":
            continue
        rank, race = _race(" ".join(cells[4].split()))
        name = " ".join(" ".join(part for part in (cells[7], cells[8]) if part.strip()).split())
        if not name:
            raise ValueError(f"a row without a name: {race.office}")
        code = CODES.get(label)
        party_name = None if code or not label else NAMES.get(label, label)
        start = starts.setdefault(race.office_id, len(starts))
        filings.append(race.filing(day="", name=name, party=code, party_name=party_name,
                                   order=rank * 100_000 + start * 10 + party_rank(code, party_name)))
    return filings


class MnList(StateList):
    state = "MN"
    source = "state_mn"
    label = "Minnesota Secretary of State"
    page = "https://www.sos.mn.gov/elections-voting/"
    description = ("Minnesota's official list of the candidates for Congress, its statewide offices and its "
                   "Legislature, from its Secretary of State's election results files.")
    max_bytes = 4 << 20
    index_key = "files"
    scope_note = ("The judges, county and city races and the ballot questions aren't shown: your county's sample "
                  "ballot has them.")

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", f"{BASE}/{day:%Y%m%d}/{INDEX}")

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        """The U.S. House's file, with the names of the files to ask next; None for another."""
        filings = candidates(decoded(raw))
        if not any(f.reach == "cd" for f in filings):
            return None
        return {**filings_json(filings), "files": list(FILES)}

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        return [RequestSpec("GET", f"{BASE}/{day:%Y%m%d}/{name}") for name in index["files"]]

    def combine(self, lists: list[list[Filing]]) -> list[Filing]:
        """The files' filings; UpstreamError for a ballot short of its races (MINIMUM)."""
        kept = [f for found in lists for f in found]
        try:
            return require(kept, MINIMUM)
        except ValueError as exc:
            raise UpstreamError(self.source, f"its list isn't whole: {exc}") from exc

    def on(self, value: Any, day: dt.date) -> list[Filing]:
        """The filings in a stored answer, dated ``day``: its file is in that election's folder."""
        return [dataclasses.replace(f, day=day.isoformat()) if not f.day else f
                for f in self.read(value) if not f.day or f.day == day.isoformat()]

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        return candidates(decoded(raw) if isinstance(raw, bytes) else raw if isinstance(raw, str) else "")


MNVOTES = "https://mnvotes.sos.mn.gov"
GUIDE = Guide(
    name="Minnesota",
    source="Minnesota Secretary of State",
    url="https://www.sos.mn.gov/elections-voting/",
    computed=True,
    registration_url=MNVOTES,
    mail_url=MNVOTES,
    register="The last day to register to vote in {election} in Minnesota before Election Day: online by 11:59 p.m., "
             "or by mail or in person by 5 p.m. After it, you can still register at your polling place on Election "
             "Day, with proof of where you live.",
    mail_summary="Last day to ask for an absentee ballot",
    mail="If you vote absentee in {election}, ask for your ballot by today; ask well before, so it can reach you and "
         "come back. A mailed ballot must arrive by 8 p.m. on Election Day, one brought in person by 5 p.m. Any voter "
         "can vote absentee; how to ask:",
    early_where="Your county election office, and any other place your county or city names: vote absentee in person "
                "there from 46 days before Election Day through the day before. Your county lists the places and "
                "hours.",
    credit="Dates worked out from Minnesota's election law; more from the Minnesota Secretary of State",
    poll_hours="7 a.m. – 8 p.m.",
    check_url=MNVOTES,
    check_hint="Minnesota Secretary of State: your registration and your absentee ballot",
    where_url="https://pollfinder.sos.mn.gov/",
    where_hint="Poll Finder (Minnesota Secretary of State): your polling place",
    mail_label="How to ask",
    mail_eligibility="Any registered voter can vote absentee, no reason needed. A mailed ballot must arrive by 8 p.m. on "
                     "Election Day; one brought to your election office in person, by 5 p.m.",
    mail_deadline="Ask for your ballot by ",
    late_registration="After that, register at your polling place on Election Day, with proof of where you live",
)
RULE = Counts(21, 1, 46, 1).rule("MN")
