"""Maryland: the State Board of Elections' list of the general election's state candidates, a CSV
(``2026_GG_statewide_candidatelist.csv``), linked from the year's general candidate listings page
(``elections/2026/general_candidates/index.html``) under a name with the election's kind ("GG" for a
gubernatorial general), so it's found by its link on that page, never by a name worked out ahead.
A year's page not made yet answers 200 with the board's "Page Not Found" page. A plain script gets a
200 from both.

The CSV has a row per candidate who filed: the office ("Governor / Lt. Governor", "House of
Delegates"), the district it's run by ("State Of Maryland", "Congressional District 6",
"Legislative District 1A", "Judicial Circuit 7", "Appellate Circuit 4"), the name in two parts, the
party ("Unaffiliated", "Judicial" or "Other Candidates" for none), the status (only "Active" is on
the ballot; "Withdrawn - 09/21/2026", "Declined - …", "Failed to Submit Required Number of
Signatures - …" aren't), the filing type and date ("Write-In - 01/14/2026" for a declared write-in),
and the running mate, a Governor's Lieutenant Governor, in the related candidate's columns. It has no
incumbents and no election date: the election is the general of the year of its latest filing. It
also has the candidates' addresses, phones and emails; the file is streamed to disk and kept as its
filings, so the cache and the bundle hold nothing else.

Placed: Congress, Governor and Lieutenant Governor (one ticket), Comptroller, Attorney General, the
State Senate and House of Delegates, and the appellate judges standing for retention ("continuance
in office"), each a yes-or-no race: the Appellate Court's at-large judges statewide, and the Supreme
Court's justices and the Appellate Court's circuit judges in their appellate judicial circuit's
counties (Md. Const. Art. IV §14; the circuits as the Maryland Judiciary lists them). The 2nd and
6th circuits are Baltimore County's and Baltimore City's, which the Census names alike
("Baltimore"), so they're left out. The House of Delegates has three delegates in each of the 47
legislative districts, some elected in subdistricts (1A, 1B…) the Census names the same way: a
district has three seats, a subdistrict one, or two where the 2022 Legislative Districting Plan
gives it two (TWO_SEATS). The circuit court's judges are elected in their county for as many seats
as are open, which the list doesn't say, so they're left out with the county offices and school
boards (the board's list of local offices) and the orphans' courts.

Maryland's key dates, for its general election (the Tuesday after the first Monday in November of an
even year, Md. Const. Art. XV §7, EL §8-301), checked against the State Board of Elections' 2026
Election Calendar on 2026-10-29: registration closes on the 21st day before (EL §3-302(a)), and after
it a voter can register and vote the same day at an early voting center or at their polling place on
Election Day with proof of residence (EL §3-305, §3-306); any voter can vote by mail (EL §9-301),
asking by the Tuesday before Election Day for a ballot sent by mail or fax, or by the Friday before
for one sent online (EL §9-305(b), (d)), or in person at the local board through Election Day; the
ballot counts if it reaches the local board by 8 p.m. on Election Day, or if it's postmarked by
then and reaches the board by 10 a.m. on the second Friday after (COMAR 33.11.03.08B). Early voting
runs from the second Thursday before Election Day through the Thursday before, 7 a.m. to 8 p.m. (EL
§10-301.1). Polls are open 7 a.m. to 8 p.m. (EL §10-301).
"""

from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import html
import io
import re
from typing import Any

from ..http_cache import RequestSpec
from . import Filing, Office, StateList, decoded, legislator, party, require, statewide, us_house
from .dates import Counts, Guide, first_tuesday_after_first_monday

BASE = "https://elections.maryland.gov/elections"
PAGE = f"{BASE}/{{year}}/general_candidates/index.html"
COLUMNS = ("Office Name", "Contest Run By District Name and Number", "Candidate Ballot Last Name and Suffix",
           "Candidate First Name and Middle Name", "Office Political Party", "Candidate Status",
           "Filing Type and Date", "Related Candidate Last Name and Suffix",
           "Related Candidate First Name and Middle Name", "Related Candidate Status")
MINIMUM = {"cd": 8, "sd": 45, "hd": 68}  # nearly every district up: one can go without a candidate
TWO_SEATS = frozenset({"2A", "7A", "9A", "11B", "12A", "30A", "34A", "35A", "37B", "43A", "44B", "47A"})
APPELLATE = {  # each appellate judicial circuit's counties, but Baltimore's (the 2nd and 6th)
    1: ("CAROLINE", "CECIL", "DORCHESTER", "KENT", "QUEEN ANNE'S", "SOMERSET", "TALBOT", "WICOMICO", "WORCESTER"),
    3: ("ALLEGANY", "CARROLL", "FREDERICK", "GARRETT", "HOWARD", "WASHINGTON"),
    4: ("PRINCE GEORGE'S",),
    5: ("ANNE ARUNDEL", "CALVERT", "CHARLES", "ST. MARY'S"),
    7: ("MONTGOMERY",),
}
STATEWIDE = {"COMPTROLLER": "Comptroller", "ATTORNEY GENERAL": "Attorney General"}
COURTS = {"JUSTICE SUPREME COURT OF MARYLAND": ("Supreme Court of Maryland", "Justice"),
          "JUDGE APPELLATE COURT OF MARYLAND": ("Appellate Court of Maryland", "Judge")}
_TITLE = re.compile(r"<title>([^<]*)</title>", re.I)
_HEADING = re.compile(r"<h1>\s*\d{4} \w+ General Candidate Listings\s*</h1>", re.I)
_LINK = re.compile(r"""href=["']?((\d{4})_[A-Z]+_statewide_candidatelist)\.html""", re.I)
_DISTRICT = re.compile(r"(Congressional|Legislative) District (\d+)([A-C]?)", re.I)
_CIRCUIT = re.compile(r"Appellate Circuit (\d+)", re.I)
_DATE = re.compile(r"\d{2}/\d{2}/(\d{4})")
_NO_PARTY = {"JUDICIAL", "OTHER CANDIDATES"}


def links(text: str) -> dict[str, Any]:
    """The year's general candidate listings page as kept: its link to the statewide list's CSV, by
    year; none for the board's "Page Not Found" page (a year it hasn't made yet). ValueError for a
    page that's neither."""
    title = _TITLE.search(text)
    if title and "Page Not Found" in title.group(1):
        return {"links": {}}
    if not _HEADING.search(text):
        raise ValueError("not the State Board of Elections' general candidate listings")
    found: dict[str, str] = {}
    for name, year in _LINK.findall(text):
        found.setdefault(year, f"{BASE}/{year}/general_candidates/{html.unescape(name)}.csv")
    return {"links": found}


def seats(district: str) -> int:
    """A House of Delegates district's delegates: three, or a subdistrict's one or two."""
    return 3 if district.isdigit() else 2 if district in TWO_SEATS else 1


def _name(first: str, last: str) -> str:
    """"Joseph C." and "Ruddy, III" -> "Joseph C. Ruddy III"."""
    return " ".join(f"{first} {last.replace(',', ' ')}".split())


def _race(office: str, district: str) -> Office | None:
    """The race of a row's office and district; None for one left out. ValueError for an office it
    doesn't know, or a district it can't read."""
    upper = " ".join(office.upper().split())
    if upper == "JUDGE OF THE CIRCUIT COURT":
        return None
    if upper == "GOVERNOR / LT. GOVERNOR":
        return statewide("Governor and Lieutenant Governor", "GOVERNOR")
    if upper in STATEWIDE:
        return statewide(STATEWIDE[upper])
    if upper in ("REPRESENTATIVE IN CONGRESS", "STATE SENATOR", "HOUSE OF DELEGATES"):
        found = _DISTRICT.fullmatch(district.strip())
        if not found or (found.group(1).upper() == "CONGRESSIONAL") != (upper == "REPRESENTATIVE IN CONGRESS"):
            raise ValueError(f"a district it can't read: {office}, {district}")
        number, letter = int(found.group(2)), found.group(3).upper()
        if upper == "REPRESENTATIVE IN CONGRESS":
            return us_house("MD", number)
        if upper == "STATE SENATOR":
            return legislator("sd", number)
        code = f"{number}{letter}"
        race = legislator("hd", code, office=f"House of Delegates District {code}")
        return dataclasses.replace(race, seats=seats(code))
    court = next((key for key in COURTS if upper.startswith(key)), None)
    if court is None:
        raise ValueError(f"an office it doesn't know: {office}")
    return _court(court, district)


def _court(court: str, district: str) -> Office | None:
    """An appellate court's retention race, before the judge's name is added to it (parse_text);
    None for one in Baltimore's circuits."""
    name, _title = COURTS[court]
    family = name.upper()
    if district.strip().upper() == "STATE OF MARYLAND":
        return Office(family, name, family, "judicial", "state", incumbent=True, retention=True)
    found = _CIRCUIT.fullmatch(district.strip())
    if not found:
        raise ValueError(f"a circuit it can't read: {district}")
    number = int(found.group(1))
    if number in (2, 6):
        return None
    if number not in APPELLATE:
        raise ValueError(f"a circuit it doesn't know: {district}")
    return Office(f"{family} {number}", name, family, "judicial", "counties", str(number), counties=APPELLATE[number],
                  incumbent=True, retention=True)


def parse_text(text: str) -> list[Filing]:
    """Every active candidate the list places, a Governor's ticket as one; ValueError for a file
    that isn't the list (its columns, an office it doesn't know, a row without a name, no filing
    dates) or isn't all of it (MINIMUM: Congress in any year, the Legislature in a Governor's)."""
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or ())]
    if missing:
        raise ValueError(f"not the list of general election candidates: no {', '.join(missing)} column")
    rows = list(reader)
    years = [int(found.group(1)) for row in rows if (found := _DATE.search(row["Filing Type and Date"] or ""))]
    if not years:
        raise ValueError("not the list of general election candidates: no filing dates")
    year = max(years)
    day = first_tuesday_after_first_monday(year, 11).isoformat()
    filings = []
    for index, row in enumerate(rows):
        if (row["Candidate Status"] or "").strip().upper() != "ACTIVE":
            continue
        race = _race(row["Office Name"] or "", row["Contest Run By District Name and Number"] or "")
        if race is None:
            continue
        name = _name(row["Candidate First Name and Middle Name"] or "", row["Candidate Ballot Last Name and Suffix"] or "")
        if not name:
            raise ValueError(f"a row without a name: {row['Office Name']}")
        if race.family == "GOVERNOR":
            mate = _name(row["Related Candidate First Name and Middle Name"] or "",
                         row["Related Candidate Last Name and Suffix"] or "")
            if mate and (row["Related Candidate Status"] or "").strip().upper() in ("", "ACTIVE"):
                name = f"{name} and {mate}"
        if race.retention:
            court, title = COURTS[next(key for key in COURTS if race.family == COURTS[key][0].upper())]
            race = dataclasses.replace(race, office_id=f"{race.office_id} {name.upper()}",
                                       office=f"Retain {court} {title} {name}")
        label = " ".join((row["Office Political Party"] or "").split())
        code, party_name = (None, None) if label.upper() in _NO_PARTY else party(label)
        write_in = (row["Filing Type and Date"] or "").strip().upper().startswith("WRITE-IN")
        filings.append(race.filing(day=day, name=name, party=code, party_name=party_name, write_in=write_in,
                                   order=index + (100_000 if write_in else 0)))
    if not any(f.group == "federal" for f in filings):
        return filings
    return require(filings, {reach: least for reach, least in MINIMUM.items() if reach == "cd" or year % 4 == 2})


class MdList(StateList):
    state = "MD"
    source = "state_md"
    label = "Maryland State Board of Elections"
    page = "https://elections.maryland.gov/elections/2026/general_candidates/index.html"
    description = ("Maryland's official list of the candidates for Congress, Governor and its other statewide "
                   "offices, the General Assembly, and the appellate judges standing for retention, from its State "
                   "Board of Elections.")
    max_bytes = 8 << 20
    index_key = "links"
    scope_note = ("Your county's races (county executive, council or commissioners, sheriff, state's attorney and the "
                  "like), the board of education, the circuit and orphans' courts' judges, Baltimore's appellate judges "
                  "standing for retention and any questions aren't shown: your local board of elections' sample "
                  "ballot has them.")

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", PAGE.format(year=day.year))

    @classmethod
    def read_index(cls, raw: bytes) -> dict[str, Any] | None:
        text = decoded(raw)
        return None if text.startswith("Office Name") else links(text)

    def follow(self, index: dict[str, Any], day: dt.date) -> list[RequestSpec] | None:
        url = index["links"].get(str(day.year))
        return [RequestSpec("GET", url)] if url else None

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        return parse_text(decoded(raw) if isinstance(raw, bytes) else raw if isinstance(raw, str) else "")


VOTER_SERVICES = "https://voterservices.elections.maryland.gov/"
GUIDE = Guide(
    name="Maryland",
    source="Maryland State Board of Elections",
    url="https://elections.maryland.gov/",
    computed=True,
    registration_url=VOTER_SERVICES,
    mail_url=VOTER_SERVICES,
    register="The last day to register to vote in {election} in Maryland, online, by mail (postmarked today) or in "
             "person. After it, you can still register and vote the same day at an early voting center, or at your "
             "polling place on Election Day, with proof of where you live.",
    mail_summary="Mail-in ballot request due",
    mail="If you vote by mail in {election} and want your ballot sent by mail or fax, your request must reach your "
         "local board of elections today; one sent online can be asked for through Friday. Your ballot must reach the "
         "board by 8 p.m. on Election Day, or be postmarked by then and reach it by 10 a.m. on the second Friday "
         "after. Any voter can vote by mail; how to ask:",
    early_where="Your county's early voting centers, open 7 a.m. to 8 p.m. every day; your local board of elections "
                "lists them.",
    credit="Dates worked out from Maryland's election law; more from the Maryland State Board of Elections",
    poll_hours="7 a.m. – 8 p.m.",
    check_url=f"{VOTER_SERVICES}VoterSearch",
    check_hint="Maryland's voter look-up (State Board of Elections): your registration, your polling place and your "
               "mail-in ballot",
    where_url=f"{VOTER_SERVICES}VoterSearch",
    where_hint="The voter look-up: your polling place; your local board of elections lists its early voting centers",
    mail_label="How to ask",
    mail_eligibility="Any registered voter can vote by mail, no reason needed. Your ballot must reach your local board "
                     "of elections by 8 p.m. on Election Day, or be postmarked by then and reach it by 10 a.m. on the "
                     "second Friday after.",
    mail_deadline="To have your ballot sent by mail or fax, your request must reach your local board by ",
    local_office="Your local board of elections",
    late_registration="After that, register and vote the same day at an early voting center or your polling place, "
                      "with proof of where you live",
)
RULE = Counts(21, 7, 12, 5).rule("MD")
