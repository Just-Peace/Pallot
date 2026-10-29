"""Nebraska: the Secretary of State's Final Statewide General Candidate List, a PDF, and its List
of Judges Who Filed for Retention, another, both linked from its elections page under names that
carry the day they were made ("Final_Statewide_General_Candidate_Filing_List_9.11.26.pdf"), so
they're found on that page by their links, under the year's folder, never by a name worked out
ahead.

The candidate list's pages are turned sideways (read upright by pdf_lines), a row per candidate:
the office ("For Member of the Legislature"), the district ("District 02"), the term, how many
to vote for, the party (blank for a nonpartisan office; a long one wraps onto the next line:
"Legal Marijuana" / "NOW"), the name ("Jim Pillen and Joe Kelly" for a Governor's ticket), the
city they live in, Incumbent or Nonincumbent, then a mailing address, phone and email, which are
never read. Only the name, office, district, party and whether they're the incumbent are kept:
each file is streamed and kept as its filings, so the cache and the bundle hold nothing else. The
list has no withdrawn candidates or write-ins.

Its offices of the state ("For …") are Congress, Governor and the other statewide offices, the
Legislature (one house, nonpartisan, whose districts the Census calls the upper house's), the
Public Service Commission, the State Board of Education and the University's Regents; the rest
are local boards (community colleges, educational service units, natural resources and public
power districts). Only Congress, the statewide offices and the Legislature are placed: the other
boards' districts aren't any the Census knows. A race whose term is shorter than the office's is
for the rest of a term (unexpired).

The judges for retention are each a yes-or-no race, their one candidate: a statewide court's
("Statewide") for the whole state, a separate juvenile court's ("4 - Douglas") for its county. The
Court of Appeals' and the district and county courts' judges are elected in judicial districts
made of counties, which aren't placed, so they're left out.

Nebraska's key dates, for its general election (the Tuesday after the first Monday of November in
an even year, Neb. Rev. Stat. §32-403), checked on nebraskalegislature.gov and against the
Secretary of State's 2026 Official Election Calendar on 2026-10-28: a registration by mail must be
postmarked, and one online made before midnight, by the third Friday before (§32-321(3), §32-304);
in person, at the county election office until 6 p.m. on the second Friday before (§32-302); an
early ballot by mail can be asked for until close of business on the second Friday before
(§32-941), any voter can vote early (§32-938), and the ballot must be back when the polls close
(§32-950); early voting in person at the county election office opens no more than thirty days
before, a Sunday, so the Monday after, the 29th day (§32-942, as the calendar has it), through the
day before. Polls are open 8 a.m. to 8 p.m. Central time and 7 a.m. to 7 p.m. Mountain time, the
same hours at once across the state (§32-908).
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any
from urllib.parse import unquote, urljoin

from ..http_cache import RequestSpec
from . import (
    MONTH_DAY_YEAR, Filing, Office, StateList, filings_json, legislator, party, pdf_lines, require, statewide,
    us_house, us_senate,
)
from .dates import Counts, Guide

PAGE = "https://sos.nebraska.gov/elections"
MINIMUM = {"cd": 3, "sd": 20}  # nearly all the Legislature's half up each election
STATEWIDE = {"For Secretary of State": "Secretary of State", "For State Treasurer": "State Treasurer",
             "For Attorney General": "Attorney General", "For Auditor of Public Accounts": "Auditor of Public Accounts"}
LEFT_OUT = ("For Public Service Commissioner", "For Member of the State Board of", "For University of Nebraska Board of")
_TITLE = re.compile(r"<title>[^<]*\bElections\b[^<]*Nebraska Secretary of State", re.I)
_LINK = re.compile(r"""href=["']([^"']*/elections/(\d{4})/([^"'/]+\.pdf))["']""", re.I)
_DAY = re.compile(rf"({MONTH_DAY_YEAR}) General Election")
_STATUS = re.compile(r"\s{2,}(Incumbent|Nonincumbent)\b")
_JUDGE = re.compile(r"(Judge of the .+?)\s{2,}(\S.*?)\s{2,}(\d+)\s{2,}(\S.*?)\s{2,}Shall Judge\b.*")
_COUNTY = re.compile(r"\d+ - ([A-Za-z][A-Za-z ]*)")


def links(text: str) -> dict[str, Any]:
    """The elections page as kept: its links to the general election's candidate list and to the
    judges for retention, by the year of their folder (a final list over an earlier one);
    ValueError for a page that isn't it."""
    if not _TITLE.search(text):
        raise ValueError("not the Secretary of State's elections page")
    found: dict[str, str] = {}
    retention: dict[str, str] = {}
    for href, year, name in _LINK.findall(text):
        url = urljoin(PAGE, href)
        words = re.sub(r"[_\s]+", " ", unquote(name)).lower()
        if "general candidate" in words and "list" in words and ("final" in words or year not in found):
            found[year] = url
        elif "retention" in words and ("final" in words or year not in retention):
            retention[year] = url
    return {"links": found, "retention": retention}


def _day(lines: list[str], what: str) -> str:
    """The election's ISO day in a list's heading; ValueError for a file that isn't ``what``."""
    text = " ".join(" ".join(lines[:8]).split())
    day = _DAY.search(text)
    if day is None:
        raise ValueError(f"not the {what}")
    return dt.datetime.strptime(day.group(1), "%B %d, %Y").date().isoformat()


def _race(office: str, district: str | None) -> tuple[Office, int] | None:
    """The race an office and district name, with the office's usual term; None for a board
    that isn't placed. ValueError for an office of the state the list never had."""
    if office == "For United States Senator":
        return us_senate("NE"), 6
    if office == "For Governor and Lt. Governor":
        return statewide("Governor and Lieutenant Governor", "GOVERNOR"), 4
    if office in STATEWIDE:
        return statewide(STATEWIDE[office]), 4
    if office in ("For Representative in Congress", "For Member of the Legislature"):
        number = re.fullmatch(r"District (\d+)", district or "")
        if not number:
            raise ValueError(f"no district for {office}: {district!r}")
        n = int(number.group(1))
        if office == "For Representative in Congress":
            return us_house("NE", n), 2
        return legislator("sd", n, office=f"Member of the Legislature District {n}"), 4
    if office.startswith(LEFT_OUT) or not office.startswith("For "):
        return None
    raise ValueError(f"an office it doesn't know: {office}")


def candidates(lines: list[str]) -> list[Filing]:
    """Every candidate for Congress, the statewide offices and the Legislature, from pdf_lines'
    layout of the list: a row's cells apart by runs of spaces, and a party that wraps continued
    on the next line, between the seats' column and the name's. ValueError for a file that isn't the list, a row it
    can't read, or a list short of its races (MINIMUM)."""
    if not any("Final Statewide General Candidate List" in " ".join(line.split()) for line in lines[:8]):
        raise ValueError("not the list of general election candidates")
    day = _day(lines, "list of general election candidates")
    filings: list[Filing] = []
    rows: list[tuple[dict[str, Any], int, int]] = []  # each kept row's fields, and where its party's column is
    for index, line in enumerate(lines):
        status = _STATUS.search(line)
        if not status:
            if rows and rows[-1][0].get("order") == index - 1:
                fields, start, end = rows[-1]
                for word in re.finditer(r"\S+(?: \S+)*", line):
                    if start <= word.start() < end and fields["party"]:
                        fields["party"] += f" {word.group()}"
            continue
        cells = re.split(r"\s{2,}", line[:status.start()].strip())
        office = cells[0]
        district = cells[1] if len(cells) > 1 and re.match(r"(?:Sub)?district\b", cells[1], re.I) else None
        at = 2 if district else 1
        found = _race(office, district)
        if found is None:
            rows.append(({"party": None}, 0, 0))
            continue
        middle = cells[at + 2:]
        if not (cells[at:at + 2] and all(c.isdigit() for c in cells[at:at + 2])) or len(middle) not in (2, 3):
            raise ValueError(f"a row it can't read: {' '.join(line.split())[:80]}")
        label, name = (middle[0], middle[1]) if len(middle) == 3 else ("", middle[0])
        seats_end = line.index(cells[at + 1], line.index(office) + len(office)) + len(cells[at + 1])
        name_start = line.index(name, seats_end)
        fields = {"race": found, "term": int(cells[at]), "seats": int(cells[at + 1]), "name": name,
                  "party": label or None, "incumbent": status.group(1) == "Incumbent", "order": index}
        rows.append((fields, seats_end, name_start))
    for fields, _, _ in rows:
        race = fields.get("race")
        if race is None:
            continue
        office, term = race
        nonpartisan = office.reach == "sd"
        code, party_name = (None, None) if nonpartisan else party(fields["party"])
        filings.append(office.filing(
            day=day, name=fields["name"], party=code, party_name=party_name, seats=fields["seats"],
            unexpired=fields["term"] < term, incumbent=fields["incumbent"], order=fields["order"],
        ))
    return require(filings, MINIMUM)


def retention(lines: list[str]) -> list[Filing]:
    """The judges for retention whose races are placed (a statewide court's, a county's separate
    juvenile court's), each a yes-or-no race; ValueError for a file that isn't the list or a
    judge's line it can't read."""
    if not any("Who Filed For Retention" in " ".join(line.split()) for line in lines[:8]):
        raise ValueError("not the list of judges for retention")
    day = _day(lines, "list of judges for retention")
    filings = []
    for index, line in enumerate(lines):
        if not line.strip().startswith("Judge of the"):
            continue
        found = _JUDGE.fullmatch(line.strip())
        if not found:
            raise ValueError(f"a judge it can't read: {' '.join(line.split())[:80]}")
        title, where, _, name = (" ".join(group.split()) for group in found.groups())
        court = title.removeprefix("Judge of the ").removeprefix("Nebraska ")
        family = court.upper()
        if where == "Statewide":
            race = Office(f"{family} {name.upper()}", f"Retain {court} Judge {name}", family, "judicial", "state",
                          incumbent=True, retention=True)
        elif county := _COUNTY.fullmatch(where):
            place = county.group(1).strip()
            race = Office(f"{family} {place.upper()} {name.upper()}", f"Retain {place} County {court} Judge {name}",
                          family, "judicial", "county", counties=(place.upper(),), incumbent=True, retention=True)
        elif where.isdigit():
            continue
        else:
            raise ValueError(f"a court it can't place: {title}, {where}")
        filings.append(race.filing(day=day, name=name, order=100_000 + index))
    return filings


class NeList(StateList):
    state = "NE"
    source = "state_ne"
    label = "Nebraska Secretary of State"
    page = PAGE
    description = ("Nebraska's official list of the candidates for Congress, its statewide offices and the "
                   "Legislature, and the judges standing for retention, from its Secretary of State.")
    max_bytes = 8 << 20
    index_key = "links"
    scope_note = ("The Public Service Commission, State Board of Education, Regents and local boards (community "
                  "college, educational service unit, natural resources and public power districts), the judges of "
                  "the Court of Appeals and the district and county courts standing for retention, and any questions "
                  "aren't shown: your county election office's sample ballot has them.")

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", PAGE)

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        """The page's links; a PDF as its filings, the judges' beside an empty index, so a year
        with none of the judges it places still reads as an answer."""
        if not raw.startswith(b"%PDF"):
            return links(raw.decode("utf-8", "replace"))
        lines = pdf_lines(raw)
        if any("Who Filed For Retention" in " ".join(line.split()) for line in lines[:8]):
            return {**filings_json(retention(lines)), "links": {}}
        return filings_json(candidates(lines))

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        year = str(day.year)
        url = index["links"].get(year)
        if not url:
            return None
        judges = (index.get("retention") or {}).get(year)
        return [RequestSpec("GET", link) for link in (url, judges) if link]

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, bytes):
            raise ValueError("not a PDF")
        lines = pdf_lines(raw)
        if any("Who Filed For Retention" in " ".join(line.split()) for line in lines[:8]):
            return retention(lines)
        return candidates(lines)


GUIDE = Guide(
    name="Nebraska",
    source="Nebraska Secretary of State",
    url=PAGE,
    computed=True,
    registration_url="https://www.nebraska.gov/apps-sos-voter-registration/",
    mail_url="https://sos.nebraska.gov/elections/early-voting",
    register="The last day to register online, or by mail postmarked today, for {election} in Nebraska. After it, you "
             "can still register in person at your county election office until 6 p.m. on the second Friday before "
             "Election Day.",
    mail_summary="Early ballot request due",
    mail="If you vote early by mail in {election}, your request must reach your county election office by the close of "
         "business today. Your ballot must be back by the time the polls close on Election Day; one that arrives later "
         "isn't counted. Any voter can vote early; how to ask:",
    early_where="Your county election office: vote early in person there through the day before Election Day. Your "
                "county sets the hours.",
    credit="Dates worked out from Nebraska's election law; more from the Nebraska Secretary of State",
    poll_hours="8 a.m. – 8 p.m. Central, 7 a.m. – 7 p.m. Mountain",
    polls_text="Polls are open 8 a.m. to 8 p.m. Central time, 7 a.m. to 7 p.m. Mountain time; if you're in line when "
               "they close, you can vote.",
    check_url="https://www.votercheck.necvr.ne.gov/VoterView/",
    check_hint="Nebraska Secretary of State's Voter Information Lookup: your registration and your polling place",
    where_url="https://www.votercheck.necvr.ne.gov/VoterView/",
    where_hint="Nebraska Secretary of State's Voter Information Lookup: your polling place",
    mail_label="How to ask",
    mail_eligibility="Any registered voter can vote early by mail, no reason needed. Your ballot must reach your county "
                     "election office by the time the polls close on Election Day.",
    mail_deadline="Ask your county election office for your ballot by ",
)
RULE = Counts(18, 11, 29, 1).rule("NE")
