"""Idaho: the Secretary of State's candidate search (run.voteidaho.gov/search), a JavaScript app
whose API sits behind Cloudflare's bot check, so the maintainer exports the general election's
filed candidates to a spreadsheet in a browser, saved by hand (manual/state_id); Pallot never asks it.

Each row is a candidate: the ballot name, the election ("November 03, 2026 - 2026 General"), the
district type ("Federal", "Statewide", "State Legislature", "County", "Judicial", "Local"), the
office, its district and seat ("A", "B"), the party, the filing date, whether a write-in, and any
withdrawal. Its mailing address columns are never read: only the name, office, district and party
are kept. A withdrawn candidate is dropped, and the reader refuses another election, or a race with
two Democrats or two Republicans, which would mean a primary's list.

It is the general election's list, not the primary's: on 2026-10-30 every Democrat and Republican
on it for Congress, a statewide office or the Legislature (209) was the winner of their party's
May 19 primary on the Secretary of State's canvass (archive.voteidaho.gov/results/2026/primary/
canvass_report_2026_primary.pdf), and no primary loser is on it; five primary winners who withdrew
since (David Roth, the U.S. Senate's Democrat, among them) are off it. The Constitution Party's
nominees, independents and declared write-ins are on it.

Placed: the U.S. Senate, the U.S. House (two districts), the statewide offices, and the
Legislature's 35 districts, each with a State Senator and two State Representatives, Seat A and
Seat B, each seat its own race, placed by the district (the Census's State House district is the
legislative district's number).
The district judges, magistrate judges standing for retention and the county and local races are
left out with a ballot note. An office it doesn't know is refused.

Idaho's key dates, for its general election (the first Tuesday after the first Monday of November in
an even year, I.C. §34-101), checked on 2026-10-30 against the Idaho Code and the Secretary of
State's 2026 election calendar: registering ahead closes at 5 p.m. on the 11th day before (§34-408(1),
§34-410(4)), and you can register at the polls on Election Day (§34-408A) or while voting early
(§34-1012(3)); an absentee ballot's application must reach the county clerk by 5 p.m. on the 11th
day before (§34-1002(7)), and the ballot by 8 p.m. on Election Day (§34-1005); a county that offers
early voting may open it from the fourth Monday before, through 5 p.m. on the Friday before
(§34-1012(1)); the calendar opens it the next day when that Monday is Columbus Day, a state holiday
(§73-108). Polls are open 8 a.m. to 8 p.m. (§34-1101), each place's own time across Idaho's two
time zones. Any voter can vote absentee. 2026: register by Oct 23 (or on Election Day), apply by
Oct 23, early voting Oct 13 - Oct 30.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import re
from collections import Counter
from typing import Any

from ..sources.key_dates import Deadlines
from . import Filing, ManualList, Office, legislator, party, party_rank, require, sheet_rows, statewide, us_house, us_senate
from .dates import Counts, Guide, columbus_day

COLUMNS = ("Ballot Name", "Election Date - Name", "District Type", "Office", "District", "Seat/Zone",
           "Party Affiliation", "Write-In", "Withdrawal Date")
MINIMUM = {"cd": 2, "sd": 35, "hd": 35}
STATEWIDE = ("Governor", "Lieutenant Governor", "Secretary of State", "State Controller", "State Treasurer",
             "Attorney General", "Superintendent of Public Instruction")
LEFT_OUT = ("County", "Judicial", "Local")
_ELECTION = re.compile(r"([A-Z][a-z]+ \d{2}, \d{4}) - \d{4} General", re.I)


def _race(kind: str, office: str, district: str, seat: str) -> Office | None:
    """The race of a row's district type, office, district and seat; None for one left out.
    ValueError for one it doesn't know."""
    if kind in LEFT_OUT:
        return None
    if office == "United States Senator":
        return us_senate("ID")
    if office == "United States Representative" and district.isdigit():
        return us_house("ID", int(district))
    if office in STATEWIDE:
        return statewide(office)
    if office == "State Senator" and district.isdigit():
        return legislator("sd", int(district))
    if office == "State Representative" and district.isdigit() and seat in ("A", "B"):
        number = int(district)
        return legislator("hd", number, f"STATE HOUSE {number} SEAT {seat}",
                          f"State Representative District {number} Seat {seat}")
    raise ValueError(f"an office it doesn't know: {kind}, {office} {district} {seat}".strip())


def _rank(race: Office) -> tuple[int, int, str]:
    """Where a race comes on the ballot: the U.S. Senate, the U.S. House, the statewide offices in
    STATEWIDE's order, then each district's State Senator and its Seats A and B."""
    if race.family == "US SENATE":
        return 0, 0, ""
    if race.family == "US HOUSE":
        return 1, int(race.district or 0), ""
    if race.group == "state":
        return 2, STATEWIDE.index(race.office), ""
    return 3, int(race.district or 0), race.office_id if race.reach == "hd" else ""


def parse_rows(rows: list[list[str]]) -> list[Filing]:
    """Every candidate in the export's rows (its header first); ValueError for one that isn't the
    list (its columns missing, another election, an office it doesn't know, two Democrats or two
    Republicans in a race, no candidates, fewer than MINIMUM's races)."""
    if not rows:
        raise ValueError("an empty sheet")
    header = rows[0]
    missing = [name for name in COLUMNS if name not in header]
    if missing:
        raise ValueError(f"no {', '.join(missing)} column{'s' if len(missing) > 1 else ''}")
    at = {name: header.index(name) for name in COLUMNS}
    found: list[tuple[Office, str, str, bool]] = []
    days: set[dt.date] = set()
    for row in rows[1:]:
        cells = {name: row[i].strip() if i < len(row) else "" for name, i in at.items()}
        name = cells["Ballot Name"]
        if not name:
            continue
        election = _ELECTION.fullmatch(cells["Election Date - Name"])
        if not election:
            raise ValueError(f"not a general election's list: {cells['Election Date - Name']!r}")
        days.add(dt.datetime.strptime(election.group(1), "%B %d, %Y").date())
        if cells["Withdrawal Date"]:
            continue
        race = _race(cells["District Type"], cells["Office"], cells["District"], cells["Seat/Zone"].upper())
        if race is not None:
            found.append((race, name, cells["Party Affiliation"], cells["Write-In"].lower() == "yes"))
    if len(days) > 1:
        raise ValueError(f"more than one election: {', '.join(sorted(d.isoformat() for d in days))}")
    if not found:
        raise ValueError("no candidates")
    majors = Counter((race.office_id, code) for race, _, label, _ in found if (code := party(label)[0]) in ("D", "R"))
    if twice := sorted({office_id for (office_id, _), n in majors.items() if n > 1}):
        raise ValueError(f"two candidates of one party in {', '.join(twice)}: a primary's list")
    day = days.pop().isoformat()
    filings = []
    for race, name, label, write_in in sorted(found, key=lambda f: (_rank(f[0]), f[3], party_rank(*party(f[2])), f[1])):
        code, party_name = party(label)
        filings.append(race.filing(day=day, name=name, party=code, party_name=party_name, write_in=write_in,
                                   order=len(filings)))
    return require(filings, MINIMUM)


class IdList(ManualList):
    state = "ID"
    source = "state_id"
    label = "Idaho Secretary of State"
    page = "https://run.voteidaho.gov/search"
    description = ("Idaho's official list of the candidates for Governor, Congress, its other statewide offices and its "
                   "Legislature, from its Secretary of State, imported by hand.")
    folder = "manual/state_id"
    binary = True
    scope_note = ("The judges, county and local races and the measures aren't shown: your county clerk has your sample "
                  "ballot.")

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, bytes):
            raise ValueError("not a spreadsheet")
        return parse_rows(sheet_rows(raw)[1])


def idaho(day: dt.date) -> Deadlines | None:
    """Idaho's dates of the general election on ``day`` (the module's docstring gives the law):
    early voting opens the day after the fourth Monday before when that Monday is Columbus Day."""
    found = Counts(11, 11, 22, 4).on("ID", day)
    if found and found.early_start == columbus_day(day.year):
        return dataclasses.replace(found, early_start=found.early_start + dt.timedelta(days=1))
    return found


VOTER = "https://votertools.voteidaho.gov/TEDElectionLink/VoterServices"
GUIDE = Guide(
    name="Idaho",
    source="Idaho Secretary of State",
    url="https://voteidaho.gov/",
    computed=True,
    registration_url=f"{VOTER}/wizard/ovr",
    mail_url=f"{VOTER}/voter-search/oabr-voter-search",
    register="The last day to register ahead of {election} in Idaho: your registration must reach your county clerk "
             "by 5 p.m. After it, you can still register at your polling place on Election Day, or while voting early, "
             "with proof of who you are and where you live.",
    mail_summary="Absentee request due",
    mail="If you vote absentee in {election}, your request must reach your county clerk by 5 p.m. today, and your "
         "ballot by 8 p.m. on Election Day. Any voter can vote absentee; how to ask:",
    early_where="Counties that offer early voting open it from this day through 5 p.m. on the Friday before Election "
                "Day; your county clerk lists the places and hours.",
    credit="Dates worked out from Idaho's election law; more from the Idaho Secretary of State",
    poll_hours="8 a.m. – 8 p.m.",
    check_url="https://votertools.voteidaho.gov/electionlink/electionlink/VoterSearch.aspx",
    check_hint="VoteIdaho (Idaho Secretary of State): your registration",
    where_url=f"{VOTER}/voter/where-do-I-vote",
    where_hint="VoteIdaho (Idaho Secretary of State): your polling place",
    mail_label="How to ask",
    mail_eligibility="Any registered voter can vote absentee, no reason needed. Your ballot must reach your county clerk "
                     "by 8 p.m. on Election Day.",
    mail_deadline="Ask for your ballot by ",
    late_registration="After that, register at your polling place on Election Day, with proof of who you are and where "
                      "you live",
    local_office="Your county clerk",
    local_time=True,
)
RULE = idaho
