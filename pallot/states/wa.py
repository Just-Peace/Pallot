"""Washington: the Secretary of State's candidate list on VoteWA, its CandidateList.aspx grid
(grid.py). The page's election dropdown has every election under an id ("GENERAL 2026
(11/03/2026) (General)" under 899, 2027's under 906), and the list is the grid's Export to CSV,
posted back for that election. Its Cloudflare refuses Python's default User-Agent with a 403,
but takes Pallot's, with no challenge.

A row per candidate: the district type ("Congressional", "Legislative", "Judicial", "Statewide",
"Federal", and many local ones), the district ("Legislative District 5", "Court of Appeals,
Division 1, District 1", "Cowlitz Superior Court", "County"), the race ("State Representative
Pos. 1"), the term type (Regular, Unexpired, Short & Full), the name, the candidate's address,
email and phone, the filing date, the party preference, the status and the ballot order. The
address, email and phone are never read: the list is kept as its filings, so the cache and the
bundle hold only the name, office, district and party.

Washington's primary is top-two: a partisan candidate states a party preference, which the ballot
prints as "(Prefers Democratic Party)", the party the candidate prefers rather than one that
nominated them. The list has the words alone ("DEMOCRATIC", "GOP", "LABOR DEMOCRAT"), so a
candidate's party is shown as the ballot prints it; "STATES NO PARTY PREFERENCE" is no party.

Its races are Congress (the U.S. Senate in 2028 and 2030, not 2026), the statewide offices (every
four years, 2028 next), the Legislature, whose 49 districts each elect a Senator and two
Representatives, Position 1 and Position 2, each its own race, and the Supreme Court statewide,
the Court of Appeals by its districts' counties (RCW 2.06.020) and the superior courts by their
counties. The President is left out. The county offices, district and municipal courts, cities and
special districts are named in the list without their county ("County", "District Court"), so
they're left out with a ballot note.

Washington's key dates, for its general election (the first Tuesday after the first Monday of
November, every year, RCW 29A.04.321), checked on 2026-10-29 against the RCW and the Secretary of
State's 2026 Dates and Deadlines: every voter is mailed a ballot at least 18 days before (RCW
29A.40.070), and voting centers are open during business hours from that day through 8 p.m. on
Election Day, where anyone in line at 8 p.m. can vote (RCW 29A.40.160(1), (16)); registration
online or by mail must be received 8 days before, and in person it goes on until 8 p.m. on
Election Day (RCW 29A.08.140); a ballot comes back by mail postmarked by Election Day, or to a drop
box or the county auditor by 8 p.m. (RCW 29A.40.091(4)). No deadline moves past a weekend or
holiday. 2026: Oct 16, Oct 26 and Nov 3.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from .. import counties
from . import Filing, Office, legislator, party, require, statewide, us_house, us_senate
from .dates import Counts, Guide, mailed_to_every_voter
from .grid import GridList, GridRow

PAGE = "https://voter.votewa.gov/CandidateList.aspx"
STATEWIDE = ("Governor", "Lt. Governor", "Secretary of State", "State Treasurer", "State Auditor", "Attorney General",
             "Commissioner of Public Lands", "Superintendent of Public Instruction", "Insurance Commissioner")
EVEN_YEAR = {"cd": 10, "hd": 45}  # every U.S. House district, nearly every Legislative District
APPEALS = {  # RCW 2.06.020: each division's districts and their counties
    (1, 1): ("KING",), (1, 2): ("SNOHOMISH",), (1, 3): ("ISLAND", "SAN JUAN", "SKAGIT", "WHATCOM"),
    (2, 1): ("PIERCE",), (2, 2): ("CLALLAM", "GRAYS HARBOR", "JEFFERSON", "KITSAP", "MASON", "THURSTON"),
    (2, 3): ("CLARK", "COWLITZ", "LEWIS", "PACIFIC", "SKAMANIA", "WAHKIAKUM"),
    (3, 1): ("FERRY", "LINCOLN", "OKANOGAN", "PEND OREILLE", "SPOKANE", "STEVENS"),
    (3, 2): ("ADAMS", "ASOTIN", "BENTON", "COLUMBIA", "FRANKLIN", "GARFIELD", "GRANT", "WALLA WALLA", "WHITMAN"),
    (3, 3): ("CHELAN", "DOUGLAS", "KITTITAS", "KLICKITAT", "YAKIMA"),
}
NO_PREFERENCE = frozenset({"", "STATES NO PARTY PREFERENCE", "NO PARTY PREFERENCE", "NONPARTISAN", "NON PARTISAN"})
CODES = {"GOP": "R", "G.O.P.": "R", "REPUBLICAN - GOP": "R", "INDEPENDENT": "I", "INDEPENDANT": "I", "IND": "I"}
_ACRONYMS = frozenset({"GOP", "G.O.P."})
_NUMBER = re.compile(r"(\d+)$")
_POSITION = re.compile(r"(?:Pos\.?|Position)\s*(?:No\.\s*)?#?\s*0*(\d+)$", re.I)
_APPEALS = re.compile(r"Court of Appeals, Division (\d), District (\d)", re.I)
_SUPERIOR = re.compile(r"(.+?) Superior Court", re.I)


def _number(row: GridRow) -> int:
    found = _NUMBER.search(row.district.strip())
    if not found:
        raise ValueError(f"no district for {row.race}: {row.district!r}")
    return int(found.group(1))


def _position(row: GridRow) -> int | None:
    found = _POSITION.search(" ".join(row.race.split()))
    return int(found.group(1)) if found else None


def _county(name: str) -> str:
    found = counties.find("WA", name)
    if found is None:
        raise ValueError(f"no county {name!r}")
    return found.name.upper()


def _judge(row: GridRow) -> Office | None:
    """A judge's race: the Supreme Court's statewide, a Court of Appeals district's in its counties,
    a superior court's in its county or counties; None for a district or municipal court."""
    court, seat = " ".join(row.district.split()), _position(row)
    shown = f" Position {seat}" if seat else ""
    if court.upper() == "SUPREME COURT":
        if seat is None:
            raise ValueError(f"no position for the Supreme Court: {row.race!r}")
        return Office(f"SUPREME COURT {seat}", f"Justice of the Supreme Court{shown}", "SUPREME COURT", "judicial",
                      "state")
    if found := _APPEALS.fullmatch(court):
        division, district = int(found.group(1)), int(found.group(2))
        if (division, district) not in APPEALS:
            raise ValueError(f"no Court of Appeals district {court!r}")
        return Office(f"COURT OF APPEALS {division} {district} {seat or ''}".strip(),
                      f"Court of Appeals, Division {division}, District {district}, Judge{shown}", "COURT OF APPEALS",
                      "judicial", "counties", f"{division}-{district}", APPEALS[division, district])
    if found := _SUPERIOR.fullmatch(court):
        where = tuple(sorted(_county(name) for name in found.group(1).split(",")))
        named = ", ".join(name.title() for name in where)
        key = " ".join(where)
        return Office(f"SUPERIOR COURT {key} {seat or ''}".strip(),
                      f"{named} {'Counties' if len(where) > 1 else 'County'} Superior Court Judge{shown}",
                      "SUPERIOR COURT", "judicial", "counties", key, where)
    return None


def _printed(words: str) -> str:
    """A party preference as the ballot prints it: "LABOR DEMOCRAT" is "Labor Democrat", "GOP" stays."""
    return " ".join(word if word.upper() in _ACRONYMS or word != word.upper() else word.title() for word in words.split())


class WaList(GridList):
    state = "WA"
    source = "state_wa"
    label = "Washington Secretary of State"
    page = PAGE
    description = ("Washington's official list of the candidates for Congress, its statewide offices, the Legislature "
                   "and its courts, from its Secretary of State.")
    scope_note = ("Your county's offices, the district and municipal courts, your city's and special districts' races and "
                  "any measures aren't shown: the voters' pamphlet your county auditor mails has them.")

    @classmethod
    def office(cls, row: GridRow) -> Office | None:
        """The race of a row, its term unexpired where the list says so; None for one the ballot
        leaves out (a local office, a district or municipal court, the President). ValueError for a
        federal, statewide or legislative office it doesn't know."""
        found = cls._office(row)
        if found and row.cells.get("TERM TYPE", "").upper() == "UNEXPIRED":
            return dataclasses.replace(found, unexpired=True)
        return found

    @classmethod
    def _office(cls, row: GridRow) -> Office | None:
        kind, race = row.district_type.upper(), " ".join(row.race.split())
        if kind == "CONGRESSIONAL":
            if race != "U.S. Representative":
                raise ValueError(f"an office it doesn't know: {race}")
            return us_house("WA", _number(row))
        if kind == "FEDERAL":
            if race == "U.S. Senator":
                return us_senate("WA")
            if race.startswith("President"):
                return None
            raise ValueError(f"an office it doesn't know: {race}")
        if kind == "STATEWIDE":
            if race not in STATEWIDE:
                raise ValueError(f"an office it doesn't know: {race}")
            return statewide(race.replace("Lt.", "Lieutenant"))
        if kind == "LEGISLATIVE":
            number = _number(row)
            if race == "State Senator":
                return legislator("sd", number)
            seat = _position(row)
            if not race.startswith("State Representative") or seat not in (1, 2):
                raise ValueError(f"an office it doesn't know: {race}")
            return legislator("hd", number, f"STATE HOUSE {number} POSITION {seat}",
                              f"State Representative District {number} Position {seat}")
        if kind == "JUDICIAL":
            return _judge(row)
        return None

    @classmethod
    def affiliation(cls, row: GridRow) -> tuple[str | None, str | None]:
        """The party the candidate prefers, as the ballot prints it ("Prefers Democratic Party"), and
        its code where it's one (GOP is R); no party for "STATES NO PARTY PREFERENCE" or none."""
        words = " ".join(row.party.split())
        if words.upper() in NO_PREFERENCE:
            return None, None
        code = CODES.get(words.upper()) or party(words)[0]
        printed = _printed(words)
        return code, f"Prefers {printed}" if printed.upper().endswith(" PARTY") else f"Prefers {printed} Party"

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        """GridList's, refused short of EVEN_YEAR's districts where the list has Congress (an even
        year's); an odd year's has the Legislature's and the courts' vacancies alone."""
        filings = super().parse(raw)
        return require(filings, EVEN_YEAR) if any(f.reach == "cd" for f in filings) else filings


GUIDE = Guide(
    name="Washington",
    source="Washington Secretary of State",
    url="https://www.sos.wa.gov/elections",
    computed=True,
    registration_url="https://voter.votewa.gov/WhereToVote.aspx",
    mail_url="https://voter.votewa.gov/portal2023/login.aspx",
    register="The last day to register online or by mail for {election} in Washington: it must be received today. "
             "After it, you can still register in person at your county auditor's office or a voting center, until "
             "8 p.m. on Election Day.",
    mail_summary="Ballots are mailed",
    mail="Every voter in Washington is mailed a ballot for {election}. Mail it back postmarked by Election Day, or put "
         "it in a drop box by 8 p.m. on Election Day. Track yours:",
    early_where="Your county auditor's voting centers, during business hours through 8 p.m. on Election Day; your "
                "county auditor lists them and the drop boxes.",
    credit="Dates worked out from Washington's election law; more from the Washington Secretary of State",
    poll_hours="8 p.m.",
    check_url="https://voter.votewa.gov/portal2023/login.aspx",
    check_hint="VoteWA (Washington Secretary of State): your registration and your ballot's status",
    where_url="https://www.sos.wa.gov/elections/voters/voter-registration/drop-box-and-voting-center-locations",
    where_hint="Washington Secretary of State: every drop box and voting center",
    mail_label="Track your ballot",
    mail_eligibility=mailed_to_every_voter("It goes out 18 days before Election Day. Mail it back postmarked by "
                                           "Election Day, or put it in a drop box by 8 p.m. on Election Day."),
    local_office="Your county auditor",
    polls_text="Drop boxes and voting centers close at 8 p.m. on Election Day; if you're in line at a voting center at "
               "8, you can vote.",
    late_registration="After that, register in person at your county auditor's office or a voting center until 8 p.m. "
                      "on Election Day",
    hours_set_by="your county auditor",
)
RULE = Counts(8, None, 18, None, every_year=True).rule("WA")  # every voter is mailed a ballot
