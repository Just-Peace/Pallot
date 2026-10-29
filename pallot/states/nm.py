"""New Mexico: the Secretary of State's Election Contest/Candidate List, its CandidateList.aspx
grid (grid.py). The grid has no election dropdown: each election is under an id (``eid``) the
Secretary of State's home page links ("2026 General Election – Candidate Filing Day"), so the id is
found there by the link's year, never written ahead. The grid's page for that election and the
whole state (``cty=99``) holds every row in its HTML table, so it's asked with one GET, no postback.
A plain script gets a 200 from both.

A row per candidate: the contest ("State Representative"), the district ("DISTRICT 33"), the
filing county, the name in capitals ("GREGGORY D HULL AND DAVID M GALLEGOS" for a Governor's
ticket, "… (write-in)" for a declared write-in), the party's code (DEM, REP, LIB, FWD, DTS for a
candidate of no party), the filing date, the ballot order, the status (Qualified, Withdrawn,
Disqualified; only Qualified is kept), the district type and the candidate's addresses, phone and
email, which are never read. Only the name, office, district, party and whether it's a write-in
are kept: the page is kept as its filings, so the cache and the bundle hold nothing else.

Its races are Congress, Governor and Lieutenant Governor (one ticket), the other statewide
offices, the State House (all 70 seats in 2026) and the State Senate (its 42 seats are up in 2028;
2026's list has only a vacancy's, District 33), a seat on the Court of Appeals, and the Supreme
Court's and Court of Appeals' judges standing for retention ("Judicial Retention", its court
unnamed). The Public Education Commission's districts aren't any the Census knows, and the
district, magistrate, metropolitan and probate courts and the county offices are elected in
counties and judicial districts the list doesn't place: they're left out.

New Mexico's key dates, for its general election (the Tuesday after the first Monday of November
in an even year, 2 U.S.C. §7), checked on 2026-10-29 against NMSA 1978 as amended in 2023 (SB 180)
and the Secretary of State's 2026 Important Dates: registration by mail, by an agent or online
closes 28 days before (§1-4-8(A)), and a voter can still register in person at an early voting
site or at the polls on Election Day (same-day registration, §1-4-5.7); any voter can vote by
mail, no reason needed (the Absent Voter Act), the county clerk taking a request until 14 days
before (§1-6-5(A)), and the ballot must reach the clerk by 7 p.m. on Election Day (§1-6-10(A));
early voting is at the county clerk's office from the 28th day before through the Saturday
before, and at more sites from the third Saturday before (§1-6-5.7). Polls are open 7 a.m. to
7 p.m. (§1-12-1), the whole state in one time zone. No deadline moves past a weekend or holiday.
"""

from __future__ import annotations

import re

from . import Office, legislator, statewide, us_house, us_senate
from .dates import Counts, Guide
from .grid import GridList, GridRow

INDEX = "https://www.sos.nm.gov/"
PAGE = "https://candidateportal.servis.sos.state.nm.us/CandidateList.aspx"
STATEWIDE = ("Governor", "Lieutenant Governor", "Secretary of State", "Attorney General", "State Auditor",
             "State Treasurer", "Commissioner of Public Lands")
LEFT_OUT = frozenset({"ECX", "JDX", "JMC", "MGX", "MUX", "CTY", "CCX"})  # district types it doesn't place
_DISTRICT = re.compile(r"DISTRICT (\d+)", re.I)
_APPEALS = re.compile(r"Judge of the Court of Appeals Position (\d+)", re.I)
_NUMERALS = frozenset({"II", "III", "IV"})


def _number(row: GridRow) -> int:
    found = _DISTRICT.fullmatch(row.district.strip())
    if not found:
        raise ValueError(f"no district for {row.race}: {row.district!r}")
    return int(found.group(1))


def _word(word: str) -> str:
    """A word of a name in capitals as the ballot shows it: "O'CONNELL" is "O'Connell", "MCDANIEL"
    "McDaniel", "AND" (a ticket's) "and", "III" stays."""
    bare = word.strip(",.\"'()")
    if bare in _NUMERALS:
        return word
    if bare == "AND":
        return word.lower()
    return re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), word.title())


class NmList(GridList):
    state = "NM"
    source = "state_nm"
    label = "New Mexico Secretary of State"
    page = PAGE
    index = INDEX
    election = "eid"
    query = {"cty": "99"}
    form = {}
    kept = ("QUALIFIED",)
    parties = {"FWD": "Forward"}
    minimum = {"cd": 3, "hd": 60}  # nearly every House district: one can go without a candidate
    description = ("New Mexico's official list of the candidates for Congress, its statewide offices and the "
                   "Legislature, and the judges standing for retention statewide, from its Secretary of State.")
    scope_note = ("The Public Education Commission, the district, magistrate, metropolitan and probate courts and "
                  "their judges standing for retention, your county's offices and any questions aren't shown: your "
                  "county clerk's sample ballot has them.")

    @classmethod
    def office(cls, row: GridRow) -> Office | None:
        """The race of a row; None for one the ballot leaves out (LEFT_OUT, a local court's retention).
        ValueError for an office of the state it doesn't know."""
        race = " ".join(row.race.split())
        if race == "United States Senator":
            return us_senate("NM")
        if race == "United States Representative":
            return us_house("NM", _number(row))
        if race == "Governor and Lieutenant Governor":
            return statewide(race, "GOVERNOR")
        if race in STATEWIDE:
            return statewide(race)
        if race in ("State Senator", "State Representative"):
            return legislator("sd" if race == "State Senator" else "hd", _number(row))
        if found := _APPEALS.fullmatch(race):
            return Office(f"COURT OF APPEALS {found.group(1)}", race, "COURT OF APPEALS", "judicial", "state")
        if race == "Judicial Retention":
            return Office(f"JUDICIAL RETENTION {row.name.upper()}", f"Retain {cls.named(row.name)}",
                          "JUDICIAL RETENTION", "judicial", "state", incumbent=True, retention=True)
        if race.startswith("Judicial Retention") or row.district_type.upper() in LEFT_OUT:
            return None
        raise ValueError(f"an office it doesn't know: {race}")

    @classmethod
    def affiliation(cls, row: GridRow) -> tuple[str | None, str | None]:
        """DTS ("declined to state") is no party."""
        return (None, None) if row.party.upper() == "DTS" else super().affiliation(row)

    @classmethod
    def named(cls, name: str) -> str:
        """The list's name in capitals, as the ballot shows it ("Ben R Lujan", "Juan De Jesus Sanchez,
        III"); a name not all in capitals as it is."""
        return name if name != name.upper() else " ".join(_word(word) for word in name.split())


GUIDE = Guide(
    name="New Mexico",
    source="New Mexico Secretary of State",
    url="https://www.sos.nm.gov/voting-and-elections/",
    computed=True,
    registration_url="https://portal1.sos.nm.gov/OVR/WebPages/InstructionsStep1.aspx",
    mail_url="https://portal1.sos.nm.gov/OVR/WebPages/AbsenteeApplication.aspx",
    register="The last day to register online, by mail or through a registration agent for {election} in New Mexico. "
             "After it, you can still register in person, and vote, at an early voting site or at your polling place "
             "on Election Day.",
    mail_summary="Mailed ballot request due",
    mail="If you vote by mail in {election}, your request must reach your county clerk by today. Your ballot must reach "
         "the clerk by 7 p.m. on Election Day; one that arrives later isn't counted. Any voter can vote by mail; how to "
         "ask:",
    early_where="Your county clerk's office, through the Saturday before Election Day, and more early voting sites from "
                "the third Saturday before; your county clerk lists them and their hours.",
    credit="Dates worked out from New Mexico's election law; more from the New Mexico Secretary of State",
    poll_hours="7 a.m. – 7 p.m.",
    check_url="https://voterportal.servis.sos.state.nm.us/WhereToVote.aspx",
    check_hint="New Mexico Secretary of State's Voter Information Portal: your registration and your polling place",
    where_url="https://voterportal.servis.sos.state.nm.us/WhereToVote.aspx",
    where_hint="New Mexico Secretary of State's Voter Information Portal: your polling place and sample ballot",
    mail_label="How to ask",
    mail_eligibility="Any registered voter can vote by mail, no reason needed. Your ballot must reach your county clerk "
                     "by 7 p.m. on Election Day.",
    mail_deadline="Ask your county clerk for your ballot by ",
    local_office="Your county clerk",
    late_registration="After that, register in person at an early voting site or at your polling place on Election Day",
)
RULE = Counts(28, 14, 28, 3).rule("NM")
