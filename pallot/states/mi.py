"""Michigan: the Bureau of Elections' "Official Candidate Listing" of state and judicial offices
for a general election, one HTML report from its public candidate system.

Each office is a heading ("5th District Representative in Congress 2 Year Term (1) Position"),
then a row per candidate: Status (WITHD, DISQ), party (or INCUMBENT for a nonpartisan seat),
"Last, First" name, filing date and method. County and local candidates file with the counties,
so they aren't in it. Its circuit, district and appeals courts don't say which counties they
cover, so they're left out, with a note.
"""

from __future__ import annotations

import datetime as dt
import re
from html.parser import HTMLParser
from typing import Any

from ..http_cache import RequestSpec
from ..matching import last_first
from ..sources.fec import race_name
from . import Filing, StateList, party

URL = "https://mi-boe.entellitrak.com/etk-mi-boe-prod/page.request.do"
_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_HEADING = re.compile(
    r"^(?P<office>.+?)\s+(?:(?P<seat>Incumbent|Non-Incumbent)\s+)?(?P<term>Partial Term.*?|\d+ Year Terms?)\s*"
    r"\((?P<seats>\d+)\)\s+Positions?(?:\s+Files (?:In .+ County|With County))?$"
)
_STATEWIDE = (
    "Governor / Lt. Governor", "Secretary of State", "Attorney General", "Member of the State Board of Education",
    "Regent of the University of Michigan", "Trustee of Michigan State University", "Governor of Wayne State University",
)


class _Rows(HTMLParser):
    """Each table row's cells, as text, empty ones included."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _kind(office: str) -> tuple[str, str, str | None, str, tuple[str, ...]]:
    """(group, reach, district, shown name, counties) of an office heading."""
    if office == "U.S. Senate":
        return "federal", "state", None, race_name("MI", None), ()
    if found := re.fullmatch(r"(\d+)\w\w District Representative in Congress", office):
        return "federal", "cd", found.group(1), race_name("MI", int(found.group(1))), ()
    if found := re.fullmatch(r"(\d+)\w\w District State Senator", office):
        return "legislature", "sd", found.group(1), f"State Senator District {found.group(1)}", ()
    if found := re.fullmatch(r"(\d+)\w\w District Representative in State Legislature", office):
        return "legislature", "hd", found.group(1), f"State Representative District {found.group(1)}", ()
    if office in _STATEWIDE:
        return "state", "state", None, office, ()
    if office == "Justice of Supreme Court":
        return "judicial", "state", None, "Justice of the Supreme Court", ()
    if found := re.fullmatch(r"([A-Z][A-Z. ]+) Judge of Probate Court", office):
        county = found.group(1).strip()
        return "judicial", "county", None, f"{county.title()} County Judge of Probate", (county,)
    return "judicial" if "Judge" in office else "state", "unplaced", None, office, ()


class MiList(StateList):
    state = "MI"
    source = "state_mi"
    label = "Michigan Bureau of Elections"
    page = "https://mi-boe.entellitrak.com/etk-mi-boe-prod/page.request.do?page=page.miboePublicReport&electionType=GEN"
    description = "Michigan's official list of the candidates for state and judicial offices, from its Bureau of Elections."

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", URL, params={"page": "page.miboePublicReport", "electionType": "GEN",
                                               "electionYear": str(day.year)}, as_text=True)

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        reader = _Rows()
        reader.feed(raw if isinstance(raw, str) else "")
        texts = [[cell for cell in row if cell] for row in reader.rows]
        day = None
        for cells in texts:
            for cell in cells:
                try:
                    day = dt.datetime.strptime(cell, "%A, %B %d, %Y").date()
                    break
                except ValueError:
                    continue
            if day:
                break
        if day is None or not any(cells[:1] == ["Status"] for cells in texts):
            raise ValueError("no election date or column headings")
        filings: list[Filing] = []
        heading: re.Match[str] | None = None
        for index, (row, cells) in enumerate(zip(reader.rows, texts)):
            if len(cells) == 1 and (found := _HEADING.match(cells[0])):
                heading = found
                continue
            dated = next((i for i, cell in enumerate(row) if _DATE.match(cell)), None)
            if heading is None or dated is None or dated < 2:
                continue
            status = row[dated - 4] if dated >= 4 else ""
            if status.upper() in ("WITHD", "DISQ"):
                continue
            office = heading.group("office")
            group, reach, district, shown, counties = _kind(office)
            label = row[dated - 2]
            code, party_name = party(None if label.upper() == "INCUMBENT" else label)
            name = " / ".join(last_first(part) for part in row[dated - 1].split(" / "))
            office_id = office if not heading.group("seat") else f"{office} ({heading.group('seat')})"
            filings.append(Filing(
                day=day.isoformat(), office_id=office_id,
                office=shown if not heading.group("seat") else f"{shown}, {heading.group('seat').lower()} position",
                family=office, group=group, reach=reach, district=district, name=name, party=code,
                party_name=party_name, counties=counties, seats=int(heading.group("seats")),
                unexpired=heading.group("term").startswith("Partial"), incumbent=label.upper() == "INCUMBENT",
                order=index,
            ))
        return filings
