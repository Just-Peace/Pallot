"""Missouri: the Secretary of State's certification of the general election's candidates, a PDF
("2026GeneralElectionCertifiedCandidates.pdf"; 2024's was "CertificationOfCandidatesNovember2024.pdf"),
linked from its elections page as "Certified Candidates - November 2026", so it's found on that page
by its link, never by a name worked out ahead (an earlier year's link is left in an HTML comment,
which isn't read). sos.mo.gov's Cloudflare shows a script's default User-Agent a challenge, but
answers Pallot's with a 200, as it does a browser.

The certification lists each party's candidates in ballot order, under the party's heading
("REPUBLICAN CANDIDATES", "INDEPENDENT CANDIDATES"), each office's under its heading ("For State
Auditor", "U.S. Representative" in 2024), a district's candidates as "District 2, Ann Wagner", a
circuit court's as "Circuit 19 Division 2, Daniel Green"; then the judges standing for retention
("JUDICIAL CANDIDATES", Mo. Const. Art. V §25(c)): the Supreme Court's, the Court of Appeals' by
district ("Eastern District, Virginia W. Lay"), and the circuit and associate circuit judges of the
circuits under the nonpartisan court plan. It names no incumbents, write-ins or withdrawn
candidates, and no addresses; the file is kept as its filings all the same. Its election is the
general election its heading names. The Secretary of
State's list of withdrawn and removed candidates covers only the primary's filings, so it isn't read.

Placed: Congress, the statewide offices, the State Senate (half its districts up each election)
and State House, the judges for retention, and the contested circuit judges. The Supreme Court's judges are retained statewide, and the Court of
Appeals' by their district's counties (RSMo 477.050, 477.060, 477.070: the Western District is every
county not in the other two). A circuit's judges are placed by its counties, as the Revised
Statutes' chapter 478 heads each circuit's sections (CIRCUITS). St. Louis County's (the 21st
circuit) and St. Louis City's (the 22nd) can't be, since the Census names them alike ("St.
Louis"), and neither can a circuit whose counties chapter 478 doesn't head (the 36th): those
races are counted, not shown. The President is left out, as in other states.

Missouri's U.S. House map for 2026 is its 2022 map, not the 2025 one the Census geocoder gives
(tigerweb.GOVERNING), so the voter's district comes from the 2022 map.

Missouri's key dates, for its general election (the Tuesday after the first Monday in November of
an even year, RSMo 115.121), checked against the Secretary of State's 2026 election calendar on
2026-10-29: registration closes at 5 p.m. on the fourth Wednesday before (RSMo 115.135); an absentee
ballot can be asked for by mail, fax or email until 5 p.m. on the second Wednesday before, and in
person until 5 p.m. the day before (115.279.4); voting absentee needs one of the reasons the law
lists (115.277.3), except in person from the second Tuesday before (115.277.1), so that's early
voting, through the day before; the ballot must reach the election authority by the time the polls
close (115.293.1). Polls are open 6 a.m. to 7 p.m. (115.407).
"""

from __future__ import annotations

import datetime as dt
import html
import re
from typing import Any
from urllib.parse import urljoin

from .. import counties
from ..http_cache import RequestSpec
from . import (
    MONTH_DAY_YEAR, Filing, Office, StateList, decoded, legislator, party, pdf_lines, require, statewide, us_house,
    us_senate,
)
from .dates import Counts, Guide, only_if

PAGE = "https://www.sos.mo.gov/elections"
MINIMUM = {"cd": 8, "sd": 15, "hd": 140}  # every House district up, and the Senate's half: one can go unopposed
# Each judicial circuit's counties, as RSMo chapter 478 heads its sections; St. Louis County's
# (21) and St. Louis City's (22) aren't placed, nor the 36th, which the chapter doesn't head.
CIRCUITS: dict[int, tuple[str, ...]] = {
    6: ("PLATTE",), 7: ("CLAY",), 10: ("MARION", "MONROE", "RALLS"), 11: ("ST. CHARLES",),
    13: ("BOONE", "CALLAWAY"), 16: ("JACKSON",), 19: ("COLE",), 20: ("FRANKLIN", "GASCONADE", "OSAGE"),
    23: ("JEFFERSON",), 24: ("MADISON", "ST. FRANCOIS", "STE. GENEVIEVE", "WASHINGTON"),
    25: ("MARIES", "PHELPS", "PULASKI", "TEXAS"), 26: ("CAMDEN", "LACLEDE", "MILLER", "MONITEAU", "MORGAN"),
    31: ("GREENE",), 32: ("BOLLINGER", "CAPE GIRARDEAU", "PERRY"), 42: ("CRAWFORD", "DENT", "IRON", "REYNOLDS", "WAYNE"),
}
EASTERN = ("MONROE", "SHELBY", "KNOX", "SCOTLAND", "CLARK", "LEWIS", "MARION", "RALLS", "PIKE", "LINCOLN", "MONTGOMERY",
           "WARREN", "ST. CHARLES", "ST. LOUIS", "JEFFERSON", "STE. GENEVIEVE", "PERRY", "CAPE GIRARDEAU", "MADISON",
           "ST. FRANCOIS", "WASHINGTON", "FRANKLIN", "AUDRAIN", "GASCONADE", "OSAGE")  # RSMo 477.050, St. Louis City too
SOUTHERN = ("BARRY", "BARTON", "BUTLER", "CAMDEN", "CEDAR", "CARTER", "CHRISTIAN", "DADE", "DALLAS", "DOUGLAS", "GREENE",
            "HOWELL", "HICKORY", "JASPER", "LACLEDE", "LAWRENCE", "MCDONALD", "NEWTON", "OZARK", "OREGON", "POLK",
            "PULASKI", "PHELPS", "RIPLEY", "ST. CLAIR", "SHANNON", "STONE", "TEXAS", "TANEY", "WEBSTER", "WRIGHT", "DENT",
            "CRAWFORD", "MARIES", "REYNOLDS", "IRON", "WAYNE", "BOLLINGER", "SCOTT", "STODDARD", "DUNKLIN", "PEMISCOT",
            "NEW MADRID", "MISSISSIPPI")  # RSMo 477.060
APPEALS = {
    "EASTERN": tuple(sorted(EASTERN)),
    "SOUTHERN": tuple(sorted(SOUTHERN)),
    "WESTERN": tuple(sorted({c.name.upper() for c in counties.counties("MO")} - set(EASTERN) - set(SOUTHERN))),
}
STATEWIDE = ("Governor", "Lieutenant Governor", "Secretary of State", "State Treasurer", "State Auditor",
             "Attorney General")
DISTRICTED = {"u.s. representative": "cd", "state senator": "sd", "state representative": "hd"}
COURTS = {"circuit judge": "Circuit Judge", "associate circuit judge": "Associate Circuit Judge"}
LEFT_OUT = ("president and vice president",)
NAMED = (*(s.lower() for s in STATEWIDE), "u.s. senator", "supreme court", *LEFT_OUT)  # a candidate's line is a name
HEADINGS = frozenset({*DISTRICTED, *COURTS, *NAMED})
_TITLE = re.compile(r"<title>[^<]*\bElections\b", re.I)
_ANCHOR = re.compile(r"""<a\s[^>]*href=["']([^"']+\.pdf)["'][^>]*>(.*?)</a>""", re.I | re.S)
_DAY = re.compile(rf"General Election\b.*?({MONTH_DAY_YEAR})")
_SECTION = re.compile(r"([A-Z][A-Z ]*?) CANDIDATES")
_END = re.compile(r"EMBLEM|^CERTIFICATION|^Certificate|^State of Missouri|^COUNTY CLERK", re.I)
_DISTRICT = re.compile(r"Di\w*\s+(\d+)\s*,\s*(\S.*)")  # "District 2, …" (once "Distrcit 108, …")
_CIRCUIT = re.compile(r"Circuit\s+(\d+)(?:\s*,?\s*Division\s+(\d+))?\s*,\s*(\S.*)")
_APPEALS = re.compile(r"(Eastern|Western|Southern) District\s*,\s*(\S.*)", re.I)


def links(text: str) -> dict[str, Any]:
    """The elections page as kept: its link to each November's certified candidates, by year (not
    a link left in an HTML comment); ValueError for a page that isn't it (a challenge page)."""
    if not _TITLE.search(text):
        raise ValueError("not the Secretary of State's elections page")
    found: dict[str, str] = {}
    for href, words in _ANCHOR.findall(re.sub(r"<!--.*?-->", "", text, flags=re.S)):
        url = urljoin(PAGE, html.unescape(href))
        label = " ".join(re.sub(r"<[^>]*>", " ", words).split())
        if not re.search(r"candidates", f"{url} {label}", re.I) or not re.search(r"certif", f"{url} {label}", re.I):
            continue
        year = re.search(r"November (\d{4})", label) or re.search(r"(20\d{2})", url.rsplit("/", 1)[-1])
        if year:
            found.setdefault(year.group(1), url)
    return {"links": found}


def _heading(text: str) -> str:
    """An office's heading as one key: "For the Missouri Court of Appeals Judges" -> "court of appeals judge"."""
    words = re.sub(r"^(?:For\s+)?(?:the\s+)?(?:Missouri\s+)?", "", text, flags=re.I).lower()
    return re.sub(r"judges$", "judge", words)


def _party(section: str) -> tuple[str | None, str | None]:
    """A party heading's party: "REPUBLICAN" is R, "INDEPENDENT" no party's, "BETTER" the Better Party."""
    code, _ = party(section)
    if code:
        return code, None
    return None, "Independent" if section == "INDEPENDENT" else f"{section.title()} Party"


def _court(title: str, circuit: int, division: str | None, name: str, retention: bool) -> Office:
    """A circuit court's race: its judges' counties, or unplaced where they can't be told."""
    where = f"Circuit {circuit}" + (f" Division {division}" if division else "")
    family = title.upper()
    places = CIRCUITS.get(circuit, ())
    reach = "unplaced" if not places else "county" if len(places) == 1 else "counties"
    office_id = f"{family} {circuit} {division or ''}".strip()
    if retention:
        return Office(f"{office_id} {name.upper()}", f"Retain {where} {title} {name}", family, "judicial", reach,
                      str(circuit), counties=places, incumbent=True, retention=True)
    return Office(office_id, f"{title}, {where}", family, "judicial", reach, str(circuit), counties=places)


def _retained(kind: str, line: str) -> tuple[Office | None, str]:
    """A Supreme Court or Court of Appeals judge's retention race, and the judge's name; None for a
    line that isn't a Court of Appeals judge's."""
    if kind == "supreme court":
        return Office(f"SUPREME COURT {line.upper()}", f"Retain Supreme Court Judge {line}", "SUPREME COURT",
                      "judicial", "state", incumbent=True, retention=True), line
    found = _APPEALS.fullmatch(line)
    if not found:
        return None, ""
    district, name = found.group(1).upper(), found.group(2)
    return Office(f"COURT OF APPEALS {district} {name.upper()}", f"Retain Court of Appeals {district.title()} District "
                  f"Judge {name}", "COURT OF APPEALS", "judicial", "counties", district.title(),
                  counties=APPEALS[district], incumbent=True, retention=True), name


def candidates(lines: list[str]) -> list[Filing]:
    """Every candidate the certification places, in its order; ValueError for a file that isn't it,
    an office or a line it can't read, or a list short of its races (MINIMUM, in a year with the
    Legislature up)."""
    text = [" ".join(line.split()) for line in lines]
    day = _DAY.search(" ".join(text[:120]))
    if day is None or not any(_SECTION.fullmatch(line) for line in text):
        raise ValueError("not the certification of general election candidates")
    election = dt.datetime.strptime(day.group(1), "%B %d, %Y").date().isoformat()
    filings: list[Filing] = []
    code: str | None = None
    party_name: str | None = None
    judicial = False
    inside = False  # inside a party's or the judges' section, between its heading and the next emblem or certificate
    office: str | None = None  # the heading's key while reading its candidates
    for index, line in enumerate(text):
        section = _SECTION.fullmatch(line)
        if section:
            judicial, inside, office = section.group(1) == "JUDICIAL", True, None
            code, party_name = (None, None) if judicial else _party(section.group(1))
            continue
        if not line:
            if office in NAMED:
                office = None
            continue
        if line.isdigit() or not inside:
            continue
        if _END.search(line):
            inside, office = False, None
            continue
        key = _heading(line)
        if key in HEADINGS or key.startswith("court of appeals"):
            office = "court of appeals" if key.startswith("court of appeals") else key
            continue
        if line.startswith("For "):
            raise ValueError(f"an office it doesn't know: {line[:80]}")
        if office is None or office in LEFT_OUT:
            continue
        race, name = _race(office, line, judicial)
        if race is None:
            office = None
            continue
        party_code, label = (None, None) if race.retention else (code, party_name)
        filings.append(race.filing(day=election, name=name, party=party_code, party_name=label, order=index))
    if not any(f.group == "legislature" for f in filings):
        return filings
    return require(filings, MINIMUM)


def _race(office: str, line: str, judicial: bool) -> tuple[Office | None, str]:
    """The race of a candidate's line under ``office``'s heading, and the name; None for a line
    that isn't a candidate's (the office's list has ended)."""
    if office in DISTRICTED:
        found = _DISTRICT.fullmatch(line)
        if not found:
            return None, ""
        number, name = int(found.group(1)), found.group(2)
        reach = DISTRICTED[office]
        return (us_house("MO", number) if reach == "cd" else legislator(reach, number)), name
    if office in COURTS:
        found = _CIRCUIT.fullmatch(line)
        if not found:
            return None, ""
        circuit, division, name = int(found.group(1)), found.group(2), found.group(3)
        return _court(COURTS[office], circuit, division, name, judicial), name
    if office in ("supreme court", "court of appeals"):
        return _retained(office, line)
    if office == "u.s. senator":
        return us_senate("MO"), line
    title = next(s for s in STATEWIDE if s.lower() == office)
    return statewide(title), line


class MoList(StateList):
    state = "MO"
    source = "state_mo"
    label = "Missouri Secretary of State"
    page = PAGE
    description = ("Missouri's official list of the candidates for Congress, its statewide offices, the General "
                   "Assembly and the circuit courts, and the judges standing for retention, from its Secretary of State.")
    max_bytes = 8 << 20
    index_key = "links"
    scope_note = ("Your U.S. House district is on Missouri's 2022 map, which the courts kept for this election. County "
                  "offices, the circuit judges of St. Louis City and St. Louis County and of a circuit Pallot can't "
                  "place by its counties, and the questions (Proposition A among them) aren't shown: your local "
                  "election authority's sample ballot has them.")

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", PAGE)

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        return None if raw.startswith(b"%PDF") else links(decoded(raw))

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        url = index["links"].get(str(day.year))
        return [RequestSpec("GET", url)] if url else None

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, bytes):
            raise ValueError("not a PDF")
        return candidates(pdf_lines(raw))


GOVOTE = "https://www.sos.mo.gov/elections/goVoteMissouri"
PORTAL = "https://voteroutreach.sos.mo.gov/portal/"
GUIDE = Guide(
    name="Missouri",
    source="Missouri Secretary of State",
    url=PAGE,
    computed=True,
    registration_url=f"{GOVOTE}/register",
    mail_url=f"{GOVOTE}/howtovote",
    register="The last day to register to vote in {election} in Missouri: by 5 p.m., in person, by mail or online. "
             "There's no registering after it.",
    mail_summary="Absentee ballot request due",
    mail="If you vote absentee by mail in {election}, your request must reach your local election authority (county "
         "clerk or election board) by 5 p.m. today. Your ballot must reach it by 7 p.m. on Election Day. Who can vote "
         "absentee, and how to ask:",
    early_where="Your local election authority (county clerk or election board), and any other place it names: any "
                "voter can vote absentee there in person, no reason needed, through the day before Election Day. It "
                "sets the hours.",
    credit="Dates worked out from Missouri's election law; more from the Missouri Secretary of State",
    poll_hours="6 a.m. – 7 p.m.",
    check_url=PORTAL,
    check_hint="Missouri's Voter Outreach Portal (Secretary of State): your registration and your polling place",
    where_url=PORTAL,
    where_hint="Missouri's Voter Outreach Portal: your polling place",
    mail_label="How to ask",
    mail_eligibility=only_if("you're away on Election Day", "ill or disabled, or caring for someone who is",
                             "kept away by your religion", "working for the election authority, or as a first "
                             "responder, health care worker or in law enforcement", "in jail",
                             "in the address confidentiality program")
    + " Your ballot must reach your local election authority by 7 p.m. on Election Day.",
    mail_deadline="Your request must reach your local election authority by 5 p.m. on ",
    local_office="Your local election authority (county clerk or election board)",
)
RULE = Counts(27, 13, 14, 1).rule("MO")
