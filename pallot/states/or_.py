"""Oregon: the Secretary of State's candidate filings for a general election, from ORESTAR's
candidate search (secure.sos.state.or.us/orestar/CFSearchPage.do), a Java form whose results the
maintainer exports to a spreadsheet (XcelCFSearch.xlsx) in a browser, saved by hand
(manual/state_or); Pallot never asks it.

Each row is a filing: the election ("2026 General Election"), the office group ("US
Representative"), the office's district ("5th District", "statewide"), how it was filed
("Nominated" by a party's primary, "Minor Party" by a minor party's nomination, "Write In" won in a
primary, "Fee" or petition for a nonpartisan office), the party, the name as the ballot prints it,
its ballot order, whether it qualified and any withdrawal. Its addresses, phones, emails,
occupation and background columns are never read: only the name, office, district and party are
kept. It is the general election's list, not the primary's: every nominee filed after the May
primary was certified (June 25, 2026), and the reader refuses another election or a race with two
candidates of one party. A withdrawn or unqualified filing is dropped.

Oregon lets several parties nominate one candidate (ORS 254.135(3)(a)), and the ballot prints them
once with each party: every filing of one name in one race is one candidate, with each party in
ballot order ("Democrat / Working Families"), the first with a code giving the party.

Placed: Governor (and the Commissioner of Labor and Industries in a year it's on the November
ballot), the U.S. Senate, the U.S. House (six districts), the State Senate (about half its 30
districts up) and the State House (all 60). The judges and district attorneys are left out with a
ballot note. An office it doesn't know is refused.

Oregon's key dates, for its general election (the first Tuesday after the first Monday of November
in an even year, ORS 254.056(1)), checked on 2026-10-30 against the ORS and the Secretary of
State's 2026 elections calendar: registration closes 21 days before, online or postmarked (ORS
247.025); every active voter is mailed a ballot between 20 and 14 days before (ORS 254.470(2)(a)); a
ballot comes back to an official drop site, open until at least 8 p.m. on Election Day (ORS
254.470(1), (6)(b)), or by mail postmarked by Election Day and received within 7 days (ORS
253.070(3)). The county elections office takes
ballots in person from the day they're mailed through Election Day. No registering on Election
Day. 2026: register by Oct 13, ballots mailed from Oct 14, returned by Nov 3 (by mail, received by
Nov 10).
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from . import Filing, ManualList, Office, legislator, party, require, sheet_rows, statewide, us_house, us_senate
from .dates import Counts, Guide, first_tuesday_after_first_monday, mailed_to_every_voter

COLUMNS = ("Election Txt", "Office Group", "Office", "Filetype Descr", "Party Descr", "Cand Ballot Name Txt",
           "Ballot Order Nbr", "Qlf Ind", "Witdrw Date")
MINIMUM = {"cd": 6, "hd": 60}
STATEWIDE = {"GOVERNOR": "Governor", "COMMISSIONER OF THE BUREAU OF LABOR AND INDUSTRIES":
             "Commissioner of the Bureau of Labor and Industries"}
LEFT_OUT = {"JUDGE OF THE SUPREME COURT", "JUDGE OF THE COURT OF APPEALS", "JUDGE OF THE TAX COURT",
            "JUDGE OF THE CIRCUIT COURT", "DISTRICT ATTORNEY"}
_ELECTION = re.compile(r"(\d{4}) General Election", re.I)
_DISTRICT = re.compile(r"(\d+)(?:st|nd|rd|th) District", re.I)


def _race(group: str, office: str) -> Office | None:
    """The race of a row's office group and office; None for one left out. ValueError for one it doesn't know."""
    title = group.upper()
    if title in STATEWIDE:
        return statewide(STATEWIDE[title])
    if title == "US SENATOR":
        return us_senate("OR")
    found = _DISTRICT.fullmatch(office)
    if found and title == "US REPRESENTATIVE":
        return us_house("OR", int(found.group(1)))
    if found and title in ("STATE SENATOR", "STATE REPRESENTATIVE"):
        return legislator("sd" if title == "STATE SENATOR" else "hd", int(found.group(1)))
    if title in LEFT_OUT:
        return None
    raise ValueError(f"an office it doesn't know: {group}, {office}")


def _rank(race: Office) -> tuple[int, int]:
    """Where a race comes on the ballot: the U.S. Senate, the U.S. House, the statewide offices,
    the State Senate, the State House."""
    return {"US SENATE": 0, "US HOUSE": 1, "STATE SENATE": 3, "STATE HOUSE": 4}.get(race.family, 2), int(race.district or 0)


def _order(text: str) -> int:
    return int(text) if text.isdigit() else 999


def parse_rows(rows: list[list[str]]) -> list[Filing]:
    """Every candidate on the general election's ballot in the export's rows (its header first),
    each once with every party that nominated them; ValueError for one that isn't the list (its
    columns missing, another election, an office it doesn't know, two candidates of one party in a
    race, fewer than MINIMUM's races)."""
    if not rows:
        raise ValueError("an empty sheet")
    header = rows[0]
    missing = [name for name in COLUMNS if name not in header]
    if missing:
        raise ValueError(f"no {', '.join(missing)} column{'s' if len(missing) > 1 else ''}")
    at = {name: header.index(name) for name in COLUMNS}
    people: dict[tuple[str, str], tuple[Office, str, list[tuple[int, str]]]] = {}
    years: set[str] = set()
    for row in rows[1:]:
        cells = {name: row[i] if i < len(row) else "" for name, i in at.items()}
        name = cells["Cand Ballot Name Txt"]
        if not name:
            continue
        election = _ELECTION.fullmatch(cells["Election Txt"])
        if not election:
            raise ValueError(f"not a general election's list: {cells['Election Txt']!r}")
        years.add(election.group(1))
        if cells["Witdrw Date"] or cells["Qlf Ind"].upper() != "Y":
            continue
        race = _race(cells["Office Group"], cells["Office"])
        if race is None:
            continue
        _, _, lines = people.setdefault((race.office_id, re.sub(r"\W", "", name.upper())), (race, name, []))
        lines.append((_order(cells["Ballot Order Nbr"]), cells["Party Descr"]))
    if len(years) > 1:
        raise ValueError(f"more than one election: {', '.join(sorted(years))}")
    if not people:
        raise ValueError("no candidates")
    day = first_tuesday_after_first_monday(int(years.pop()), 11).isoformat()
    labels = Counter((office_id, label.upper()) for (office_id, _), (*_, lines) in people.items()
                     for label in {label for _, label in lines} if party(label)[1] or party(label)[0])
    if twice := sorted({office_id for (office_id, _), n in labels.items() if n > 1}):
        raise ValueError(f"two candidates of one party in {', '.join(twice)}: a primary's list")
    filings = []
    for race, name, lines in sorted(people.values(), key=lambda p: (_rank(p[0]), min(p[2]), p[1])):
        named = list(dict.fromkeys(label for _, label in sorted(lines) if party(label) != (None, None)))
        codes = [party(label) for label in named]
        code = next((found for found, _ in codes if found), None)
        filings.append(race.filing(day=day, name=name, party=code,
                                   party_name=" / ".join(named) if len(named) > 1 else (codes[0][1] if codes else None),
                                   order=len(filings)))
    return require(filings, MINIMUM)


class OrList(ManualList):
    state = "OR"
    source = "state_or"
    label = "Oregon Secretary of State"
    page = "https://secure.sos.state.or.us/orestar/CFSearchPage.do"
    description = ("Oregon's official list of the candidates for Governor, Congress and its Legislature, from its "
                   "Secretary of State, imported by hand.")
    folder = "manual/state_or"
    binary = True
    scope_note = ("The judges, district attorneys, county and city races and the measures aren't shown: the voters' "
                  "pamphlet mailed to you has them.")

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, bytes):
            raise ValueError("not a spreadsheet")
        return parse_rows(sheet_rows(raw)[1])


SOS = "https://sos.oregon.gov/elections/Pages/default.aspx"
MYVOTE = "https://secure.sos.state.or.us/orestar/vr/showVoterSearch.do?lang=eng&source=SOS"
GUIDE = Guide(
    name="Oregon",
    source="Oregon Secretary of State",
    url=SOS,
    computed=True,
    registration_url="https://sos.oregon.gov/elections/Pages/registration.aspx",
    mail_url="https://sos.oregon.gov/elections/Pages/track-your-ballot.aspx",
    register="The last day to register to vote in {election} in Oregon: online, or by mail postmarked today. There's "
             "no registering on Election Day.",
    mail_summary="Ballots are mailed",
    mail="Every voter in Oregon is mailed a ballot for {election}, from today. Put it in an official drop box by 8 p.m. "
         "on Election Day, or mail it postmarked by Election Day. Track yours:",
    early_where="Your county elections office takes ballots in person from the day they're mailed through 8 p.m. on "
                "Election Day; your county lists its drop boxes.",
    credit="Dates worked out from Oregon's election law; more from the Oregon Secretary of State",
    poll_hours="8 p.m.",
    check_url=MYVOTE,
    check_hint="My Vote (Oregon Secretary of State): your registration and your ballot's status",
    where_url="https://sos.oregon.gov/elections/Pages/drop-box-locator.aspx",
    where_hint="Oregon Secretary of State: every county's drop boxes",
    mail_label="Track your ballot",
    mail_eligibility=mailed_to_every_voter("It goes out 14 to 20 days before Election Day. Put it in an official drop "
                                           "box by 8 p.m. on Election Day, or mail it postmarked by Election Day (it "
                                           "must reach your county within 7 days)."),
    polls_text="Official drop boxes and your county elections office close at 8 p.m. on Election Day; if you're in line "
               "at 8, you can vote.",
    hours_set_by="your county elections office",
)
RULE = Counts(21, None, 20, None).rule("OR")  # every voter is mailed a ballot; no deadline moves past a weekend
