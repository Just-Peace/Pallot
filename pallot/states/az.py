"""Arizona: the Secretary of State's list of the candidates for a general election, from its
Election Information app (apps.arizona.vote/electioninfo), one page per election.

Every Arizona election site answers scripts with Cloudflare's challenge, so Pallot never asks
it: the maintainer saves the page in their own browser and imports it (manual/state_az). The
page is in tabs (Federal, State, Legislative, Judicial, Ballot Measures). Each office is a
heading ("State Representative - District No. 11"), then a heading per candidate, "LAST, FIRST
(DEM)", with a line under it for a write-in, and folded-away details (phone, email, statement)
that are never read. The judges standing for retention are only their names, each a race of
their own. The page can change at any time, so it's read by its headings, never by position,
and anything it can't read is refused.

Each Legislative District elects one senator and two representatives; the Census answers both
of Arizona's legislative layers with the district, so a representative's race is placed by
its State House district, which is the same number.

Arizona's key dates are entered by hand from its Secretary of State's list, whose site blocks
scripts; early voting in person ends at 5 p.m. the Friday before Election Day (A.R.S. 16-542(E)).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import re
from collections import Counter
from html.parser import HTMLParser
from typing import Any

from ..sources.key_dates import Deadlines
from ..text import display_person
from . import MONTH_DAY_YEAR, Filing, ManualList, Office, legislator, party, statewide, us_house, us_senate
from .dates import Guide

PAGE = "https://apps.arizona.vote/electioninfo/Election/69"
_DATE = re.compile(rf"\b{MONTH_DAY_YEAR}\b")
_DISTRICT = r"District\s*(?:No\.?\s*)?(\d+)"
_CANDIDATE = re.compile(r"(?P<name>.+?)\s*\((?P<party>[A-Za-z ]+)\)")
_PARTY_NAMES = {"NOL": "No Labels Party", "IND": "Independent", "INDEPENDENT": "Independent"}
_STATEWIDE = (
    "Governor", "Secretary of State", "Attorney General", "State Treasurer", "Superintendent of Public Instruction",
    "State Mine Inspector", "Corporation Commissioner",
)
_APPEALS = {  # A.R.S. 12-120: the counties each division of the Court of Appeals serves
    "I": ("One", ("MARICOPA", "YUMA", "LA PAZ", "MOHAVE", "COCONINO", "YAVAPAI", "NAVAJO", "APACHE")),
    "II": ("Two", ("PIMA", "PINAL", "COCHISE", "SANTA CRUZ", "GREENLEE", "GRAHAM", "GILA")),
}


class _Page(HTMLParser):
    """The page's h2, h3 and h4 headings and paragraphs in order, as (tag, text), and the end of
    each tab as ("tab", ""), leaving out a candidate's folded-away details and the ballot
    measures' tab."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, str]] = []
        self._divs: list[str] = []
        self._open: tuple[str, list[str]] | None = None

    def _hidden(self) -> bool:
        return any("collapse" in div or "candidate-info" in div or div.startswith("tab-content-bm ")
                   for div in self._divs)

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag == "div":
            found = dict(attrs)
            self._divs.append(f"{found.get('id') or ''} {found.get('class') or ''}")
        elif tag in ("h2", "h3", "h4", "p") and not self._hidden():
            self._open = (tag, [])

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._divs:
            if self._divs.pop().startswith("tab-content-"):
                self.items.append(("tab", ""))
        elif self._open is not None and tag == self._open[0]:
            text = " ".join("".join(self._open[1]).split())
            if text:
                self.items.append((tag, text))
            self._open = None

    def handle_data(self, data: str) -> None:
        if self._open is not None:
            self._open[1].append(data)


def _office(heading: str) -> Office | None:
    """The office a heading names; None for one Pallot doesn't place (a proposition). Its seats
    are 0 where they're as many as a party nominated (the Corporation Commission's), and a judge
    standing for retention is a race of their own, under this office's name."""
    if re.match(r"U\.?S\.? Senator", heading, re.I):
        return us_senate("AZ")
    if re.match(r"U\.?S\.? Representative", heading, re.I) and (found := re.search(_DISTRICT, heading, re.I)):
        return us_house("AZ", int(found.group(1)))
    if re.match(r"State Senator", heading, re.I) and (found := re.search(_DISTRICT, heading, re.I)):
        number = int(found.group(1))
        return legislator("sd", number, office=f"State Senator, Legislative District {number}")
    if re.match(r"State Representative", heading, re.I) and (found := re.search(_DISTRICT, heading, re.I)):
        number = int(found.group(1))
        return dataclasses.replace(legislator("hd", number, office=f"State Representative, Legislative District {number}"),
                                   seats=2)
    for office in _STATEWIDE:
        if heading.lower() == office.lower():
            return dataclasses.replace(statewide(office), seats=0)
    if re.match(r"Justice of the (?:Arizona )?Supreme Court", heading, re.I):
        return Office("SUPREME COURT", "Supreme Court Justice", "SUPREME COURT", "judicial", "state", retention=True)
    if (found := re.fullmatch(r"Judge of the Court of Appeals,? Division (I|II)", heading, re.I)) \
            and found.group(1).upper() in _APPEALS:
        word, counties = _APPEALS[found.group(1).upper()]
        return Office(f"COURT OF APPEALS {found.group(1).upper()}", f"Court of Appeals Division {word} Judge",
                      "COURT OF APPEALS", "judicial", "counties", found.group(1).upper(), counties, retention=True)
    return None


def _name(text: str) -> str:
    """ 'FEELY, THOMAS "JAY", IV' -> 'Thomas "Jay" Feely IV'; a name without a comma as it is."""
    last, comma, rest = text.partition(",")
    if not comma:
        words = text.split()
    else:
        given, *suffixes = [part.strip() for part in rest.split(",")]
        words = [*given.split(), *last.split(), *(" ".join(suffixes).split())]
    return " ".join(f'"{display_person(word.strip(chr(34)))}"' if word.startswith('"') else display_person(word)
                    for word in words)


class AzList(ManualList):
    state = "AZ"
    source = "state_az"
    label = "Arizona Secretary of State"
    page = PAGE
    description = ("Arizona's official list of the candidates for Congress, statewide offices, the Legislature and "
                   "the judges standing for retention, from its Secretary of State, imported by hand.")
    folder = "manual/state_az"
    challenge = ("Just a moment...", "challenges.cloudflare.com", "cf-browser-verification")

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        text = raw if isinstance(raw, str) else ""
        reader = _Page()
        reader.feed(text)
        start = next((i for i, (tag, heading) in enumerate(reader.items)
                      if tag == "h2" and "general election" in heading.lower()), None)
        heading = re.search(r"<h2[^>]*>[^<]*General Election[^<]*</h2>", text, re.I)
        found = _DATE.search(" ".join(re.sub(r"<[^>]+>", " ", text[heading.end():]).split())) if heading else None
        if start is None or found is None:
            raise ValueError("no general election's heading with its date")
        day = dt.datetime.strptime(found.group(0), "%B %d, %Y").date().isoformat()
        rows: list[dict[str, Any]] = []
        office: Office | None = None
        for index, (tag, text) in enumerate(reader.items[start + 1:]):
            if tag in ("h2", "h3", "tab"):
                office = _office(text) if tag == "h3" else None
                continue
            if office is None:
                continue
            if office.retention:
                if tag == "p":
                    rows.append({"office": office, "name": display_person(text), "party": None, "order": index})
                continue
            if tag == "h4":
                candidate = _CANDIDATE.fullmatch(text)
                if candidate is None:
                    raise ValueError(f"a candidate without a party under {office.office}: {text!r}")
                rows.append({"office": office, "name": _name(candidate.group("name")), "order": index,
                             "party": candidate.group("party").strip().upper()})
            elif tag == "p" and rows and rows[-1]["office"] is office:
                if text.lower() == "write-in candidate":
                    rows[-1]["write_in"] = True
                elif "withdr" in text.lower():
                    rows[-1]["withdrawn"] = True
        rows = [row for row in rows if not row.get("withdrawn")]
        if not any(row["office"].reach == "cd" for row in rows):
            raise ValueError("no candidates for Congress under the offices' headings")
        nominated = Counter((row["office"].office_id, row["party"]) for row in rows if not row.get("write_in"))
        filings = []
        for row in rows:
            office = row["office"]
            code, party_name = party(row["party"], _PARTY_NAMES)
            seats = office.seats or max([n for (race, _), n in nominated.items() if race == office.office_id] or [1])
            race = dataclasses.replace(office, seats=seats)
            if office.retention:
                race = dataclasses.replace(race, office_id=f"{office.office_id} {row['name'].upper()}",
                                           office=f"Retain {office.office} {row['name']}")
            filings.append(race.filing(
                day=day, name=row["name"], party=code, party_name=party_name, write_in=bool(row.get("write_in")),
                order=row["order"],
            ))
        return filings


GUIDE = Guide(
    name="Arizona",
    source="Arizona Secretary of State",
    url="https://azsos.gov/elections",
    computed=False,
    registration_url="https://my.arizona.vote/",
    mail_url="https://my.arizona.vote/",
    register="The last day to register to vote in {election} in Arizona, by 11:59 p.m.",
    mail_summary="Early ballot request due",
    mail="If you vote early by mail in {election}, ask your county recorder for your ballot in time for it to reach "
         "you and come back by Election Day. Any voter can vote early by mail; how to ask:",
    early_where="Your county recorder lists the places and hours.",
    credit="Dates from the Arizona Secretary of State",
    poll_hours="6 a.m. – 7 p.m.",
    check_url="https://my.arizona.vote/",
    check_hint="Arizona.Vote (Arizona Secretary of State): your registration, your polling place and your ballot's "
               "status",
    where_url="https://my.arizona.vote/",
    where_hint="Arizona.Vote: your polling place; Maricopa and Pima counties also have their own lookups",
    mail_label="How to ask",
    mail_eligibility="Any registered voter can vote early by mail, no reason needed. Early ballots go out from "
                     "October 7; ask your county recorder for yours, or join the Active Early Voting List.",
    local_office="Your county recorder",
)

DATES = {
    dt.date(2026, 11, 3): Deadlines(
        dt.date(2026, 11, 3), "General Election", register_by=dt.date(2026, 10, 5),
        early_start=dt.date(2026, 10, 7), early_end=dt.date(2026, 10, 30), state="AZ",
    ),
}


def arizona(day: dt.date) -> Deadlines | None:
    """The dates of Arizona's statewide election on ``day``, as its Secretary of State lists them."""
    return DATES.get(day)


RULE = arizona
