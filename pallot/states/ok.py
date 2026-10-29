"""Oklahoma: the State Election Board's list of elections (hosting.okelections.gov/electionlist.html),
one static HTML page for the next election day ("NOVEMBER / 2026 List of Elections"), county by
county: under each county's heading, its sections ("STATE OFFICERS", "CONGRESSIONAL OFFICERS",
"LEGISLATIVE, DISTRICT AND COUNTY OFFICERS", "JUDICIAL OFFICERS", "JUDICIAL RETENTION", "STATE
QUESTIONS", then each city's, town's or district's own), each office's heading and its candidates,
one a line ("MIKE MAZZEI, REPUBLICAN"; a judge's or a city's without a party). A plain script gets a
200. Its filings portal (filings.okelections.gov) answers 403 to scripts, so it isn't read.

A race comes under every county it reaches, so it's read once, with those counties: a district
judge's office, or a district attorney's, is placed by them. The page has only the races on the
ballot: a candidate with no opponent is elected without one, so most State House and Senate seats
aren't on it. It has no withdrawn candidates, write-ins (Oklahoma has none), incumbents, contact
details or ballot order (its candidates are shown in its order). The judges standing for retention
are named only by their seat ("SUPREME COURT DISTRICT 1"), so they aren't read, nor are the state
questions; the cache and the bundle keep its filings alone. A page for an election that isn't a
general election (the next one is a city's or school's) reads as no list yet.

Placed: Congress, the statewide offices (Governor and Lieutenant Governor elected apart), the State
House (all 101 districts up every even year) and the State Senate (the 24 even-numbered districts
in 2026, the 24 odd ones in 2028), the district judges and district attorneys by the counties the
list puts them under, and each county's associate district judge and its countywide officers
(assessor, treasurer, sheriff and the like). A county commissioner's district is part of a county,
so it's on the ballot only maybe. The President, the city, town, school and fire district races and
the county and city questions are left out; an office it doesn't know is counted but not placed.

Oklahoma's key dates, for its general election on the first Tuesday after the first Monday in
November of every even year (26 O.S. §1-101), checked against the State Election Board's 2026
Voter Information Calendar and 2026 Statutory Election Dates and Deadlines on 2026-10-29: a
registration application received, postmarked or submitted online 24 or fewer days before isn't
approved for the election (26 O.S. §4-110.1(A)), so the last day to register is the 25th day before,
always a Friday. An absentee ballot request must be received by 5 p.m. on the third Monday before,
the 15th day (§14-103), and any voter can ask, no reason needed; the affidavit is signed before a
notary, free of charge (§14-108(A)), and the ballot must reach the county election board by 7 p.m.
on Election Day, or by the end of business hours the day before when hand-delivered, with proof of
identity (§14-104, §14-108(C)). In-person absentee (early) voting, at the county election board's
places, runs 8 a.m. to 6 p.m. on the Wednesday, Thursday and Friday before a general election and
8 a.m. to 2 p.m. on the Saturday (§14-115.4(A)(1)). Polls are open 7 a.m. to 7 p.m. (§7-104(A)).
2026: Oct 9, Oct 19, Oct 28 - Oct 31.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import html
import re
from typing import Any

from .. import counties
from ..http_cache import RequestSpec
from ..text import display_office, display_person
from . import (
    SUFFIXES, Filing, Office, StateList, decoded, filings_json, from_json, legislator, party, require, statewide, us_house,
    us_senate,
)
from .dates import Counts, Guide, first_tuesday_after_first_monday

SITE = "https://hosting.okelections.gov"
PAGE = f"{SITE}/electionlist.html"
MINIMUM = {"cd": 3, "hd": 20}  # only the contested races are on it: 5 and 55 in 2026
STATE, FEDERAL, DISTRICT, JUDICIAL = ("STATE OFFICERS", "CONGRESSIONAL OFFICERS",
                                      "LEGISLATIVE, DISTRICT AND COUNTY OFFICERS", "JUDICIAL OFFICERS")
PARTIES = {"REPUBLICAN", "DEMOCRAT", "DEMOCRATIC", "LIBERTARIAN", "INDEPENDENT", "GREEN"}
_TITLE = re.compile(r"<title>\s*([A-Z]+)\s*/\s*(\d{4})\s+List of Elections", re.I)
_PART = re.compile(r"""<font\s+size=["']?([345])["']?\s*>(.*?)</font>|<td\s+width=["']?970["']?\s*>(.*?)</td>""",
                   re.I | re.S)
_UNEXPIRED = re.compile(r"\s*\(Unexpired Term\)$", re.I)
_DISTRICTED = re.compile(r"(UNITED STATES REPRESENTATIVE|STATE SENATOR|STATE REPRESENTATIVE) - DISTRICT (\d+)")
_DISTRICT_JUDGE = re.compile(r"DISTRICT JUDGE - DISTRICT (\d+), OFFICE (\d+)")
_ASSOCIATE = re.compile(r"ASSOCIATE DISTRICT JUDGE - (.+) COUNTY")
_ATTORNEY = re.compile(r"DISTRICT ATTORNEY - DISTRICT (\d+)")
_COMMISSIONER = re.compile(r"COUNTY COMMISSIONER DISTRICT NO\. (\d+)")
_MIXED = re.compile(r"^([A-Z][a-z]+)([A-Z'][A-Z'-]+)$")  # "LaFLEUR", "McCLENDON", "MacINTYRE"


def _text(part: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", part)).split())


def _county(name: str) -> str:
    """A county as the Census names it, in capitals: "LEFLORE" is "LE FLORE"."""
    found = counties.find("OK", name)
    return found.name.upper() if found else name


def _county_name(upper: str) -> str:
    """"MCCURTAIN" -> "McCurtain County", as the Census names it."""
    found = counties.find("OK", upper)
    return found.full_name if found else f"{upper.title()} County"


def _capitalized(name: str) -> str:
    """A name in capitals as the ballot prints it: "T. W. SHANNON" is "T. W. Shannon", "MICHELLE LaFLEUR"
    "Michelle LaFleur"."""
    def word(text: str) -> str:
        if text.isupper() or not any(c.isalpha() for c in text):
            return display_person(text)
        mixed = _MIXED.match(text)
        return mixed.group(1) + display_person(mixed.group(2)) if mixed else text

    return " ".join(word(part) for part in name.split())


def election(text: str) -> str:
    """The general election the page is for, as its ISO date; "" for another election. ValueError
    for a page that isn't the list of elections."""
    title = _TITLE.search(text)
    if title is None:
        raise ValueError("not the State Election Board's list of elections")
    year = int(title.group(2))
    if title.group(1).upper() != "NOVEMBER" or year % 2:
        return ""
    return first_tuesday_after_first_monday(year, 11).isoformat()


def _race(section: str, title: str, county: str) -> Office | None:
    """The race of an office's heading in a county's section; None for one left out. ValueError
    for a federal office it doesn't know. A district judge's and district attorney's counties are
    added as the list names them (candidates)."""
    unexpired = bool(_UNEXPIRED.search(title))
    upper = _UNEXPIRED.sub("", title).upper()
    race = _office(section, upper, county)
    if race is None or not unexpired:
        return race
    return dataclasses.replace(race, office_id=f"{race.office_id} UNEXPIRED", unexpired=True)


def _office(section: str, upper: str, county: str) -> Office | None:
    if section == STATE:
        return statewide(display_office(upper), upper)
    if section == FEDERAL:
        if upper == "UNITED STATES SENATOR":
            return us_senate("OK")
        found = _DISTRICTED.fullmatch(upper)
        if found and found.group(1) == "UNITED STATES REPRESENTATIVE":
            return us_house("OK", int(found.group(2)))
        raise ValueError(f"a federal office it doesn't know: {upper}")
    if section == DISTRICT:
        if found := _DISTRICTED.fullmatch(upper):
            return legislator("sd" if found.group(1) == "STATE SENATOR" else "hd", int(found.group(2)))
        if found := _COMMISSIONER.fullmatch(upper):
            return Office(f"COUNTY COMMISSIONER {county} {found.group(1)}",
                          f"{_county_name(county)} Commissioner, District {found.group(1)}", "COUNTY COMMISSIONER",
                          "county", "part_county", found.group(1), counties=(county,))
        if found := _ATTORNEY.fullmatch(upper):
            return Office(f"DISTRICT ATTORNEY {found.group(1)}", f"District Attorney, District {found.group(1)}",
                          "DISTRICT ATTORNEY", "judicial", "counties", found.group(1))
        if upper.startswith("COUNTY ") or upper in ("COURT CLERK",):
            office = display_office(upper.removeprefix("COUNTY "))
            return Office(f"{upper} {county}", f"{_county_name(county)} {office}", upper, "county", "county",
                          counties=(county,))
        return Office(f"{upper} {county}", display_office(upper), upper, "county", "unplaced")
    if section == JUDICIAL:
        if found := _DISTRICT_JUDGE.fullmatch(upper):
            district, seat = found.groups()
            return Office(f"DISTRICT JUDGE {district} {seat}", f"District Judge, District {district}, Office {seat}",
                          "DISTRICT JUDGE", "judicial", "counties", district)
        if found := _ASSOCIATE.fullmatch(upper):
            place = _county(found.group(1))
            return Office(f"ASSOCIATE DISTRICT JUDGE {place}", f"{_county_name(place)} Associate District Judge",
                          "ASSOCIATE DISTRICT JUDGE", "judicial", "county", counties=(place,))
        return Office(f"{upper} {county}", display_office(upper), upper, "judicial", "unplaced")
    return None


def _candidate(line: str, partisan: bool) -> tuple[str, str | None, str | None]:
    """A candidate's line: (name, party code, party name); a party only in a partisan race."""
    name, comma, label = line.rpartition(", ")
    if not comma or not (label.upper() in PARTIES or partisan and label.isupper() and label not in SUFFIXES):
        return _capitalized(line), None, None
    code, party_name = party(label.title())
    return _capitalized(name), code, party_name


def candidates(text: str) -> tuple[str, list[Filing]]:
    """The general election the page is for (election) and every candidate it places, by race in
    the page's order, each race once with the counties it comes under; ("", []) for another
    election. ValueError for a page that isn't the list, a candidate outside an office, or a list
    short of its races (MINIMUM)."""
    day = election(text)
    if not day:
        return "", []
    races: dict[str, Office] = {}
    named: dict[str, list[tuple[str, str | None, str | None]]] = {}
    county = section = ""
    race: Office | None = None
    first = False
    for size, heading, line in _PART.findall(text):
        if line:
            if section in (STATE, FEDERAL, DISTRICT, JUDICIAL) and race is None:
                raise ValueError(f"a candidate outside an office: {_text(line)}")
            if race is not None and first:
                named[race.office_id].append(_candidate(_text(line), race.group != "judicial"))
            continue
        title = _text(heading)
        if size == "5":
            county, section, race = _county(title), "", None
        elif size == "4":
            section, race = title.upper(), None
        else:
            race = _race(section, title, county)
            if race is None:
                continue
            first = race.office_id not in races
            if first:
                races[race.office_id], named[race.office_id] = race, []
            if race.reach == "counties" and county not in races[race.office_id].counties:
                kept = races[race.office_id]
                races[race.office_id] = dataclasses.replace(kept, counties=tuple(sorted((*kept.counties, county))))
    filings = [races[office_id].filing(day=day, name=name, party=code, party_name=party_name, order=start * 100 + index)
               for start, office_id in enumerate(races)
               for index, (name, code, party_name) in enumerate(named[office_id])]
    return day, require(filings, MINIMUM)


def page(text: str) -> dict[str, Any]:
    """The page as kept: the general election it's for (none for another election) and its filings alone."""
    day, filings = candidates(text)
    return {"elections": [day] if day else [], **filings_json(filings)}


class OkList(StateList):
    state = "OK"
    source = "state_ok"
    label = "Oklahoma State Election Board"
    page = PAGE
    description = ("Oklahoma's official list of the candidates for Congress, its statewide offices, the Legislature, "
                   "the district courts and its county offices, from its State Election Board.")
    max_bytes = 16 << 20
    index_key = "elections"  # the page names its election, and is the list too
    scope_note = ("Only the races with more than one candidate are on Oklahoma's ballot: a candidate with no opponent "
                  "is elected without a vote. The judges standing for retention, the state questions and city, town "
                  "and school races aren't shown: your sample ballot on the OK Voter Portal has them.")

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", PAGE)

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        return page(decoded(raw))

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        return []

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        return from_json(page(decoded(raw) if isinstance(raw, bytes) else raw if isinstance(raw, str) else ""))


ELECTIONS = "https://oklahoma.gov/elections"
PORTAL = "https://okvoterportal.okelections.us"
GUIDE = Guide(
    name="Oklahoma",
    source="Oklahoma State Election Board",
    url=f"{ELECTIONS}.html",
    computed=True,
    registration_url=f"{ELECTIONS}/voter-registration/register-to-vote.html",
    mail_url=f"{ELECTIONS}/voters/absentee-voting.html",
    register="The last day to register to vote in {election} in Oklahoma: online on the OK Voter Portal, or by mail "
             "postmarked today, or delivered to your county election board. There's no registering after it.",
    mail_summary="Absentee ballot request due",
    mail="If you vote absentee in {election}, your request must reach your county election board by 5 p.m. today. Your "
         "ballot must reach it by 7 p.m. on Election Day. How to ask:",
    early_where="Your county election board's early voting place (a big county can have more than one): any voter can "
                "vote early there, no reason needed, 8 a.m. to 6 p.m. on the Wednesday, Thursday and Friday before "
                "Election Day, and 8 a.m. to 2 p.m. on the Saturday. Vote in the county you're registered in.",
    credit="Dates worked out from Oklahoma's election law; more from the Oklahoma State Election Board",
    poll_hours="7 a.m. – 7 p.m.",
    check_url=f"{PORTAL}/",
    check_hint="The OK Voter Portal (State Election Board): your registration, your absentee ballot and your sample ballot",
    where_url=f"{PORTAL}/",
    where_hint="The OK Voter Portal: your polling place and your county's early voting place",
    mail_label="How to ask",
    mail_eligibility="Any registered voter can vote absentee, no reason needed. Sign the affidavit with your ballot "
                     "before a notary public, free of charge. Your ballot must reach your county election board by "
                     "7 p.m. on Election Day; brought by hand, by the end of its business hours the day before, with "
                     "your ID.",
    mail_deadline="Your request must reach your county election board by 5 p.m. on ",
    local_office="Your county election board",
)
RULE = Counts(25, 15, 6, 3).rule("OK")
