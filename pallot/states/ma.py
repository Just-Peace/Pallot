"""Massachusetts: the Secretary of the Commonwealth's page of the state election's candidates
(sec.state.ma.us/divisions/elections/research-and-statistics/{year}-state-election-candidates.htm),
saved by hand (manual/state_ma): Imperva turns scripts away from the whole site, browser headers
included, so Pallot never asks it.

The page is a heading per office ("Senator in Congress", "Representative in General Court"), a
subheading per district ("Third District", "Twenty-First Middlesex District") and a paragraph per
candidate: the name (a suffix after a comma: "John Barrett, III"), the street, the town and the
party ("Democratic", "Unenrolled", "Workers Party"), which a few leave out. Only the name, office,
district and party are kept. The Governor's race is one ticket with the Lieutenant Governor, named
by their surnames as the ballot prints them ("Healey and Driscoll"). It's the state election's
list, after the September primaries: no race has two candidates of one party, which the reader
refuses. Its title names the year, so its filings are dated by that year's general election.

Placed: the U.S. Senate, Governor and Lieutenant Governor, the other statewide offices, the U.S.
House (nine districts), the State Senate (40) and the State House (160), whose districts are named
by county, spelt as the Census spells them (census_name: "Twenty-First Middlesex" is "21st
Middlesex", "Cape & Islands" is "Cape and Islands"). The Governor's Council's eight districts, which the Census doesn't know,
the district attorneys, the county offices and Barnstable and Dukes counties' own bodies are left
out with a ballot note. An office it doesn't know is refused, and so is a district that isn't named
by Massachusetts's counties.

Massachusetts's key dates, for its biennial state election (the Tuesday after the first Monday of
November, M.G.L. c.54 §62), checked on malegislature.gov on 2026-10-30: registration closes at 5 p.m.
on the 10th day before, a mailed form postmarked by then counting (c.51 §26), with no registering on
Election Day; any voter can vote early by mail, the application reaching the city or town clerk by
5 p.m. on the 5th business day before (c.54 §25B(a)(2)), the Tuesday before a Tuesday election, so
7 days; early voting in person runs from the 17th day before through the 4th (c.54 §25B(b)(2)(i)),
weekends included; a ballot mailed by Election Day counts if it reaches the clerk by 5 p.m. on the
3rd day after, one in a drop box by the close of the polls (c.54 §93). Polls open by 7 a.m. (a town
may open from 5:45) and close at 8 p.m. (c.54 §64). 2026: register by Sat Oct 24, apply by Tue Oct
27, early voting Oct 17 – 30, a mailed ballot by Fri Nov 6.
"""

from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser
from typing import Any

from . import (_ORDINALS, Filing, ManualList, Office, legislator, ordinal, party, require, statewide, us_house,
               us_senate)
from .dates import Counts, Guide, first_tuesday_after_first_monday

MINIMUM = {"cd": 9, "sd": 35, "hd": 140}  # every seat is up: a few districts can go without a candidate
STATEWIDE = ("Attorney General", "Secretary of State", "Treasurer", "Auditor")
GOVERNOR = Office("GOVERNOR", "Governor and Lieutenant Governor", "GOVERNOR", "state", "state")
LEFT_OUT = ("Councillor", "District Attorney", "Register of", "County ", "Sheriff", "Council of Governments",
            "Martha", "Barnstable ")  # the headings of offices left out
COUNTIES = frozenset({"Barnstable", "Berkshire", "Bristol", "Dukes", "Essex", "Franklin", "Hampden", "Hampshire",
                      "Middlesex", "Nantucket", "Norfolk", "Plymouth", "Suffolk", "Worcester"})
PARTIES = {"DEMO": "Democratic"}  # a party the page cuts short
_YEAR = re.compile(r"<title>\s*(\d{4}) State Election Candidates", re.I)
_TENS = {"TWENTY": 20, "THIRTY": 30}


class _Page(HTMLParser):
    """The (tag, text) of each heading and paragraph in the page's article, in order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, str]] = []
        self._article = False
        self._open: tuple[str, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag == "article":
            self._article = True
        elif self._article and tag in ("h2", "h3", "p") and "top-of-page-link" not in (dict(attrs).get("class") or ""):
            self._open = (tag, [])

    def handle_endtag(self, tag: str) -> None:
        if tag == "article":
            self._article = False
        elif self._open and tag == self._open[0]:
            text = " ".join("".join(self._open[1]).split())
            if text:
                self.items.append((tag, text))
            self._open = None

    def handle_data(self, data: str) -> None:
        if self._open:
            self._open[1].append(data)


def _number(heading: str) -> int:
    """"Twenty-First" -> 21; ValueError for a word that isn't an ordinal."""
    tens, _, unit = heading.upper().rpartition("-")
    found = 30 if unit == "THIRTIETH" and not tens else _ORDINALS.get(unit)
    if found is None or (tens and (tens not in _TENS or found > 9)):
        raise ValueError(f"a district it doesn't know: {heading!r}")
    return _TENS.get(tens, 0) + found


def _congress(heading: str) -> Office:
    words = heading.split()
    if len(words) != 2 or words[1] != "District":
        raise ValueError(f"a district it doesn't know: {heading!r}")
    return us_house("MA", _number(words[0]))


def census_name(reach: str, heading: str) -> str:
    """A State Senate or House district as the Census names it, from the page's heading: "Twenty-
    First Middlesex District" is the House's "21st Middlesex", "First Essex & Middlesex District"
    the Senate's "First Essex and Middlesex", "Barnstable, Dukes & Nantucket District"
    "Barnstable-Dukes-Nantucket". ValueError for one that isn't named by Massachusetts's counties."""
    name = heading.removesuffix(" District")
    first, _, rest = name.partition(" ")
    try:
        number: int | None = _number(first)
    except ValueError:
        number, rest = None, name
    counties = re.split(r", | & ", rest)
    if name == heading or not (rest == "Cape & Islands" or all(county in COUNTIES for county in counties)):
        raise ValueError(f"a district it doesn't know: {heading!r}")
    joined = " and ".join(counties) if len(counties) == 2 else "-".join(counties)
    if number is None:
        return joined
    return f"{ordinal(number) if reach == 'hd' else first} {joined}"


def _legislator(reach: str, heading: str) -> Office:
    title = "State Senator" if reach == "sd" else "State Representative"
    return legislator(reach, census_name(reach, heading), office=f"{title}, {heading}")


def _candidate(text: str) -> tuple[str, str]:
    """A paragraph's (name, party): the parts before the street are the name, the one after the
    town the party; a ticket with no street is "Healey and Driscoll, Democratic"."""
    parts = text.split(", ")
    street = next((at for at, part in enumerate(parts) if part[:1].isdigit()), None)
    if street is None:
        return parts[0], ", ".join(parts[1:])
    return ", ".join(parts[:street]), ", ".join(parts[street + 2:])


def parse_page(text: str) -> list[Filing]:
    """Every candidate on the saved page, dated by the general election of the year in its title;
    ValueError for a page that isn't the list (no year, an office or district it doesn't know, two
    candidates of one party in a race, fewer than MINIMUM's races)."""
    year = _YEAR.search(text)
    if not year:
        raise ValueError("not the state election's candidates page (no \"<year> State Election Candidates\" title)")
    day = first_tuesday_after_first_monday(int(year.group(1)), 11).isoformat()
    page = _Page()
    page.feed(text)
    office: str | None = None
    race: Office | None = None
    found: list[tuple[Office, str, str]] = []
    for tag, line in page.items:
        if tag == "h2":
            office, race = line, None
            if line == "Senator in Congress":
                race = us_senate("MA")
            elif line in ("Governor & Lieutenant Governor", "Governor and Lieutenant Governor"):
                race = GOVERNOR
            elif line in STATEWIDE:
                race = statewide(line)
            elif line not in ("Representative in Congress", "Senator in General Court",
                              "Representative in General Court") and not line.startswith(LEFT_OUT):
                raise ValueError(f"an office it doesn't know: {line}")
        elif tag == "h3":
            if office == "Representative in Congress":
                race = _congress(line)
            elif office in ("Senator in General Court", "Representative in General Court"):
                race = _legislator("sd" if office.startswith("Senator") else "hd", line)
        elif race is not None and line.upper() != "NO NOMINATIONS":
            found.append((race, *_candidate(line)))
    if not found:
        raise ValueError("no candidates")
    filings = []
    for race, name, label in found:
        code, party_name = party(PARTIES.get(label.upper(), label))
        filings.append(race.filing(day=day, name=name, party=code, party_name=party_name, order=len(filings)))
    twice = [key for key, n in Counter((f.office_id, f.party) for f in filings if f.party).items() if n > 1]
    if twice:
        raise ValueError(f"two candidates of one party in {', '.join(sorted(o for o, _ in twice))}: a primary's list")
    return require(filings, MINIMUM)


class MaList(ManualList):
    state = "MA"
    source = "state_ma"
    label = "Massachusetts Secretary of the Commonwealth"
    page = "https://www.sec.state.ma.us/divisions/elections/research-and-statistics/2026-state-election-candidates.htm"
    description = ("Massachusetts's official list of the candidates for Congress, its statewide offices and its "
                   "Legislature, from its Secretary of the Commonwealth, imported by hand.")
    folder = "manual/state_ma"
    challenge = ("Request unsuccessful", "Incapsula incident ID")
    scope_note = ("The Governor's Council, district attorneys, county offices (register of probate, sheriff and the "
                  "like) and the ballot questions aren't shown: your city or town clerk has your sample ballot.")

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, str):
            raise ValueError("not a web page")
        return parse_page(raw)


ELECTIONS = "https://www.sec.state.ma.us/divisions/elections"
GUIDE = Guide(
    name="Massachusetts",
    source="Massachusetts Secretary of the Commonwealth",
    url=f"{ELECTIONS}/elections-and-voting.htm",
    computed=True,
    registration_url="https://www.sec.state.ma.us/ovr/",
    mail_url=f"{ELECTIONS}/voting-information/vote-early.htm",
    register="The last day to register to vote in {election} in Massachusetts: online, in person at your city or "
             "town election office by 5 p.m., or by mail postmarked today. There's no registering on Election Day.",
    mail_summary="Vote-by-mail application due",
    mail="If you vote by mail in {election}, your application must reach your city or town clerk by 5 p.m. today. "
         "Your ballot counts if it's mailed by Election Day and arrives by 5 p.m. on the third day after, or is in "
         "your town's drop box by 8 p.m. on Election Day. Any voter can vote by mail; how to apply:",
    early_where="Your city or town sets its early voting places and hours, weekends included.",
    credit="Dates worked out from Massachusetts's election law; more from the Secretary of the Commonwealth",
    poll_hours="7 a.m. – 8 p.m.",
    check_url="https://www.sec.state.ma.us/VoterRegistrationSearch/MyVoterRegStatus.aspx",
    check_hint="Voter registration status (Secretary of the Commonwealth): whether you're registered, and where",
    where_url="https://www.sec.state.ma.us/WhereDoIVoteMA/bal/MyElectionInfo.aspx",
    where_hint="Where Do I Vote (Secretary of the Commonwealth): your polling place and your early voting sites",
    mail_label="How to vote by mail",
    mail_eligibility="Any registered voter can vote by mail, no reason needed. Your ballot counts if it's mailed by "
                     "Election Day and reaches your city or town clerk by 5 p.m. on the third day after, or if it's in "
                     "your town's drop box by 8 p.m. on Election Day.",
    mail_deadline="Your application must reach your city or town clerk by 5 p.m. on ",
    local_office="Your city or town clerk",
)
RULE = Counts(10, 7, 17, 4).rule("MA")
