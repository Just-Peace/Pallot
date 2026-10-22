"""Each state's official list of the candidates on its general-election ballot, from its
Secretary of State or elections board: one adapter per state (adapters.py), reading the list
into Filings, one per candidate in a race, with withdrawn and disqualified candidates left out.

An adapter asks for its whole list in one request through HttpCache, under its own source
(``state_<st>``), so each state has its own throttle, pause and Settings row. A list the
adapter can't read is refused as a failed request (HttpCache.check_answers), so the last good
copy keeps serving. The bundled copy (bundles/states.py) is the parsed filings, not the raw
file, which carries candidates' addresses and phone numbers: read() takes either. A list that's
a big file (California's PDF, mostly images) is streamed to disk and kept as its filings alone
(``max_bytes``), so the cache and the bundle hold the same.
A state whose site blocks scripts (ManualList) is never asked: its list is saved by hand and imported.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import io
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, ClassVar

from pypdf import PdfReader

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec

# Where a race is on the ballot, which placement (place.py) checks against the voter's address.
REACHES = (
    "cd",  # a U.S. House district
    "sd", "hd",  # a State Senate or State House district
    "state",  # the whole state
    "counties",  # one district of an office split among whole counties (a judicial district): ``counties``
    "county",  # the whole county in ``counties``
    "part_county",  # part of the county in ``counties`` (a commissioner's district): not placed
    "city",  # the whole of ``city``
    "part_city",  # part of ``city`` (a ward): not placed
    "unplaced",  # somewhere the list doesn't say (Michigan's circuit courts): left out
)


@dataclass(frozen=True)
class Filing:
    day: str  # the election's ISO date
    office_id: str  # the race in the list: the state's own name for it
    office: str  # as shown: "U.S. Representative District 9"
    family: str  # the office without its district or seat ("NC SUPERIOR COURT JUDGE")
    group: str  # models.GROUPS
    reach: str  # REACHES
    district: str | None  # the state's own spelling: "9", "12A", "Third Suffolk"
    name: str  # as printed on the ballot
    party: str | None = None  # D, R, L, G, I
    party_name: str | None = None
    counties: tuple[str, ...] = ()  # in capitals, as the list names them
    city: str | None = None  # in capitals
    seats: int = 1
    unexpired: bool = False
    write_in: bool = False
    incumbent: bool = False
    order: int = 0  # where the race and the candidate come in the list (ballot order where it gives one)


def filings_json(filings: list[Filing]) -> dict[str, Any]:
    return {"filings": [dataclasses.asdict(f) for f in filings]}


def from_json(value: dict[str, Any]) -> list[Filing]:
    return [Filing(**{**row, "counties": tuple(row.get("counties") or ())}) for row in value.get("filings") or []]


_PARTIES = {
    "DEM": "D", "DEMOCRAT": "D", "DEMOCRATIC": "D", "DEMOCRATIC PARTY": "D",
    "REP": "R", "REPUBLICAN": "R", "REPUBLICAN PARTY": "R",
    "LIB": "L", "LBT": "L", "LIBERTARIAN": "L", "LIBERTARIAN PARTY": "L",
    "GRE": "G", "GRN": "G", "GREEN": "G", "GREEN PARTY": "G",
}


def party(text: str | None, names: dict[str, str] | None = None) -> tuple[str | None, str | None]:
    """(code, name) for a list's party: D/R/L/G with no name, or no code and the party's own
    name ("Working Class Party", from ``names`` for a code like "CST"); (None, None) for none."""
    raw = " ".join((text or "").split())
    code = _PARTIES.get(raw.upper())
    if code:
        return code, None
    if not raw or raw.upper() in ("UNA", "NON", "NPA", "NONPARTISAN", "NO PARTY AFFILIATION", "UNAFFILIATED"):
        return None, None
    return None, (names or {}).get(raw.upper(), raw)


class Rows(HTMLParser):
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


def pdf_lines(raw: bytes, *, layout: bool = True) -> list[str]:
    """A PDF list's text, line by line, without trailing spaces: with ``layout``, each line's
    columns kept apart by runs of spaces as the page lays them out; without, in the order the
    file holds its text, which some tools' pages (California's courts) keep whole where layout
    splits words. One encrypted for printing only (no password) is opened with the empty one.
    ValueError for a file that isn't a PDF it can read."""
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            reader.decrypt("")
        pages = [page.extract_text(extraction_mode="layout") if layout else page.extract_text() for page in reader.pages]
    except Exception as exc:
        raise ValueError(f"not a PDF it can read ({type(exc).__name__})") from exc
    return [line.rstrip() for text in pages for line in text.splitlines()]


def ordinal(number: int) -> str:
    """3 -> "3rd", 11 -> "11th"."""
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


_ORDINALS = {
    "FIRST": 1, "SECOND": 2, "THIRD": 3, "FOURTH": 4, "FIFTH": 5, "SIXTH": 6, "SEVENTH": 7, "EIGHTH": 8, "NINTH": 9,
    "TENTH": 10, "ELEVENTH": 11, "TWELFTH": 12, "THIRTEENTH": 13, "FOURTEENTH": 14, "FIFTEENTH": 15,
    "SIXTEENTH": 16, "SEVENTEENTH": 17, "EIGHTEENTH": 18, "NINETEENTH": 19, "TWENTIETH": 20,
}


def district_key(text: str | int | None) -> str:
    """One spelling for a district however it's written, so a list's and the Census's agree:
    "025", "District 25" and 25 are "25"; "3rd Suffolk" and "Third Suffolk" are "3 SUFFOLK"."""
    words = re.sub(r"[^A-Z0-9 ]", " ", str(text if text is not None else "").upper()).split()
    out = []
    for word in words:
        if word in ("DISTRICT", "STATE", "SENATE", "HOUSE", "SENATORIAL", "REPRESENTATIVE"):
            continue
        word = str(_ORDINALS.get(word, word))
        word = re.sub(r"^(\d+)(?:ST|ND|RD|TH)$", r"\1", word)
        out.append((word.lstrip("0") or "0") if word.isdigit() else re.sub(r"^0+(?=\d)", "", word))
    return " ".join(out)


class StateList:
    """One state's list. A subclass names its state, source, label and page, makes its request
    (spec) and reads the answer (parse); everything else is shared."""

    state: ClassVar[str]  # "NC"
    source: ClassVar[str]  # "state_nc"
    label: ClassVar[str]  # "NC State Board of Elections"
    page: ClassVar[str]  # where voters can see the list themselves
    description: ClassVar[str]  # its Settings line
    max_bytes: ClassVar[int] = 0  # a list that's a file this big at most (a PDF): kept as its filings alone

    def __init__(self, cache: HttpCache, ttl: Ttls):
        self.cache = cache
        self.ttl = ttl
        self._read: tuple[Any, list[Filing]] | None = None
        cache.pause_on(self.source, ttl.state_list_backoff)
        cache.check_answers(self.source, self.check)
        if self.max_bytes:
            cache.read_files(self.source, cache.path.parent, self.read_file, max_bytes=self.max_bytes)

    @classmethod
    def read_file(cls, path: Path) -> dict[str, Any]:
        """A list fetched as a file (``max_bytes``) as it's stored: its filings, never the file."""
        return filings_json(cls.parse(path.read_bytes()))

    def spec(self, day: dt.date) -> RequestSpec:
        raise NotImplementedError

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        """Every candidate in the raw answer, for every general election it lists; ValueError
        for an answer that isn't the list (a maintenance page, renamed columns)."""
        raise NotImplementedError

    @classmethod
    def shape(cls, raw: Any) -> dict[str, Any]:
        """The answer as bundled: its filings, without the raw file."""
        return raw if isinstance(raw, dict) else filings_json(cls.parse(raw))

    def read(self, value: Any) -> list[Filing]:
        """The filings in a stored answer, raw or bundled, parsed once per copy HttpCache keeps."""
        if self._read is not None and self._read[0] is value:
            return self._read[1]
        filings = from_json(value) if isinstance(value, dict) else self.parse(value)
        self._read = (value, filings)
        return filings

    def check(self, value: Any) -> str | None:
        try:
            filings = self.read(value)
        except ValueError as exc:
            return f"can't read its list of candidates: {exc}"
        return None if filings else "its list has no candidates"

    async def filings(self, day: dt.date) -> list[Filing] | None:
        """The candidates on the ballot of the general election on ``day``, or None while the
        list doesn't have that election yet. UpstreamError when it can't be had."""
        got = await self.cache.get_json(self.source, self.spec(day), ttl=self.ttl.state_list)
        found = [f for f in self.read(got.value) if f.day == day.isoformat()]
        return found or None

    def missing(self, when: str) -> str:
        """The ballot's note when the list has no candidates for the election on ``when``."""
        return f"The {self.label} hasn't published its list of candidates for {when} yet"


class ManualList(StateList):
    """A list Pallot never fetches, because the state's site blocks scripts: the maintainer saves
    it in their own browser and imports the file (pallot-bundle import-list), which bundles its
    parsed filings under spec(day). A lookup reads only that imported copy."""

    folder: ClassVar[str]  # where the saved file and the steps to refresh it are: "manual/state_az"
    binary: ClassVar[bool] = False  # parse() takes the saved file's bytes (a PDF), not its text
    challenge: ClassVar[tuple[str, ...]] = ()  # what the site's bot check page says, to refuse it by name

    @classmethod
    def spec(cls, day: dt.date) -> RequestSpec:  # type: ignore[override]
        """The imported copy's key: not an address, so nothing can ever ask the state's site for it."""
        return RequestSpec("GET", f"manual:{cls.source}", params={"day": day.isoformat()})

    async def filings(self, day: dt.date) -> list[Filing] | None:
        kept = self.cache.peek(self.spec(day))
        found = [f for f in self.read(kept.value) if f.day == day.isoformat()] if kept else []
        return found or None

    def missing(self, when: str) -> str:
        return f"Pallot doesn't have the {self.label}'s list of candidates for {when} yet"
