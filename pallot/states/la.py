"""Louisiana: the Secretary of State's candidate inquiry (voterportal.sos.la.gov/candidateinquiry),
a JavaScript page whose "Statewide/Multi-Parish" tab the maintainer exports to CSV in a browser
for one election date, saved by hand (manual/state_la); Pallot never asks it.

Each row is a candidate: the election's date ("11/03/2026"), the office ("U. S. Representative")
and its district ("1st Congressional District"), the seats, the ballot's first name, last name and
suffix, the party, and the outcome so far ("Unopposed", "Withdrew", "Other/Disq"). Its address,
phone, email, race and gender columns aren't kept. A first name prints its nickname in single
quotes ("Patricia 'Pat'"), kept in double quotes as other lists do, or only the nickname
("'Jamie'"), kept without them.

November 3, 2026 holds two kinds of contest on one ballot (the Secretary of State's 2026 elections
calendar, revised July 2026): the general election for the offices chosen in closed party
primaries in the spring (the U.S. Senate, the Public Service Commission, BESE and the Supreme
Court: one nominee a party, which the reader checks for the U.S. Senate), and the open primary
for the U.S. House (Act 7 of 2026 took it out of the closed party primaries for 2026) and for
state and local offices, where every candidate, of any party or none, runs together, so two of
one party in a race is usual: one who wins a majority is elected, else the top two meet on
December 12. Each open-primary race says so on the ballot (contest).

A candidate unopposed is elected without a vote and isn't on the ballot, nor is a withdrawn or
disqualified one: only rows with no outcome are kept.

Placed: the U.S. Senate, the U.S. House (six districts, on the map of Act 2 of 2026, which the
Census geocoder's districts already are: eight addresses checked against the Legislature's
shapefile for it, Shreveport and downtown Baton Rouge among them, all agreed) and any State Senate or
State House special election (House 92's in 2026). The Public Service Commission and BESE districts,
the judges, district attorneys and local offices are left out with a ballot note. An office it
doesn't know is refused.

Louisiana's key dates, for its November election (La. R.S. 18:402(B)), as the Secretary of
State's 2026 elections calendar has them: the registrar closes registration 30 days before
(R.S. 18:135(A)(1)), or 20 for one made online through GeauxVote (18:135(A)(3), 18:115.1), which
the calendar counts as the 21st day before, Oct 13 in 2026; early voting runs from 14 days before
to 7 days before, 8:30 a.m. to 6 p.m., but not on Sunday (18:1309); a mail ballot must be asked for
by 4:30 p.m. 4 days before (18:1307) and reach the registrar by 4:30 p.m. the day before
(18:1311), and needs one of the reasons in 18:1303 (65 or older among them). Polls are open 6 a.m.
to 8 p.m. (18:541). No registering on Election Day. 2026: register online by Oct 13 (in person or by
mail Oct 5), early voting Oct 20 – 27, mail ballot asked for by Oct 30.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from collections import Counter
from typing import Any

from ..models import Race
from . import Filing, ManualList, Office, legislator, party, require, us_house, us_senate
from .dates import Counts, Guide, only_if

COLUMNS = ("Election", "OfficeTitle", "OfficeTitleDescription", "NumberToBeElected", "BallotFirstName",
           "BallotLastName", "BallotSuffix", "Party", "Outcome")
MINIMUM = {"cd": 6}
OFF_BALLOT = {"UNOPPOSED", "WITHDREW", "OTHER/DISQ"}  # outcomes of candidates who aren't on the ballot
LEFT_OUT = {"PSC", "BESE", "ASSOCIATE JUSTICE", "JUDGE, COURT OF APPEAL", "DISTRICT JUDGE", "DISTRICT ATTORNEY", "JUDGE",
            "MAGISTRATE", "MAGISTRATE JUDGE", "CITY JUDGE", "CITY JUDGE, CITY COURT", "CITY MARSHAL", "MAYOR",
            "CHIEF OF POLICE", "ALDERMAN", "ALDERMEN", "ALDERMAN AT LARGE", "COUNCILMAN", "COUNCILMAN AT LARGE",
            "COUNCIL MEMBER", "SHERIFF", "CONSTABLE", "JUSTICE OF THE PEACE"}
OPEN_PRIMARY = ("Open Primary", "Louisiana's open primary: every candidate, of any party or none, runs together. One who "
                "wins more than half the votes is elected; if no one does, the top two meet again in December.")
_NUMBERED = re.compile(r"(\d+)(?:st|nd|rd|th) (Congressional|Representative|Senatorial) District", re.I)
_NICKNAME = re.compile(r"(?<![\w'])'([^']+)'(?![\w'])")


def _text(value: str | None) -> str:
    return " ".join((value or "").split())


def _name(first: str, last: str, suffix: str) -> str:
    """The ballot's name: "'Jamie'" + "Davis" is "Jamie Davis"; "Patricia 'Pat'" + "Moore" is
    'Patricia "Pat" Moore'; a suffix after the surname ("Troy A. Carter Sr.")."""
    first = _NICKNAME.fullmatch(first).group(1) if _NICKNAME.fullmatch(first) else _NICKNAME.sub(r'"\1"', first)
    return " ".join(part for part in (first, last, suffix) if part)


def _race(office: str, district: str) -> Office | None:
    """The race of a row's office and district; None for one left out. ValueError for one it doesn't know."""
    title = office.upper().replace("U. S.", "U.S.")
    if title == "U.S. SENATOR":
        return us_senate("LA")
    found = _NUMBERED.fullmatch(district)
    if title == "U.S. REPRESENTATIVE" and found and found.group(2).upper() == "CONGRESSIONAL":
        return us_house("LA", int(found.group(1)))
    if title in ("STATE REPRESENTATIVE", "STATE SENATOR") and found and found.group(2).upper() != "CONGRESSIONAL":
        return legislator("hd" if title == "STATE REPRESENTATIVE" else "sd", int(found.group(1)))
    if title in LEFT_OUT:
        return None
    raise ValueError(f"an office it doesn't know: {office} {district}".strip())


def _rank(race: Office) -> tuple[int, int]:
    """Where a race comes on the ballot: the U.S. Senate, the U.S. House, the State Senate, the State House."""
    return {"US SENATE": 0, "US HOUSE": 1, "STATE SENATE": 2}.get(race.family, 3), int(race.district or 0)


def parse_rows(text: str) -> list[Filing]:
    """Every candidate on the ballot in the CSV, dated by its election; ValueError for a file that
    isn't the list (its columns missing, an office or outcome it doesn't know, a U.S. Senate race
    with two candidates of one party, no candidates, fewer than MINIMUM's races)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = [name for name in COLUMNS if name not in (reader.fieldnames or ())]
    if missing:
        raise ValueError(f"no {', '.join(missing)} column{'s' if len(missing) > 1 else ''}")
    found: list[tuple[Office, str, str, str, int, str]] = []
    for row in reader:
        office, last = _text(row["OfficeTitle"]), _text(row["BallotLastName"])
        if not office or not last:
            continue
        outcome = _text(row["Outcome"]).upper()
        if outcome in OFF_BALLOT:
            continue
        if outcome:
            raise ValueError(f"an outcome it doesn't know: {row['Outcome']}")
        race = _race(office, _text(row["OfficeTitleDescription"]))
        if race is None:
            continue
        try:
            day = dt.datetime.strptime(_text(row["Election"]), "%m/%d/%Y").date().isoformat()
            seats = int(_text(row["NumberToBeElected"]) or 1)
        except ValueError as exc:
            raise ValueError(f"an election date or seats it can't read: {row['Election']!r}, "
                             f"{row['NumberToBeElected']!r}") from exc
        if race.reach in ("sd", "hd"):
            race = Office(f"{race.office_id} UNEXPIRED", race.office, race.family, race.group, race.reach,
                          race.district, unexpired=True)  # the Legislature's next regular election is in 2027
        name = _name(_text(row["BallotFirstName"]), last, _text(row["BallotSuffix"]))
        found.append((race, name, last, _text(row["Party"]), seats, day))
    if not found:
        raise ValueError("no candidates")
    senate = Counter((day, label) for race, *_, label, _, day in found if race.family == "US SENATE")
    if any(count > 1 for count in senate.values()):
        raise ValueError("two U.S. Senate candidates of one party: a party primary's list")
    filings = []
    for race, name, _, label, seats, day in sorted(found, key=lambda f: (f[5], _rank(f[0]), f[2], f[1])):
        code, party_name = party(None if label.upper() == "NO PARTY" else label)
        filings.append(race.filing(day=day, name=name, party=code, party_name=party_name, seats=seats,
                                   order=len(filings)))
    return require(filings, MINIMUM)


class LaList(ManualList):
    state = "LA"
    source = "state_la"
    label = "Louisiana Secretary of State"
    page = "https://voterportal.sos.la.gov/candidateinquiry"
    description = ("Louisiana's official list of the candidates for Congress and any special election for its "
                   "Legislature, from its Secretary of State, imported by hand.")
    folder = "manual/state_la"
    scope_note = ("The Public Service Commission and BESE, the judges, district attorneys, parish and city races and "
                  "the constitutional amendments aren't shown, nor any candidate unopposed, who is elected without a "
                  "vote: your sample ballot on the Secretary of State's Voter Portal has them.")

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, str):
            raise ValueError("not a CSV")
        return parse_rows(raw)

    @classmethod
    def contest(cls, race: Race) -> tuple[str, str] | None:
        """Every race but the U.S. Senate's is an open primary in 2026 (the module's docstring)."""
        return None if race.seat == "LA-SEN" else OPEN_PRIMARY


SOS = "https://www.sos.la.gov/elections-voting"
PORTAL = "https://voterportal.sos.la.gov"
GUIDE = Guide(
    name="Louisiana",
    source="Louisiana Secretary of State",
    url=SOS,
    computed=True,
    registration_url=f"{SOS}/register-to-vote",
    mail_url=PORTAL,
    register="The last day to register to vote online (GeauxVote) for {election} in Louisiana; in person at your "
             "parish registrar of voters or by mail, registration closed 30 days before. There's no registering on "
             "Election Day.",
    mail_summary="Mail ballot request due",
    mail="If you vote by mail in {election}, ask your parish registrar of voters for a ballot by 4:30 p.m. today. "
         "Your ballot must reach the registrar by 4:30 p.m. the day before Election Day. Who can vote by mail, and "
         "how to ask:",
    early_where="Early voting is 8:30 a.m. to 6 p.m. every day but Sunday, at your parish registrar of voters' office "
                "and any other early voting sites in your parish.",
    credit="Dates worked out from Louisiana's election code; more from the Louisiana Secretary of State",
    poll_hours="6 a.m. – 8 p.m.",
    check_url=PORTAL,
    check_hint="The Voter Portal (Louisiana Secretary of State): your registration, your polling place and your "
               "sample ballot",
    where_url=PORTAL,
    where_hint="The Voter Portal: your polling place; your parish registrar of voters lists its early voting sites",
    mail_label="How to vote by mail",
    mail_eligibility=only_if("you're 65 or older", "you'll be away from your parish on Election Day and during early "
                             "voting", "you're ill or disabled", "you're a student, in the military or overseas")
    + " Your ballot must reach your parish registrar of voters by 4:30 p.m. the day before Election Day.",
    mail_deadline="Ask your parish registrar of voters for a mail ballot by 4:30 p.m. on ",
    local_office="Your parish registrar of voters",
)
RULE = Counts(21, 4, 14, 7).rule("LA")  # always a Tuesday, a Friday, a Tuesday and a Tuesday: nothing to roll
