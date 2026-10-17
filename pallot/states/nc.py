"""North Carolina: the State Board of Elections' candidate list, one CSV on S3 for the year's
elections (layout: https://s3.amazonaws.com/dl.ncsbe.gov/Elections/layout_candidate_listing.txt).

It has every contest in the state, one row per candidate per county the contest reaches, for the
primary and the general; a general's rows carry its November date. It has no withdrawn
candidates, write-ins or incumbents. A contest's reach comes from its name and the counties it
has rows in: a judicial or district attorney's district is the counties it's listed in, a county
office the one county, a town's the town.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from typing import Any

from ..http_cache import RequestSpec
from ..sources.fec import race_name
from ..text import display_office
from . import Filing, StateList, party

URL = "https://s3.amazonaws.com/dl.ncsbe.gov/Elections/{year}/Candidate%20Filing/Candidate_Listing_{year}.csv"
COLUMNS = ("election_dt", "county_name", "contest_name", "name_on_ballot", "party_candidate", "is_unexpired",
           "is_partisan", "vote_for")

_PART = re.compile(r"\b(?:DISTRICT|DIST|SEAT|WARD|AREA|ZONE|TOWNSHIP|PRECINCT)\b(?!\s*AT-LARGE)|\((?:NORTH|SOUTH|EAST|WEST)\)")
_PARTY_ORDER = {"D": 0, "R": 1, "L": 2, "G": 3}


def _kind(contest: str, county: str) -> tuple[str, str, str, str | None, str | None]:
    """(group, reach, family, district, city) of a contest, from its name and a county it has rows in."""
    if contest == "US SENATE":
        return "federal", "state", "US SENATE", None, None
    if found := re.fullmatch(r"US HOUSE OF REPRESENTATIVES DISTRICT (\d+)", contest):
        return "federal", "cd", "US HOUSE", str(int(found.group(1))), None
    if found := re.fullmatch(r"NC STATE SENATE DISTRICT (\d+)", contest):
        return "legislature", "sd", "NC STATE SENATE", str(int(found.group(1))), None
    if found := re.fullmatch(r"NC HOUSE OF REPRESENTATIVES DISTRICT (\d+)", contest):
        return "legislature", "hd", "NC HOUSE", str(int(found.group(1))), None
    if contest.startswith(("NC SUPREME COURT", "NC COURT OF APPEALS")):
        return "judicial", "state", contest, None, None
    if found := re.match(r"(NC SUPERIOR COURT JUDGE|NC DISTRICT COURT JUDGE|DISTRICT ATTORNEY) DISTRICT (\w+)", contest):
        return "judicial", "counties", found.group(1), found.group(2), None
    if found := re.match(r"(?:CITY|TOWN|VILLAGE) OF (.+)", contest):
        return "local", "part_city" if _PART.search(contest) else "city", contest, None, found.group(1)
    if contest.startswith(f"{county} COUNTY ") or contest.startswith(f"{county} SOIL AND WATER CONSERVATION"):
        return "county", "part_county" if _PART.search(contest.removeprefix(f"{county} SOIL AND WATER CONSERVATION DISTRICT")) else "county", contest, None, None
    return "local", "part_county", contest, None, None


def _office(contest: str, reach: str, district: str | None) -> str:
    if reach == "cd" or contest == "US SENATE":
        return race_name("NC", int(district) if district else None)
    return re.sub(r"\b(District|Seat) 0+(?=\d)", r"\1 ", re.sub(r"^Nc ", "NC ", display_office(contest)))


def _rank(group: str, reach: str) -> int:
    """Where a race comes on the ballot, within its group: the Senate before the House, and so on."""
    return {"state": 0, "cd": 1, "sd": 0, "hd": 1, "counties": 2, "county": 3, "city": 4}.get(reach, 5)


class NcList(StateList):
    state = "NC"
    source = "state_nc"
    label = "NC State Board of Elections"
    page = "https://www.ncsbe.gov/results-data/candidate-lists"
    description = "North Carolina's official list of the candidates on its ballot, from the State Board of Elections."

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", URL.format(year=day.year), as_text=True)

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        reader = csv.DictReader(io.StringIO(raw if isinstance(raw, str) else ""))
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or ())]
        if missing:
            raise ValueError(f"no {', '.join(missing)} column")
        merged: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in reader:
            try:
                day = dt.datetime.strptime(row["election_dt"].strip(), "%m/%d/%Y").date()
            except ValueError:
                continue
            contest, name = " ".join(row["contest_name"].upper().split()), " ".join(row["name_on_ballot"].split())
            if day.month != 11 or not contest or not name:
                continue
            key = (day.isoformat(), contest, name)
            county = " ".join(row["county_name"].upper().split())
            if key in merged:
                merged[key]["counties"].add(county)
                continue
            partisan = row["is_partisan"].strip().upper() == "TRUE"
            merged[key] = {"row": row, "county": county, "counties": {county}, "partisan": partisan}
        position = {contest: i for i, contest in enumerate(sorted({key[1] for key in merged}))}
        filings = []
        for (day, contest, name), found in merged.items():
            group, reach, family, district, city = _kind(contest, found["county"])
            code, party_name = party(found["row"]["party_candidate"]) if found["partisan"] else (None, None)
            seats = found["row"]["vote_for"].strip()
            filings.append(Filing(
                day=day, office_id=contest, office=_office(contest, reach, district), family=family, group=group,
                reach=reach, district=district, name=name, party=code, party_name=party_name,
                counties=tuple(sorted(found["counties"])), city=city,
                seats=int(seats) if seats.isdigit() and int(seats) > 0 else 1,
                unexpired=found["row"]["is_unexpired"].strip().upper() == "TRUE" or "(UNEXPIRED)" in contest,
                order=(_rank(group, reach) * 10_000 + position[contest]) * 10
                + _PARTY_ORDER.get(code or "", 4 if party_name else 5),
            ))
        return filings
