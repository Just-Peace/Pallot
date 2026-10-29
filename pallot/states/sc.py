"""South Carolina: the State Election Commission's candidate tracking (vrems.scvotes.sc.gov), every
candidate who filed for an election, asked in two steps as its own page asks them: its list of the
year's statewide elections (``GetElections``, JSON: each election's id, name and date), then the
search of the general election's candidates (a POST of the search form with nothing chosen, which
answers the grid of every candidate as an HTML table). A plain script gets a 200 from both, with no
token or cookie.

The grid has a row per candidate: the office, with its district ("U.S. House of Representatives,
District 1", "State House of Representatives, District 71", "Solicitor Circuit 5", "Sheriff"), the
counties it reaches (empty for a statewide office), the name on the ballot, the running mate (a
Governor's Lieutenant Governor, "Pamela Evette (Active)"), the party ("Petition" for a candidate
nominated by petition, "Nonpartisan"), where they filed and their status. Primary losers and the
withdrawn stay on the list ("Defeated In Primary", "Withdrew"): only "Active" is on the ballot (and,
once it's over, "Elected" and "Defeated in Election"). The grid has no election date, no write-ins,
no incumbents and no contact details (those are only in its CSV export); the cache and the bundle
keep its filings alone.

Placed: Congress, Governor and Lieutenant Governor (one ticket) and the other statewide offices, the
State House (all 124 districts up every even year) and the State Senate (all 46 up in the years of a
presidential election), each judicial circuit's solicitor by the circuit's counties, and the county
offices elected countywide to one seat: sheriff, probate judge, clerk of court, coroner, auditor,
treasurer, register of deeds, supervisor and council chair. County council and school board
districts, at-large seats elected several at a time (the list doesn't say how many), soil and water,
watershed, fire and public service districts, and the President, are left out. An office with no
counties that it doesn't know is refused, so a new statewide office is seen rather than dropped.

South Carolina's key dates, for its general election (the first Tuesday after the first Monday in
November of an even year, S.C. Code §7-13-10), checked against the State Election Commission's 2026
Election Calendar (draft of 2026-08-31) on 2026-10-29: the registration books close 30 days before
(§7-5-150), always a Sunday: online, by fax or email until 11:59 p.m. that day (§7-5-185(B)(1)), in
person at the county office until 5 p.m. on the Friday before, unless it opens that weekend, and by
mail postmarked by the Monday after (§7-5-155(a)(1)); there's no registering after it. An absentee
application must reach the county board by 5 p.m. on the 11th day before (§7-15-330(C)), and only
the voters §7-15-320 lists can vote absentee: anyone 65 or older or disabled, the armed forces and
their families, and those away, working, caring for the sick or in jail through early voting and
Election Day; the ballot must reach the board by the time the polls close (§7-15-420(B)). Early
voting, no excuse needed, runs Monday through Saturday for the two weeks before Election Day,
8:30 a.m. to 6 p.m., closed on Sunday (§7-13-25(E), (F)): the 15th through the 3rd day before. Polls
are open 7 a.m. to 7 p.m. (§7-13-60).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
from typing import Any

from .. import counties
from ..http_cache import RequestSpec
from . import Filing, Office, Rows, StateList, decoded, legislator, party, require, statewide, us_house, us_senate
from .dates import Counts, Guide, only_if

SITE = "https://vrems.scvotes.sc.gov"
PAGE = f"{SITE}/Candidate/SelectElection"
ELECTIONS = f"{SITE}/Candidate/GetElections"
SEARCH = f"{SITE}/Candidate/CandidateSearch/"
# The search form with nothing chosen, as the page sends it for "a list of all candidates".
FORM = {"SelectedOffice": "-1", "SelectedCandidateStatus": "All", "CandidateFirstName": "", "CandidateLastName": "",
        "SelectedPoliticalParty": "All", "SelectedFilingLocation": "All"}
HEADINGS = ("Office", "Associated Counties", "Name on Ballot", "Running Mate", "Party", "Location of Filing",
            "Candidate Status")
ON_BALLOT = {"ACTIVE", "ELECTED", "DEFEATED IN ELECTION"}
MINIMUM = {"cd": 7, "hd": 110}  # every House district up: a few can go without a candidate
SENATE = 40  # all 46 State Senate districts, in a year they're up
STATEWIDE = {
    "SECRETARY OF STATE": "Secretary of State", "STATE TREASURER": "State Treasurer",
    "ATTORNEY GENERAL": "Attorney General", "COMPTROLLER GENERAL": "Comptroller General",
    "STATE SUPERINTENDENT OF EDUCATION": "State Superintendent of Education",
    "COMMISSIONER OF AGRICULTURE": "Commissioner of Agriculture",
}
COUNTYWIDE = {  # the office as listed -> its title after the county's name
    "SHERIFF": "Sheriff", "PROBATE JUDGE": "Probate Judge", "CLERK OF COURT": "Clerk of Court", "CORONER": "Coroner",
    "AUDITOR": "Auditor", "COUNTY TREASURER": "Treasurer", "REGISTER OF DEEDS": "Register of Deeds",
    "COUNTY SUPERVISOR": "Supervisor", "COUNTY COUNCIL CHAIR": "Council Chair",
}
LEFT_OUT = ("PRESIDENT AND VICE PRESIDENT",)
_NO_PARTY = {"NONPARTISAN", "OTHER PARTY/PARTY NOT SPECIFIED", "PARTY NOT SPECIFIED"}
_UNEXPIRED = re.compile(r"\s*\(Unexpired(?: Term)?\)$", re.I)
_DISTRICTED = re.compile(r"(U\.S\. House of Representatives|State House of Representatives|State Senate), "
                         r"District (\d+)", re.I)
_SOLICITOR = re.compile(r"Solicitor,? Circuit (\d+)", re.I)
_MATE = re.compile(r"(.+?)\s*\(([^)]*)\)$")
_HEADER = re.compile(r"<th\b[^>]*>(.*?)</th>", re.I | re.S)
_GRID = re.compile(r"""id=["']gridCandidateSearch["']""")


def elections(value: Any) -> dict[str, Any]:
    """The year's list of statewide elections as kept: the general election's id, by its date.
    ValueError for an answer that isn't the list."""
    if not isinstance(value, list) or not all(isinstance(e, dict) and "electionId" in e for e in value):
        raise ValueError("not the State Election Commission's list of elections")
    found: dict[str, str] = {}
    for election in value:
        if " ".join(str(election.get("electionName") or "").split()).upper() != "STATEWIDE GENERAL ELECTION":
            continue
        day = dt.date.fromisoformat(str(election.get("electionDate") or "")[:10])
        found.setdefault(day.isoformat(), str(election["electionId"]))
    return {"elections": found}


def _county_name(upper: str) -> str:
    """"MCCORMICK" -> "McCormick County", as the Census names it."""
    found = next((c for c in counties.counties("SC") if c.name.upper() == upper), None)
    return found.full_name if found else f"{upper.title()} County"


def _race(office: str, where: str) -> Office | None:
    """The race of a row's office and associated counties; None for one left out. ValueError for
    an office it doesn't know with no counties (a statewide one), or a district it can't read."""
    unexpired = bool(_UNEXPIRED.search(office))
    title = " ".join(_UNEXPIRED.sub("", office).split())
    upper = title.upper()
    places = tuple(" ".join(c.split()).upper() for c in where.split(",") if c.strip())
    race = _placed(title, upper, places)
    if race is None:
        if not places and upper not in LEFT_OUT:
            raise ValueError(f"an office it doesn't know: {office}")
        return None
    return dataclasses.replace(race, unexpired=True) if unexpired else race


def _placed(title: str, upper: str, places: tuple[str, ...]) -> Office | None:
    if upper == "U.S. SENATE":
        return us_senate("SC")
    if upper == "GOVERNOR AND LIEUTENANT GOVERNOR":
        return statewide("Governor and Lieutenant Governor", "GOVERNOR")
    if upper in STATEWIDE:
        return statewide(STATEWIDE[upper])
    if found := _DISTRICTED.fullmatch(title):
        kind, number = found.group(1).upper(), int(found.group(2))
        if kind.startswith("U.S."):
            return us_house("SC", number)
        return legislator("sd" if kind == "STATE SENATE" else "hd", number)
    if found := _SOLICITOR.fullmatch(title):
        circuit = found.group(1)
        if not places:
            raise ValueError(f"a circuit without its counties: {title}")
        return Office(f"SOLICITOR {circuit}", f"Solicitor, Circuit {circuit}", "SOLICITOR", "judicial", "counties",
                      circuit, counties=tuple(sorted(places)))
    if upper in COUNTYWIDE and len(places) == 1:
        county = places[0]
        return Office(f"{upper} {county}", f"{_county_name(county)} {COUNTYWIDE[upper]}", upper, "county", "county",
                      counties=places)
    return None


def _ticket(name: str, mate: str) -> str:
    """A Governor's name with an active running mate's: "Alan Wilson and Mike Reichenbach"."""
    found = _MATE.fullmatch(mate)
    if found and found.group(2).strip().upper() == "ACTIVE" and found.group(1):
        return f"{name} and {found.group(1)}"
    return name


def _party(label: str) -> tuple[str | None, str | None]:
    """A row's party: D, R, L, G; another party by its name ("Workers Party"); a petition
    candidate as "Petition", as the ballot prints them; none for "Nonpartisan"."""
    upper = label.upper()
    if not label or upper in _NO_PARTY:
        return None, None
    code, name = party(label)
    if code or upper == "PETITION" or name is None:
        return code, name
    return None, name if upper.endswith(" PARTY") else f"{name} Party"


def candidates(text: str) -> list[Filing]:
    """Every candidate on the ballot the grid places, in its order, undated (ScList.on dates them
    with the election asked); ValueError for a page that isn't the grid (its headings, a row it
    can't read, an office it doesn't know) or isn't all of it (MINIMUM, and the State Senate's in
    a year it's up)."""
    headings = tuple(" ".join(re.sub(r"<[^>]*>", " ", h).split()) for h in _HEADER.findall(text))
    if not _GRID.search(text) or headings[:len(HEADINGS)] != HEADINGS:
        raise ValueError("not the State Election Commission's candidate search")
    parser = Rows()
    parser.feed(text)
    filings: list[Filing] = []
    for index, cells in enumerate(r for r in parser.rows if r):
        if len(cells) < len(HEADINGS):
            raise ValueError(f"a row it can't read: {cells}")
        office, where, name, mate, label, _filed, status = cells[:len(HEADINGS)]
        if status.upper() not in ON_BALLOT:
            continue
        race = _race(office, where)
        if race is None:
            continue
        if not name:
            raise ValueError(f"a row without a name: {office}")
        if race.family == "GOVERNOR":
            name = _ticket(name, mate)
        code, party_name = _party(label)
        filings.append(race.filing(day="", name=name, party=code, party_name=party_name, order=index))
    if not any(f.group == "federal" for f in filings):
        return filings
    senate = {"sd": SENATE} if any(f.reach == "sd" for f in filings) else {}
    return require(filings, {**MINIMUM, **senate})


class ScList(StateList):
    state = "SC"
    source = "state_sc"
    label = "South Carolina State Election Commission"
    page = PAGE
    description = ("South Carolina's official list of the candidates for Congress, its statewide offices, the State "
                   "House and Senate, the solicitors and its county offices, from its State Election Commission.")
    max_bytes = 16 << 20
    index_key = "elections"
    scope_note = ("County council and school board races, races for several seats at once (at-large council seats, soil "
                  "and water commissioners), special purpose districts and the questions aren't shown: your county "
                  "board of voter registration and elections' sample ballot has them.")

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", ELECTIONS, params={"electionType": "General", "year": str(day.year)})

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        text = decoded(raw).lstrip()
        if text.startswith("<") or not text:
            return None
        try:
            value = json.loads(text)
        except ValueError as exc:
            raise ValueError("not the State Election Commission's list of elections") from exc
        return elections(value)

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        election = index["elections"].get(day.isoformat())
        return [RequestSpec("POST", SEARCH, form={"ElectionId": election, **FORM})] if election else None

    def on(self, value: Any, day: dt.date) -> list[Filing]:
        """The filings in a stored answer, dated ``day``: the search asked for that election alone."""
        return [dataclasses.replace(f, day=day.isoformat()) if not f.day else f
                for f in self.read(value) if not f.day or f.day == day.isoformat()]

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        return candidates(decoded(raw) if isinstance(raw, bytes) else raw if isinstance(raw, str) else "")


SCVOTES = "https://scvotes.gov"
VREMS = f"{SITE}/Voter/Login"
GUIDE = Guide(
    name="South Carolina",
    source="South Carolina State Election Commission",
    url=f"{SCVOTES}/",
    computed=True,
    registration_url=f"{SCVOTES}/voters/register-to-vote/",
    mail_url=f"{SCVOTES}/voters/absentee-voting/",
    register="The last day to register to vote in {election} in South Carolina: online, or by fax or email, by 11:59 "
             "p.m. In person, your county's voter registration office takes it until 5 p.m. on the Friday before, "
             "unless it opens that weekend; by mail, it must be postmarked by the Monday after. There's no registering "
             "after that.",
    mail_summary="Absentee application due",
    mail="If you vote absentee in {election}, your application must reach your county board of voter registration and "
         "elections by 5 p.m. today. Your ballot must reach it by 7 p.m. on Election Day. Who can vote absentee, and "
         "how to apply:",
    early_where="Your county's early voting centers, open 8:30 a.m. to 6 p.m. Monday through Saturday, closed on "
                "Sunday: any voter can vote early there, no reason needed. Your county board of voter registration and "
                "elections lists them.",
    credit="Dates worked out from South Carolina's election law; more from the South Carolina State Election Commission",
    poll_hours="7 a.m. – 7 p.m.",
    check_url=f"{VREMS}?PageMode=VoterInformation",
    check_hint="South Carolina's voter look-up (State Election Commission): your registration and your absentee ballot",
    where_url=f"{VREMS}?PageMode=PollingPlace",
    where_hint="The voter look-up: your polling place; your county lists its early voting centers",
    mail_label="How to apply",
    mail_eligibility=only_if("you're 65 or older", "disabled", "in the armed forces or merchant marine, or their spouse "
                             "or dependent", "admitted to a hospital as an emergency patient in the four days before",
                             "unable to vote early or on Election Day because you're away from your county, working, "
                             "caring for someone sick or disabled, or in jail awaiting trial")
    + " Your ballot must reach your county board of voter registration and elections by 7 p.m. on Election Day.",
    mail_deadline="Your application must reach your county board of voter registration and elections by 5 p.m. on ",
    local_office="Your county board of voter registration and elections",
)
RULE = Counts(30, 11, 15, 3).rule("SC")
