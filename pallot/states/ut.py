"""Utah: the Lieutenant Governor's General Election Certification, the list of every candidate and
judge on the general election's ballot, published as a scanned PDF (vote.utah.gov) with no text to
read, so the maintainer copies its text (the cover page's title too, which names the year) into a
text file saved by hand (manual/state_ut); Pallot never fetches it.

It is the general election's ballot, not the primary's: the certification lists the nominees the
law puts on it (Utah Code 20A-5a-209(2)), each party's once, in the order the ballot prints them.
A heading per race ("Utah Senate District 5. Utah Senate District 5 consists of …"), then a
"Candidate Party" line and a line per candidate, the name in capitals and the party's name last.
Then the judges standing for retention ("Shall JILL M. POHLMAN be retained in the office of …?"),
under the Supreme Court and Court of Appeals, each judicial district by its counties, and the
justice courts; then the constitutional amendments and the registered parties. Nothing else: no
addresses, incumbents or write-ins. The scan's text has misreadings ("CHRJS REID"); READ_AS puts
right those checked against the 2026 PDF, and a line it can't read is refused.

Placed: the U.S. House (four districts, on the court-ordered map of 2026, Map 1A, which the Census
geocoder's 120th Congressional Districts already are), the State Senate (about half its 29
districts), the State House (all 75), and the judges standing for retention: the Supreme Court and
the Court of Appeals statewide, the district and juvenile courts' in their judicial district's
counties (JUDICIAL). The State Board of Education's districts aren't the Legislature's or the
Census's, and the justice courts' are towns' and counties' own, so both are left out with a ballot
note, as are the amendments. A line it doesn't know is refused.

Utah's key dates, for its general election (the first Tuesday after the first Monday of November
in an even year, Utah Code 20A-1-201), checked on 2026-10-30 against the Utah Code (le.utah.gov):
registering online, by mail or at the county clerk's office closes at 5 p.m. 11 days before
(20A-2-102.5(2)(a)); after that, a voter registers and votes in person with a provisional ballot
during early voting or on Election Day (20A-2-102.5(2)(b)-(c), 20A-2-207). Every active voter is
mailed a ballot 21 to 7 days before (20A-3a-202(2)(a)), which must reach the county clerk by 8 p.m.
on Election Day, by mail or in a drop box: a postmark no longer counts (20A-3a-204(3), since May
2025). Early voting in person runs from 14 days before through the Friday before (20A-3a-601(2));
a clerk may extend it to the Monday. Polls are open 7 a.m. to 8 p.m. 2026: register by Oct 23,
early voting Oct 20 – Oct 30, ballots back by 8 p.m. Nov 3.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from ..text import display_person
from . import Filing, ManualList, Office, legislator, party, require, us_house
from .dates import Counts, Guide, first_tuesday_after_first_monday, mailed_to_every_voter

MINIMUM = {"cd": 4, "hd": 75}
PARTIES = ("Democratic", "Republican", "Libertarian", "Constitution", "Forward", "Green", "Independent American",
           "Peoples' Freedom", "Unaffiliated")
PARTY_NAMES = {"CONSTITUTION": "Constitution Party", "FORWARD": "Forward Party",
               "INDEPENDENT AMERICAN": "Independent American Party", "PEOPLES' FREEDOM": "Peoples' Freedom Party"}
# The judicial districts' counties, as the certification gives them (Utah Code 78A-1-102 for the Eighth).
JUDICIAL = {
    1: ("BOX ELDER", "CACHE", "RICH"), 2: ("DAVIS", "MORGAN", "WEBER"), 3: ("SALT LAKE", "SUMMIT", "TOOELE"),
    4: ("JUAB", "MILLARD", "UTAH", "WASATCH"), 5: ("BEAVER", "IRON", "WASHINGTON"),
    6: ("GARFIELD", "KANE", "PIUTE", "SANPETE", "SEVIER", "WAYNE"), 7: ("CARBON", "EMERY", "GRAND", "SAN JUAN"),
    8: ("DAGGETT", "DUCHESNE", "UINTAH"),
}
NUMBERS = ("FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH", "EIGHTH")
# The scan's misreadings of names, checked against the 2026 certification's PDF.
READ_AS = {
    "ADONIS HOOSL YN": "ADONIS HOOSLYN", "A, DANE ANDERSON": "A. DANE ANDERSON",
    "RICHARDS ROBILLARD": "RICHARD S ROBILLARD", "CHRJS REID": "CHRIS REID",
    "BARBARAJ.HAGGERTY": "BARBARA J. HAGGERTY", "JASONB KYLE": "JASON B KYLE", "RICHARDT NOWAK": "RICHARD T NOWAK",
    "MICHAELE FINCH": "MICHAEL E FINCH", "TYNLEYBEAN": "TYNLEY BEAN", "SAHARA HA YES": "SAHARA HAYES",
    "JESS BLRTCHER": "JESS BIRTCHER", "CANDICE B. PJERUCCI": "CANDICE B. PIERUCCI", "VALL. PETERSON": "VAL L. PETERSON",
    "KARL! BLACK": "KARLI BLACK", "SCOTTHCHEW": "SCOTT H CHEW", "EVA MWELDON": "EVA M WELDON",
    "APRJL A PINKSTON": "APRIL A PINKSTON", "GLENNDWEBB": "GLENN D WEBB",
}
_TITLE = re.compile(r"(\d{4}) GENERAL ELECTION CERTIFICATION", re.I)
_RACE = re.compile(r"(U\.S\. House of Representatives|Utah Senate|Utah House\s*of\s*Rep\S*|Utah State Board of Education)"
                   r"\s+Dis\S*\s+(\d+)\.", re.I)
_COLUMNS = re.compile(r"Ca\w+(?:\s+Party)?", re.I)
_CANDIDATE = re.compile(rf"(.+?)\s+({'|'.join(re.escape(p) for p in PARTIES)})", re.I)
_COURTS = re.compile(rf"({'|'.join(n.title() for n in NUMBERS)}) Judicial District\.|(Supreme Court and Court of "
                     r"Appeals)\.|(Justice Courts)\.", re.I)
_RETAIN = re.compile(r"Shall (.+?) be retained in the office of (.+?)\?", re.I)
SECTIONS = ("FEDERAL OFFICE", "STATE SENATOR", "STATE REPRESENTATIVE", "STATE BOARD OF EDUCATION MEMBER",
            "NON-PARTISAN JUDICIAL RETENTION ELECTIONS")
END = "PROPOSED CONSTITUTIONAL AMENDMENTS"


def _word(word: str) -> str:
    """A name's word in mixed case; a nickname's initials in quotes kept: "\"CJ\"" stays."""
    if word.startswith('"'):
        bare = word.strip('"')
        return f'"{bare}"' if len(bare) <= 2 else f'"{display_person(bare)}"'
    return display_person(word)


def _name(text: str) -> str:
    """A name as the ballot prints it, in mixed case, its misreading put right (READ_AS)."""
    upper = " ".join(text.split()).upper()
    return " ".join(_word(word) for word in READ_AS.get(upper, upper).split())


def _race(kind: str, number: int) -> Office | None:
    """A heading's race; None for the State Board of Education's, left out."""
    kind = kind.upper()
    if kind.startswith("U.S."):
        return us_house("UT", number)
    if kind == "UTAH SENATE":
        return legislator("sd", number)
    if kind.startswith("UTAH HOUSE"):
        return legislator("hd", number)
    return None


def _retained(name: str, office: str, district: int | None) -> Office:
    """A judge's retention race: statewide for the Supreme Court and Court of Appeals, else their
    judicial district's counties. ValueError for an office it doesn't know."""
    title = office.upper()
    key = name.upper()
    if "SUPREME COURT" in title:
        return Office(f"SUPREME COURT {key}", f"Retain Supreme Court Justice {name}", "SUPREME COURT", "judicial",
                      "state", incumbent=True, retention=True)
    if "COURT OF APPEALS" in title:
        return Office(f"COURT OF APPEALS {key}", f"Retain Court of Appeals Judge {name}", "COURT OF APPEALS",
                      "judicial", "state", incumbent=True, retention=True)
    if district is None:
        raise ValueError(f"a judge with no judicial district: {name}")
    where = NUMBERS[district - 1].title()
    family = "JUVENILE COURT" if "JUVENILE" in title else "DISTRICT COURT" if "DISTRICT" in title else None
    if family is None:
        raise ValueError(f"an office it doesn't know: {office}")
    court = f"{where} District Juvenile Court" if family == "JUVENILE COURT" else f"{where} District Court"
    places = JUDICIAL[district]
    return Office(f"{family} {district} {key}", f"Retain {court} Judge {name}", family, "judicial",
                  "counties" if len(places) > 1 else "county", str(district), counties=places, incumbent=True,
                  retention=True)


def candidates(text: str) -> list[Filing]:
    """Every candidate and judge the certification places, in its order; ValueError for a file that
    isn't it (no year in its title), a line it can't read, two candidates of one party in a race,
    or fewer than MINIMUM's races."""
    title = _TITLE.search(text)
    if title is None:
        raise ValueError("not the general election certification: no year in its title")
    day = first_tuesday_after_first_monday(int(title.group(1)), 11).isoformat()
    lines = [" ".join(line.split()) for line in text.splitlines()]
    filings: list[Filing] = []
    race: Office | None = None
    taking = justice = judicial = False
    district: int | None = None
    question = ""
    for line in lines:
        if line.upper() == END:
            break
        if not line:
            continue
        if line.upper() in SECTIONS:
            judicial = line.upper() == SECTIONS[-1]
            race, taking = None, False
            continue
        if judicial:
            if court := _COURTS.match(line):
                district = NUMBERS.index(court.group(1).upper()) + 1 if court.group(1) else None
                justice = bool(court.group(3))
                continue
            if justice:
                continue
            if line.startswith("Shall") or question:
                question = f"{question} {line}".strip()
                if found := _RETAIN.search(question):
                    name = _name(found.group(1))
                    filings.append(_retained(name, found.group(2), district).filing(
                        day=day, name=name, order=len(filings)))
                    question = ""
            continue
        if heading := _RACE.match(line):
            race, taking = _race(heading.group(1), int(heading.group(2))), False
            continue
        if not taking:
            taking = bool(_COLUMNS.fullmatch(line))
            continue
        found = _CANDIDATE.fullmatch(line)
        if found is None:
            raise ValueError(f"a line it can't read: {line!r}")
        if race is None:
            continue
        code, party_name = party(found.group(2), PARTY_NAMES)
        filings.append(race.filing(day=day, name=_name(found.group(1)), party=code, party_name=party_name,
                                   order=len(filings)))
    if not filings:
        raise ValueError("no candidates")
    labels = Counter((f.office_id, f.party or f.party_name) for f in filings if f.party or f.party_name)
    if twice := sorted({office_id for (office_id, _), n in labels.items() if n > 1}):
        raise ValueError(f"two candidates of one party in {', '.join(twice)}: a primary's list")
    return require(filings, MINIMUM)


class UtList(ManualList):
    state = "UT"
    source = "state_ut"
    label = "Utah Lieutenant Governor's Office"
    page = "https://vote.utah.gov/"
    description = ("Utah's official list of the candidates for Congress and its Legislature, and the judges standing "
                   "for retention, from its Lieutenant Governor's Office, imported by hand.")
    folder = "manual/state_ut"
    scope_note = ("The State Board of Education, the justice court judges, county and city races and the "
                  "constitutional amendments aren't shown: the ballot mailed to you has them.")

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, str):
            raise ValueError("not a text file")
        return candidates(raw)


SITE = "https://vote.utah.gov/"
PORTAL = "https://vote.utah.gov/voter-registration-portal/"
GUIDE = Guide(
    name="Utah",
    source="Utah Lieutenant Governor's Office",
    url=SITE,
    computed=True,
    registration_url=PORTAL,
    mail_url="https://vote.utah.gov/track-my-ballot/",
    register="The last day to register to vote in {election} in Utah, by 5 p.m., online, by mail or at your county "
             "clerk's office. After it, you can still register and vote in person during early voting or on Election "
             "Day, with ID and proof of where you live.",
    mail_summary="Ballots are mailed",
    mail="Every active voter in Utah is mailed a ballot for {election}. Your county clerk must have it back by 8 p.m. on "
         "Election Day, by mail or in a drop box; a postmark doesn't count. Track yours:",
    early_where="Early voting in person is on weekdays through the Friday before Election Day; your county clerk lists "
                "the places and hours, and may add days.",
    credit="Dates worked out from Utah's election law; more from the Utah Lieutenant Governor's Office",
    poll_hours="7 a.m. – 8 p.m.",
    check_url=PORTAL,
    check_hint="Utah's voter registration portal (Lieutenant Governor's Office): your registration",
    where_url="https://votesearch.utah.gov/voter-search/search/search-by-address/how-and-where-can-i-vote",
    where_hint="Utah Vote Search: your vote centers, drop boxes and early voting places",
    mail_label="Track your ballot",
    mail_eligibility=mailed_to_every_voter("It goes out 7 to 21 days before Election Day. Mail it back or put it in a "
                                           "drop box: it must reach your county clerk by 8 p.m. on Election Day, and a "
                                           "postmark doesn't count."),
    local_office="Your county clerk",
    late_registration="After that, register and vote in person during early voting or on Election Day, with ID and "
                      "proof of where you live",
)
RULE = Counts(11, None, 14, 4).rule("UT")  # every voter is mailed a ballot; early voting ends the Friday before
