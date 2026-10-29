"""Nevada: the Secretary of State's Statewide Certified List of Candidates for a general election,
a PDF with one table for every office in the state, saved by hand (manual/state_nv), since
nvsos.gov answers scripts with a bot check and Pallot never asks it.

Its columns are Name on Ballot ("Last, First"), Candidate Name, Party or Nonpartisan Office,
Office Sought, Filing Office, Filed Date and Note, named once on the first page and laid out
anew on each page, so a row is its cells in the headings' order, read apart by the runs of
spaces between them. A row whose Note says the candidate withdrew, died or was successfully
challenged is left out.

Congress, the Legislature, statewide offices, the Supreme Court and the district courts come
first, then each county's and city's offices, by the clerk they filed with. A district court
reaches the counties of its judicial district (NRS 3.010); a county's row office (sheriff,
assessor) the whole county; a city's the whole city, but a ward only part of it; anything with
a district, seat or area, a township or a special district only part of the county, so those are
unconfirmed.

Nevada's key dates, for its general election (NRS 293.12755: the first Tuesday after the first
Monday of November in an even year): registration by mail or in person at the county clerk's closes
the fourth Tuesday before, online on Election Day itself (NRS 293.560), and in person at a polling
place it goes on through Election Day (NRS 293.5772 to 293.5887); every active voter is mailed a
ballot, and so is anyone who registers or updates their registration by 14 days before (NRS
293.269911); early voting runs from the third Saturday before through the Friday before (NRS
293.3568); a mailed ballot must be postmarked by Election Day and reach the clerk by 5 p.m. on the
fourth day after (NRS 293.269921); polls are open 7 a.m. to 7 p.m. (NRS 293.273).
"""

from __future__ import annotations

import dataclasses
import functools
import re
from typing import Any

from . import (
    _ORDINALS, SUFFIXES, WITHDRAWN, Filing, ManualList, Office, legislator, party, pdf_lines, us_house,
)
from .dates import Counts, Guide, first_tuesday_after_first_monday

COLUMNS = {
    "name on ballot": "name", "party or nonpartisan office": "party", "office sought": "office",
    "filing office": "filed", "filed date": "date", "note": "note",
}
JUDICIAL_DISTRICTS = {
    1: ("CARSON CITY", "STOREY"), 2: ("WASHOE",), 3: ("LYON",), 4: ("ELKO",), 5: ("ESMERALDA", "NYE"),
    6: ("HUMBOLDT",), 7: ("EUREKA", "LINCOLN", "WHITE PINE"), 8: ("CLARK",), 9: ("DOUGLAS",), 10: ("CHURCHILL",),
    11: ("LANDER", "MINERAL", "PERSHING"),
}
CITY_COUNTIES = {
    "BOULDER CITY": "CLARK", "HENDERSON": "CLARK", "LAS VEGAS": "CLARK", "MESQUITE": "CLARK", "NORTH LAS VEGAS": "CLARK",
    "RENO": "WASHOE", "SPARKS": "WASHOE", "FALLON": "CHURCHILL", "CARLIN": "ELKO", "ELKO": "ELKO", "WELLS": "ELKO",
    "WEST WENDOVER": "ELKO", "WINNEMUCCA": "HUMBOLDT", "CALIENTE": "LINCOLN", "FERNLEY": "LYON", "YERINGTON": "LYON",
    "LOVELOCK": "PERSHING", "ELY": "WHITE PINE",
}
STATEWIDE = ("Governor", "Lieutenant Governor", "Secretary of State", "State Treasurer", "State Controller",
             "Attorney General")
_TITLE = re.compile(r"\b(\d{4}) General Election\b")
_DATE = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")
_GONE = re.compile(rf"challeng|{WITHDRAWN.pattern}", re.I)
_PARTIES = {"LIBERTARIAN PARTY OF NEVADA": "L", "NO POLITICAL PARTY": None, "NONPARTISAN": None}
_SUFFIXES = SUFFIXES | {"ESQ"}
_WHOLE_COUNTY = re.compile(
    r"(?:COUNTY )?(?:ASSESSOR|CLERK|TREASURER|RECORDER|AUDITOR|SHERIFF|DISTRICT ATTORNEY|PUBLIC ADMINISTRATOR|"
    r"COMMISSIONER|COUNTY COMMISSIONER|SCHOOL BOARD TRUSTEE)(?: ?[-/] ?(?:RECORDER|TREASURER|AUDITOR))?"
)
_SEATS = re.compile(r"\s*\(Vote (\d+)\)", re.I)


def _tidy(office: str) -> str:
    """ "Justice Of The Supreme Court, Seat B" -> "Justice of the Supreme Court, Seat B"."""
    return re.sub(r"(?<=\S) (Of|The|And|In)\b", lambda found: f" {found.group(1).lower()}", " ".join(office.split()))


def ballot_name(text: str) -> str:
    """The list's "Last, First" as the ballot reads it, nicknames kept: "Hafen, II, Gregory T." ->
    "Gregory T. Hafen II", 'Aguilar, Francisco "Cisco"' -> 'Francisco "Cisco" Aguilar'. A name
    without a comma is as the list writes it."""
    parts = [" ".join(part.split()) for part in text.split(",")]
    parts = [part for part in parts if part]
    if len(parts) < 2:
        return " ".join(text.split())
    last, rest = parts[0], parts[1:]
    suffixes = [part for part in rest if part.strip(".").upper() in _SUFFIXES]
    return " ".join([*(part for part in rest if part not in suffixes), last, *suffixes])


def _place(filed: str) -> tuple[str | None, str | None]:
    """(county, city) of a filing office, in capitals: "Clark County" -> ("CLARK", None),
    "City Of Las Vegas" -> (None, "LAS VEGAS"), "Carson City" (a city and county) -> ("CARSON CITY", None)."""
    text = " ".join(filed.upper().split())
    if found := re.fullmatch(r"(.+) COUNTY", text):
        return found.group(1), None
    if found := re.fullmatch(r"CITY OF (.+)", text):
        return None, found.group(1)
    if text == "CARSON CITY":
        return text, None
    if text.endswith(" CITY"):
        return None, text
    return None, None


def _kind(office: str, filed: str, near: str | None = None) -> Office:
    """The race of an Office Sought filed with ``filed``, with its seats and whether it's an
    unexpired term. A city's race is in its county (CITY_COUNTIES), or else ``near``, the county
    the list was on."""
    shown = _tidy(_SEATS.sub("", office))
    seats = int(found.group(1)) if (found := _SEATS.search(office)) else 1
    upper = shown.upper()
    terms = {"seats": seats, "unexpired": "UNEXPIRED" in upper}
    race = functools.partial(dataclasses.replace, Office(upper, shown, upper, "local", "unplaced", **terms))
    if found := re.fullmatch(r"REPRESENTATIVE IN CONGRESS, DISTRICT (\d+)", upper):
        return dataclasses.replace(us_house("NV", int(found.group(1)), upper), **terms)
    for pattern, reach, family, label in ((r"STATE SENATE, DISTRICT (\d+)", "sd", "STATE SENATE", "State Senate"),
                                          (r"STATE ASSEMBLY, DISTRICT (\d+)", "hd", "STATE ASSEMBLY", "State Assembly")):
        if found := re.fullmatch(pattern, upper):
            number = int(found.group(1))
            return dataclasses.replace(legislator(reach, number, upper, f"{label} District {number}"), family=family,
                                       **terms)
    if upper in (office.upper() for office in STATEWIDE):
        return race(group="state", reach="state")
    if upper.startswith("JUSTICE OF THE SUPREME COURT"):
        return race(family="JUSTICE OF THE SUPREME COURT", group="judicial", reach="state")
    if found := re.match(r"DISTRICT COURT JUDGE, (\w+) JUDICIAL DISTRICT\b", upper):
        number = _ORDINALS.get(found.group(1))
        if number not in JUDICIAL_DISTRICTS:
            raise ValueError(f"no judicial district {found.group(1).title()}")
        return race(family="DISTRICT COURT JUDGE", group="judicial", reach="counties", district=str(number),
                    counties=JUDICIAL_DISTRICTS[number])
    county, city = _place(filed)
    local = f"{upper} ({' '.join(filed.upper().split())})"
    if upper.startswith("BOARD OF REGENT"):
        return race(office_id=local, office=shown.replace("Board of Regent,", "Board of Regents,"),
                    family="Board of Regents", group="state", reach="part_county" if county else "unplaced",
                    counties=(county,) if county else ())
    judicial = upper.startswith(("JUSTICE OF THE PEACE", "MUNICIPAL COURT", "JUSTICE AND MUNICIPAL COURT")) \
        or "MUNICIPAL COURT JUDGE" in upper
    group = "judicial" if judicial else "local"
    if city:
        home = CITY_COUNTIES.get(city, near)
        return race(office_id=local, group=group, city=city, counties=(home,) if home else (),
                    reach="part_city" if re.search(r"\bWARD\b", upper) else "city")
    if county:
        whole = bool(_WHOLE_COUNTY.fullmatch(upper))
        return race(office_id=local, group="county" if whole and "SCHOOL" not in upper else group,
                    counties=(county,), reach="county" if whole else "part_county")
    return race(group=group)


def _columns(line: str) -> list[str] | None:
    """The table's columns, in order, from its heading line; None for any other line."""
    names = [" ".join(cell.lower().split()) for cell in re.split(r"\s{2,}", line.strip())]
    if not {"name on ballot", "office sought", "filed date"} <= set(names):
        return None
    return [COLUMNS.get(name, name) for name in names]


def parse_lines(lines: list[str]) -> list[Filing]:
    """Every candidate on the list, from pdf_lines' layout; ValueError for a file that isn't the
    list (no title or column headings, a row it can't split into its columns)."""
    year = next((int(found.group(1)) for line in lines if (found := _TITLE.search(line))), None)
    columns = next((found for line in lines if (found := _columns(line))), None)
    if year is None:
        raise ValueError("no general election's title")
    if columns is None or not {"name", "party", "office", "filed", "date"} <= set(columns):
        raise ValueError("no column headings")
    day = first_tuesday_after_first_monday(year, 11).isoformat()
    at = {name: i for i, name in enumerate(columns)}
    filings: list[Filing] = []
    near = None
    for index, line in enumerate(lines):
        cells = re.split(r"\s{3,}", line.strip())
        if len(cells) < 4 or _columns(line) or not _DATE.search(line):
            continue
        if not at["date"] < len(cells) <= len(columns) or not _DATE.fullmatch(cells[at["date"]]):
            raise ValueError(f"a row it can't split into the list's columns: {' '.join(line.split())[:80]}")
        row = dict(zip(columns, cells))
        if _GONE.search(row.get("note", "")):
            continue
        near = _place(row["filed"])[0] or near
        race = _kind(row["office"], row["filed"], near)
        label = " ".join(row["party"].split())
        code, party_name = (_PARTIES[label.upper()], None) if label.upper() in _PARTIES else party(label)
        filings.append(race.filing(day=day, name=ballot_name(row["name"]), party=code, party_name=party_name,
                                   order=index))
    if not filings:
        raise ValueError("no candidates")
    return filings


class NvList(ManualList):
    state = "NV"
    source = "state_nv"
    label = "Nevada Secretary of State"
    page = "https://www.nvsos.gov/sos/elections"
    description = ("Nevada's official list of the candidates on its ballot, from Congress to its counties and cities, "
                   "from its Secretary of State, imported by hand.")
    folder = "manual/state_nv"
    binary = True
    challenge = ("Request unsuccessful", "Incapsula incident ID")

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, bytes):
            raise ValueError("not a PDF")
        return parse_lines(pdf_lines(raw))


GUIDE = Guide(
    name="Nevada",
    source="Nevada Secretary of State",
    url="https://www.nvsos.gov/sos/elections",
    computed=True,
    registration_url="https://registertovote.nv.gov/",
    mail_url="https://www.nvsos.gov/sos/elections",
    register="The last day to register by mail or in person at your county clerk's office for {election} in Nevada. "
             "After it, you can still register online through Election Day, or in person at a polling place during "
             "early voting or on Election Day.",
    mail_summary="Last day to register and still be mailed a ballot",
    mail="Every active voter in Nevada is mailed a ballot for {election}. Register or update your registration by "
         "today to still be mailed one. Mailed back, it must be postmarked by Election Day and reach your county "
         "clerk by 5 p.m. on the fourth day after; or drop it off at any polling place or drop box by 7 p.m. on "
         "Election Day. More:",
    early_where="Your county clerk lists the places and hours.",
    credit="Dates worked out from Nevada's election law; more from the Nevada Secretary of State",
    poll_hours="7 a.m. – 7 p.m.",
    check_url="https://www.nvsos.gov/votersearch/",
    check_hint="Nevada Secretary of State's voter search: your registration and your polling place",
    where_url="https://www.nvsos.gov/sos/elections",
    where_hint="Nevada Secretary of State's elections page; your county clerk publishes where and when you can vote",
    mail_label="More on voting by mail",
    mail_eligibility="Every active voter is mailed a ballot. Mail it back postmarked by Election Day (it must arrive by "
                     "5 p.m. on the fourth day after), or drop it off at any polling place or drop box by 7 p.m. on "
                     "Election Day.",
    mail_deadline="To still be mailed one, register or update your registration by ",
    local_office="Your county clerk",
    late_registration="After that, register online or at a polling place through Election Day",
)
RULE = Counts(28, 14, 17, 4).rule("NV")  # mail: register by then to still be mailed a ballot
