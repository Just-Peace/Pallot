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

Alaska's key dates, for its general election (AS 15.15.020: the Tuesday after the first Monday of
November in an even year), checked on akleg.gov on 2026-10-25: a registration must be made in
person, or postmarked or sent electronically, at least 30 days before (15.07.070(c), (d)); early
voting runs for the 15 days before and on Election Day (15.20.064(a)); any voter can vote absentee,
an application for a ballot by mail reaching the Division of Elections at least 10 days before
(15.20.081(b)), and a mailed ballot must be postmarked by Election Day and reach the election
supervisor by the close of business on the 10th day after (15.20.081(e)); polls are open 7 a.m. to 8
p.m.
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
from . import (
    SUFFIXES, Filing, Office, StateList, filings_json, from_json, legislator, ordinal, party, require, statewide,
    us_house, us_senate,
)
from .dates import Counts, Guide

BASE = "https://www.elections.alaska.gov/candidates/"
URL = BASE + "?election={year:02d}genr"
MINIMUM = {"hd": 40}
_ELECTION = re.compile(r"<h2>\s*(\d{4}) General Election\s*</h2>.*?Election Date\s+([A-Z][a-z]+ \d{1,2}, \d{4})", re.S)
_PAGES = re.compile(r"""href=["']([^"']*\?election=(\d{2}genr)&(?:amp;)?frm-page-\d+=(\d+))["']""")
_TITLE = re.compile(r"""class=["']entry-title["'][^>]*>\s*Candidates\s*</h1>""")  # the page, with or without a list
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


def _race(heading: str) -> Office | None:
    """A race's heading's race; None for a court's, whose judges are races of their own
    (_retention). ValueError for a heading it doesn't know."""
    text = heading.upper()
    if text == "GOVERNOR / LIEUTENANT GOVERNOR":
        return statewide("Governor and Lieutenant Governor", "GOVERNOR")
    if text == "UNITED STATES SENATOR":
        return us_senate("AK")
    if text == "UNITED STATES REPRESENTATIVE":
        return us_house("AK", 0, "US HOUSE")
    if found := re.fullmatch(r"SENATE DISTRICT ([A-T])", text):
        return legislator("sd", found.group(1), text)
    if found := re.fullmatch(r"HOUSE DISTRICT (\d{1,2})", text):
        number = int(found.group(1))
        return legislator("hd", number, f"HOUSE DISTRICT {number}")
    if text == "SUPREME COURT" or re.fullmatch(r"STATE (SUPERIOR|DISTRICT) COURT \d{1,2}", text):
        return None
    raise ValueError(f"a race it doesn't know: {heading}")


def _retention(heading: str, name: str) -> Office:
    """A judge's retention question, a race of its own with the judge as its one candidate."""
    text = heading.upper()
    if text == "SUPREME COURT":
        return Office(f"SUPREME COURT {name.upper()}", f"Retain Supreme Court Justice {name}", "SUPREME COURT",
                      "judicial", "state", incumbent=True, retention=True)
    court, number = re.fullmatch(r"STATE (SUPERIOR|DISTRICT) COURT (\d+)", text).groups()
    district = int(number)
    if district not in _JUDICIAL:
        raise ValueError(f"no judicial district {district}")
    return Office(f"{court} COURT {district} {name.upper()}",
                  f"Retain {_COURTS[court]} {name}, {ordinal(district)} Judicial District", f"{court} COURT",
                  "judicial", "counties", str(district), _JUDICIAL[district], incumbent=True, retention=True)


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
    suffix = [words.pop()] if len(words) > 1 and words[-1].strip(".,").upper() in SUFFIXES else []
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
                name = " ".join(row["name"].split())
                filings.append(_retention(heading, name).filing(day=day, name=name, order=order))
                continue
            if len(found) < 2:
                raise ValueError(f"no registration for {row['name']} under {heading}")
            code, party_name = _registration(found[0])
            name = " and ".join(_person(part) for part in re.split(r"\s*/\s*", row["name"]))
            filings.append(race.filing(
                day=day, name=name, party=code, party_name=party_name, write_in="Write-In" in row["note"],
                incumbent="Incumbent" in row["note"], order=order,
            ))
    return {**filings_json(filings), "pages": pages}


def whole(filings: list[Filing]) -> None:
    """ValueError for a list short of the U.S. House race or of a State House district."""
    if not any(f.reach == "cd" for f in filings):
        raise ValueError("no U.S. House race")
    require(filings, MINIMUM)


class AkList(StateList):
    state = "AK"
    source = "state_ak"
    label = "Alaska Division of Elections"
    page = "https://www.elections.alaska.gov/candidates/"
    description = "Alaska's list of the candidates on its general election ballot, from its Division of Elections."
    max_bytes = 8 << 20
    cafile = Path(__file__).parent / "certs" / "ak.pem"
    index_key = "pages"  # its first page, which also has the first part of the list

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", URL.format(year=day.year % 100))

    @classmethod
    def ranked_choice(cls, race: Race) -> bool:
        """Every race but the judges' retention questions (AS 15.15.350)."""
        return not race.retention

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        return read_page(raw.decode("utf-8", "replace"))

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        if not isinstance(raw, str):
            raise ValueError("not a page")
        return from_json(read_page(raw))

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        if not self.on(index, day):
            return None
        return [RequestSpec("GET", url) for url in index["pages"]]

    def combine(self, lists: list[list[Filing]]) -> list[Filing]:
        """The pages' filings in their order, each court's judges once (they come on every page);
        UpstreamError for a list that isn't whole."""
        kept, seen = [], set()
        for number, found in enumerate(lists):
            for filing in found:
                if (filing.office_id, filing.name) not in seen:
                    seen.add((filing.office_id, filing.name))
                    kept.append(dataclasses.replace(filing, order=filing.order + number * 100_000))
        try:
            whole(kept)
        except ValueError as exc:
            raise UpstreamError(self.source, f"its list isn't whole: {exc}") from exc
        return kept


GUIDE = Guide(
    name="Alaska",
    source="Alaska Division of Elections",
    url="https://www.elections.alaska.gov/",
    computed=True,
    registration_url="https://voterregistration.alaska.gov/",
    mail_url="https://absenteeballotapplication.alaska.gov/",
    register="The last day to register to vote in {election} in Alaska: in person, online, or by mail postmarked "
             "today. There's no registration on Election Day.",
    mail_summary="Absentee ballot application due",
    mail="If you vote absentee by mail in {election}, your application must reach the Division of Elections today. "
         "Your ballot must be postmarked by Election Day and reach the Division within 10 days after. Any voter can "
         "vote absentee; how to apply:",
    early_where="The Division of Elections lists the places and hours. Early voting goes on through Election Day.",
    credit="Dates worked out from Alaska's election law; more from the Alaska Division of Elections",
    poll_hours="7 a.m. – 8 p.m.",
    check_url="https://myvoterinformation.alaska.gov/",
    check_hint="Alaska Division of Elections' My Voter Information: your registration and your polling place",
    where_url="https://www.elections.alaska.gov/voter-information/absentee-and-early-voting/",
    where_hint="Alaska Division of Elections: early and in-person absentee voting places",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote absentee by mail, no reason needed. Your ballot must be postmarked "
                     "by Election Day and reach the Division of Elections within 10 days after.",
    mail_deadline="Your application must reach the Division of Elections by ",
    local_office="The Division of Elections' regional office",
)
RULE = Counts(30, 10, 15, None).rule("AK")
