"""Kentucky: the Secretary of State's candidate filings (web.sos.ky.gov/CandidateFilings), every
candidate who filed with the Secretary of State for an election, asked in two steps as its own page
asks them. The page (an ASP.NET form) lists its elections in a dropdown ("2026 General Election",
"2027 Primary Election"), so the general election's id is read there by its year, never written
ahead; then a postback of its "List All Candidates" button for that election, sent with the page's
own hidden fields (HttpCache.form_from_page), answers every office's candidates as HTML tables. A
plain script gets a 200 from both, with no token, cookie or bot check. An election with no
candidates yet answers the page as it was, without the list.

Each office's table has a row per candidate: the name (a Governor's running mate under it), a post
office box or email, the office, the district and division as ordinals ("6th / 1st"), and the
party ("Nonpartisan" for the courts, "Write-In" for a declared write-in candidate). The withdrawn,
deceased and disqualified come in their own tables after the rest, and are left out. The list has
no election date, no incumbents and no ballot order (its candidates are by name, so they're shown
by party, write-ins last); the cache and the bundle keep its filings alone, never the addresses or
emails.

Placed: Congress, Governor and Lieutenant Governor (one ticket) and the other statewide offices, the
State House (all 100 districts up every even year) and the State Senate (the 19 even-numbered
districts in 2026, the 19 odd ones in 2028), and the courts by their counties: the Supreme Court's
districts (KRS 21A.010) and the Court of Appeals' (the same seven, KRS 22A.010), the judicial
circuits' circuit judges and Commonwealth's Attorneys (KRS 23A.020) and the judicial districts'
district judges (KRS 24A.030; from the 2030 election, its version in force on January 1, 2031). The
constitutional amendments, the President and the county offices (the clerks' own filings) are left
out. An office with a district it doesn't know is counted but not placed.

Kentucky's key dates, for its general election on the first Tuesday after the first Monday in
November of every year (KRS 118.025(4)), checked against the State Board of Elections' 2026 Election
Calendar (final version, 2025-10-06) on 2026-10-29: registration closes the fourth Tuesday before
(KRS 116.045(2)), so the last day to register is the Monday 29 days before, moved to the next working
day when it's a state or federal holiday (Columbus Day in a year whose election is November 8); the
calendar says online by 4 p.m. local time, by mail postmarked that day. A mail-in absentee ballot is
asked for on the State Board of Elections' portal, which closes at 11:59 p.m. local time 14 days
before (KRS 117.085(1)(f)), and only the voters KRS 117.085(1)(h) and 117.077 name can ask: the
military and overseas, students away, those temporarily out of state or away from their county for
all of in-person voting, those who can't vote in person through age, disability or illness, those
in jail awaiting trial and those in the address confidentiality program; the ballot must reach the
county clerk by the time the polls close (KRS 117.086(1)(b)). No-excuse in-person voting runs the
Thursday, Friday and Saturday before Election Day, at least 8 hours a day between 6 a.m. and 8 p.m.
as each county board of elections sets (KRS 117.076(1)); in the six business days before that
Thursday (the 13th to the 6th day before), only voters with one of KRS 117.076(2)'s excuses can vote
in person. Polls are open 6 a.m. to 6 p.m. prevailing (local) time (KRS 118.035(1)), the same hours
in the Eastern and Central zones. 2026: Oct 5, Oct 20, Oct 29 - Oct 31.
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
from .dates import Counts, Guide, Roll, columbus_day, first_tuesday_after_first_monday, only_if

SITE = "https://web.sos.ky.gov/CandidateFilings"
PAGE = f"{SITE}/Default.aspx"
ELECTION = "ctl00$MainContent$ddlElection"
FORM = {"ctl00$MainContent$bListAll": "List All Candidates"}  # the "List All Candidates" button, as the page sends it
MINIMUM = {"cd": 6, "sd": 15, "hd": 90}  # every House district up, and the Senate's half: a few can go unopposed
# The Supreme Court's seven districts (KRS 21A.010), which are the Court of Appeals' too (KRS 22A.010).
SUPREME: dict[int, tuple[str, ...]] = {
    1: ("BALLARD", "CALDWELL", "CALLOWAY", "CARLISLE", "CHRISTIAN", "CRITTENDEN", "DAVIESS", "FULTON", "GRAVES",
        "HENDERSON", "HICKMAN", "HOPKINS", "LIVINGSTON", "LOGAN", "LYON", "MARSHALL", "MCCRACKEN", "MCLEAN",
        "MUHLENBERG", "TODD", "TRIGG", "UNION", "WEBSTER"),
    2: ("ALLEN", "BARREN", "BRECKINRIDGE", "BULLITT", "BUTLER", "EDMONSON", "GRAYSON", "HANCOCK", "HARDIN", "HART",
        "LARUE", "MEADE", "MONROE", "OHIO", "SIMPSON", "SPENCER", "WARREN"),
    3: ("ADAIR", "ANDERSON", "BELL", "BOYLE", "CASEY", "CLINTON", "CUMBERLAND", "GARRARD", "GREEN", "HARLAN", "KNOX",
        "LAUREL", "LINCOLN", "MARION", "MCCREARY", "MERCER", "METCALFE", "NELSON", "PULASKI", "ROCKCASTLE", "RUSSELL",
        "TAYLOR", "WASHINGTON", "WAYNE", "WHITLEY"),
    4: ("JEFFERSON",),
    5: ("BOURBON", "CLARK", "FAYETTE", "FRANKLIN", "JESSAMINE", "MADISON", "SCOTT", "WOODFORD"),
    6: ("BOONE", "BRACKEN", "CAMPBELL", "CARROLL", "GALLATIN", "GRANT", "HENRY", "KENTON", "OLDHAM", "OWEN",
        "PENDLETON", "SHELBY", "TRIMBLE"),
    7: ("BATH", "BOYD", "BREATHITT", "CARTER", "CLAY", "ELLIOTT", "ESTILL", "FLEMING", "FLOYD", "GREENUP", "HARRISON",
        "JACKSON", "JOHNSON", "KNOTT", "LAWRENCE", "LEE", "LESLIE", "LETCHER", "LEWIS", "MAGOFFIN", "MARTIN", "MASON",
        "MENIFEE", "MONTGOMERY", "MORGAN", "NICHOLAS", "OWSLEY", "PERRY", "PIKE", "POWELL", "ROBERTSON", "ROWAN",
        "WOLFE"),
}
# The judicial circuits (KRS 23A.020, in force since January 2, 2023).
CIRCUITS: dict[int, tuple[str, ...]] = {
    1: ("BALLARD", "CARLISLE", "FULTON", "HICKMAN"), 2: ("MCCRACKEN",), 3: ("CHRISTIAN",), 4: ("HOPKINS",),
    5: ("CRITTENDEN", "UNION", "WEBSTER"), 6: ("DAVIESS",), 7: ("LOGAN", "TODD"), 8: ("EDMONSON", "WARREN"),
    9: ("HARDIN",), 10: ("HART", "LARUE", "NELSON"), 11: ("GREEN", "MARION", "TAYLOR", "WASHINGTON"),
    12: ("HENRY", "OLDHAM", "TRIMBLE"), 13: ("GARRARD", "JESSAMINE"), 14: ("BOURBON", "SCOTT", "WOODFORD"),
    15: ("CARROLL", "GRANT", "OWEN"), 16: ("KENTON",), 17: ("CAMPBELL",),
    18: ("HARRISON", "NICHOLAS", "PENDLETON", "ROBERTSON"), 19: ("BRACKEN", "FLEMING", "MASON"), 20: ("GREENUP", "LEWIS"),
    21: ("BATH", "MENIFEE", "MONTGOMERY", "ROWAN"), 22: ("FAYETTE",), 23: ("ESTILL", "LEE", "OWSLEY"),
    24: ("JOHNSON", "LAWRENCE", "MARTIN"), 25: ("CLARK", "MADISON"), 26: ("HARLAN",), 27: ("KNOX", "LAUREL"),
    28: ("LINCOLN", "PULASKI", "ROCKCASTLE"), 29: ("ADAIR", "CASEY"), 30: ("JEFFERSON",), 31: ("FLOYD",), 32: ("BOYD",),
    33: ("PERRY",), 34: ("MCCREARY", "WHITLEY"), 35: ("PIKE",), 36: ("KNOTT", "MAGOFFIN"),
    37: ("CARTER", "ELLIOTT", "MORGAN"), 38: ("BUTLER", "HANCOCK", "OHIO"), 39: ("BREATHITT", "POWELL", "WOLFE"),
    40: ("CLINTON", "CUMBERLAND", "MONROE"), 41: ("CLAY", "JACKSON", "LESLIE"), 42: ("CALLOWAY", "MARSHALL"),
    43: ("BARREN", "METCALFE"), 44: ("BELL",), 45: ("MCLEAN", "MUHLENBERG"), 46: ("BRECKINRIDGE", "GRAYSON", "MEADE"),
    47: ("LETCHER",), 48: ("FRANKLIN",), 49: ("ALLEN", "SIMPSON"), 50: ("BOYLE", "MERCER"), 51: ("HENDERSON",),
    52: ("GRAVES",), 53: ("ANDERSON", "SHELBY", "SPENCER"), 54: ("BOONE", "GALLATIN"), 55: ("BULLITT",),
    56: ("CALDWELL", "LIVINGSTON", "LYON", "TRIGG"), 57: ("RUSSELL", "WAYNE"),
}
# The judicial districts (KRS 24A.030 in force until January 1, 2031): the circuits' counties but where they differ.
DISTRICTS: dict[int, tuple[str, ...]] = {
    **CIRCUITS, 8: ("WARREN",), 10: ("HART", "LARUE"), 13: ("GARRARD", "JESSAMINE", "LINCOLN"),
    28: ("PULASKI", "ROCKCASTLE"), 38: ("BUTLER", "EDMONSON", "HANCOCK", "OHIO"), 40: ("CLINTON", "RUSSELL", "WAYNE"),
    42: ("CALLOWAY",), 57: ("NELSON",), 58: ("MARSHALL",), 59: ("CUMBERLAND", "MONROE"),
}
# Its version from January 1, 2031 (2022 Ky. Acts ch. 129), whose judges are elected in 2030.
DISTRICTS_2031: dict[int, tuple[str, ...]] = {
    **{number: places for number, places in DISTRICTS.items() if number != 59},
    8: ("EDMONSON", "WARREN"), 38: ("BUTLER", "HANCOCK", "OHIO"), 42: ("CALLOWAY", "MARSHALL"),
    58: ("CUMBERLAND", "MONROE"),
}
DISTRICTED = {"US REPRESENTATIVE": "cd", "STATE SENATOR": "sd", "STATE REPRESENTATIVE": "hd"}
LEFT_OUT = re.compile(r"^(?:CONSTITUTIONAL AMENDMENT|AMENDMENT|PRESIDENT|LIEUTENANT GOVERNOR)\b")
_ORDINAL = r"(\d+)(?:st|nd|rd|th)?"
_DIVISION = re.compile(rf"{_ORDINAL}(?:\s*/\s*{_ORDINAL})?", re.I)
_OPTION = re.compile(r"""<option\b[^>]*\bvalue=["'](\d+)["'][^>]*>([^<]*)""", re.I)
_GENERAL = re.compile(r"(\d{4}) General Election", re.I)
_SELECT = re.compile(r"""<select\b[^>]*name=["']ctl00\$MainContent\$ddlElection["'][^>]*>(.*?)</select>""", re.I | re.S)
_CHOSEN = re.compile(r"""<option\b[^>]*\bselected\b[^>]*>\s*(\d{4}) General Election""", re.I)  # the list's election
_HEADER = re.compile(r"""id=["']ctl00_MainContent_lblSearchHeader["'][^>]*>([^<]*)<""", re.I)
_WITHDRAWN = re.compile(r"""id=["']ctl00_MainContent_pnlWddResults["']""", re.I)
_ROW = re.compile(r"""<tr\b[^>]*class=["']boldleft["'][^>]*>(.*?)</tr>""", re.I | re.S)
_CELL = re.compile(r"<td\b[^>]*>(.*?)</td>", re.I | re.S)
_BREAK = re.compile(r"<br\s*/?>", re.I)


def _text(cell: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", cell)).split())


def elections(text: str) -> dict[str, Any]:
    """The page as kept: each general election's id in its dropdown, by its date. ValueError for a
    page that isn't the candidate filings."""
    select = _SELECT.search(text)
    if select is None:
        raise ValueError("not the Secretary of State's candidate filings")
    found: dict[str, str] = {}
    for value, label in _OPTION.findall(select.group(1)):
        general = _GENERAL.fullmatch(" ".join(html.unescape(label).split()))
        if general:
            found.setdefault(first_tuesday_after_first_monday(int(general.group(1)), 11).isoformat(), value)
    return {"elections": found}


def _numbers(district: str) -> tuple[int, int | None] | None:
    """ "6th / 1st" -> (6, 1), "3rd" -> (3, None); None for none."""
    found = _DIVISION.fullmatch(district)
    if not found:
        return None
    return int(found.group(1)), int(found.group(2)) if found.group(2) else None


def _court(family: str, title: str, unit: str, counties: tuple[str, ...], number: int, division: int | None) -> Office:
    """A court's (or a Commonwealth's Attorney's) race in its circuit or district, placed by its counties."""
    where = f"{ordinal(number)} {unit}" + (f", {ordinal(division)} Division" if division else "")
    reach = "unplaced" if not counties else "county" if len(counties) == 1 else "counties"
    office_id = f"{family} {number}" + (f" {division}" if division else "")
    return Office(office_id, f"{title}, {where}", family, "judicial", reach, str(number), counties=counties)


def _race(office: str, district: str, year: int) -> Office | None:
    """The race of a row's office and district; None for one left out. ValueError for a district
    it can't read where the office has one."""
    title = " ".join(office.split())
    upper = title.upper().replace("’", "'")
    if not district:
        if upper == "US SENATOR":
            return us_senate("KY")
        if upper == "GOVERNOR":
            return statewide("Governor and Lieutenant Governor", "GOVERNOR")
        if LEFT_OUT.match(upper) or upper in DISTRICTED:
            return None
        return statewide(title)
    numbers = _numbers(district)
    if numbers is None:
        raise ValueError(f"a district it can't read: {office} {district}")
    number, division = numbers
    if upper in DISTRICTED:
        reach = DISTRICTED[upper]
        return us_house("KY", number) if reach == "cd" else legislator(reach, number)
    if upper == "JUSTICE OF THE SUPREME COURT":
        return _court("SUPREME COURT", "Justice of the Supreme Court", "Supreme Court District", SUPREME.get(number, ()),
                      number, division)
    if upper == "JUDGE OF THE COURT OF APPEALS":
        return _court("COURT OF APPEALS", "Judge of the Court of Appeals", "Appellate District",
                      SUPREME.get(number, ()), number, division)
    if upper == "CIRCUIT JUDGE":
        return _court("CIRCUIT JUDGE", "Circuit Judge", "Circuit", CIRCUITS.get(number, ()), number, division)
    if upper == "DISTRICT JUDGE":
        table = DISTRICTS_2031 if year >= 2030 else DISTRICTS
        return _court("DISTRICT JUDGE", "District Judge", "District", table.get(number, ()), number, division)
    if upper == "COMMONWEALTH'S ATTORNEY":
        return _court("COMMONWEALTHS ATTORNEY", "Commonwealth's Attorney", "Circuit", CIRCUITS.get(number, ()),
                      number, None)
    return Office(f"{upper} {district}", f"{title}, {district}", upper, "state", "unplaced", district)


def _rows(text: str) -> list[list[str]]:
    """Each candidate row's cells, as their inner HTML; ValueError for a row it can't read."""
    rows = []
    for row in _ROW.findall(text):
        cells = _CELL.findall(row)
        if len(cells) < 5:
            raise ValueError(f"a row it can't read: {_text(row)[:80]}")
        rows.append(cells)
    return rows


def _name(cell: str) -> str:
    """The name on the ballot: a Governor's with the running mate's under it, "A and B"."""
    names = [name for name in (_text(part) for part in _BREAK.split(cell)) if name]
    return " and ".join(names[:2])


def _party(label: str) -> tuple[str | None, str | None]:
    """A row's party: D, R, L, G; another party by its name ("Kentucky Party", "Independent"); none
    for "Nonpartisan" or a write-in."""
    if label.upper() in ("NONPARTISAN", "WRITE-IN"):
        return None, None
    return party(label)


def _listed(text: str) -> bool:
    """Whether the page is the list of all candidates, not the page without it."""
    header = _HEADER.search(text)
    return bool(header) and " ".join(header.group(1).split()).upper() == "ALL CANDIDATES"


def candidates(text: str) -> list[Filing]:
    """Every candidate the list places, undated (KyList.on dates them with the election asked), by
    race in the list's order and by party in each, write-ins last; ValueError for a page that isn't
    the list of all candidates (or doesn't say whose election it is), a row it can't read, or a
    list short of its races (MINIMUM, in a year with Congress up)."""
    select = _SELECT.search(text)
    chosen = _CHOSEN.search(select.group(1)) if select else None
    if not _listed(text) or chosen is None:
        raise ValueError("not the Secretary of State's list of all candidates")
    year = int(chosen.group(1))
    cut = _WITHDRAWN.search(text)
    listed, gone = (text[:cut.start()], text[cut.start():]) if cut else (text, "")
    off = {(_text(c[2]).upper(), _text(c[3]), _name(c[0]).upper()) for c in _rows(gone)}
    filings: list[Filing] = []
    starts: dict[str, int] = {}
    for cells in _rows(listed):
        name, office, district, label = _name(cells[0]), _text(cells[2]), _text(cells[3]), _text(cells[4])
        if not name:
            raise ValueError(f"a row without a name: {office}")
        if (office.upper(), district, name.upper()) in off:
            continue
        race = _race(office, district, year)
        if race is None:
            continue
        if race.family != "GOVERNOR":
            name = _text(cells[0])
        write_in = label.upper() == "WRITE-IN"
        code, party_name = _party(label)
        start = starts.setdefault(race.office_id, len(starts))
        order = start * 10 + (9 if write_in else party_rank(code, party_name))
        filings.append(race.filing(day="", name=name, party=code, party_name=party_name, write_in=write_in,
                                   order=order))
    if not any(f.group == "federal" for f in filings):
        return filings
    return require(filings, MINIMUM)


class KyList(StateList):
    state = "KY"
    source = "state_ky"
    label = "Kentucky Secretary of State"
    page = PAGE
    description = ("Kentucky's official list of the candidates for Congress, its statewide offices, the General "
                   "Assembly, the courts and the Commonwealth's Attorneys, from its Secretary of State.")
    max_bytes = 16 << 20
    postback = True
    index_key = "elections"
    scope_note = ("County and city races and the constitutional amendments aren't shown: your county clerk's sample "
                  "ballot has them.")

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", PAGE)

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        """The page's dropdown, or None for the list of all candidates. An election with no
        candidates answers the page without the list, read as its dropdown: no list yet."""
        text = decoded(raw)
        return None if _listed(text) else elections(text)

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


ELECT = "https://elect.ky.gov"
VRSWS = "https://vrsws.sos.ky.gov"
GOVOTEKY = f"{VRSWS}/ovrweb/govoteky"
GUIDE = Guide(
    name="Kentucky",
    source="Kentucky State Board of Elections",
    url=f"{ELECT}/",
    computed=True,
    registration_url=GOVOTEKY,
    mail_url=f"{VRSWS}/abrweb",
    register="The last day to register to vote in {election} in Kentucky: online by 4 p.m. local time, by mail "
             "postmarked today, or in person at your county clerk's office by the time it closes. There's no "
             "registering after it.",
    mail_summary="Mail-in absentee ballot request due",
    mail="If you vote by mail in {election}, ask for your ballot on the State Board of Elections' portal by 11:59 p.m. "
         "local time today. Your ballot must reach your county clerk by 6 p.m. on Election Day. Who can vote by mail, "
         "and how to ask:",
    early_where="Your county clerk's office, and any other place your county board of elections names: any voter can "
                "vote early there, no reason needed, on the Thursday, Friday and Saturday before Election Day, at least "
                "8 hours a day between 6 a.m. and 8 p.m. In the six business days before that Thursday, you can vote "
                "there in person only with a reason the law allows (away from your county on those days and Election "
                "Day, surgery, the last months of pregnancy, age, disability or illness, a student away, or working all "
                "those hours).",
    credit="Dates worked out from Kentucky's election law; more from the Kentucky State Board of Elections",
    poll_hours="6 a.m. – 6 p.m.",
    check_url=GOVOTEKY,
    check_hint="GoVoteKY (State Board of Elections): your registration and your absentee ballot",
    where_url=f"{VRSWS}/vic/",
    where_hint="The voter information center: your polling place; your county clerk lists its early voting places",
    mail_label="How to ask",
    mail_eligibility=only_if("you're in the military or overseas, or their family", "a student living away from your "
                             "county", "living out of state for now", "away from your county on Election Day and every "
                             "day of in-person voting", "unable to vote in person because of your age, a disability or "
                             "an illness", "in jail awaiting trial", "in the Secretary of State's address "
                             "confidentiality program")
    + " Your ballot must reach your county clerk by 6 p.m. on Election Day.",
    mail_deadline="Ask on the State Board of Elections' portal by 11:59 p.m. local time on ",
    local_office="Your county clerk",
    local_time=True,
)
RULE = Counts(29, 14, 5, 3, every_year=True, roll=Roll(holidays=lambda year: (columbus_day(year),))).rule("KY")
