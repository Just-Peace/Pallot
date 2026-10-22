"""Wisconsin: the Elections Commission's "All Contests and Candidates" CSV for a general election,
saved by hand (manual/state_wi), since elections.wi.gov answers scripts with Cloudflare's
challenge and Pallot never asks it.

Each row is a candidate in a contest, read by its column names: the election, the name on the
ballot, the party, the jurisdiction that runs the contest ("STATE OF WISCONSIN", "DANE COUNTY",
"CITY OF VERONA - DANE COUNTY"), the contest, its district, and the contest's and candidate's
ballot positions, which give the order. Referendums have rows of their own with no candidate:
the ballot has no measures, so they're left out, as are contests no one filed for.

The statewide offices, Congress, the State Senate and the Assembly come under the state. A county's
contest whose district is the whole county (sheriff, clerk of circuit court, coroner) reaches the
whole county, and a city's or village's whose district is the whole of it, the whole place;
anything else within a county (a supervisory district, a joint municipal court, a town) only part
of it, so those are unconfirmed. A city spanning counties ("- MULTIPLE COUNTIES") isn't placed.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from ..sources.fec import race_name
from . import Filing, ManualList, party
from .key_dates import first_tuesday_after_first_monday

COLUMNS = ("Election", "IsReferendum", "Name On Ballot", "Political Party", "Jurisdiction", "Contest", "District",
           "Contest Ballot Position", "Candidate Ballot Position")
STATEWIDE = {
    "GOVERNOR / LIEUTENANT GOVERNOR": "Governor / Lieutenant Governor", "ATTORNEY GENERAL": "Attorney General",
    "SECRETARY OF STATE": "Secretary of State", "STATE TREASURER": "State Treasurer",
}
LEGISLATURE = (
    (r"STATE SENATOR DISTRICT (\d+)", "sd", "STATE SENATE", "State Senate"),
    (r"REPRESENTATIVE TO THE ASSEMBLY DISTRICT (\d+)", "hd", "STATE ASSEMBLY", "State Assembly"),
)
_ELECTION = re.compile(r"(\d{4}) General Election", re.I)
_CONGRESS = re.compile(r"REPRESENTATIVE IN CONGRESS DISTRICT (\d+)")
_COUNTY = re.compile(r"(.+) COUNTY")
_MUNICIPALITY = re.compile(r"(CITY|VILLAGE|TOWN) OF (.+?) - (.+)")
_JUDICIAL = re.compile(r"\bJUDGE\b|\bJUSTICE\b")
_PARTIES = {"WISCONSIN GREEN": ("G", None), "INDEPENDENT": (None, None)}


def _text(value: str | None) -> str:
    return " ".join((value or "").split())


def _number(value: str | None) -> int:
    text = _text(value)
    return int(text) if text.isdigit() else 0


def _kind(jurisdiction: str, contest: str, district: str) -> dict[str, Any]:
    """The race of a row's contest, as Filing's fields: its id, shown name, family, group, reach,
    district, counties and city."""
    where, upper, area = jurisdiction.upper(), contest.upper(), district.upper()
    race = {"office_id": f"{upper} ({where})", "office": contest, "family": upper, "district": None, "counties": (),
            "city": None}
    group = "judicial" if _JUDICIAL.search(upper) else "local"
    if where == "STATE OF WISCONSIN":
        race["office_id"] = upper
        if found := _CONGRESS.fullmatch(upper):
            number = int(found.group(1))
            return {**race, "office": race_name("WI", number), "family": "US HOUSE", "group": "federal", "reach": "cd",
                    "district": str(number)}
        for pattern, reach, family, label in LEGISLATURE:
            if found := re.fullmatch(pattern, upper):
                number = str(int(found.group(1)))
                return {**race, "office": f"{label} District {number}", "family": family, "group": "legislature",
                        "reach": reach, "district": number}
        if area == "WISCONSIN":
            return {**race, "office": STATEWIDE.get(upper, contest), "group": "judicial" if group == "judicial" else "state",
                    "reach": "state"}
        return {**race, "group": "state", "reach": "unplaced"}
    if found := _MUNICIPALITY.fullmatch(where):
        kind, name, county = found.groups()
        if not (counted := _COUNTY.fullmatch(county)):
            return {**race, "group": group, "reach": "unplaced"}
        counties = (counted.group(1),)
        if kind == "TOWN":
            return {**race, "group": group, "reach": "part_county", "counties": counties}
        whole = area == f"{kind} OF {name}"
        return {**race, "group": group, "reach": "city" if whole else "part_city", "city": name, "counties": counties}
    if found := _COUNTY.fullmatch(where):
        county = found.group(1)
        if area == where:
            return {**race, "family": re.sub(rf"^{re.escape(county)}(?: COUNTY)? ", "", upper),
                    "group": "judicial" if group == "judicial" else "county", "reach": "county", "counties": (county,)}
        return {**race, "group": group, "reach": "part_county", "counties": (county,)}
    return {**race, "group": group, "reach": "unplaced"}


def parse_rows(text: str) -> list[Filing]:
    """Every candidate in the CSV; ValueError for a file that isn't the list (its columns missing,
    no general election's candidates)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = [name for name in COLUMNS if name not in (reader.fieldnames or ())]
    if missing:
        raise ValueError(f"no {', '.join(missing)} column{'s' if len(missing) > 1 else ''}")
    filings: list[Filing] = []
    for row in reader:
        found = _ELECTION.fullmatch(_text(row["Election"]))
        name = _text(row["Name On Ballot"])
        if not found or _text(row["IsReferendum"]) or not name:
            continue
        day = first_tuesday_after_first_monday(int(found.group(1)), 11).isoformat()
        race = _kind(_text(row["Jurisdiction"]), _text(row["Contest"]), _text(row["District"]))
        label = _text(row["Political Party"])
        code, party_name = _PARTIES.get(label.upper()) or party(label)
        filings.append(Filing(day=day, name=name, party=code, party_name=party_name,
                              order=_number(row["Contest Ballot Position"]) * 100
                              + _number(row["Candidate Ballot Position"]), **race))
    if not filings:
        raise ValueError("no candidates")
    return filings


class WiList(ManualList):
    state = "WI"
    source = "state_wi"
    label = "Wisconsin Elections Commission"
    page = "https://elections.wi.gov/candidates"
    description = ("Wisconsin's official list of the candidates on its ballot, from Congress to its counties, from its "
                   "Elections Commission, imported by hand.")
    folder = "manual/state_wi"
    challenge = ("Just a moment...", "challenges.cloudflare.com", "cf-browser-verification")

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        if not isinstance(raw, str):
            raise ValueError("not a CSV")
        return parse_rows(raw)
