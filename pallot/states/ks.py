"""Kansas: the Secretary of State's candidate list (sos.ks.gov/elections/elections_upcoming_candidate.aspx),
every candidate for a national or state office who filed with the Secretary of State, asked in two
steps as its own page asks them. The page (an ASP.NET form) lists its elections in a dropdown
("2026 General", "2026 Primary"), so the general election's id is read there by its year, never
written ahead; then a postback of the page for that election, sent with the page's own hidden fields
(HttpCache.form_from_page), answers one HTML table of every candidate. A plain script gets a 200
from both, with no token, cookie or bot check.

Each row has the name (a Governor's running mate after a slash), the office, its district, a
judge's position and division ("0" where there's none), the party (empty for a judge standing for
retention), then the name's parts, addresses, phones, emails and the filing date, which aren't
read. The list has no election date, incumbents, write-ins or withdrawn candidates (it's updated as
candidates file); its candidates are shown by party. The cache and the bundle keep its filings
alone, never the addresses, phones or emails.

Placed: Congress, Governor and Lieutenant Governor (one ticket), the other statewide offices, the
State House (all 125 districts up every even year) and the State Senate (elected in the years
divisible by four, so a race for it in another even year is for the rest of a term); the State
Board of Education, each of whose ten districts is four State Senate districts (Kan. Const. art. 6,
§2(a); K.S.A. 4-530 to 4-539, on the Senate districts of K.S.A. 4-4,499 et seq., 4-528), placed
by the voter's Senate district; the Supreme Court's justices and the Court of Appeals' judges
standing for retention, statewide; and the district judges by their judicial district's counties
(K.S.A. 4-202 to 4-232 and 4-223a), each elected by party or standing for retention as its
district has chosen, the list's party empty for retention. District magistrate judges serve one
county the list doesn't name, so they're counted but not placed, as is an office it doesn't know.

Kansas's key dates, for its general election on the Tuesday after the first Monday in November of
an even year (K.S.A. 25-101), from the Kansas Statutes on ksrevisor.gov, checked on 2026-10-29
against the Secretary of State's Important Election Dates (registration Oct 13, advance voting
from Oct 14): registration closes for the 20 days before the election (K.S.A. 25-2311(a)(3)), so
the last day is the 21st day before, a mailed application postmarked by then (25-2311(e)(1)). An
advance ballot by mail can be asked for, by any voter, through the Tuesday of the week before
(K.S.A. 25-1122(f)(1)(B)), and must reach the county election officer by 7 p.m. on Election Day
(K.S.A. 25-1132(b), as amended by L. 2025, ch. 8, from January 1, 2026: there's no longer a grace
period). Advance voting in person opens no earlier than the 20th day before (K.S.A. 25-1123(a)),
as each county chooses, and in every county by the Tuesday before, through 12 noon on the day
before (K.S.A. 25-1122(g)(1)). Polls are open 7 a.m. to 7 p.m. in the Central zone and 6 a.m. to
6 p.m. in the Mountain zone, the same hours at once, unless the county election officer sets and
announces other hours, at least 12 in a row (K.S.A. 25-106). 2026: Oct 13, Oct 27, Oct 14 - Nov 2.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import html
import re
from typing import Any

from ..http_cache import RequestSpec
from . import (
    Filing, Office, StateList, decoded, legislator, ordinal, party, party_rank, require, statewide, us_house, us_senate,
)
from .dates import Counts, Guide, first_tuesday_after_first_monday

SITE = "https://www.sos.ks.gov/elections"
PAGE = f"{SITE}/elections_upcoming_candidate.aspx"
ELECTION = "ddlElections"
FORM = {"btnSubmit": "Submit"}  # the page's Submit button, as it sends it
COLUMNS = ("Candidate", "Office", "District", "Position", "Division", "Party")
MINIMUM = {"cd": 4, "hd": 120}  # every House district up: a few might have no candidate
# The State Board of Education's districts, each four State Senate districts (K.S.A. 4-530 to 4-539).
BOARD: dict[int, tuple[int, ...]] = {
    1: (1, 5, 18, 22), 2: (4, 6, 7, 8), 3: (11, 23, 35, 37), 4: (3, 9, 10, 21), 5: (36, 38, 39, 40),
    6: (2, 17, 19, 20), 7: (24, 31, 33, 34), 8: (25, 28, 29, 30), 9: (12, 13, 14, 15), 10: (16, 26, 27, 32),
}
# The judicial districts' counties (K.S.A. 4-202 to 4-232, the 22nd's 4-223a).
JUDICIAL: dict[int, tuple[str, ...]] = {
    1: ("ATCHISON", "LEAVENWORTH"), 2: ("JACKSON", "JEFFERSON", "POTTAWATOMIE", "WABAUNSEE"), 3: ("SHAWNEE",),
    4: ("ANDERSON", "COFFEY", "FRANKLIN", "OSAGE"), 5: ("CHASE", "LYON"), 6: ("BOURBON", "LINN", "MIAMI"),
    7: ("DOUGLAS",), 8: ("DICKINSON", "GEARY", "MARION", "MORRIS"), 9: ("HARVEY", "MCPHERSON"), 10: ("JOHNSON",),
    11: ("CHEROKEE", "CRAWFORD", "LABETTE"), 12: ("CLOUD", "JEWELL", "LINCOLN", "MITCHELL", "REPUBLIC", "WASHINGTON"),
    13: ("BUTLER", "ELK", "GREENWOOD"), 14: ("CHAUTAUQUA", "MONTGOMERY"),
    15: ("CHEYENNE", "LOGAN", "RAWLINS", "SHERIDAN", "SHERMAN", "THOMAS", "WALLACE"),
    16: ("CLARK", "COMANCHE", "FORD", "GRAY", "KIOWA", "MEADE"),
    17: ("DECATUR", "GRAHAM", "NORTON", "OSBORNE", "PHILLIPS", "SMITH"), 18: ("SEDGWICK",), 19: ("COWLEY",),
    20: ("BARTON", "ELLSWORTH", "RICE", "RUSSELL", "STAFFORD"), 21: ("CLAY", "RILEY"),
    22: ("BROWN", "DONIPHAN", "MARSHALL", "NEMAHA"), 23: ("ELLIS", "GOVE", "ROOKS", "TREGO"),
    24: ("EDWARDS", "HODGEMAN", "LANE", "NESS", "PAWNEE", "RUSH"),
    25: ("FINNEY", "GREELEY", "HAMILTON", "KEARNY", "SCOTT", "WICHITA"),
    26: ("GRANT", "HASKELL", "MORTON", "SEWARD", "STANTON", "STEVENS"), 27: ("RENO",), 28: ("OTTAWA", "SALINE"),
    29: ("WYANDOTTE",), 30: ("BARBER", "HARPER", "KINGMAN", "PRATT", "SUMNER"),
    31: ("ALLEN", "NEOSHO", "WILSON", "WOODSON"),
}
STATEWIDE = {"SECRETARY OF STATE": "Secretary of State", "ATTORNEY GENERAL": "Attorney General",
             "STATE TREASURER": "State Treasurer", "COMMISSIONER OF INSURANCE": "Commissioner of Insurance"}
_OPTION = re.compile(r"""<option\b[^>]*\bvalue=["'](\d+)["'][^>]*>([^<]*)""", re.I)
_GENERAL = re.compile(r"(\d{4}) General", re.I)
_SELECT = re.compile(r"""<select\b[^>]*name=["']ddlElections["'][^>]*>(.*?)</select>""", re.I | re.S)
_LISTED = re.compile(r"""<span\b[^>]*id=["']lblElection["'][^>]*>([^<]*)<""", re.I)
_TABLE = re.compile(r"""<table\b[^>]*id=["']gvCandidateList["'][^>]*>(.*?)</table>""", re.I | re.S)
_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.I | re.S)


def _text(cell: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", cell)).split())


def elections(text: str) -> dict[str, Any]:
    """The page as kept: each general election's id in its dropdown, by its date. ValueError for a
    page that isn't the candidate list."""
    select = _SELECT.search(text)
    if select is None:
        raise ValueError("not the Secretary of State's candidate list")
    found: dict[str, str] = {}
    for value, label in _OPTION.findall(select.group(1)):
        general = _GENERAL.fullmatch(" ".join(html.unescape(label).split()))
        if general:
            found.setdefault(first_tuesday_after_first_monday(int(general.group(1)), 11).isoformat(), value)
    return {"elections": found}


def _number(cell: str, what: str) -> int:
    if not cell.isdigit():
        raise ValueError(f"a {what} it can't read: {cell!r}")
    return int(cell)


def _court(family: str, title: str, name: str, retained: bool, reach: str, district: int | None, seat: int,
           counties: tuple[str, ...] = ()) -> Office:
    """A judge's race: a retention question of its own (the judge its one candidate) or a seat
    elected by party."""
    office_id = " ".join(str(part) for part in (family, district, seat) if part)
    if retained:
        return Office(f"{office_id} {name.upper()}", f"Retain {name}, {title}", family, "judicial", reach,
                      str(district) if district else None, counties, incumbent=True, retention=True)
    return Office(office_id, title, family, "judicial", reach, str(district) if district else None, counties)


def _race(name: str, office: str, district: int, position: int, division: int, retained: bool,
          year: int) -> Office:
    """The race of a row. ValueError for a federal office it doesn't know."""
    upper = office.upper()
    if upper == "UNITED STATES SENATE":
        return us_senate("KS")
    if upper == "UNITED STATES HOUSE OF REPRESENTATIVES":
        return us_house("KS", district)
    if upper.startswith("UNITED STATES"):
        raise ValueError(f"a federal office it doesn't know: {office}")
    if upper == "GOVERNOR / LT. GOVERNOR":
        return statewide("Governor and Lieutenant Governor", "GOVERNOR")
    if upper in STATEWIDE:
        return statewide(STATEWIDE[upper])
    if upper == "KANSAS HOUSE OF REPRESENTATIVES":
        return legislator("hd", district)
    if upper == "KANSAS SENATE":
        return dataclasses.replace(legislator("sd", district), unexpired=year % 4 != 0)
    if upper == "MEMBER, STATE BOARD OF EDUCATION":
        senate = BOARD.get(district)
        return Office(f"STATE BOARD OF EDUCATION {district}", f"State Board of Education District {district}",
                      "STATE BOARD OF EDUCATION", "state", "sd" if senate else "unplaced",
                      ",".join(str(number) for number in senate) if senate else str(district))
    if upper == "SUPREME COURT JUSTICE":
        return _court("SUPREME COURT", "Justice of the Supreme Court", name, retained, "state", None, position)
    if upper == "COURT OF APPEALS JUDGE":
        return _court("COURT OF APPEALS", "Judge of the Court of Appeals", name, retained, "state", None, position)
    if upper == "DISTRICT COURT JUDGE":
        counties = JUDICIAL.get(district, ())
        title = f"District Judge, {ordinal(district)} Judicial District" + (f", Division {division}" if division else "")
        return _court("DISTRICT COURT", title, name, retained, "counties" if counties else "unplaced", district,
                      division, counties)
    if upper == "DISTRICT MAGISTRATE JUDGE":
        title = (f"District Magistrate Judge, {ordinal(district)} Judicial District"
                 + (f", Position {position}" if position else ""))
        return _court("DISTRICT MAGISTRATE", title, name, retained, "unplaced", district, position)
    return Office(f"{upper} {district or ''}".strip(), office + (f", District {district}" if district else ""), upper,
                  "state", "unplaced", str(district) if district else None)


def _party(label: str) -> tuple[str | None, str | None]:
    """A row's party: D, R, L; another by its name ("United Kansas", "Independent"); none for none."""
    code, name = party(label)
    return code, name[:1].upper() + name[1:] if name else None


def _listed(text: str) -> str | None:
    """The election the page lists the candidates of ("2026 General"), or None for the page without a list."""
    found = _LISTED.search(text)
    return " ".join(html.unescape(found.group(1)).split()) if found else None


def _rows(text: str) -> list[list[str]]:
    """The list's rows, each its cells as text, after checking its header. ValueError for a page
    without the table or with other columns."""
    table = _TABLE.search(text)
    if table is None:
        return []
    rows = [[_text(cell) for cell in _CELL.findall(row)] for row in _ROW.findall(table.group(1))]
    if not rows or tuple(rows[0][:len(COLUMNS)]) != COLUMNS:
        raise ValueError(f"its columns aren't the list's: {rows[0][:len(COLUMNS)] if rows else []}")
    for row in rows[1:]:
        if len(row) < len(COLUMNS):
            raise ValueError(f"a row it can't read: {' '.join(row)[:80]}")
    return rows[1:]


def candidates(text: str) -> list[Filing]:
    """Every candidate on the list of a general election, undated (KsList.on dates them with the
    election asked), by race in the list's order and by party in each; ValueError for a page that
    isn't a general election's list, a row it can't read, or a list short of its races (MINIMUM, in
    a year with Congress up)."""
    election = _listed(text)
    general = _GENERAL.fullmatch(election or "")
    if general is None:
        raise ValueError(f"not the Secretary of State's list of a general election's candidates: {election}")
    year = int(general.group(1))
    filings: list[Filing] = []
    starts: dict[str, int] = {}
    for cells in _rows(text):
        name, office, label = cells[0], cells[1], cells[5]
        if not name or not office:
            raise ValueError(f"a row without a name or office: {' '.join(cells[:6])}")
        district, position, division = (_number(cells[i], what) for i, what in
                                        ((2, "district"), (3, "position"), (4, "division")))
        race = _race(name, office, district, position, division, not label, year)
        if race.family == "GOVERNOR":
            name = " and ".join(part.strip() for part in name.split("/") if part.strip())
        code, party_name = _party(label)
        start = starts.setdefault(race.office_id, len(starts))
        filings.append(race.filing(day="", name=name, party=code, party_name=party_name,
                                   order=start * 10 + party_rank(code, party_name)))
    if not any(f.group == "federal" for f in filings):
        return filings
    return require(filings, MINIMUM)


class KsList(StateList):
    state = "KS"
    source = "state_ks"
    label = "Kansas Secretary of State"
    page = PAGE
    description = ("Kansas's official list of the candidates for Congress, its statewide offices, the Legislature, the "
                   "State Board of Education and the courts, from its Secretary of State.")
    max_bytes = 16 << 20
    postback = True
    index_key = "elections"
    scope_note = ("County and city races, the district magistrate judges and any questions aren't shown: your county "
                  "election office's sample ballot has them.")

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", PAGE)

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        """The page's dropdown, or None for a list of candidates. A list without any candidates yet
        is read as its dropdown: no list yet."""
        text = decoded(raw)
        return None if _listed(text) and _rows(text) else elections(text)

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        election = index["elections"].get(day.isoformat())
        return [RequestSpec("POST", PAGE, form={ELECTION: election, **FORM})] if election else None

    def on(self, value: Any, day: dt.date) -> list[Filing]:
        """The filings in a stored answer, dated ``day``: the postback asked for that election alone."""
        return [dataclasses.replace(f, day=day.isoformat()) if not f.day else f
                for f in self.read(value) if not f.day or f.day == day.isoformat()]

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        return candidates(decoded(raw) if isinstance(raw, bytes) else raw if isinstance(raw, str) else "")


VOTERVIEW = "https://myvoteinfo.voteks.org/voterview"
GUIDE = Guide(
    name="Kansas",
    source="Kansas Secretary of State",
    url=f"{SITE}/elections.html",
    computed=True,
    registration_url="https://www.kdor.ks.gov/Apps/VoterReg",
    mail_url=f"{SITE}/advance-voting.html",
    register="The last day to register to vote in {election} in Kansas: online, in person at your county election "
             "office, or by mail postmarked today. There's no registering after it.",
    mail_summary="Advance ballot by mail application due",
    mail="If you vote by mail in {election}, your application for an advance ballot must reach your county election "
         "office today. Your ballot must reach it by 7 p.m. on Election Day; one that arrives later isn't counted. Any "
         "voter can vote by mail; how to apply:",
    early_where="Your county election office, and any other place your county names: vote early in person there "
                "through 12 noon on the day before Election Day. Your county can open it from 20 days before, and every "
                "county opens it by the Tuesday before; it sets the days and hours, and can add the Saturday before.",
    credit="Dates worked out from Kansas's election law; more from the Kansas Secretary of State",
    poll_hours="7 a.m. – 7 p.m. Central, 6 a.m. – 6 p.m. Mountain",
    polls_text="Polls are open 7 a.m. to 7 p.m. Central time, 6 a.m. to 6 p.m. Mountain time, unless your county "
               "announces other hours; if you're in line when they close, you can vote.",
    check_url=VOTERVIEW,
    check_hint="VoterView (Kansas Secretary of State): your registration, your advance ballot and your polling place",
    where_url=VOTERVIEW,
    where_hint="VoterView (Kansas Secretary of State): your polling place; your county lists its advance voting places",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote by mail, no reason needed. Your ballot must reach your county "
                     "election office by 7 p.m. on Election Day.",
    mail_deadline="Your application must reach your county election office by ",
)
RULE = Counts(21, 7, 20, 1).rule("KS")
