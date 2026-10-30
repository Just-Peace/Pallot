"""Mississippi: the Secretary of State's Candidate Qualifying List (sos.ms.gov/content/CandidateQualifying),
one HTML page of all offices and candidates on file, updated daily, with no year in its address. A
plain script gets a 200.

A card per office ("Candidates for United States House of Representatives"), each with its
elections' dates ("General Election: November 3, 2026", a special's "Election: …") and a table of
its candidates: the name, the party for a partisan race, the district, and a judge's place. It has
no withdrawn, incumbent or write-in flag, and no contact details. Each card's filings are dated by
its own election (the general election's when it gives none), so a card for another day isn't on
this ballot; the page is kept as its filings alone.

Placed in 2026: the U.S. Senate, the U.S. House (four districts), the Court of Appeals by its
districts' counties, and the special elections: State House 70 and 77 and State Senate 34 (the
Legislature is elected in odd years, so an even year's are for unexpired terms), and District
Attorney 7, the Seventh Circuit Court District, Hinds County (Miss. Code §9-7-23(1)). The Court of
Appeals' five districts are whole counties and parts of ten more (§9-4-5(5), as brought forward by
2023's House Bill 726): a race reaching part of the voter's county is on the ballot only maybe. The
chancery and circuit judges, elected by districts and subdistricts, are left out with a ballot note,
as is the Supreme Court, whose 2026 race a federal court has stopped. An office it doesn't know is
refused, so a new one is seen rather than dropped.

Mississippi's key dates, for its general election (the Tuesday after the first Monday of November,
2 U.S.C. §7), checked on 2026-10-29 against the Secretary of State's 2026 Elections Calendar (last
revised 2026-09-08) and its absentee voting page: a voter registers in person at the circuit or
municipal clerk's office, or by mail postmarked, by the 30th day before (Miss. Code §§23-15-37,
23-15-47, 23-15-125), always a Sunday, so the deadline is the Monday after (Roll; Mississippi keeps
no Columbus Day). There's no early voting and no registering on Election Day. A voter with an excuse
(65 or older, disabled, away from the county or at work on Election Day, among others, as the absentee
page lists them)
can vote absentee in person at the circuit clerk's office once its ballots are in, 45 days before
(§23-15-715(b)), a Saturday, so from the Monday after (the 43rd day, as the calendar has it),
through noon on the Saturday before (§23-15-653). A mailed ballot must be postmarked by Election
Day and reach the circuit clerk within five business days (§23-15-637(1)(a)); there's no deadline
to ask for one. Polls are open 7 a.m. to 7 p.m. (§23-15-541). 2026: register by Oct 5, in-person
absentee Sep 21 – Oct 31, mailed ballots received by Nov 10.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import html
import re
from typing import Any

from ..http_cache import RequestSpec
from . import (
    MONTH_DAY_YEAR, Filing, Office, Rows, StateList, decoded, legislator, party, require, us_house, us_senate,
)
from .dates import Counts, Guide, Roll, only_if

SITE = "https://www.sos.ms.gov"
PAGE = f"{SITE}/content/CandidateQualifying/default.aspx"
MINIMUM = {"cd": 4}
# The Court of Appeals' districts (§9-4-5(5)): its whole counties, then the counties only part of
# which is in it, as Census names them, in capitals.
APPEALS = {
    1: (("ALCORN", "BENTON", "CALHOUN", "CHICKASAW", "CHOCTAW", "DESOTO", "ITAWAMBA", "LAFAYETTE", "LEE", "MARSHALL",
         "MONROE", "PONTOTOC", "PRENTISS", "TATE", "TIPPAH", "TISHOMINGO", "UNION", "WEBSTER", "YALOBUSHA"),
        ("GRENADA", "MONTGOMERY", "PANOLA", "TALLAHATCHIE")),
    2: (("BOLIVAR", "CARROLL", "CLAIBORNE", "COAHOMA", "HOLMES", "HUMPHREYS", "ISSAQUENA", "JEFFERSON", "LEFLORE",
         "QUITMAN", "SHARKEY", "SUNFLOWER", "TUNICA", "WARREN", "WASHINGTON", "YAZOO"),
        ("ATTALA", "GRENADA", "HINDS", "LEAKE", "MADISON", "MONTGOMERY", "PANOLA", "TALLAHATCHIE")),
    3: (("CLARKE", "CLAY", "JASPER", "KEMPER", "LAUDERDALE", "LOWNDES", "NESHOBA", "NEWTON", "NOXUBEE", "OKTIBBEHA",
         "RANKIN", "SCOTT", "SMITH", "WINSTON"),
        ("ATTALA", "JONES", "LEAKE", "MADISON", "WAYNE")),
    4: (("ADAMS", "AMITE", "COPIAH", "COVINGTON", "FRANKLIN", "JEFFERSON DAVIS", "LAWRENCE", "LINCOLN", "MARION",
         "PIKE", "SIMPSON", "WALTHALL", "WILKINSON"),
        ("HINDS", "JONES")),
    5: (("FORREST","GEORGE", "GREENE", "HANCOCK", "HARRISON", "JACKSON", "LAMAR", "PEARL RIVER", "PERRY", "STONE"),
        ("WAYNE",)),
}
ATTORNEYS = {"7": ("HINDS",)}  # a district attorney's circuit court district's counties (§9-7-23(1))
LEFT_OUT = ("SUPREME COURT", "CHANCERY COURT", "CIRCUIT COURT")
_CARD = re.compile(r"<div class='card officeCard'>")
_TITLE = re.compile(r"<div class='officeTitle'>(.*?)</div>", re.S)
_PILL = re.compile(r"<span class='datePillLabel'>(.*?)</span>\s*<span class='datePillValue'>(.*?)</span>", re.S)


def _text(part: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", part)).split())


def _day(text: str) -> str:
    return dt.datetime.strptime(text, "%B %d, %Y").date().isoformat()


def appeals_counties(district: int) -> tuple[str, ...]:
    """The counties of a Court of Appeals district as a filing names them: a county only part of
    which is in it starred ("HINDS*"), so the race is there only maybe (place.where)."""
    whole, part = APPEALS[district]
    return tuple(sorted((*whole, *(f"{county}*" for county in part))))


def _race(title: str, cells: dict[str, str], even: bool) -> Office | None:
    """The race of a candidate's row under an office's title; None for one left out. ValueError
    for an office it doesn't know."""
    upper = title.upper().removeprefix("CANDIDATES FOR ").strip()
    district = cells.get("District", "")
    if upper == "UNITED STATES SENATE":
        return us_senate("MS")
    if upper == "UNITED STATES HOUSE OF REPRESENTATIVES":
        return us_house("MS", int(district))
    if "COURT OF APPEALS" in upper:
        number, place = int(district), cells.get("Place", "")
        return Office(f"COURT OF APPEALS {number} {place}", f"Court of Appeals Judge, District {number}, Place {place}",
                      "COURT OF APPEALS", "judicial", "counties", str(number), counties=appeals_counties(number))
    if any(court in upper for court in LEFT_OUT):
        return None
    unexpired = "SPECIAL" in upper or even  # the Legislature is elected in odd years
    if upper.startswith("STATE HOUSE OF REPRESENTATIVES"):
        race = legislator("hd", int(district))
    elif upper.startswith("STATE SENATE"):
        race = legislator("sd", int(district))
    elif upper.startswith("DISTRICT ATTORNEY"):
        reached = ATTORNEYS.get(district)
        return Office(f"DISTRICT ATTORNEY {district}", f"District Attorney, District {district}", "DISTRICT ATTORNEY",
                      "judicial", "counties" if reached else "unplaced", district, counties=reached or (),
                      unexpired="SPECIAL" in upper)
    else:
        raise ValueError(f"an office it doesn't know: {title}")
    return dataclasses.replace(race, unexpired=unexpired)


def candidates(text: str) -> list[Filing]:
    """Every candidate on the page, dated by their card's election; ValueError for a page that
    isn't the list (no general election named, a card it can't read, an office it doesn't know)
    or one short of its races (MINIMUM)."""
    cards = _CARD.split(text)[1:]
    general = next((_day(value.strip()) for card in cards for label, value in _PILL.findall(card)
                    if _text(label).rstrip(":") == "General Election" and re.fullmatch(MONTH_DAY_YEAR, value.strip())),
                   None)
    if general is None:
        raise ValueError("not the Candidate Qualifying List: no general election on it")
    filings: list[Filing] = []
    for card in cards:
        title = _TITLE.search(card)
        if title is None:
            raise ValueError("an office without its title")
        pills = {_text(label).rstrip(":"): value.strip() for label, value in _PILL.findall(card)}
        when = pills.get("General Election") or pills.get("Election")
        day = _day(when) if when else general
        rows = Rows(cells=("th", "td"))
        rows.feed(card)
        if not rows.rows:
            continue
        heading, *listed = rows.rows
        if "Name" not in heading:
            raise ValueError(f"a table without its names: {_text(title.group(1))}")
        for row in listed:
            cells = dict(zip(heading, row))
            name = cells.get("Name", "")
            if not name:
                continue
            race = _race(_text(title.group(1)), cells, int(day[:4]) % 2 == 0)
            if race is None:
                continue
            code, party_name = party(cells.get("Party"))
            filings.append(race.filing(day=day, name=name, party=code, party_name=party_name, order=len(filings)))
    return require(filings, MINIMUM) if any(f.day == general for f in filings) else filings


class MsList(StateList):
    state = "MS"
    source = "state_ms"
    label = "Mississippi Secretary of State"
    page = PAGE
    description = ("Mississippi's official list of the candidates for Congress, the Court of Appeals and its special "
                   "elections, from its Secretary of State.")
    max_bytes = 4 << 20
    scope_note = ("The chancery and circuit judges, county and city races and any questions aren't shown, nor is the "
                  "Supreme Court, whose race a federal court has stopped for now: your circuit clerk has your sample "
                  "ballot.")

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", PAGE)

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        return candidates(decoded(raw) if isinstance(raw, bytes) else raw if isinstance(raw, str) else "")


ABSENTEE = f"{SITE}/yall-vote/absentee-voting-information"
GUIDE = Guide(
    name="Mississippi",
    source="Mississippi Secretary of State",
    url=f"{SITE}/elections-voting",
    computed=True,
    registration_url=f"{SITE}/sites/default/files/elections/Mail-in%20Voter%20Registration%20Application.pdf",
    mail_url=ABSENTEE,
    register="The last day to register to vote in {election} in Mississippi: in person at your circuit clerk's or "
             "municipal clerk's office, or by mail postmarked today. There's no registering on Election Day.",
    mail_summary="",
    mail="",
    early_where="In Mississippi, voting early means voting absentee in person, which needs a reason: you're 65 or "
                "older, disabled, or away from your county or at work on Election Day, among others. Vote at your "
                "circuit clerk's office, 8 a.m. to 5 p.m. on weekdays, through noon on the Saturday before Election "
                "Day. Bring your photo ID.",
    credit="Dates worked out from Mississippi's election law; more from the Mississippi Secretary of State",
    poll_hours="7 a.m. – 7 p.m.",
    check_url="https://www.msegov.com/sos/voter_registration/amiregistered/Search",
    check_hint="Mississippi's voter registration search (Secretary of State)",
    where_url="https://myelectionday.sos.state.ms.us/VoterOutreach/Pages/VOSearch.aspx",
    where_hint="My Election Day (Mississippi Secretary of State): your polling place",
    mail_label="How to vote absentee",
    mail_eligibility=only_if("you're 65 or older", "disabled, or with someone disabled in hospital on Election Day",
                             "living outside your county for now")
    + " Ask your circuit clerk for an application, and sign your ballot's envelope before a notary. Mail it "
      "postmarked by Election Day; it must reach your circuit clerk within five business days after.",
    local_office="Your circuit clerk",
)
RULE = Counts(30, None, 43, 3, roll=Roll()).rule("MS")
