"""Virginia: the Department of Elections' list of the candidates for federal offices in a
November election, one page with a table (a spreadsheet's rows): office, district, party,
name as on the ballot, and whether they hold the seat.

Its state and local candidates are on another, much larger page; Virginia elects its
Legislature and governor in odd years, so a federal year's list is the federal one.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from ..http_cache import RequestSpec
from . import Filing, Rows, StateList, party, party_rank, us_house, us_senate

URL = "https://www.elections.virginia.gov/casting-a-ballot/candidate-list/november-{day}-{year}-gen-elect-federal-offices/"
COLUMNS = ("Office Title", "District", "Candidate Party", "Candidate Name", "Incumbent")
_DAY = re.compile(r"<h1>\s*(November \d{1,2}, \d{4})")


class VaList(StateList):
    state = "VA"
    source = "state_va"
    label = "Virginia Department of Elections"
    page = "https://www.elections.virginia.gov/casting-a-ballot/candidate-list/"
    description = "Virginia's official list of the candidates for Congress, from its Department of Elections."

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", URL.format(day=day.day, year=day.year), as_text=True)

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        text = raw if isinstance(raw, str) else ""
        found = _DAY.search(text)
        reader = Rows()
        reader.feed(text)
        header = next((i for i, row in enumerate(reader.rows) if tuple(row[:len(COLUMNS)]) == COLUMNS), None)
        if not found or header is None:
            raise ValueError("no election date or column headings")
        day = dt.datetime.strptime(found.group(1), "%B %d, %Y").date().isoformat()
        filings = []
        for index, row in enumerate(reader.rows[header + 1:]):
            if len(row) < len(COLUMNS) or any("withdr" in cell.lower() for cell in row):
                continue
            office, district, label, name, incumbent = row[:len(COLUMNS)]
            number = re.fullmatch(r"(\d+)\w\w District", district)
            if office == "Member, United States Senate":
                race = us_senate("VA")
            elif office == "Member, House of Representatives" and number:
                race = us_house("VA", int(number.group(1)))
            else:
                continue
            code, party_name = party(label)
            filings.append(race.filing(
                day=day, name=name, party=code, party_name=party_name, incumbent=incumbent.strip().lower() == "yes",
                order=(0 if race.reach == "state" else 1 + int(race.district or 0)) * 1_000
                + party_rank(code, party_name) * 100 + index,
            ))
        return filings
