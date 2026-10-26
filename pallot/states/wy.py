"""Wyoming: the Secretary of State's General Election Candidates data file, a CSV beside its
candidate roster PDF on the election information page, open to scripts. One row per candidate:
the election ("2026 GENERAL ELECTION"), the office ("STATE REPRESENTATIVE 11"), the party's
code, the name in parts and as on the ballot, the dates filed and withdrawn, and the campaign's
address, phone, email and website, which are never read. The file is streamed to disk and kept
as its filings alone (``max_bytes``), so the cache and the bundle never hold the contact details.

Its State Senate races are half the districts (the odd ones in 2026). The judges standing for
retention have no party, each a race of their own: the Supreme Court's and the Chancery Court's
for the whole state, a district court's or a circuit court's for its judicial district's counties.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from typing import Any

from ..http_cache import RequestSpec
from . import (
    _ORDINALS, Filing, Office, StateList, decoded, legislator, ordinal, party, require, statewide, us_house, us_senate,
)
from .key_dates import first_tuesday_after_first_monday

URL = "https://sos.wyo.gov/Elections/Docs/{year}/{year}_WY_General_Election_Candidates.csv"
MINIMUM = {"hd": 62}  # a list with fewer State House races isn't the whole list
STATEWIDE = ("Governor", "Secretary of State", "State Auditor", "State Treasurer", "Superintendent of Public Instruction")
_COLUMNS = ("Election", "Office Sought", "Party Affiliation", "Ballot Name", "Date Withdrawn")
_ELECTION = re.compile(r"(\d{4}) GENERAL ELECTION")
_LEGISLATURE = re.compile(r"STATE (SENATOR|REPRESENTATIVE) (\d+)")
_JUDGE = re.compile(r"(SC|CHC|DC|CC)-\d+ - (.+)")
_DISTRICT = re.compile(r"\b(\w+) JUDICIAL DISTRICT\b")
_CODES = {"LBR": "LIBERTARIAN"}
_NAMES = {"CT": "Constitution Party", "IND": "Independent"}
_JUDICIAL = {  # W.S. 5-3-101: the counties of each judicial district, whose circuit courts are the same (5-9-101)
    1: ("LARAMIE",),
    2: ("ALBANY", "CARBON"),
    3: ("LINCOLN", "SWEETWATER", "UINTA"),
    4: ("JOHNSON", "SHERIDAN"),
    5: ("BIG HORN", "HOT SPRINGS", "PARK", "WASHAKIE"),
    6: ("CAMPBELL", "CROOK", "WESTON"),
    7: ("NATRONA",),
    8: ("CONVERSE", "GOSHEN", "NIOBRARA", "PLATTE"),
    9: ("FREMONT", "SUBLETTE", "TETON"),
}


def _race(office: str, name: str) -> Office:
    """The race an office names; ValueError for one the list never had."""
    upper = " ".join(office.upper().split())
    if upper == "UNITED STATES SENATOR":
        return us_senate("WY", upper)
    if upper == "UNITED STATES REPRESENTATIVE":
        return us_house("WY", 0, upper)
    if found := _LEGISLATURE.fullmatch(upper):
        return legislator("sd" if found.group(1) == "SENATOR" else "hd", int(found.group(2)), upper)
    for title in STATEWIDE:
        if upper == title.upper():
            return statewide(title, upper)
    if found := _JUDGE.fullmatch(upper):
        court, judge = found.group(1), {"SC": "SUPREME COURT", "CHC": "CHANCERY COURT", "DC": "DISTRICT COURT",
                                       "CC": "CIRCUIT COURT"}[found.group(1)]
        office_id = f"{upper} {name.upper()}"
        if court in ("SC", "CHC"):
            shown = "Supreme Court Justice" if court == "SC" else "Chancery Court Judge"
            return Office(office_id, f"Retain {shown} {name}", judge, "judicial", "state", incumbent=True,
                          retention=True)
        district = _DISTRICT.search(found.group(2))
        number = _ORDINALS.get(district.group(1)) if district else None
        if number not in _JUDICIAL:
            raise ValueError(f"no judicial district in {office}")
        shown = "District Court Judge" if court == "DC" else "Circuit Court Judge"
        return Office(office_id, f"Retain {shown} {name}, {ordinal(number)} Judicial District", judge, "judicial",
                      "counties", str(number), _JUDICIAL[number], incumbent=True, retention=True)
    raise ValueError(f"an office it doesn't know: {office}")


def parse_text(text: str) -> list[Filing]:
    """Every candidate on the ballot, from the data file's text, withdrawn ones left out;
    ValueError for a file that isn't the list (its columns, an office or election it doesn't
    know, a row without a ballot name) or isn't all of it (MINIMUM)."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or any(column not in reader.fieldnames for column in _COLUMNS):
        raise ValueError("not the list of general election candidates")
    filings: list[Filing] = []
    for index, row in enumerate(reader):
        election = _ELECTION.fullmatch(" ".join((row["Election"] or "").upper().split()))
        name = " ".join((row["Ballot Name"] or "").split())
        if election is None or not name:
            raise ValueError(f"a row it can't read: {row['Election']!r}, {row['Office Sought']!r}")
        if (row["Date Withdrawn"] or "").strip():
            continue
        race = _race(row["Office Sought"] or "", name)
        label = " ".join((row["Party Affiliation"] or "").upper().split())
        code, party_name = party(_CODES.get(label, label), _NAMES)
        filings.append(race.filing(
            day=first_tuesday_after_first_monday(int(election.group(1)), 11).isoformat(), name=name, party=code,
            party_name=party_name, order=index,
        ))
    return require(filings, MINIMUM)


class WyList(StateList):
    state = "WY"
    source = "state_wy"
    label = "Wyoming Secretary of State"
    page = "https://sos.wyo.gov/Elections/2026ElectionInformation.aspx"
    description = ("Wyoming's official list of the candidates for Congress, its statewide offices, the Legislature "
                   "and the judges standing for retention, from its Secretary of State.")
    max_bytes = 8 << 20

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", URL.format(year=day.year))

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if isinstance(raw, bytes):
            raw = decoded(raw)
        if not isinstance(raw, str):
            raise ValueError("not a CSV")
        return parse_text(raw)
