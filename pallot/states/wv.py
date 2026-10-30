"""West Virginia: the Secretary of State's candidate listing (candidates.wvsos.gov), saved by hand
(manual/state_wv): its load balancer answers 403 to scripts, so the maintainer exports the 2026
general election's candidates to CSV in a browser, and Pallot never asks it.

Each row is a candidate: the ballot name, in capitals ("SHELLEY MOORE CAPITO"), the party, the race
with its district ("HOUSE OF DELEGATES - DISTRICT 12", "STATE SENATE - UNEXPIRED - DISTRICT 3") and
the filing date. Its legal name, address, phone and email columns are never read: only the name,
office, district and party are kept. It names no election, so its filings are dated by the general
election after its newest filing.

It is the general election's list, not the primary's: on 2026-10-30 every Republican and Democrat on
it (221) was the winner of their party's May 12 primary on the Secretary of State's certified
results (results.enr.clarityelections.com/WV/126209), but for two named after the primary to a
place no one won (House of Delegates 27 and 94); no primary loser is on it, and minor parties'
nominees and independents who filed by August are. The reader refuses a race with two Democrats or
two Republicans, which would mean a primary's list.

Placed: the U.S. Senate, the U.S. House (two districts), the State Senate (one of each of the 17
districts' two seats, and in 2026 the rest of the other seat's term in Districts 3 and 17, a race of
its own) and the House of Delegates (100 single-member districts). The Supreme Court and the
Intermediate Court of Appeals are elected in May; the unexpired terms of circuit and family court
judges on the November ballot, and the county races, are left out with a ballot note. An office it
doesn't know is refused.

West Virginia's key dates, for its general election (the Tuesday after the first Monday of
November, W. Va. Code §3-1-31), checked on 2026-10-30 against the Code and the Secretary of State's
2026 election calendar: registration closes 21 days before (§3-2-6(a); always a Tuesday, so never
moved past a weekend); an application to vote absentee must reach the county clerk 6 days before
(§3-3-5(b)), and voting absentee needs an excuse (§3-3-1(b)); a mailed ballot counts if it arrives
the day after the election, or postmarked by Election Day before the canvass (§3-3-5(g)). Early
voting runs from 13 days before through the Saturday 3 days before (§3-3-3). Polls are open 6:30
a.m. to 7:30 p.m. (§3-1-31(b)). 2026: register by Oct 13, apply by Oct 28, early voting Oct 21 -
Oct 31.
"""

from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import io
import re
from collections import Counter
from typing import Any

from ..text import display_person
from . import Filing, ManualList, Office, legislator, party, party_rank, require, us_house, us_senate
from .dates import Counts, Guide, first_tuesday_after_first_monday, only_if

COLUMNS = ("Name", "Party", "Race", "Filing Date")
MINIMUM = {"cd": 2, "sd": 17, "hd": 100}
LEFT_OUT = ("CIRCUIT COURT JUDGE", "FAMILY COURT JUDGE", "MAGISTRATE")
_RACE = re.compile(r"(U\.S\. HOUSE OF REPRESENTATIVES|STATE SENATE|HOUSE OF DELEGATES)( - UNEXPIRED)? - DISTRICT (\d+)")
_INITIALS = re.compile(r"(?:[A-Z]\.){2,}|(?!JR|SR)[B-DF-HJ-NP-TV-XZ]{2}")  # "D.R.", "JB": kept as they are


def _text(value: str | None) -> str:
    return " ".join((value or "").split())


def _name(text: str) -> str:
    """ 'KATHRYN "KAT" WEILAND' -> 'Kathryn "Kat" Weiland'; "D.R. BUCK JENNINGS" -> "D.R. Buck Jennings"."""
    return " ".join(word if _INITIALS.fullmatch(word) else display_person(word) for word in text.split())


def _race(office: str) -> Office | None:
    """The race of a row's office; None for one left out. ValueError for one it doesn't know."""
    title = office.upper()
    if title == "U.S. SENATE":
        return us_senate("WV")
    if found := _RACE.fullmatch(title):
        kind, unexpired, number = found.group(1), bool(found.group(2)), int(found.group(3))
        if kind.startswith("U.S."):
            race = us_house("WV", number)
        elif kind == "STATE SENATE":
            race = legislator("sd", number)
        else:
            race = legislator("hd", number, office=f"House of Delegates District {number}")
        return dataclasses.replace(race, office_id=f"{race.office_id} UNEXPIRED", unexpired=True) if unexpired else race
    if title.startswith(LEFT_OUT):
        return None
    raise ValueError(f"an office it doesn't know: {office}")


def _rank(race: Office) -> tuple[int, int, bool]:
    """Where a race comes on the ballot: the U.S. Senate, the U.S. House, the State Senate, the House of Delegates."""
    order = {"US SENATE": 0, "US HOUSE": 1, "STATE SENATE": 2}.get(race.family, 3)
    return order, int(race.district or 0), race.unexpired


def parse_rows(text: str) -> list[Filing]:
    """Every candidate in the CSV, dated by the general election after its newest filing;
    ValueError for a file that isn't the list (its columns missing, an office it doesn't know, two
    Democrats or two Republicans in a race, no candidates, fewer than MINIMUM's races)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = [name for name in COLUMNS if name not in (reader.fieldnames or ())]
    if missing:
        raise ValueError(f"no {', '.join(missing)} column{'s' if len(missing) > 1 else ''}")
    found: list[tuple[Office, str, str, dt.date]] = []
    for row in reader:
        name, office = _text(row["Name"]), _text(row["Race"])
        if not name or not office:
            continue
        try:
            filed = dt.datetime.strptime(_text(row["Filing Date"]), "%m/%d/%Y").date()
        except ValueError as exc:
            raise ValueError(f"a filing date it can't read: {row['Filing Date']!r}") from exc
        race = _race(office)
        if race is not None:
            found.append((race, _name(name), _text(row["Party"]).title(), filed))
    if not found:
        raise ValueError("no candidates")
    majors = Counter((race.office_id, code) for race, _, label, _ in found if (code := party(label)[0]) in ("D", "R"))
    if twice := sorted({office_id for (office_id, _), n in majors.items() if n > 1}):
        raise ValueError(f"two candidates of one party in {', '.join(twice)}: a primary's list")
    newest = max(filed for *_, filed in found)
    year = newest.year + newest.year % 2
    day = first_tuesday_after_first_monday(year, 11)
    if newest > day:
        day = first_tuesday_after_first_monday(year + 2, 11)
    filings = []
    for race, name, label, _ in sorted(found, key=lambda f: (_rank(f[0]), party_rank(*party(f[2])), f[1])):
        code, party_name = party(label)
        filings.append(race.filing(day=day.isoformat(), name=name, party=code, party_name=party_name,
                                   order=len(filings)))
    return require(filings, MINIMUM)


class WvList(ManualList):
    state = "WV"
    source = "state_wv"
    label = "West Virginia Secretary of State"
    page = "https://candidates.wvsos.gov/"
    description = ("West Virginia's official list of the candidates for Congress and its Legislature, from its "
                   "Secretary of State, imported by hand.")
    folder = "manual/state_wv"
    scope_note = ("The unexpired terms of circuit and family court judges, county races and the amendments aren't "
                  "shown: your county clerk has your sample ballot.")

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, str):
            raise ValueError("not a CSV")
        return parse_rows(raw)


SOS = "https://sos.wv.gov/elections"
APPS = "https://apps.sos.wv.gov/Elections/Voter"
GUIDE = Guide(
    name="West Virginia",
    source="West Virginia Secretary of State",
    url=SOS,
    computed=True,
    registration_url="https://ovr.sos.wv.gov/Register/Landing",
    mail_url="https://sos.wv.gov/absentee-voting-information",
    register="The last day to register to vote in {election} in West Virginia: online, in person at your county "
             "clerk's office, or by mail postmarked today. There's no registering on Election Day.",
    mail_summary="Absentee application due",
    mail="If you vote absentee in {election}, your application must reach your county clerk today. Mail your ballot "
         "back postmarked by Election Day. Who can vote absentee, and how to apply:",
    early_where="Early voting runs during your county's business hours on weekdays and 9 a.m. to 5 p.m. on Saturdays, "
                "at the courthouse and any other sites your county sets.",
    credit="Dates worked out from West Virginia's election law; more from the West Virginia Secretary of State",
    poll_hours="6:30 a.m. – 7:30 p.m.",
    check_url=f"{APPS}/AmIRegisteredToVote",
    check_hint="West Virginia Secretary of State: your registration",
    where_url=f"{APPS}/FindMyPollingPlace",
    where_hint="West Virginia Secretary of State: your polling place",
    mail_label="How to vote absentee",
    mail_eligibility=only_if("you're ill, injured, disabled or immobile", "you'll be away from your county for all of "
                             "early voting and Election Day", "your work hours keep you from voting in person",
                             "you're in the military or overseas")
    + " Mail your ballot back postmarked by Election Day.",
    mail_deadline="Absentee applications must reach your county clerk by ",
)
RULE = Counts(21, 6, 13, 3).rule("WV")  # registration closes on a Tuesday and applications on a Wednesday: no weekend
