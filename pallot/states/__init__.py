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
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, ClassVar, Mapping
from xml.etree import ElementTree

from pypdf import PdfReader

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec, hidden_fields
from ..models import Race
from ..sources.fec import race_name

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
    retention: bool = False  # a yes-or-no question on keeping a judge, its one candidate, in office
    order: int = 0  # where the race and the candidate come in the list (ballot order where it gives one)


@dataclass(frozen=True)
class Office:
    """A race as a list names it: Filing's fields but its candidates'. An adapter reads each
    office into one (us_senate, us_house, legislator, statewide, or its own), then each candidate
    into a Filing (filing)."""

    office_id: str
    office: str
    family: str
    group: str
    reach: str
    district: str | None = None
    counties: tuple[str, ...] = ()
    city: str | None = None
    seats: int = 1
    unexpired: bool = False
    incumbent: bool = False  # a retention question's judge
    retention: bool = False

    def filing(self, **candidate: Any) -> Filing:
        """A candidate in this race: ``candidate`` gives Filing's other fields (day, name, party…)."""
        return Filing(**{**dataclasses.asdict(self), **candidate})


def us_senate(state: str, office_id: str = "US SENATE") -> Office:
    return Office(office_id, race_name(state, None), "US SENATE", "federal", "state")


def us_house(state: str, number: int, office_id: str | None = None) -> Office:
    """A U.S. House district's race (0 for an at-large seat)."""
    return Office(office_id or f"US HOUSE {number}", race_name(state, number), "US HOUSE", "federal", "cd", str(number))


def legislator(reach: str, district: int | str, office_id: str | None = None, office: str | None = None) -> Office:
    """A State Senate (``reach`` "sd") or State House ("hd") district's race: "State Senator District 9"."""
    family = "STATE SENATE" if reach == "sd" else "STATE HOUSE"
    title = "State Senator" if reach == "sd" else "State Representative"
    return Office(office_id or f"{family} {district}", office or f"{title} District {district}", family,
                  "legislature", reach, str(district))


def statewide(office: str, office_id: str | None = None) -> Office:
    """A statewide office's race ("Attorney General"), its id and family the office in capitals."""
    key = office_id or office.upper()
    return Office(key, office, key, "state", "state")


def counties_of(districts: Mapping[int, tuple[str, ...]], numbers: tuple[int, ...]) -> tuple[str, ...]:
    """The counties of judicial ``districts`` (a circuit's counties, by its number) ``numbers``
    cover together, sorted: an appeals court's, made of circuits."""
    return tuple(sorted(county for number in numbers for county in districts.get(number, ())))


REACH_NAMES = {"cd": "U.S. House", "sd": "State Senate", "hd": "State House"}


def require(filings: list[Filing], minimum: Mapping[str, int]) -> list[Filing]:
    """``filings``, or ValueError when they have fewer districts of a reach than ``minimum``
    gives ({"cd": 52}): a list short of them isn't the whole list. A "cd" counts U.S. House
    races only, not a board elected by congressional district."""
    for reach, least in minimum.items():
        found = len({f.district for f in filings if f.reach == reach and (reach != "cd" or f.group == "federal")})
        if found < least:
            raise ValueError(f"{found} {REACH_NAMES[reach]} races, not {least}")
    return filings


SUFFIXES = {"JR", "SR", "II", "III", "IV", "V"}  # a name's last word that isn't the surname
MONTH_DAY_YEAR = (r"(?:January|February|March|April|May|June|July|August|September|October|November|December) "
                  r"\d{1,2}, \d{4}")  # "November 3, 2026", as a regex
WITHDRAWN = re.compile(r"withdr|deceas|disqualif|remov|ineligib", re.I)  # a list's note on a candidate who's off it


def decoded(raw: bytes) -> str:
    """A text file's text: UTF-8 (a byte-order mark dropped), or Windows-1252 where it isn't."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", "replace")


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


PARTY_ORDER = {"D": 0, "R": 1, "L": 2, "G": 3}


def party_rank(code: str | None, name: str | None) -> int:
    """Where a candidate's party comes in a race the list doesn't order: D, R, L, G, another
    party, then no party."""
    return PARTY_ORDER.get(code or "", 4 if name else 5)


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
    """Each table row's cells (``cells``: td, or th too), as text, empty ones included; with
    ``breaks``, a br or p inside a cell is a space."""

    def __init__(self, *, cells: tuple[str, ...] = ("td",), breaks: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._cells = cells
        self._breaks = breaks
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag == "tr":
            self._row = []
        elif tag in self._cells and self._row is not None:
            self._cell = []
        elif tag in ("br", "p") and self._breaks and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._cells and self._row is not None and self._cell is not None:
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


_XLSX = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def sheet_rows(raw: bytes) -> tuple[str, list[list[str]]]:
    """A spreadsheet's (.xlsx) first sheet: its name and each row's cells as text, an empty
    cell's as "", with runs of spaces made one. ValueError for a file that isn't one it can read."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as book:
            names = book.namelist()
            shared = [
                "".join(t.text or "" for t in item.iter(f"{_XLSX}t"))
                for item in ElementTree.fromstring(book.read("xl/sharedStrings.xml")).iter(f"{_XLSX}si")
            ] if "xl/sharedStrings.xml" in names else []
            sheet = ElementTree.fromstring(book.read("xl/workbook.xml")).find(f"{_XLSX}sheets/{_XLSX}sheet")
            first = min((n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)),
                        key=lambda n: int(re.sub(r"\D", "", n)))
            cells = ElementTree.fromstring(book.read(first))
    except (zipfile.BadZipFile, KeyError, ValueError, ElementTree.ParseError) as exc:
        raise ValueError(f"not a spreadsheet it can read ({type(exc).__name__})") from exc
    rows = []
    for row in cells.iter(f"{_XLSX}row"):
        out: list[str] = []
        for cell in row.iter(f"{_XLSX}c"):
            column = re.match(r"[A-Z]+", cell.get("r") or "")
            if column:
                at = 0
                for letter in column.group():
                    at = at * 26 + ord(letter) - 64
                out += [""] * (at - 1 - len(out))
            kind, value = cell.get("t"), cell.findtext(f"{_XLSX}v")
            if kind == "s" and value is not None:
                text = shared[int(value)]
            elif kind == "inlineStr":
                text = "".join(t.text or "" for t in cell.iter(f"{_XLSX}t"))
            else:
                text = value or ""
            out.append(" ".join(text.split()))
        rows.append(out)
    return (sheet.get("name", "") if sheet is not None else ""), rows


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
    scope_note: ClassVar[str] = ""  # the ballot's note on what a list covering only part of the ballot leaves out
    cafile: ClassVar[Path | None] = None  # a certificate its server leaves out of its chain (HttpCache.trust)
    postback: ClassVar[bool] = False  # its requests with a form are ASP.NET postbacks (HttpCache.form_from_page)
    # A list asked in two steps: spec(day) answers an index (a page of links, a list of elections)
    # kept as a dict under this key, and follow() gives the requests for the list itself.
    index_key: ClassVar[str | None] = None

    def __init__(self, cache: HttpCache, ttl: Ttls):
        self.cache = cache
        self.ttl = ttl
        self._read: tuple[Any, list[Filing]] | None = None
        if self.cafile:
            cache.trust(self.source, self.cafile)
        if self.postback:
            cache.form_from_page(self.source, hidden_fields)
        cache.pause_on(self.source, ttl.state_list_backoff)
        cache.check_answers(self.source, self.check)
        if self.max_bytes:
            cache.read_files(self.source, cache.path.parent, self.read_file, max_bytes=self.max_bytes)

    @classmethod
    def read_file(cls, path: Path) -> dict[str, Any]:
        """A list fetched as a file (``max_bytes``) as it's stored: its filings, never the file;
        or its index (read_index)."""
        raw = path.read_bytes()
        index = cls.read_index(raw) if cls.index_key else None
        return index if index is not None else filings_json(cls.parse(raw))

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        """A two-step list's index as kept, or None when ``raw`` is the list itself."""
        raise NotImplementedError

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        """The requests for a two-step list's election on ``day``, from its index; None while the
        index has none."""
        raise NotImplementedError

    def combine(self, lists: list[list[Filing]]) -> list[Filing]:
        """One list from each answer's filings (the index's first): all of them, by default."""
        return [f for found in lists for f in found]

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
        index = self.index_key and isinstance(value, dict) and self.index_key in value
        if index and not isinstance(value[self.index_key], (dict, list)):
            return "its index isn't one"
        try:
            filings = self.read(value)
        except (TypeError, ValueError) as exc:
            return f"can't read its list of candidates: {exc}"
        return None if filings or index else "its list has no candidates"

    def on(self, value: Any, day: dt.date) -> list[Filing]:
        """The filings in a stored answer for the election on ``day``."""
        return [f for f in self.read(value) if f.day == day.isoformat()]

    async def filings(self, day: dt.date) -> list[Filing] | None:
        """The candidates on the ballot of the general election on ``day``, or None while the
        list doesn't have that election yet. UpstreamError when it can't be had."""
        got = await self.cache.get_json(self.source, self.spec(day), ttl=self.ttl.state_list)
        lists = [self.on(got.value, day)]
        if self.index_key:
            specs = self.follow(got.value, day)
            if specs is None:
                return None
            for spec in specs:
                lists.append(self.on((await self.cache.get_json(self.source, spec, ttl=self.ttl.state_list)).value, day))
        return self.combine(lists) or None

    def missing(self, when: str) -> str:
        """The ballot's note when the list has no candidates for the election on ``when``."""
        return f"The {self.label} hasn't published its list of candidates for {when} yet"

    @classmethod
    def ranked_choice(cls, race: Race) -> bool:
        """Whether the voter ranks the candidates in ``race`` instead of picking."""
        return False


IMPORTED = "manual:"  # the scheme of an imported list's key (ManualList.spec)


class ManualList(StateList):
    """A list Pallot never fetches, because the state's site blocks scripts: the maintainer saves
    it in their own browser and imports the file (pallot-bundle import-list), which bundles its
    parsed filings under spec(day). A lookup reads only that imported copy."""

    folder: ClassVar[str]  # where the saved file and the steps to refresh it are: "manual/state_az"
    binary: ClassVar[bool] = False  # parse() takes the saved file's bytes (a PDF), not its text
    challenge: ClassVar[tuple[str, ...]] = ()  # what the site's bot check page says, to refuse it by name
    fetched: ClassVar[bool] = False  # part of its ballot is fetched as it's used (Georgia's nominees): bundled apart, daily

    @classmethod
    def spec(cls, day: dt.date) -> RequestSpec:  # type: ignore[override]
        """The imported copy's key: not an address, so nothing can ever ask the state's site for it."""
        return RequestSpec("GET", f"{IMPORTED}{cls.source}", params={"day": day.isoformat()})

    @staticmethod
    def imported(spec: RequestSpec) -> bool:
        """Whether ``spec`` is an imported copy's key (spec), not a request of what's fetched."""
        return spec.url.startswith(IMPORTED)

    async def filings(self, day: dt.date) -> list[Filing] | None:
        kept = self.cache.peek(self.spec(day))
        return (self.on(kept.value, day) if kept else []) or None

    def missing(self, when: str) -> str:
        return f"Pallot doesn't have the {self.label}'s list of candidates for {when} yet"
