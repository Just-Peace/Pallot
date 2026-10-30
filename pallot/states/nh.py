"""New Hampshire: the Secretary of State's general election candidate list, a PDF
(mm.nh.gov/files/uploads/sos/docs/{year}-ge-candidate-list.pdf), saved by hand (manual/state_nh):
Akamai answers "Access Denied" to scripts on sos.nh.gov and mm.nh.gov, browser headers included,
so Pallot never asks it. The maintainer has the PDF's table transcribed to CSV (by an AI tool, in
2026) and imports that.

A row per candidate: the office ("State Representative"), the district ("District 2", or a county
and its district, "HILLSBOROUGH District 12"), the name, the town they live in, the address and
the party (DEM, REP, LIB, CON, IND…). It's the general election's ballot, so primary losers are
off it; a candidate nominated by two parties is on it twice, and is kept once with both. Only
the name, office, district and party are kept. It names no election, so its filings are dated by
ELECTION, the general election of the year the list is for.

Placed: Governor (elected every two years), the U.S. Senate, the U.S. House (two districts), the
State Senate (24 districts) and the State House: 400 seats in 203 districts named by county, as
RSA 662:5 (2022, 9:1) draws them. 164 of those are base districts, the Census's State House
districts ("Hillsborough 12"); the other 39 are floterials, each made of whole base districts
(FLOTERIALS) and on the ballot of every voter in them, so a voter has both their base district's
race and their floterial's. SEATS gives each district's seats from the same table. The Executive
Council's five districts, which the Census doesn't know, and the county offices (commissioner,
sheriff, county attorney, treasurer, registers of deeds and probate) are left out with a ballot
note. An office it doesn't know is refused, as is a row with a column's name for a name (a
transcription's slip).

New Hampshire's key dates, for its general election (the Tuesday after the first Monday of
November, RSA 653:1), checked on gc.nh.gov on 2026-10-29: a voter can register with the town or
city clerk until the supervisors of the checklist's last session before the election, which each
town sets 6 to 13 days before (RSA 654:8, II; 654:27), and at the polling place on Election Day
(RSA 654:7-a), so there's no one deadline. Voting absentee needs a reason: away from town on
Election Day, a religious commitment, a disability, or work or caring for children or infirm
adults during all the polling hours (RSA 657:1). An application by mail has no deadline; the
clerk's office takes applications and absentee votes in person on the day before until at least
5 p.m. (RSA 657:1, II(c); 652:20), and a ballot must reach the clerk by 5 p.m. on Election Day
(RSA 657:22). There's no early voting. Polls open by 11 a.m. and close at 7 p.m. or later, as each
town or city sets (RSA 659:4). 2026: apply in person by Mon Nov 2.
"""

from __future__ import annotations

import csv
import dataclasses
import io
from typing import Any

from . import Filing, ManualList, Office, legislator, party, party_rank, require, statewide, us_house, us_senate
from .dates import Counts, Guide, first_tuesday_after_first_monday, only_if

ELECTION = first_tuesday_after_first_monday(2026, 11)  # the list's election: its file names the year, its rows don't
COLUMNS = ("Office / Section", "District / County", "Candidate Name", "Party")
MINIMUM = {"cd": 2, "sd": 24, "hd": 190}  # every district is up: a few can go without a candidate
PARTIES = {"DEM": "Democratic", "REP": "Republican", "LIB": "Libertarian", "CON": "Constitution",
           "IND": "Independent"}
LEFT_OUT = frozenset({"EXECUTIVE COUNCILOR", "COUNTY COMMISSIONER", "SHERIFF", "COUNTY ATTORNEY", "COUNTY TREASURER",
                      "REGISTER OF DEEDS", "REGISTER OF PROBATE"})
# Each county's State House districts' seats, by district number (RSA 662:5).
SEATS = {
    "Belknap": (1, 2, 1, 1, 4, 4, 3, 2),
    "Carroll": (3, 2, 2, 2, 1, 2, 1, 2),
    "Cheshire": (1, 1, 1, 1, 1, 2, 1, 1, 1, 2, 1, 1, 1, 1, 2, 1, 1, 2),
    "Coos": (2, 1, 1, 1, 2, 1, 1),
    "Grafton": (3, 1, 1, 1, 2, 1, 1, 3, 1, 1, 1, 4, 1, 1, 1, 1, 1, 1),
    "Hillsborough": (4, 7, 3, 3, 3, 3, 3, 3, 3, 3, 3, 8, 6, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1, 2, 4, 3, 1, 3, 2,
                     3, 2, 2, 1, 2, 2, 4, 3, 3, 4, 2, 1),
    "Merrimack": (1, 1, 2, 2, 2, 1, 2, 3, 4, 4, 1, 2, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 1, 1, 1),
    "Rockingham": (3, 3, 1, 3, 2, 1, 1, 1, 2, 3, 4, 2, 10, 2, 2, 7, 4, 2, 1, 3, 1, 1, 1, 2, 9, 1, 1, 1, 4, 2, 2, 1, 1,
                   1, 1, 1, 1, 1, 1, 1),
    "Strafford": (2, 3, 1, 3, 1, 1, 1, 1, 1, 4, 3, 4, 1, 1, 1, 1, 1, 1, 3, 1, 3),
    "Sullivan": (1, 1, 3, 1, 1, 3, 1, 2),
}
# Each floterial district -> the base districts of its county it's made of (RSA 662:5).
FLOTERIALS = {
    "Belknap 8": (3, 4), "Carroll 7": (5, 6), "Carroll 8": (3, 4), "Cheshire 15": (1, 2, 3, 4, 5, 6),
    "Cheshire 16": (7, 8, 9), "Cheshire 17": (10, 11, 12), "Cheshire 18": (13, 14), "Coos 7": (4, 5),
    "Grafton 17": (13, 14, 15), "Grafton 18": (9, 10, 11, 16), "Hillsborough 37": (34, 43), "Hillsborough 38": (13, 14),
    "Hillsborough 39": (15, 16, 20), "Hillsborough 40": (18, 19, 21, 22, 23), "Hillsborough 41": (17, 24, 25, 26),
    "Hillsborough 44": (28, 29), "Hillsborough 45": (35, 36), "Merrimack 25": (2, 3), "Merrimack 26": (1, 4, 5),
    "Merrimack 27": (10, 11, 14), "Merrimack 28": (15, 16, 17), "Merrimack 29": (18, 23, 24),
    "Merrimack 30": (19, 20, 21, 22), "Rockingham 31": (2, 3), "Rockingham 32": (6, 7, 8), "Rockingham 33": (10, 11, 12),
    "Rockingham 34": (14, 15), "Rockingham 35": (16, 17), "Rockingham 36": (19, 20), "Rockingham 37": (21, 22),
    "Rockingham 38": (23, 24), "Rockingham 39": (26, 27, 28), "Rockingham 40": (29, 30), "Strafford 18": (3, 4),
    "Strafford 19": (5, 6, 7, 8, 9), "Strafford 20": (10, 11), "Strafford 21": (13, 14, 15, 16, 17),
    "Sullivan 7": (2, 3), "Sullivan 8": (4, 5, 6),
}
_NOT_NAMES = frozenset({"CANDIDATE NAME", "DOMICILE", "CANDIDATE ADDRESS", "CITY/STATE/ZIP", "PARTY"})


def _text(value: str | None) -> str:
    return " ".join((value or "").split())


def _number(district: str) -> int:
    """"District 2" -> 2; ValueError for anything else."""
    words = district.split()
    if len(words) != 2 or words[0].upper() != "DISTRICT" or not words[1].isdigit():
        raise ValueError(f"a district it doesn't know: {district!r}")
    return int(words[1])


def house(district: str) -> Office:
    """A State House district's race: "HILLSBOROUGH District 12" is the Census's "Hillsborough 12";
    a floterial is placed by the base districts it's made of too ("Hillsborough 37,Hillsborough 34,…")."""
    county, _, rest = district.partition(" ")
    county = county.title()
    number = _number(rest)
    if county not in SEATS or not 1 <= number <= len(SEATS[county]):
        raise ValueError(f"a State House district it doesn't know: {district!r}")
    name = f"{county} {number}"
    places = ",".join([name, *(f"{county} {base}" for base in FLOTERIALS.get(name, ()))])
    race = legislator("hd", places, office_id=f"STATE HOUSE {name.upper()}",
                      office=f"State Representative, {county} District {number}")
    return dataclasses.replace(race, seats=SEATS[county][number - 1])


def _race(office: str, district: str) -> Office | None:
    """The race of a row; None for one left out. ValueError for one it doesn't know."""
    key = office.upper()
    if key == "GOVERNOR":
        return statewide("Governor")
    if key == "UNITED STATES SENATOR":
        return us_senate("NH")
    if key == "REPRESENTATIVE IN CONGRESS":
        return us_house("NH", _number(district))
    if key == "STATE SENATOR":
        return legislator("sd", _number(district))
    if key == "STATE REPRESENTATIVE":
        return house(district)
    if key in LEFT_OUT:
        return None
    raise ValueError(f"an office it doesn't know: {office}")


def _rank(race: Office) -> tuple[int, str, int]:
    """Where a race comes on the ballot: Governor, Congress, the Senate, the House."""
    order = {"GOVERNOR": 0, "US SENATE": 1, "US HOUSE": 2, "STATE SENATE": 3, "STATE HOUSE": 4}[race.family]
    if race.reach == "hd":
        county, number = race.office_id.removeprefix("STATE HOUSE ").rsplit(" ", 1)
        return order, county, int(number)
    return order, "", int(race.district or 0)


def parse_rows(text: str) -> list[Filing]:
    """Every candidate in the CSV, dated ELECTION; ValueError for a file that isn't the list (its
    columns missing, an office or district it doesn't know, a row that isn't a candidate, fewer
    than MINIMUM's races)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = [name for name in COLUMNS if name not in (reader.fieldnames or ())]
    if missing:
        raise ValueError(f"no {', '.join(missing)} column{'s' if len(missing) > 1 else ''}")
    found: dict[tuple[str, str], tuple[Office, list[str]]] = {}
    for row in reader:
        name, office = _text(row["Candidate Name"]), _text(row["Office / Section"])
        if not name and not office:
            continue
        if name.upper() in _NOT_NAMES or not office:
            raise ValueError(f"a row that isn't a candidate: {name or '(no name)'}, {office or '(no office)'}")
        race = _race(office, _text(row["District / County"]))
        if race is None:
            continue
        label = _text(row["Party"]).upper()
        _, labels = found.setdefault((race.office_id, name), (race, []))
        if label and label not in labels:
            labels.append(label)
    if not found:
        raise ValueError("no candidates")
    candidates = []
    for (_, name), (race, labels) in found.items():
        names = [PARTIES.get(label, label) for label in labels]
        parties = sorted((party(each) for each in names), key=lambda p: party_rank(*p))
        code, party_name = parties[0] if parties else (None, None)
        if len(names) > 1:
            party_name = " / ".join(PARTIES.get(label, label) for label in sorted(
                labels, key=lambda label: party_rank(*party(PARTIES.get(label, label)))))
        candidates.append((race, name, code, party_name))
    filings = []
    for race, name, code, party_name in sorted(candidates, key=lambda c: (_rank(c[0]), party_rank(c[2], c[3]), c[1])):
        filings.append(race.filing(day=ELECTION.isoformat(), name=name, party=code, party_name=party_name,
                                   order=len(filings)))
    return require(filings, MINIMUM)


class NhList(ManualList):
    state = "NH"
    source = "state_nh"
    label = "New Hampshire Secretary of State"
    page = "https://www.sos.nh.gov/elections"
    description = ("New Hampshire's official list of the candidates for Governor, Congress and its Legislature, from "
                   "its Secretary of State, imported by hand.")
    folder = "manual/state_nh"
    scope_note = ("The Executive Council, your county's races (commissioner, sheriff, county attorney and the like) and "
                  "any questions aren't shown: your town or city clerk has your sample ballot.")

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, str):
            raise ValueError("not a CSV")
        return parse_rows(raw)


SOS = "https://www.sos.nh.gov/elections"
VOTER_INFO = "https://app.sos.nh.gov/voterinformation"
GUIDE = Guide(
    name="New Hampshire",
    source="New Hampshire Secretary of State",
    url=SOS,
    computed=True,
    registration_url=SOS,
    mail_url=f"{SOS}/absentee-ballots",
    register="",
    mail_summary="Last day to vote absentee in person",
    mail="If you vote absentee in {election}, today is the last day to apply and vote at your town or city clerk's "
         "office, open until at least 5 p.m. Apply by mail sooner, so your ballot can reach you and get back: it must "
         "reach your clerk by 5 p.m. on Election Day. Who can vote absentee, and how to apply:",
    early_where="",
    credit="Dates worked out from New Hampshire's election law; more from the New Hampshire Secretary of State",
    poll_hours="7 p.m. or later",
    check_url=VOTER_INFO,
    check_hint="Voter Information Lookup (New Hampshire Secretary of State): your registration and your polling place",
    where_url=VOTER_INFO,
    where_hint="Voter Information Lookup: your polling place",
    mail_label="How to vote absentee",
    mail_eligibility=only_if("you'll be away from your town on Election Day", "a religious commitment keeps you home",
                             "you have a disability",
                             "work or caring for children or infirm adults keeps you away all the hours the polls "
                             "are open")
    + " Your ballot must reach your town or city clerk by 5 p.m. on Election Day.",
    mail_deadline="Apply and vote in person at your town or city clerk's office by 5 p.m. on ",
    local_office="Your town or city clerk",
    polls_text="Polls open by 11 a.m. and close at 7 p.m. or later, as your town or city sets; if you're in line at "
               "closing time, you can vote. Not registered yet? Register at your polling place when you vote.",
    late_registration="Register with your town or city clerk until your supervisors of the checklist's last session, "
                      "6 to 13 days before, or at your polling place on Election Day, with proof of who you are and "
                      "where you live",
    hours_set_by="your town or city",
)
RULE = Counts(None, 1, None, None).rule("NH")  # register at the polls; no early voting
