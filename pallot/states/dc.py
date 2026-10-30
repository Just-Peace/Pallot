"""District of Columbia: the Board of Elections' General Election Candidates in Ballot Order, a
PDF linked from the year's elections page (dcboe.org/elections/2026-elections) under a name that
carries the day it was made and a path with GUIDs, so it's found on that page by its link's words,
never by a name worked out ahead. A plain script gets a 200.

The list is one table in ballot order: each office's name on a line of its own, then a row per
candidate ("Robert White - Democrat", the party after the name; the State Board of Education is
nonpartisan, so its rows have none), then the candidate's contact person, street address, ZIP
code, phone, email and the days the petition was picked up and filed, which are never read, and a
"Write-In, if any" line closing each office. It has no withdrawn candidates or incumbents. Only
the name, office and party are kept: the file is streamed and kept as its filings, so the cache
and the bundle hold nothing else. The Advisory Neighborhood Commissions' candidates are another PDF,
not read.

Its offices are the Delegate to the U.S. House (the Census's district "98", which Pallot numbers
0), Mayor, the Council's Chairman and its at-large members (two elected each general election),
the Attorney General, and the "shadow" U.S. Senator and U.S. Representative, all elected citywide.
The Delegate is the U.S. House race; the shadow offices are the District's own, not seats in
Congress. The Council's and the State Board of Education's ward races are left out with a ballot
note, since Pallot doesn't know an address's ward yet. An office it doesn't know is refused.

Since the June 2026 primary, a contest with three candidates or more on the ballot is
ranked-choice: the voter ranks up to five (Initiative 83, the Ranked Choice Voting and Open Primary
Elections Initiative of 2024, its ranked-choice half funded in the FY2026 budget), as the Board's
Ranked Choice Voting FAQ of 2026-01-12 lists the contests, the shadow offices included.

The District's key dates, for its general election (the Tuesday after the first Monday of November
in an even year, D.C. Code §1-1001.10(a)(2)), checked against the Board's 2026 General Election
Calendar (rev. 2026-10-01) on 2026-10-30: registration by mail or online must reach the Board by the
21st day before (§1-1001.07(g)(1)-(3); 3 DCMR §504.3), and a voter can still register in person at
a vote center during early voting (§1-1001.09(b-1)) and on Election Day; every registered voter is
mailed a ballot (§1-1001.05(a)(10A)), and a voter whose ballot must go elsewhere asks for one by
the 15th day before (3 DCMR §720.5); a mailed ballot is counted postmarked by Election Day and
received within 10 days, or dropped off by 8 p.m. on Election Day (§1-1001.05(a)(10A)); early vote
centers are open 8:30 a.m. to 7 p.m. every day from the 8th day before through the 2nd
(§1-1001.09(b-1)); polls are open 7 a.m. to 8 p.m. at any vote center. 2026: Oct 13, Oct 19,
Oct 26 – Nov 1.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from typing import Any
from urllib.parse import urljoin

from ..http_cache import RequestSpec
from ..models import Race
from . import MONTH_DAY_YEAR, Filing, Office, StateList, party, pdf_lines, require, statewide, us_house
from .dates import Counts, Guide, mailed_to_every_voter

SITE = "https://www.dcboe.org"
PAGE = f"{SITE}/elections/2026-elections"
MINIMUM = {"cd": 1}
OFFICES = {
    "Delegate to the House of Representatives": us_house("DC", 0, "US HOUSE"),
    "Mayor of the District of Columbia": statewide("Mayor"),
    "Chairman of the Council of the District of Columbia": statewide("Chairman of the Council", "COUNCIL CHAIRMAN"),
    "At-Large Member of the Council": Office("COUNCIL AT-LARGE", "At-Large Member of the Council", "COUNCIL AT-LARGE",
                                             "state", "state", seats=2),
    "Attorney General": statewide("Attorney General"),
    "United States Senator": statewide("Shadow U.S. Senator", "SHADOW US SENATOR"),
    "United States Representative": statewide("Shadow U.S. Representative", "SHADOW US REPRESENTATIVE"),
}
LEFT_OUT = re.compile(r"Ward \d Member of the (?:Council|State Board of Education)")
_TITLE = re.compile(r"<title>[^<]*\bElections\b[^<]*District of Columbia Board of Elections", re.I)
_LINK = re.compile(r"""<a\b[^>]*href=["']([^"']+\.pdf[^"']*)["'][^>]*>(.*?)</a>""", re.I | re.S)
_SKIP = re.compile(r"Write-In\b|District of Columbia Board of Elections\b|Candidate's Name\b|Page \d+")  # not a row
_DAY = re.compile(rf"({MONTH_DAY_YEAR}) General Election")


def year_page(year: int) -> str:
    """The Board's page of a year's elections."""
    return f"{SITE}/elections/{year}-elections"


def links(text: str) -> dict[str, Any]:
    """The year's elections page as kept: its link to the general election's candidates in ballot
    order (not the ANC's, the write-ins' or the primary's); ValueError for a page that isn't it."""
    if not _TITLE.search(text):
        raise ValueError("not the Board of Elections' page of a year's elections")
    found = []
    for href, words in _LINK.findall(text):
        said = " ".join(re.sub(r"<[^>]+>", " ", html.unescape(words)).split())
        if said.lower() == "general election candidates in ballot order":
            found.append(urljoin(SITE, html.unescape(href)))
    return {"links": found[:1]}


def candidates(lines: list[str]) -> list[Filing]:
    """Every candidate for an office it places, from pdf_lines' layout of the list: an office's
    name a line of its own, a candidate's row the name and its contact details apart by runs of
    spaces. ValueError for a file that isn't the list, an office it doesn't know, or a list without
    the Delegate's race (MINIMUM)."""
    heading = " ".join(" ".join(lines[:3]).split())
    day = _DAY.search(heading)
    if "District of Columbia Board of Elections" not in heading or not day:
        raise ValueError("not the list of general election candidates")
    when = dt.datetime.strptime(day.group(1), "%B %d, %Y").date().isoformat()
    filings: list[Filing] = []
    office: Office | None = None
    left_out = False
    for index, line in enumerate(lines):
        if not line.strip() or line[0].isspace() or _SKIP.match(line.strip()):
            continue
        cells = re.split(r"\s{2,}", line.strip())
        if len(cells) == 1:
            title = " ".join(cells[0].split())
            left_out = bool(LEFT_OUT.fullmatch(title))
            office = OFFICES.get(title)
            if office is None and not left_out:
                raise ValueError(f"an office it doesn't know: {title}")
            continue
        if left_out:
            continue
        if office is None:
            raise ValueError(f"a candidate before any office: {cells[0][:40]}")
        name, _, label = cells[0].rpartition(" - ") if " - " in cells[0] else (cells[0], "", "")
        code, party_name = party(label)
        filings.append(office.filing(day=when, name=" ".join(name.split()), party=code, party_name=party_name,
                                     order=index))
    return require(filings, MINIMUM)


class DcList(StateList):
    state = "DC"
    source = "state_dc"
    label = "DC Board of Elections"
    page = PAGE
    description = ("The District of Columbia's official list of the candidates for Delegate, Mayor, the Council and "
                   "Attorney General, from its Board of Elections.")
    max_bytes = 8 << 20
    index_key = "links"
    scope_note = ("Your ward's Council and State Board of Education races, your Advisory Neighborhood Commission's "
                  "and any questions aren't shown: the DC Board of Elections' sample ballot for your ward has them.")

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", year_page(day.year))

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        if raw.startswith(b"%PDF"):
            return None
        return links(raw.decode("utf-8", "replace"))

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        found = index["links"]
        return [RequestSpec("GET", found[0])] if found else None

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, bytes):
            raise ValueError("not a PDF")
        return candidates(pdf_lines(raw))

    @classmethod
    def ranked_choice(cls, race: Race) -> bool:
        """Every contest with three candidates or more on the ballot (Initiative 83)."""
        return sum(not candidate.write_in for candidate in race.candidates) >= 3


GUIDE = Guide(
    name="DC",
    source="DC Board of Elections",
    url=SITE,
    computed=True,
    registration_url="https://www.dcboe.org/voters/register-to-vote/register-update-voter-registration",
    mail_url="https://www.dcboe.org/voters/casting-your-vote/mail-ballot-request",
    register="The last day for your registration online or by mail to reach the DC Board of Elections for {election}. "
             "After it, you can still register in person at any vote center during early voting or on Election Day.",
    mail_summary="Mail ballot request due",
    mail="Every registered voter in DC is mailed a ballot for {election}. If yours must go to another address, ask "
         "the DC Board of Elections for it by today. Mail it back postmarked by Election Day (it must arrive within "
         "10 days), or put it in a drop box or vote center by 8 p.m. on Election Day. How to ask:",
    early_where="Any early vote center in DC, open 8:30 a.m. to 7 p.m. every day: the DC Board of Elections lists them.",
    credit="Dates worked out from the District of Columbia's election law; more from the DC Board of Elections",
    poll_hours="7 a.m. – 8 p.m.",
    check_url="https://apps.dcboe.org/VRS",
    check_hint="DC Board of Elections' voter registration lookup: your registration and your mail ballot",
    where_url="https://dcgis.maps.arcgis.com/apps/instant/nearby/index.html?appid=763576faa0b1470ca0559c377cf3b497",
    where_hint="DC's map of vote centers and mail ballot drop boxes: vote at any of them",
    mail_label="How to ask",
    mail_eligibility=mailed_to_every_voter("Mail it back postmarked by Election Day (it must arrive within 10 days), "
                                           "or put it in a drop box or vote center by 8 p.m. on Election Day."),
    mail_deadline="To have it sent to another address, ask by ",
    local_office="The DC Board of Elections",
    late_registration="After that, register in person at any vote center during early voting or on Election Day",
)
RULE = Counts(21, 15, 8, 2).rule("DC")
