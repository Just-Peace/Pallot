"""The candidate list Hawaii, Montana, New Mexico, North Dakota, South Dakota and Washington
publish through one ASP.NET page, a CandidateList.aspx grid (a Telerik RadGrid) with an election
dropdown. A state's adapter (GridList) gives only its page, the query parameter naming the
election, and its offices; the rest is shared.

The page is asked once as an index: its dropdown lists every election by date under an id, so
the general election's id is found there, never written ahead. The list itself is a postback of
the page for that election, sent with its own hidden fields (``__VIEWSTATE``, HttpCache.form_from_page):
the grid's Export to CSV button answers the whole list as a CSV file. The HTML table shows only a
page of 100 rows, so it's read only for a grid without the export (``table``), where a postback
of its own form answers the table.

The grids share their columns under a few names (a race is "Race" or "Contest", a party "Party"
or "Party Preference"): each row is read into a GridRow, keeping only the active or qualified
candidates without a withdrawal date. Neither the CSV nor the table says the election's date,
so a filing's ``day`` is left empty and the date asked for filled in (on). The files carry
candidates' addresses, emails and phone numbers: only the parsed filings are kept.
"""

from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import io
import re
from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from ..http_cache import RequestSpec
from . import Filing, Office, Rows, StateList, decoded, filings_json, party, require

EXPORT = {"ctl00$ContentPlaceHolder1$grdCandidates$ctl00$ctl02$ctl00$ExportToCsvButton": " "}
COLUMNS = {  # each shared column's names across the grids, as headings
    "race": ("RACE", "CONTEST", "OFFICE"),
    "district_type": ("DISTRICT TYPE",),
    "district": ("DISTRICT", "JURISDICTION"),
    "name": ("NAME", "CANDIDATE NAME", "BALLOT NAME", "CANDIDATE"),
    "party": ("PARTY", "PARTY PREFERENCE", "PARTY AFFILIATION"),
    "status": ("STATUS", "CANDIDATE STATUS"),
    "order": ("BALLOT ORDER",),
    "withdrawn": ("WITHDRAWN DATE", "WITHDRAWAL DATE", "DATE WITHDRAWN"),
}
REQUIRED = ("race", "name")
KEPT = ("ACTIVE", "QUALIFIED")  # the statuses of a candidate on the ballot
_SELECT = re.compile(r"<select\b([^>]*)>(.*?)</select>", re.I | re.S)
_OPTION = re.compile(r"<option\b([^>]*)>([^<]*)", re.I)
_VALUE = re.compile(r"""value=["']([^"']*)["']""", re.I)
_DAY = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_GENERAL = re.compile(r"\bgeneral\b", re.I)
_OTHER = re.compile(r"\b(?:primary|special|runoff|recall)\b", re.I)


def elections(text: str) -> dict[str, Any]:
    """The index as kept: each general election's ISO date and its id, from the page's election
    dropdown ("GENERAL 2026 (11/03/2026) (General)" under "899"); ValueError for a page without
    one (an error page, a bot check)."""
    found: dict[str, str] = {}
    dropdown = False
    for attrs, options in _SELECT.findall(text):
        if "election" not in attrs.lower():
            continue
        dropdown = True
        for option, label in _OPTION.findall(options):
            value, day = _VALUE.search(option), _DAY.search(label)
            if value and day and _GENERAL.search(label) and not _OTHER.search(label):
                month, date, year = (int(n) for n in day.groups())
                found.setdefault(dt.date(year, month, date).isoformat(), value.group(1))
    if not dropdown:
        raise ValueError("not a candidate list page")
    return {"elections": found}


@dataclass(frozen=True)
class GridRow:
    """A candidate's row, its shared columns read (empty where the grid hasn't one)."""

    race: str  # "U.S. Representative", "State Senator"
    district_type: str  # "Congressional", "Legislative", "Countywide"
    district: str  # "Congressional District 1", "Legislative District 5", a county
    name: str
    party: str  # as the grid words it: "DEMOCRATIC", "STATES NO PARTY PREFERENCE"
    order: int  # its place among the race's candidates, 0 where the grid gives none
    cells: Mapping[str, str]  # every column, by its heading in capitals


def _heading(text: str) -> str:
    return " ".join(text.upper().split())


def table(raw: bytes | str) -> list[dict[str, str]]:
    """The grid's rows, each by its headings in capitals: the CSV export's, or the HTML table's
    after its heading row (the filter row, the pager and empty rows left out); ValueError for an
    answer with no heading row naming a race and a name."""
    text = decoded(raw) if isinstance(raw, bytes) else raw.lstrip("﻿")
    if text.lstrip().startswith("<"):
        parser = Rows(cells=("th", "td"))
        parser.feed(text)
        lines = parser.rows
    else:
        lines = list(csv.reader(io.StringIO(text)))
    for at, line in enumerate(lines):
        header = [_heading(cell) for cell in line]
        if all(any(name in header for name in COLUMNS[column]) for column in REQUIRED):
            return [dict(zip(header, (" ".join(cell.split()) for cell in row)))
                    for row in lines[at + 1:] if len(row) == len(header) and any(cell.strip() for cell in row)]
    raise ValueError("no heading row with a race and a name")


def rows(raw: bytes | str, kept: tuple[str, ...] = KEPT) -> list[GridRow]:
    """The grid's candidates on the ballot: a status in ``kept`` (where the grid has a status),
    no withdrawal date. ValueError for an answer that isn't the grid (table)."""
    found = []
    for cells in table(raw):
        shared = {column: next((cells[name] for name in names if name in cells), "") for column, names in COLUMNS.items()}
        if shared["withdrawn"] or (any(name in cells for name in COLUMNS["status"])
                                   and shared["status"].upper() not in kept):
            continue
        if not shared["race"] or not shared["name"]:
            continue
        order = shared["order"]
        found.append(GridRow(shared["race"], shared["district_type"], shared["district"], shared["name"],
                             shared["party"], int(order) if order.isdigit() else 0, cells))
    return found


class GridList(StateList):
    """A state's CandidateList.aspx grid. A subclass gives its state, source, label, description,
    ``page`` (the grid, without its election), ``election`` (the query parameter naming one) and
    office() (each row's race); and where its grid differs, ``kept``, ``parties`` (affiliation),
    ``minimum`` and ``form`` with ``table``."""

    election: ClassVar[str] = "e"  # the query parameter that names the election: "e", "eid", "elid"
    form: ClassVar[Mapping[str, str]] = EXPORT  # the postback's own fields: the CSV export's button by default
    table: ClassVar[bool] = False  # its list is the HTML table its postback answers (a grid without the export)
    kept: ClassVar[tuple[str, ...]] = KEPT
    parties: ClassVar[dict[str, str]] = {}  # its parties' names by how the grid words them
    minimum: ClassVar[dict[str, int]] = {}  # require's
    max_bytes = 16 << 20
    postback = True
    index_key = "elections"

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", self.page)

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        key = index["elections"].get(day.isoformat())
        if key is None:
            return None
        return [RequestSpec("POST", self.page, params={self.election: key}, form=dict(self.form))]

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        """The page's elections; for a grid read from its table, its filings too. None for the
        CSV export."""
        text = decoded(raw)
        if not text.lstrip().startswith("<"):
            return None
        index = elections(text)
        if cls.table:
            index["filings"] = filings_json(cls.parse(text))["filings"]
        return index

    def combine(self, lists: list[list[Filing]]) -> list[Filing]:
        """The postback's list alone: the index's own table is whichever election the page shows first."""
        return lists[-1]

    def on(self, value: Any, day: dt.date) -> list[Filing]:
        """The filings in a stored answer, dated ``day``: the postback asked for that election alone."""
        return [dataclasses.replace(f, day=day.isoformat()) if not f.day else f
                for f in self.read(value) if not f.day or f.day == day.isoformat()]

    @classmethod
    def office(cls, row: GridRow) -> Office | None:
        """The race of a row, or None for one the ballot leaves out (a local office)."""
        raise NotImplementedError

    @classmethod
    def affiliation(cls, row: GridRow) -> tuple[str | None, str | None]:
        """A row's (party code, party name), as party() reads it."""
        return party(row.party, cls.parties)

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        """Every candidate on the ballot in the grid's answer, each race in the grid's order and its
        candidates in their ballot order; ValueError for an answer that isn't the grid or a list
        short of ``minimum``."""
        if not isinstance(raw, (bytes, str)):
            raise ValueError("not a candidate list")
        races: dict[tuple[str, str, str], list[int]] = {}
        filings = []
        for row in rows(raw, cls.kept):
            race = cls.office(row)
            if race is None:
                continue
            seen = races.setdefault((row.district_type, row.district, row.race), [len(races), 0])
            seen[1] += 1
            code, name = cls.affiliation(row)
            filings.append(race.filing(day="", name=row.name, party=code, party_name=name,
                                       order=seen[0] * 1000 + (row.order or seen[1])))
        return require(filings, cls.minimum)
