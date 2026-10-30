"""Vermont: the Secretary of State's list of the general election's qualified candidates, a
spreadsheet (.xlsx) named for its year (candidates/2026_general_election_qualified_candidates.xlsx
on outside.vermont.gov), so it's asked by its name, with no page to find it on first. A plain
script gets a 200.

A row per candidate: the contest ("STATE SENATOR"), the district ("CHI SE 1", "ADD RUT", a county
for a county office, a town for a justice of the peace, "N/A" for a statewide race), the name on
the ballot, the town they live in, the party (a candidate nominated by two parties has both,
"REP/DEM"), the candidate's address, phones, email and website, the term, the "Vote for Count"
("TWO": the race's seats) and the financial disclosure's file. It has no withdrawn or incumbent
flag, and doesn't name the election, so a filing is dated by the year it was asked for. Only the
name, office, district, party and seats are kept: the sheet is kept as its filings, so the cache
and the bundle hold nothing else.

Its races in 2026 are the U.S. House (one seat, at large), the six statewide offices (elected
every two years), the whole State Senate (30 seats in 16 districts of one to three) and State
House (150 seats in 109 districts of one or two), and each county's sheriff, state's attorney,
high bailiff, probate judge and two assistant judges, placed by county. The list writes a
district in its own abbreviations ("CHI SE 1", "WDR ORA 2"), which are spelt out here as the
Census names the district ("Chittenden South East", "Windsor-Orange-2"). The justices of the
peace, elected by town, are left out with a ballot note. An office it doesn't know is refused,
so a new one is seen rather than dropped.

Vermont's key dates, for its general election (the Tuesday after the first Monday of November in
an even year, 2 U.S.C. §7), checked on 2026-10-29 against Title 17 (legislature.vermont.gov)
and the Secretary of State's 2026 elections calendar: there's no registration deadline, since a
voter can register at the town clerk's office on any day and at the polling place on Election Day
(§2144); the Secretary of State mails a ballot to every active voter, starting by the 43rd day
before and finishing by October 1 (§2537a); early ballots reach the town clerks by the 45th day
before (§2522(a)), and a voter can vote early at the clerk's office from then until the day before
(§2531(a)); a ballot must reach the clerk's office or a drop box by the close of business the day
before, the clerk by mail before the polls close, or the polling place by 7 p.m. (§2543(d)); polls
close at 7 p.m. and open between 5 and 10 a.m., as each town's board of civil authority sets
(§2561). 2026: early voting Sep 19 – Nov 2, as on the calendar.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any

from ..http_cache import RequestSpec
from ..text import display_person
from . import Filing, Office, StateList, legislator, party, require, sheet_rows, statewide, us_house, us_senate
from .dates import Counts, Guide, mailed_to_every_voter

SITE = "https://sos.vermont.gov/elections"
LISTS = "https://outside.vermont.gov/dept/sos/Elections_Division/election_info_resources/candidates/"
PAGE = "https://sos.vermont.gov/elections/election-info-resources/candidates"
MVP = "https://mvp.vermont.gov/"
COLUMNS = ("Contest", "District Name", "Name On Ballot", "Party", "Vote for Count")
MINIMUM = {"cd": 1, "sd": 16, "hd": 105}  # every district up: a few can go without a candidate
STATEWIDE = frozenset({"GOVERNOR", "LIEUTENANT GOVERNOR", "STATE TREASURER", "SECRETARY OF STATE",
                       "AUDITOR OF ACCOUNTS", "ATTORNEY GENERAL"})
US_SENATE = frozenset({"UNITED STATES SENATOR", "U.S. SENATOR", "US SENATOR"})
COUNTY_OFFICES = {"SHERIFF": ("county", "Sheriff"), "STATE'S ATTORNEY": ("county", "State's Attorney"),
                  "HIGH BAILIFF": ("county", "High Bailiff"), "PROBATE JUDGE": ("judicial", "Probate Judge"),
                  "ASSISTANT JUDGE": ("judicial", "Assistant Judge")}
LEFT_OUT = frozenset({"JUSTICE OF THE PEACE"})
COUNTIES = {"ADD": "Addison", "BEN": "Bennington", "CAL": "Caledonia", "CHI": "Chittenden", "ESX": "Essex",
            "FRA": "Franklin", "GI": "Grand Isle", "LAM": "Lamoille", "ORA": "Orange", "ORL": "Orleans",
            "RUT": "Rutland", "WAS": "Washington", "WDH": "Windham", "WDR": "Windsor"}
CHITTENDEN = {"CHI CT": ("Chittenden Central", "Chittenden-Central"), "CHI N": ("Chittenden North", "Chittenden-North"),
              "CHI SE": ("Chittenden South East", "Chittenden-Southeast")}  # (the Census's name, the state's)
SEATS = {"ONE": 1, "TWO": 2, "THREE": 3}
PARTIES = {"DEM": "Democratic", "REP": "Republican", "PROG": "Progressive", "PROGRESSIVE": "Progressive",
           "INDEPENDENT": "Independent", "PEACE AND JUSTICE": "Peace and Justice",
           "FREEDOM AND UNITY": "Freedom and Unity", "WOMEN'S LIBERATION VEGI-ARYAN": "Women's Liberation Vegi-Aryan"}
_NO_PARTY = frozenset({"", "UNKNOWN", "UNAFFILIATED"})


def senate_district(code: str) -> tuple[str, str]:
    """(the Census's name, the state's) for a list's State Senate district: "CHI SE 1" is
    ("Chittenden South East", "Chittenden-Southeast"), "ADD 1" ("Addison", "Addison")."""
    words = code.split()
    if words[-1:] == ["1"]:
        words = words[:-1]
    key = " ".join(words)
    if key in CHITTENDEN:
        return CHITTENDEN[key]
    if key not in COUNTIES:
        raise ValueError(f"a State Senate district it doesn't know: {code}")
    return COUNTIES[key], COUNTIES[key]


def house_district(code: str) -> str:
    """A list's State House district as the Census names it: "WDR ORA 2" is "Windsor-Orange-2"."""
    words = code.split()
    if not words or any(not word.isdigit() and word not in COUNTIES for word in words):
        raise ValueError(f"a State House district it doesn't know: {code}")
    return "-".join(word if word.isdigit() else COUNTIES[word] for word in words)


def affiliation(label: str) -> tuple[str | None, str | None]:
    """(code, name) for a list's party: a candidate on two parties' lines ("REP/DEM") has the
    first's code and both names."""
    labels = [" ".join(part.split()) for part in label.upper().split("/")]
    labels = [part for part in labels if part not in _NO_PARTY]
    if not labels:
        return None, None
    found = [party(PARTIES.get(part, part.title())) for part in labels]
    code = next((code for code, _ in found if code), None)
    if len(labels) > 1:
        return code, " / ".join(PARTIES.get(part, part.title()) for part in labels)
    return found[0]


def _race(contest: str, district: str, seats: int) -> Office | None:
    """The race of a row, or None for one left out (a justice of the peace). ValueError for a
    contest it doesn't know."""
    if contest == "REPRESENTATIVE TO CONGRESS":
        return us_house("VT", 0, "US HOUSE")
    if contest in US_SENATE:
        return us_senate("VT")
    if contest in STATEWIDE:
        return statewide(contest.title().replace(" Of ", " of "))
    if contest == "STATE SENATOR":
        census, named = senate_district(district)
        return dataclasses.replace(legislator("sd", census, office=f"State Senator, {named} District"), seats=seats)
    if contest == "STATE REPRESENTATIVE":
        named = house_district(district)
        return dataclasses.replace(legislator("hd", named, office=f"State Representative, {named} District"),
                                   seats=seats)
    if contest in COUNTY_OFFICES:
        group, title = COUNTY_OFFICES[contest]
        county = district.upper()
        if county not in {name.upper() for name in COUNTIES.values()}:
            raise ValueError(f"a county it doesn't know: {district}")
        return Office(f"{contest} {county}", f"{county.title()} County {title}", f"COUNTY {contest}", group, "county",
                      seats=seats, counties=(county,))
    if contest in LEFT_OUT:
        return None
    raise ValueError(f"an office it doesn't know: {contest}")


def parse_rows(rows: list[list[str]]) -> list[Filing]:
    """Every candidate on the sheet, undated (VtList.on); ValueError for a sheet that isn't the
    list (its columns, an office or district it doesn't know, a row without a name) or one short
    of its districts (MINIMUM, in a year with Congress on the ballot)."""
    heading = rows[0] if rows else []
    if not all(column in heading for column in COLUMNS):
        raise ValueError("not the list of general election candidates")
    at = {column: heading.index(column) for column in COLUMNS}
    filings = []
    for index, row in enumerate(rows[1:]):
        cells = [*row, *[""] * (len(heading) - len(row))]
        if not any(cells):
            continue
        contest, name = cells[at["Contest"]].upper(), cells[at["Name On Ballot"]]
        if not contest or not name:
            raise ValueError(f"a row without a name or contest: {cells[:3]}")
        count = cells[at["Vote for Count"]].upper()
        seats = SEATS.get(count) or (int(count) if count.isdigit() else 1)
        race = _race(contest, cells[at["District Name"]], seats)
        if race is None:
            continue
        code, party_name = affiliation(cells[at["Party"]])
        filings.append(race.filing(day="", name=display_person(name), party=code, party_name=party_name, order=index))
    if not any(f.group == "federal" for f in filings):
        return filings
    return require(filings, MINIMUM)


class VtList(StateList):
    state = "VT"
    source = "state_vt"
    label = "Vermont Secretary of State"
    page = PAGE
    description = ("Vermont's official list of the candidates for Congress, its statewide offices, the General "
                   "Assembly and its county offices, from its Secretary of State.")
    max_bytes = 4 << 20
    scope_note = ("Justices of the peace, town and school races, and any questions aren't shown: your town clerk has "
                  "your sample ballot.")

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", f"{LISTS}{day.year}_general_election_qualified_candidates.xlsx")

    def on(self, value: Any, day: dt.date) -> list[Filing]:
        """The filings in a stored answer, dated ``day``: the sheet asked for is that year's."""
        return [dataclasses.replace(f, day=day.isoformat()) if not f.day else f
                for f in self.read(value) if not f.day or f.day == day.isoformat()]

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, bytes):
            raise ValueError("not a spreadsheet")
        return parse_rows(sheet_rows(raw)[1])


GUIDE = Guide(
    name="Vermont",
    source="Vermont Secretary of State",
    url=SITE,
    computed=True,
    registration_url=MVP,
    mail_url=MVP,
    register="",
    mail_summary="",
    mail="",
    early_where="Your town clerk's office, during its business hours: vote early in person there, or drop off your "
                "mailed ballot.",
    credit="Dates worked out from Vermont's election law; more from the Vermont Secretary of State",
    poll_hours="7 p.m.",
    check_url=MVP,
    check_hint="My Voter Page (Vermont Secretary of State): your registration, your polling place and your ballot",
    where_url=MVP,
    where_hint="My Voter Page (Vermont Secretary of State): your polling place and your town clerk",
    mail_label="Track your ballot",
    mail_eligibility=mailed_to_every_voter("Mail it back to your town clerk to arrive before the polls close, drop it "
                                           "at the clerk's office or drop box by the close of business the day before, "
                                           "or bring it to your polling place by 7 p.m. on Election Day."),
    local_office="Your town clerk",
    polls_text="Polls close at 7 p.m.; your town sets when they open, between 5 and 10 a.m. If you're in line at 7, "
               "you can vote. Not registered yet? Register at your polling place when you vote.",
    late_registration="No deadline: register any day at your town clerk's office, or at your polling place on "
                      "Election Day",
    hours_set_by="your town",
)
RULE = Counts(None, None, 45, 1).rule("VT")  # every voter is mailed a ballot; register any day, at the polls too
