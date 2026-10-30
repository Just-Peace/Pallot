"""Tennessee: the Secretary of State's general election candidate lists, one spreadsheet per office
(sos.tn.gov/elections/2026-candidate-lists: Governor_Nov2026.xlsx, USSenate_, USHouse_, TNSenate_,
TNHouse_), saved by hand into one folder (manual/state_tn): CloudFront answers 403 to scripts on
sos.tn.gov and its file host, so Pallot never asks them.

Each sheet is a row per candidate: the office with its district ("Tennessee House of
Representatives District 3"), the name, the party ("Party" or "Party Name") and the candidate's
city, which isn't kept. They are the general election's lists: primary losers are off them, and
no race has two candidates of one party, which the reader refuses. A district where no one
qualified has a row saying so ("No Candidate Qualified"), which is skipped. The sheets name no
election date, only their file names do ("_Nov2026"), so the import takes the folder and dates
every candidate by the general election of that year.

Placed: Governor, the U.S. Senate, the U.S. House (nine districts, on the map enacted in 2026,
which the Census geocoder's districts already are), the State Senate (its odd- or even-numbered
half up) and the State House (all 99). The races are in the ballot's order, each race's
candidates in the list's. An office it doesn't know is refused, and so is a folder missing one of
the five lists.

Tennessee's key dates, for its general election (the Tuesday after the first Monday of November,
Tenn. Code Ann. §2-1-104), the same as the Secretary of State's "Key Dates for the 2026 Election
Cycle" gives (seen as quoted by the press: its site turns scripts away): registration closes 30 days before (§2-2-109), always a Sunday, so the next day (§1-3-102,
Roll past a Sunday only); early voting runs from the 20th day before to the 5th (§2-6-102(a)(1));
an absentee application must reach the county election commission 10 days before (§2-6-202(a)(1),
as Public Chapter 560 of 2024 has it from November 6, 2024), always a Saturday, and the ballot by
the close of the polls. Absentee voting needs one of the reasons in §2-6-201. Polls close at 7 p.m.
Central time and 8 p.m. Eastern; the county election commission sets the opening, so that the
polls are open at least 10 hours (§2-7-103). 2026: register by Oct 5, early voting Oct 14 – 29,
absentee application by Oct 24.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from . import (Filing, ManualList, Office, legislator, party, require, sheet_rows, statewide, us_house,
               us_senate)
from .dates import Counts, Guide, Roll, first_tuesday_after_first_monday, only_if

MINIMUM = {"cd": 9}
LISTS = ("Governor", "U.S. Senate", "U.S. House", "State Senate", "State House")  # each sheet's office, in ballot order
NONE_QUALIFIED = "NO CANDIDATE QUALIFIED"
_YEAR = re.compile(r"_Nov(\d{4})\.xlsx$", re.I)
_DISTRICT = re.compile(r"(United States House of Representatives|Tennessee Senate|Tennessee House of Representatives)"
                       r" District (\d+)", re.I)


def _race(office: str) -> tuple[int, Office]:
    """A row's race, and which of LISTS it's in; ValueError for an office it doesn't know."""
    if office.upper() == "GOVERNOR":
        return 0, statewide("Governor")
    if office.upper() == "UNITED STATES SENATE":
        return 1, us_senate("TN")
    if found := _DISTRICT.fullmatch(office):
        body, number = found.group(1).upper(), int(found.group(2))
        if body.startswith("UNITED"):
            return 2, us_house("TN", number)
        return (3, legislator("sd", number)) if "SENATE" in body else (4, legislator("hd", number))
    raise ValueError(f"an office it doesn't know: {office}")


def _rows(raw: bytes) -> list[tuple[str, str, str]]:
    """A sheet's (office, name, party) rows, by its header's column names."""
    _, rows = sheet_rows(raw)
    if not rows:
        raise ValueError("an empty sheet")
    header = [cell.upper() for cell in rows[0]]
    try:
        office, name = header.index("OFFICE"), header.index("CANDIDATE")
        label = next(i for i, cell in enumerate(header) if cell.startswith("PARTY"))
    except (ValueError, StopIteration) as exc:
        raise ValueError(f"no Office, Candidate and Party columns: {rows[0]}") from exc

    def cell(row: list[str], at: int) -> str:
        return row[at] if at < len(row) else ""

    return [(cell(row, office), cell(row, name), cell(row, label)) for row in rows[1:] if cell(row, office)]


def parse_books(books: dict[str, bytes]) -> list[Filing]:
    """Every candidate in the folder's spreadsheets ({file name: bytes}; other files are skipped),
    dated by the general election of the year in their names; ValueError for a folder that isn't
    the five lists of one November."""
    sheets = {name: raw for name, raw in books.items() if name.lower().endswith(".xlsx")}
    years = {found.group(1) for name in sheets if (found := _YEAR.search(name))}
    if len(years) != 1 or any(not _YEAR.search(name) for name in sheets):
        raise ValueError(f"not one November's lists (…_Nov2026.xlsx): {', '.join(sorted(sheets)) or 'no spreadsheets'}")
    day = first_tuesday_after_first_monday(int(years.pop()), 11).isoformat()
    found: list[tuple[int, int, int, Office, str, str]] = []
    for name in sorted(sheets):
        for office, candidate, label in _rows(sheets[name]):
            kind, race = _race(office)
            if candidate.upper() == NONE_QUALIFIED:
                continue
            found.append((kind, int(race.district or 0), len(found), race, candidate, label))
    kinds = {kind for kind, *_ in found}
    if missing := [LISTS[k] for k in range(len(LISTS)) if k not in kinds]:
        raise ValueError(f"no {', '.join(missing)} list")
    twice = [office for (office, _), n in Counter((race.office_id, party(label)[0]) for *_, race, _, label in found
                                                     if party(label)[0]).items() if n > 1]
    if twice:
        raise ValueError(f"two candidates of one party in {', '.join(sorted(twice))}: a primary's list")
    filings = []
    for *_, race, candidate, label in sorted(found, key=lambda f: f[:3]):
        code, party_name = party(label)
        filings.append(race.filing(day=day, name=candidate, party=code, party_name=party_name, order=len(filings)))
    return require(filings, MINIMUM)


class TnList(ManualList):
    state = "TN"
    source = "state_tn"
    label = "Tennessee Secretary of State"
    page = "https://sos.tn.gov/elections/2026-candidate-lists"
    description = ("Tennessee's official list of the candidates for Governor, Congress and its Legislature, from its "
                   "Secretary of State, imported by hand.")
    folder = "manual/state_tn"
    folders = True
    scope_note = ("County and city races and the constitutional amendments aren't shown: your county election "
                  "commission has your sample ballot.")

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, dict):
            raise ValueError("not a folder of spreadsheets")
        return parse_books(raw)


SOS = "https://sos.tn.gov/elections"
GOVOTE = "https://govotetn.gov"
GUIDE = Guide(
    name="Tennessee",
    source="Tennessee Secretary of State",
    url=SOS,
    computed=True,
    registration_url=GOVOTE,
    mail_url=GOVOTE,
    register="The last day to register to vote in {election} in Tennessee: online, in person at your county election "
             "commission, or by mail postmarked today. There's no registering on Election Day.",
    mail_summary="Absentee application due",
    mail="If you vote absentee in {election}, your application must reach your county election commission today. Your "
         "ballot must be back by the time the polls close on Election Day. Who can vote absentee, and how to apply:",
    early_where="Your county election commission sets the places and hours of early voting, Monday through Saturday.",
    credit="Dates worked out from Tennessee's election law; more from the Tennessee Secretary of State",
    poll_hours="7 p.m. Central, 8 p.m. Eastern",
    polls_text="Polls close at 7 p.m. Central time, 8 p.m. Eastern time; your county election commission sets when "
               "they open. If you're in line when they close, you can vote.",
    hours_set_by="your county election commission",
    check_url=GOVOTE,
    check_hint="GoVoteTN (Tennessee Secretary of State): your registration, your polling place and your sample ballot",
    where_url=GOVOTE,
    where_hint="GoVoteTN: your polling place and your county's early voting sites",
    mail_label="How to vote absentee",
    mail_eligibility=only_if("you'll be out of your county during early voting and on Election Day",
                             "you're 60 or older", "you're ill, hospitalized or disabled, or caring for someone who is",
                             "you're a student away from your county, or their spouse",
                             "you're in the military or overseas")
    + " Your ballot must be back by the time the polls close on Election Day.",
    mail_deadline="Your application must reach your county election commission by ",
)
RULE = Counts(30, 10, 20, 5, roll=Roll(saturday=False)).rule("TN")
