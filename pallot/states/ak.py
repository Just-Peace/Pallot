"""Alaska: the Division of Elections' list of the general election's candidates, a web page of
one table per race (``?election=26genr``, by year), split over a few pages its own links name.
Its server sends its certificate without GlobalSign's intermediate, so the list is asked through
a client that also trusts that certificate (certs/ak.pem).

A row's first cell is the name as on the ballot ("Last, First", a ticket's two names apart by
" / "), the voter registration ("(Registered Republican)", "(Nonpartisan)", "(Undeclared)") and
the status ("(Certified)"), with "Certified Write-In" or "Incumbent" beside it; the others are
the campaign's address, phone, email and website, never read. Alaska's top-four primary means
the registration isn't a nomination: it's shown as the candidate's party, as the state prints
it. Each page is kept as its filings and its links to the others, never as the page. The
courts' retention questions come on every page: each judge is a race of their own, statewide
for the Supreme Court, by its boroughs and census areas for a judicial district.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import html
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from ..http_cache import RequestSpec, UpstreamError
from ..models import Race
from ..sources.fec import race_name
from . import Filing, StateList, filings_json, from_json, ordinal, party

BASE = "https://www.elections.alaska.gov/candidates/"
URL = BASE + "?election={year:02d}genr"
HOUSE_RACES = 40
_ELECTION = re.compile(r"<h2>\s*(\d{4}) General Election\s*</h2>.*?Election Date\s+([A-Z][a-z]+ \d{1,2}, \d{4})", re.S)
_PAGES = re.compile(r"""href=["']([^"']*\?election=(\d{2}genr)&(?:amp;)?frm-page-\d+=(\d+))["']""")
_TITLE = re.compile(r"""class=["']entry-title["'][^>]*>\s*Candidates\s*</h1>""")  # the page, with or without a list
_SUFFIXES = {"JR", "SR", "II", "III", "IV", "V"}
_PARENS = re.compile(r"\(([^()]*)\)")
# Each judicial district's boroughs and census areas (AS 22.10.010), as the Census names them.
_JUDICIAL = {
    1: ("HAINES", "HOONAH-ANGOON", "JUNEAU", "KETCHIKAN GATEWAY", "PETERSBURG", "PRINCE OF WALES-HYDER", "SITKA",
        "SKAGWAY", "WRANGELL", "YAKUTAT"),
    2: ("NOME", "NORTH SLOPE", "NORTHWEST ARCTIC"),
    3: ("ALEUTIANS EAST", "ALEUTIANS WEST", "ANCHORAGE", "BRISTOL BAY", "CHUGACH", "COPPER RIVER", "DILLINGHAM",
        "KENAI PENINSULA", "KODIAK ISLAND", "LAKE AND PENINSULA", "MATANUSKA-SUSITNA"),
    4: ("BETHEL", "DENALI", "FAIRBANKS NORTH STAR", "KUSILVAK", "SOUTHEAST FAIRBANKS", "YUKON-KOYUKUK"),
}
_COURTS = {"SUPERIOR": "Superior Court Judge", "DISTRICT": "District Court Judge"}


class _Page(HTMLParser):
    """Each race's heading and its candidates' first cells, inside the page's candidates-table
    sections only: the name (in bold), the registration and status (small), and the rest (notes)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.races: list[tuple[str, list[dict[str, str]]]] = []
        self._depth = 0
        self._heading: list[str] | None = None
        self._cell: dict[str, list[str]] | None = None
        self._column = 0
        self._open: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag == "section" and (self._depth or "candidates-table" in (dict(attrs).get("class") or "").split()):
            self._depth += 1
        if not self._depth:
            return
        if tag == "h4":
            self._heading = []
        elif tag == "tr":
            self._column = 0
        elif tag == "td":
            self._column += 1
            if self._column == 1 and self.races:
                self._cell = {"name": [], "small": [], "note": []}
        elif tag in ("strong", "small"):
            self._open.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self._depth:
            return
        if tag == "section":
            self._depth -= 1
        elif tag == "h4" and self._heading is not None:
            self.races.append((" ".join("".join(self._heading).split()), []))
            self._heading = None
        elif tag == "td" and self._cell is not None:
            self.races[-1][1].append({part: " ".join(" ".join(text).split()) for part, text in self._cell.items()})
            self._cell = None
        elif tag in self._open:
            self._open.remove(tag)

    def handle_data(self, data: str) -> None:
        if self._heading is not None:
            self._heading.append(data)
        elif self._cell is not None:
            self._cell["name" if "strong" in self._open else "small" if "small" in self._open else "note"].append(data)


def _race(heading: str) -> tuple[str, str, str, str | None, str] | None:
    """(race id, group, reach, district, shown name) of a race's heading; None for a court's,
    whose judges are races of their own (_retention). ValueError for a heading it doesn't know."""
    text = heading.upper()
    if text == "GOVERNOR / LIEUTENANT GOVERNOR":
        return "GOVERNOR", "state", "state", None, "Governor and Lieutenant Governor"
    if text == "UNITED STATES SENATOR":
        return "US SENATE", "federal", "state", None, race_name("AK", None)
    if text == "UNITED STATES REPRESENTATIVE":
        return "US HOUSE", "federal", "cd", "0", race_name("AK", 0)
    if found := re.fullmatch(r"SENATE DISTRICT ([A-T])", text):
        return text, "legislature", "sd", found.group(1), f"State Senator District {found.group(1)}"
    if found := re.fullmatch(r"HOUSE DISTRICT (\d{1,2})", text):
        number = str(int(found.group(1)))
        return f"HOUSE DISTRICT {number}", "legislature", "hd", number, f"State Representative District {number}"
    if text == "SUPREME COURT" or re.fullmatch(r"STATE (SUPERIOR|DISTRICT) COURT \d{1,2}", text):
        return None
    raise ValueError(f"a race it doesn't know: {heading}")


def _retention(heading: str, name: str, day: str, order: int) -> Filing:
    """A judge's retention question, a race of its own with the judge as its one candidate."""
    text = heading.upper()
    if text == "SUPREME COURT":
        return Filing(day=day, office_id=f"SUPREME COURT {name.upper()}", office=f"Retain Supreme Court Justice {name}",
                      family="SUPREME COURT", group="judicial", reach="state", district=None, name=name,
                      incumbent=True, retention=True, order=order)
    court, number = re.fullmatch(r"STATE (SUPERIOR|DISTRICT) COURT (\d+)", text).groups()
    district = int(number)
    if district not in _JUDICIAL:
        raise ValueError(f"no judicial district {district}")
    return Filing(day=day, office_id=f"{court} COURT {district} {name.upper()}",
                  office=f"Retain {_COURTS[court]} {name}, {ordinal(district)} Judicial District",
                  family=f"{court} COURT", group="judicial", reach="counties", district=str(district), name=name,
                  counties=_JUDICIAL[district], incumbent=True, retention=True, order=order)


def _registration(text: str) -> tuple[str | None, str | None]:
    """(party code, name) of a registration: "Registered Republican" is R; "Nonpartisan",
    "Undeclared" and a ticket's two ("Registered Democrat / Nonpartisan") keep their words."""
    parts = [re.sub(r"^Registered\s+", "", part.strip(), flags=re.I) for part in text.split("/")]
    codes = {party(part)[0] for part in parts}
    if len(codes) == 1 and None not in codes:
        return codes.pop(), None
    return None, " / ".join(parts)


def _person(text: str) -> str:
    """ "Sullivan, Daniel J. Jr." -> "Daniel J. Sullivan Jr.", nicknames kept as printed."""
    last, _, first = (" ".join(part.split()) for part in text.partition(","))
    if not first:
        return last
    words = first.split()
    suffix = [words.pop()] if len(words) > 1 and words[-1].strip(".,").upper() in _SUFFIXES else []
    return " ".join([*words, last, *suffix])


def read_page(text: str) -> dict[str, Any]:
    """A page of the list as kept: its filings and the links to its other pages (from the
    second on); none of either for the page of a year it has no general election for yet.
    ValueError for a page that isn't the list, or a row it can't read."""
    election = _ELECTION.search(text)
    if election is None:
        if _TITLE.search(text):
            return {"filings": [], "pages": []}
        raise ValueError("not the Division of Elections' list of candidates")
    day = dt.datetime.strptime(election.group(2), "%B %d, %Y").date().isoformat()
    code = f"{int(election.group(1)) % 100:02d}genr"
    pages = sorted({urljoin(BASE, html.unescape(href)) for href, linked, number in _PAGES.findall(text)
                    if linked == code and number != "1"}, key=lambda url: int(url.rsplit("=", 1)[1]))
    parser = _Page()
    parser.feed(text)
    if not parser.races:
        raise ValueError("no races on the page")
    filings = []
    for index, (heading, rows) in enumerate(parser.races):
        race = _race(heading)
        for position, row in enumerate(rows):
            order = index * 100 + position
            if not row["name"]:
                raise ValueError(f"a row without a name under {heading}")
            found = _PARENS.findall(row["small"])
            if not found:
                raise ValueError(f"no status for {row['name']} under {heading}")
            if found[-1].strip() != "Certified":
                continue
            if race is None:
                filings.append(_retention(heading, " ".join(row["name"].split()), day, order))
                continue
            race_id, group, reach, district, shown = race
            if len(found) < 2:
                raise ValueError(f"no registration for {row['name']} under {heading}")
            code, party_name = _registration(found[0])
            name = " and ".join(_person(part) for part in re.split(r"\s*/\s*", row["name"]))
            filings.append(Filing(
                day=day, office_id=race_id, office=shown, family={"sd": "STATE SENATE", "hd": "STATE HOUSE"}.get(reach, race_id),
                group=group, reach=reach, district=district, name=name,
                party=code, party_name=party_name, write_in="Write-In" in row["note"],
                incumbent="Incumbent" in row["note"], order=order,
            ))
    return {**filings_json(filings), "pages": pages}


def whole(filings: list[Filing]) -> None:
    """ValueError for a list short of the U.S. House race or of a State House district."""
    if not any(f.reach == "cd" for f in filings):
        raise ValueError("no U.S. House race")
    house = {f.district for f in filings if f.reach == "hd"}
    if len(house) < HOUSE_RACES:
        raise ValueError(f"{len(house)} State House races, not {HOUSE_RACES}")


class AkList(StateList):
    state = "AK"
    source = "state_ak"
    label = "Alaska Division of Elections"
    page = "https://www.elections.alaska.gov/candidates/"
    description = "Alaska's list of the candidates on its general election ballot, from its Division of Elections."
    max_bytes = 8 << 20
    cafile = Path(__file__).parent / "certs" / "ak.pem"

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", URL.format(year=day.year % 100))

    @classmethod
    def ranked_choice(cls, race: Race) -> bool:
        """Every race but the judges' retention questions (AS 15.15.350)."""
        return not race.retention

    @classmethod
    def read_file(cls, path: Path) -> dict[str, Any]:
        return read_page(path.read_bytes().decode("utf-8", "replace"))

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        if not isinstance(raw, str):
            raise ValueError("not a page")
        return from_json(read_page(raw))

    def check(self, value: Any) -> str | None:
        if isinstance(value, dict) and isinstance(value.get("pages"), list):
            try:
                self.read(value)
            except (TypeError, ValueError) as exc:
                return f"can't read its list of candidates: {exc}"
            return None
        return super().check(value)

    async def filings(self, day: dt.date) -> list[Filing] | None:
        first = await self.cache.get_json(self.source, self.spec(day), ttl=self.ttl.state_list)
        found = [f for f in self.read(first.value) if f.day == day.isoformat()]
        if not found:
            return None
        for number, url in enumerate(first.value["pages"], 1):
            got = await self.cache.get_json(self.source, RequestSpec("GET", url), ttl=self.ttl.state_list)
            found += [dataclasses.replace(f, order=f.order + number * 100_000)
                      for f in self.read(got.value) if f.day == day.isoformat()]
        kept, seen = [], set()
        for filing in found:  # the courts come on every page
            if (filing.office_id, filing.name) not in seen:
                seen.add((filing.office_id, filing.name))
                kept.append(filing)
        try:
            whole(kept)
        except ValueError as exc:
            raise UpstreamError(self.source, f"its list isn't whole: {exc}") from exc
        return kept
