"""New York: the State Board of Elections' certification of the candidates for a general election,
a PDF saved by hand (manual/state_ny), since elections.ny.gov answers scripts with Cloudflare's
challenge and Pallot never asks it.

Each race is a block: its Office, District, Counties and Vote For, then a Party / Candidate Name
table with a row per party line. A candidate on several lines (fusion) is one candidate with
every line they're on, in the table's order; a line with no name after it is empty. A row's party
and name can wrap onto the next line, and the Governor's ticket puts both first names on one line
and both last names on the next.

The statewide offices come under the state, Congress, the State Senate and the Assembly by their
districts, and a Supreme Court judicial district reaches the whole counties it lists.

New York's key dates, for its general election (Election Law 8-100(1)(c): the Tuesday after the
first Monday of November, every year), checked on nysenate.gov on 2026-10-24: a registration must
reach the county board by the tenth day before (5-210(3)); early voting runs from the tenth day
before through the second day before (8-600(1)); an absentee or early mail ballot application online
or by mail must reach the board by the tenth day before, in person by the day before (8-400); a
mailed ballot must be postmarked by Election Day and reach the board within seven days after
(8-412); polls are open 6 a.m. to 9 p.m. (8-100(2)).
"""

from __future__ import annotations

import dataclasses
import functools
import re
from typing import Any

from . import Filing, ManualList, Office, legislator, ordinal, party, pdf_lines, require, statewide, us_house
from .dates import Counts, Guide, first_tuesday_after_first_monday

STATEWIDE = {"GOVERNOR AND LT. GOVERNOR": "Governor and Lieutenant Governor", "COMPTROLLER": "Comptroller",
             "ATTORNEY GENERAL": "Attorney General"}
LEGISLATURE = {"STATE SENATOR": ("sd", "STATE SENATE", "State Senate"),
               "MEMBER OF ASSEMBLY": ("hd", "STATE ASSEMBLY", "State Assembly")}
COUNTY_NAMES = {"SAINT LAWRENCE": "ST. LAWRENCE"}
MINIMUM = {"cd": 26, "hd": 150}  # every Congress and Assembly district is up
_TITLE = re.compile(r"November\s+\d{1,2},\s*(\d{4})\s+General Election")
_FIELD = re.compile(r"^(Office|District|Counties|Vote For):?\s*(.*)$")
_FOOTER = re.compile(r"Page\s+\d+\s+of\s+\d+")
_PARTY_COLUMN = 10


def _text(value: str) -> str:
    return re.sub(r"(?<=\w) ?- ?(?=\w)", "-", " ".join(value.split()))


def _counties(text: str) -> tuple[tuple[str, ...], bool]:
    """(the counties, in capitals, whether any is only part) of a Counties field: "Albany, Columbia & Ulster"."""
    names = [name.strip() for name in re.split(r",|&", text) if name.strip()]
    part = any(name.upper().startswith("PART OF ") for name in names)
    names = [re.sub(r"(?i)^part of ", "", name).upper() for name in names]
    return tuple(COUNTY_NAMES.get(name, name) for name in names), part


def _kind(office: str, district: str, counties: str) -> Office:
    """The race of a block."""
    upper, area = " ".join(office.upper().split()), " ".join(district.split())
    office_id = f"{upper} {area}".strip()
    race = functools.partial(dataclasses.replace, Office(office_id, " ".join(office.split()), upper, "state", "unplaced"))
    if upper in STATEWIDE:
        return statewide(STATEWIDE[upper], upper)
    if not area.isdigit():
        return race()
    number = int(area)
    if upper == "REPRESENTATIVE IN CONGRESS":
        return us_house("NY", number, office_id)
    if upper in LEGISLATURE:
        reach, family, label = LEGISLATURE[upper]
        return dataclasses.replace(legislator(reach, number, office_id, f"{label} District {number}"), family=family)
    if upper == "SUPREME COURT JUSTICE":
        names, part = _counties(counties)
        return race(office=f"Supreme Court Justice, {ordinal(number)} Judicial District", group="judicial",
                    reach="part_county" if part else "counties", district=str(number), counties=names)
    return race()


def _row(lines: list[str], ticket: bool) -> tuple[str, str]:
    """(party, name) of a row's lines: the party's words from the left column, the name's from the
    rest; a ticket's two names, column by column, joined with "and"."""
    parties: list[str] = []
    names: list[list[str]] = [[], []]
    for line in lines:
        indent = len(line) - len(line.lstrip())
        cells = re.split(r"\s{3,}", line.strip())
        if indent < _PARTY_COLUMN:
            parties.append(cells.pop(0))
        if ticket:
            for column, cell in zip(names, cells):
                column.append(cell)
        else:
            names[0] += cells
    name = " and ".join(_text(" ".join(column)) for column in names if column)
    return _text(" ".join(parties)), name


def _merge(race: Office, rows: list[tuple[str, str]], day: str, order: int) -> list[Filing]:
    """A block's candidates, one per person with every line they're on, told apart by their letters
    alone ("Karen M.Wilutis" on one line is "Karen M. Wilutis" on the next) and named as spaced out
    best: the first line with a code gives the party, and the lines' names show when there's more
    than one."""
    people: dict[str, tuple[list[str], list[str]]] = {}
    for label, name in rows:
        if name:
            names, labels = people.setdefault(re.sub(r"\W", "", name.upper()), ([], []))
            names.append(name)
            labels.append(label)
    filings = []
    for index, (names, labels) in enumerate(people.values()):
        labels = list(dict.fromkeys(labels))
        codes = [party(label) for label in labels]
        code = next((found for found, _ in codes if found), None)
        named = " / ".join(labels) if len(labels) > 1 else codes[0][1]
        filings.append(race.filing(day=day, name=max(names, key=lambda name: name.count(" ")), party=code,
                                   party_name=named, order=order * 100 + index))
    return filings


def parse_lines(lines: list[str]) -> list[Filing]:
    """Every candidate in the certification, from pdf_lines' layout; ValueError for a file that isn't
    it (no title, no races, a race without its fields)."""
    year = next((int(found.group(1)) for line in lines if (found := _TITLE.search(line))), None)
    if year is None:
        raise ValueError("no general election's title")
    day = first_tuesday_after_first_monday(year, 11).isoformat()
    blocks: list[dict[str, Any]] = []
    fields: dict[str, str] = {}
    rows: list[list[str]] = []
    current: list[str] = []
    for line in [*lines, ""]:
        if _FOOTER.search(line):
            continue
        if "Office:" in line:
            fields = {"Office": line.split("Office:", 1)[1].strip()}
            rows = []
            blocks.append({"fields": fields, "rows": rows})
            current = []
            continue
        if not blocks:
            continue
        found = _FIELD.match(line)
        if found and "Vote For" not in fields:
            fields[found.group(1)] = found.group(2).strip()
            continue
        if "Vote For" not in fields:
            if line.strip() and "Counties" in fields:
                fields["Counties"] += " " + line.strip()
            continue
        if not line.strip():
            if current:
                rows.append(current)
            current = []
        elif not re.match(r"\s*(Party\b|Candidate Name\b)", line):
            current.append(line)
    if not blocks:
        raise ValueError("no races")
    filings: list[Filing] = []
    for order, block in enumerate(blocks):
        fields = block["fields"]
        missing = [name for name in ("District", "Counties", "Vote For") if name not in fields]
        if missing or not fields["Vote For"].isdigit():
            raise ValueError(f"a race without its {', '.join(missing) or 'Vote For'}: {fields['Office']}")
        race = dataclasses.replace(_kind(fields["Office"], fields["District"], fields["Counties"]),
                                   seats=int(fields["Vote For"]))
        ticket = race.family == "GOVERNOR AND LT. GOVERNOR"
        filings += _merge(race, [_row(row, ticket) for row in block["rows"]], day, order)
    if not filings:
        raise ValueError("no candidates")
    return filings


class NyList(ManualList):
    state = "NY"
    source = "state_ny"
    label = "New York State Board of Elections"
    page = "https://elections.ny.gov/ballot-certifications-elections"
    description = ("New York's official certification of the candidates on its ballot, from the statewide offices to "
                   "its Supreme Court, from its State Board of Elections, imported by hand.")
    folder = "manual/state_ny"
    binary = True
    challenge = ("Just a moment...", "challenges.cloudflare.com", "cf-browser-verification")

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, bytes):
            raise ValueError("not a PDF")
        return require(parse_lines(pdf_lines(raw)), MINIMUM)

    def missing(self, when: str) -> str:
        return f"Pallot doesn't have the {self.label}' certification of the candidates for {when} yet"


GUIDE = Guide(
    name="New York",
    source="New York State Board of Elections",
    url="https://elections.ny.gov/",
    computed=True,
    registration_url="https://elections.ny.gov/register-vote",
    mail_url="https://absenteeballot.elections.ny.gov/",
    register="The last day for your registration to reach your county board of elections for {election} in New York.",
    mail_summary="Early mail or absentee ballot application due",
    mail="If you vote by mail in {election}, an application made online or by mail must reach your county board of "
         "elections today; in person, you can apply until the day before Election Day. Your ballot must be "
         "postmarked by Election Day and reach the board within 7 days after. Any voter can vote early by mail; "
         "how to apply:",
    early_where="Your county board of elections sets the places and hours.",
    credit="Dates worked out from New York's Election Law; more from the New York State Board of Elections",
    poll_hours="6 a.m. – 9 p.m.",
    check_url="https://voterlookup.elections.ny.gov/",
    check_hint="New York State Board of Elections' voter lookup: your registration and your polling place",
    where_url="https://voterlookup.elections.ny.gov/",
    where_hint="The voter lookup: your polling place; your county board of elections publishes its early voting places",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote early by mail, no reason needed. Your ballot must be postmarked by "
                     "Election Day and reach your county board within 7 days after.",
    mail_deadline="Online or mailed applications must reach your county board by ",
    local_office="Your county board of elections",
)
RULE = Counts(10, 10, 10, 2, every_year=True).rule("NY")
