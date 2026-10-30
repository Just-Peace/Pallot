"""Arkansas: the Secretary of State's candidate search (candidates.arkansas.gov), saved by hand
(manual/state_ar): the page has no file to download and no general-election view, so the maintainer
exports its table to CSV in a browser, and Pallot never asks it.

The search is labelled the year's preferential primary, but it keeps only the candidates still in
a race: primary losers and the withdrawn are off it, and nominees named later (Libertarians, by
convention; independents; a party's replacement) are on it. On 2026-10-29 its 198 rows were, race
for race, the general election's ballot as the Secretary of State's results site (arkansas.tally-
enr.com, "2026 General Election & Judical Runoff") had it set up.

Each row is a candidate: the name (with any title the candidate filed under, "Senator Tom Cotton",
which is dropped), the office with its district ("State Representative District 08"), the party and
the filing date. It names no election, so its filings are dated by the general election after its
newest filing. The House's District 8 has two races in 2026, its full term and a special election
for the rest of the present one, under one office name: the special's candidates are the ones who
filed for it after SPECIALS' day.

Placed: the U.S. Senate, the U.S. House (four districts), the statewide offices, the State Senate
and the State House. The nonpartisan runoffs for circuit judge and prosecuting attorney, elected by
judicial districts of several counties, are left out with a ballot note. An office it doesn't know
is refused, so a new one is seen rather than dropped.

Arkansas's key dates, for its general election (the Tuesday after the first Monday of November,
Ark. Code §7-5-102), checked against the Secretary of State's 2026 Election Calendar (rev. June
2025) and its absentee voting page: an application to register must be in 30 days before
(§7-5-201(a); Amendment 51 §9(b)), always a Sunday, so the deadline is the Monday after (§7-1-108,
Roll). Absentee voting needs an excuse (away from the polling site, ill or disabled, military or
overseas); an application by mail, fax or email must reach the county clerk 7 days before
(§7-5-404(a)(3)), in person by the Friday before, and the ballot by 7:30 p.m. on Election Day.
Early voting runs from 15 days before to 5 p.m. the day before (§7-5-418(a)(1)(A)). Polls are open
7:30 a.m. to 7:30 p.m. (§7-5-304(a)). 2026: register by Oct 5, apply by mail by Oct 27, early voting
Oct 19 – Nov 2.
"""

from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import io
import re
from typing import Any

from . import Filing, ManualList, Office, legislator, party, party_rank, require, statewide, us_house, us_senate
from .dates import Counts, Guide, Roll, first_tuesday_after_first_monday, only_if

COLUMNS = ("Candidate Name", "Position/Office", "Party Affiliation", "Filing Date")
STATEWIDE = ("Governor", "Lieutenant Governor", "Secretary of State", "Attorney General", "State Treasurer",
             "Auditor of State", "Commissioner of State Lands")
MINIMUM = {"cd": 4}
SPECIALS = {("hd", "8"): dt.date(2026, 8, 1)}  # a special election's district, and the day its filings start
LEFT_OUT = ("CIRCUIT JUDGE", "PROSECUTING ATTORNEY")
# The titles candidates filed under, before their names: longest first, so "State Senator" goes before "Senator".
TITLES = ("Justice of the Peace", "School Board Director", "Lieutenant Governor", "State Representative",
          "Commissioner of State Lands", "Secretary of State", "Attorney General", "Auditor of State", "State Treasurer",
          "Council Member", "State Senator", "Congresswoman", "Representative", "Congressman", "Governor", "Senator",
          "Sheriff", "Justice", "Mayor", "Rep.")
_TITLE = re.compile(rf"^(?:{'|'.join(re.escape(t) for t in TITLES)})\s+(?=\S+\s+\S)", re.I)
_CONGRESS = re.compile(r"U\.S\. Congress District (\d+)", re.I)
_LEGISLATURE = re.compile(r"State (Senate|Representative) District (\d+)", re.I)


def _text(value: str | None) -> str:
    return " ".join((value or "").split())


def _race(office: str) -> Office | None:
    """The race of a row's office; None for one left out. ValueError for one it doesn't know."""
    if office.upper() == "U.S. SENATE":
        return us_senate("AR")
    if found := _CONGRESS.fullmatch(office):
        return us_house("AR", int(found.group(1)))
    if found := _LEGISLATURE.fullmatch(office):
        return legislator("sd" if found.group(1).upper() == "SENATE" else "hd", int(found.group(2)))
    if title := next((t for t in STATEWIDE if t.upper() == office.upper()), None):
        return statewide(title)
    if office.upper().startswith(LEFT_OUT):
        return None
    raise ValueError(f"an office it doesn't know: {office}")


def _rank(race: Office) -> tuple[int, int]:
    """Where a race comes on the ballot: Congress, the statewide offices, the Senate, the House."""
    if race.family == "US SENATE":
        return 0, 0
    if race.family == "US HOUSE":
        return 1, int(race.district or 0)
    if race.reach == "state":
        return 2, next(i for i, t in enumerate(STATEWIDE) if t.upper() == race.family)
    return (3 if race.reach == "sd" else 4), int(race.district or 0)


def parse_rows(text: str) -> list[Filing]:
    """Every candidate in the CSV, dated by the general election after its newest filing;
    ValueError for a file that isn't the list (its columns missing, an office it doesn't know, no
    candidates, fewer than MINIMUM's races)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = [name for name in COLUMNS if name not in (reader.fieldnames or ())]
    if missing:
        raise ValueError(f"no {', '.join(missing)} column{'s' if len(missing) > 1 else ''}")
    found: list[tuple[Office, str, str, dt.date]] = []
    for row in reader:
        name, office = _text(row["Candidate Name"]), _text(row["Position/Office"])
        if not name or not office:
            continue
        try:
            filed = dt.date.fromisoformat(_text(row["Filing Date"]))
        except ValueError as exc:
            raise ValueError(f"a filing date it can't read: {row['Filing Date']!r}") from exc
        race = _race(office)
        if race is None:
            continue
        since = SPECIALS.get((race.reach, race.district or ""))
        if since and filed >= since:
            race = dataclasses.replace(race, office_id=f"{race.office_id} UNEXPIRED", unexpired=True)
        found.append((race, _TITLE.sub("", name), _text(row["Party Affiliation"]), filed))
    if not found:
        raise ValueError("no candidates")
    newest = max(filed for *_, filed in found)
    year = newest.year + newest.year % 2
    day = first_tuesday_after_first_monday(year, 11)
    if newest > day:
        day = first_tuesday_after_first_monday(year + 2, 11)
    filings = []
    for race, name, label, _ in sorted(found, key=lambda f: (_rank(f[0]), f[0].unexpired, party_rank(*party(f[2])), f[1])):
        code, party_name = party(label)
        filings.append(race.filing(day=day.isoformat(), name=name, party=code, party_name=party_name,
                                   order=len(filings)))
    return require(filings, MINIMUM)


class ArList(ManualList):
    state = "AR"
    source = "state_ar"
    label = "Arkansas Secretary of State"
    page = "https://candidates.arkansas.gov/"
    description = ("Arkansas's official list of the candidates for Congress, its statewide offices and its "
                   "Legislature, from its Secretary of State, imported by hand.")
    folder = "manual/state_ar"
    scope_note = ("The nonpartisan runoffs for circuit judge and prosecuting attorney, county and city races and the "
                  "ballot issues aren't shown: your county clerk has your sample ballot.")

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, str):
            raise ValueError("not a CSV")
        return parse_rows(raw)


SOS = "https://www.sos.arkansas.gov/elections"
VOTERVIEW = "https://www.voterview.ar-nova.org/voterview"
GUIDE = Guide(
    name="Arkansas",
    source="Arkansas Secretary of State",
    url=SOS,
    computed=True,
    registration_url=f"{SOS}/voter-information/voter-registration-information/",
    mail_url=f"{SOS}/voter-information/absentee-voting",
    register="The last day to apply to register to vote in {election} in Arkansas, at your county clerk's office or "
             "by mail. There's no registering on Election Day.",
    mail_summary="Absentee application due",
    mail="If you vote absentee in {election}, an application by mail, fax or email must reach your county clerk "
         "today; in person, you can apply until the Friday before. Your ballot must reach your county clerk by "
         "7:30 p.m. on Election Day. Who can vote absentee, and how to apply:",
    early_where="Early voting is 8 a.m. to 6 p.m. on weekdays and 10 a.m. to 4 p.m. on Saturdays, and ends at 5 p.m. "
                "on the Monday before Election Day. Your county lists the places.",
    credit="Dates worked out from Arkansas's election law; more from the Arkansas Secretary of State",
    poll_hours="7:30 a.m. – 7:30 p.m.",
    check_url=VOTERVIEW,
    check_hint="VoterView (Arkansas Secretary of State): your registration, your polling place and your sample ballot",
    where_url=VOTERVIEW,
    where_hint="VoterView: your polling place and your county's early voting sites",
    mail_label="How to vote absentee",
    mail_eligibility=only_if("you'll be away from your polling site on Election Day", "you're ill or disabled",
                             "you or your family are away on active military or merchant marine duty",
                             "you live outside the U.S. for now")
    + " Your ballot must reach your county clerk by 7:30 p.m. on Election Day.",
    mail_deadline="Applications by mail, fax or email must reach your county clerk by ",
)
RULE = Counts(30, 7, 15, 1, roll=Roll()).rule("AR")
