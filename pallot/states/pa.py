"""Pennsylvania: the Department of State's Election Info page, which carries every candidate
for the coming November election as JSON in a hidden field (``dataJson``), its election picked
in a drop-down ("2026 General Election (11/03/2026)").

It has everyone who filed for the year, primary losers and party committee seats included: a
candidate is on the general ballot when approved and either won the primary (PrimaryResult) or
was nominated by papers or as a substitute. Names are "LAST, FIRST M", parties written out, and
a cross-filed candidate comes once per party. It has no incumbents.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from typing import Any

from ..http_cache import RequestSpec
from ..sources.fec import race_name
from ..text import display_office, display_person
from . import Filing, StateList, party

URL = "https://www.pavoterservices.pa.gov/ElectionInfo/ElectionInfo.aspx"
COLUMNS = ("CandidateName", "PartyName", "CandidateStatusValue", "CandidateTypeValue", "OfficeName", "DistrictName",
           "PrimaryResult")
_DATA = re.compile(r"""<input[^>]*id=['"]dataJson['"][^>]*value='([^']*)'""")
_ELECTION = re.compile(r'<option selected="selected" value="\d+">[^<(]*\((\d{2}/\d{2}/\d{4})\)')
_NUMBERED = re.compile(r"(\d+)\w\w (?:Congressional|Senatorial|Legislative) District")
_PARTY_ORDER = {"D": 0, "R": 1, "L": 2, "G": 3}


def _kind(office: str, district: str) -> tuple[str, str, str | None, str, tuple[str, ...]] | None:
    """(group, reach, district, shown name, counties) of an office, or None for one that isn't
    on the general ballot (a party's committee seat)."""
    number = found.group(1) if (found := _NUMBERED.fullmatch(district)) else None
    if office == "UNITED STATES SENATOR":
        return "federal", "state", None, race_name("PA", None), ()
    if office == "REPRESENTATIVE IN CONGRESS" and number:
        return "federal", "cd", number, race_name("PA", int(number)), ()
    if office == "SENATOR IN THE GENERAL ASSEMBLY" and number:
        return "legislature", "sd", number, f"State Senator District {number}", ()
    if office == "REPRESENTATIVE IN THE GENERAL ASSEMBLY" and number:
        return "legislature", "hd", number, f"State Representative District {number}", ()
    if "COMMITTEE" in office or "DELEGATE" in office:
        return None
    judicial = "JUDGE" in office or "JUSTICE" in office
    if district == "Statewide":
        return "judicial" if judicial else "state", "state", None, display_office(office), ()
    if county := re.fullmatch(r"(.+?) ?County", district):
        name = county.group(1).upper()
        return "judicial" if judicial else "county", "county", None, f"{county.group(1)} County {display_office(office)}", (name,)
    return ("judicial", "unplaced", None, display_office(office), ()) if judicial else None


class PaList(StateList):
    state = "PA"
    source = "state_pa"
    label = "Pennsylvania Department of State"
    page = URL
    description = "Pennsylvania's official list of the candidates for state and federal offices, from its Department of State."

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("GET", URL, as_text=True)

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        text = raw if isinstance(raw, str) else ""
        found, election = _DATA.search(text), _ELECTION.search(text)
        if not found or not election:
            raise ValueError("no candidates or election on the page")
        rows = json.loads(html.unescape(found.group(1)))
        missing = [c for c in COLUMNS if rows and c not in rows[0]]
        if missing:
            raise ValueError(f"no {', '.join(missing)} field")
        day = dt.datetime.strptime(election.group(1), "%m/%d/%Y").date().isoformat()
        merged: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in rows:
            if row["CandidateStatusValue"] != "Approved":
                continue
            if row["PrimaryResult"] != "true" and row["CandidateTypeValue"] not in ("Paper", "Substitute"):
                continue
            office, district = " ".join(row["OfficeName"].split()), " ".join(row["DistrictName"].split())
            last, _, rest = row["CandidateName"].partition(",")  # a suffix comes with the last name: "HARVIE JR, ROBERT J"
            name = display_person(" ".join(f"{rest} {last}".split()))
            kind = _kind(office, district)
            if kind is None or not name:
                continue
            key = (office, district, name)
            if key in merged:
                merged[key]["parties"].append(row["PartyName"])
                continue
            merged[key] = {"kind": kind, "parties": [row["PartyName"]]}
        position = {race: i for i, race in enumerate(sorted({key[:2] for key in merged}))}
        filings = []
        for (office, district, name), entry in merged.items():
            group, reach, number, shown, counties = entry["kind"]
            parties = list(dict.fromkeys(p.strip() for p in entry["parties"] if p and p.strip()))
            code, party_name = party(parties[0]) if len(parties) == 1 else (None, " / ".join(parties) or None)
            rank = {"state": 0, "cd": 1, "sd": 0, "hd": 1}.get(reach, 2)
            filings.append(Filing(
                day=day, office_id=f"{office} {district}", office=shown, family=office, group=group, reach=reach,
                district=number, name=name, party=code, party_name=party_name, counties=counties,
                order=(rank * 10_000 + position[(office, district)]) * 10
                + _PARTY_ORDER.get(code or "", 4 if party_name else 5),
            ))
        return filings
