"""Florida: the Division of Elections' candidate extract for an election ("20261103-GEN"), one
tab-separated file of the state's candidates, asked for with the download page's form
(https://dos.elections.myflorida.com/candidates/downloadcanlist.asp, which shows its layout).

Each row is a candidate with a status: only the qualified (QUA) are on the ballot; the defeated
in the primary, withdrawn, unopposed (elected without a vote) and the rest aren't. Districts are
numbers (Juris1num), a circuit judge's group the second (Juris2num). Supreme Court justices and
appeals judges stand for retention, each a race of their own. County and city candidates file
with the counties, so they aren't in it; nor is where a special district is, so those are left out.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from typing import Any

from ..http_cache import RequestSpec
from ..sources.fec import race_name
from . import Filing, StateList, ordinal, party

URL = "https://dos.elections.myflorida.com/candidates/extractCanList.asp"
COLUMNS = ("ElectionID", "OfficeCode", "OfficeDesc", "Juris1num", "Juris2num", "StatusCode", "PartyCode", "PartyDesc",
           "NameLast", "NameFirst", "NameMiddle")
_STATEWIDE = {"GOV": "Governor", "ATG": "Attorney General", "CFO": "Chief Financial Officer",
              "AGR": "Commissioner of Agriculture"}
_PARTIES = {"DEM": "D", "REP": "R", "LPF": "L", "GRE": "G", "GRN": "G"}
_PARTY_ORDER = {"R": 0, "D": 1, "L": 2, "G": 3}
_BALLOT = ("USS", "USR", "GOV", "ATG", "CFO", "AGR", "STS", "STR", "SCJ", "DCA", "CTJ", "STA", "PUB")  # the ballot's order
_CIRCUITS = {
    1: ("ESCAMBIA", "OKALOOSA", "SANTA ROSA", "WALTON"),
    2: ("FRANKLIN", "GADSDEN", "JEFFERSON", "LEON", "LIBERTY", "WAKULLA"),
    3: ("COLUMBIA", "DIXIE", "HAMILTON", "LAFAYETTE", "MADISON", "SUWANNEE", "TAYLOR"),
    4: ("CLAY", "DUVAL", "NASSAU"),
    5: ("CITRUS", "HERNANDO", "LAKE", "MARION", "SUMTER"),
    6: ("PASCO", "PINELLAS"),
    7: ("FLAGLER", "PUTNAM", "ST. JOHNS", "VOLUSIA"),
    8: ("ALACHUA", "BAKER", "BRADFORD", "GILCHRIST", "LEVY", "UNION"),
    9: ("ORANGE", "OSCEOLA"),
    10: ("HARDEE", "HIGHLANDS", "POLK"),
    11: ("MIAMI-DADE",),
    12: ("DESOTO", "MANATEE", "SARASOTA"),
    13: ("HILLSBOROUGH",),
    14: ("BAY", "CALHOUN", "GULF", "HOLMES", "JACKSON", "WASHINGTON"),
    15: ("PALM BEACH",),
    16: ("MONROE",),
    17: ("BROWARD",),
    18: ("BREVARD", "SEMINOLE"),
    19: ("INDIAN RIVER", "MARTIN", "OKEECHOBEE", "ST. LUCIE"),
    20: ("CHARLOTTE", "COLLIER", "GLADES", "HENDRY", "LEE"),
}  # the judicial circuits' counties (Florida Statutes 26.021)
_APPEALS = {1: (1, 2, 3, 4, 8, 14), 2: (6, 12, 13), 3: (11, 16), 4: (15, 17, 19), 5: (5, 7, 18), 6: (9, 10, 20)}
# the district courts of appeal's circuits (Florida Statutes 35.044), since the Sixth's in 2023


def form(day: dt.date) -> dict[str, str]:
    """The download form's fields for every state candidate in the general election on ``day``."""
    return {"elecID": f"{day:%Y%m%d}-GEN", "office": "All", "status": "All", "cantype": "STA",
            "FormSubmit": "Download Candidate List"}


def _counties(circuits: tuple[int, ...]) -> tuple[str, ...]:
    return tuple(sorted(county for circuit in circuits for county in _CIRCUITS.get(circuit, ())))


def _number(text: str) -> int | None:
    return int(text) if text.strip().isdigit() else None


def _kind(row: dict[str, str], name: str) -> tuple[str, str, str, str | None, str, tuple[str, ...]] | None:
    """(race, group, reach, district, shown name, counties) of a candidate's row, or None for an
    office the list doesn't place (a special district's)."""
    code, first, second = row["OfficeCode"], _number(row["Juris1num"]), _number(row["Juris2num"])
    if code == "USS":
        return code, "federal", "state", None, race_name("FL", None), ()
    if code == "USR" and first:
        return f"{code} {first}", "federal", "cd", str(first), race_name("FL", first), ()
    if code == "STS" and first:
        return f"{code} {first}", "legislature", "sd", str(first), f"State Senator District {first}", ()
    if code == "STR" and first:
        return f"{code} {first}", "legislature", "hd", str(first), f"State Representative District {first}", ()
    if code in _STATEWIDE:
        return code, "state", "state", None, _STATEWIDE[code], ()
    if code == "SCJ":
        return f"{code} {name}", "judicial", "state", None, f"Retain Supreme Court Justice {name}", ()
    if code == "DCA" and first in _APPEALS:
        return (f"{code} {first} {name}", "judicial", "counties", str(first),
                f"Retain {ordinal(first)} District Court of Appeal Judge {name}", _counties(_APPEALS[first]))
    if code == "CTJ" and first in _CIRCUITS:
        return (f"{code} {first} {second}", "judicial", "counties", str(first),
                f"Circuit Judge, {ordinal(first)} Circuit" + (f", Group {second}" if second else ""), _counties((first,)))
    if code in ("STA", "PUB") and first in _CIRCUITS:
        return (f"{code} {first}", "judicial", "counties", str(first),
                f"{'State Attorney' if code == 'STA' else 'Public Defender'}, {ordinal(first)} Circuit",
                _counties((first,)))
    return None


class FlList(StateList):
    state = "FL"
    source = "state_fl"
    label = "Florida Division of Elections"
    page = "https://dos.elections.myflorida.com/candidates/"
    description = "Florida's official list of the candidates for state and federal offices, from its Division of Elections."

    def spec(self, day: dt.date) -> RequestSpec:
        return RequestSpec("POST", URL, form=form(day), as_text=True)

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        reader = csv.DictReader(io.StringIO(raw if isinstance(raw, str) else ""), delimiter="\t")
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or ())]
        if missing:
            raise ValueError(f"no {', '.join(missing)} column")
        kept = []
        for index, row in enumerate(reader):
            if row["StatusCode"].strip() != "QUA":
                continue
            try:
                day = dt.datetime.strptime(row["ElectionID"].strip()[:8], "%Y%m%d").date().isoformat()
            except ValueError:
                continue
            name = " ".join(f"{row['NameFirst']} {row['NameMiddle']} {row['NameLast']}".split())
            kind = _kind(row, name)
            if kind is None or not name:
                continue
            kept.append((index, day, name, row, kind))
        races = {(row["OfficeCode"], kind[0]) for *_, row, kind in kept}
        position = {race: i for i, (_, race) in enumerate(sorted(races, key=lambda r: (_BALLOT.index(r[0]), r[1])))}
        filings = []
        for index, day, name, row, (race, group, reach, district, shown, counties) in kept:
            write_in = row["PartyCode"] == "WRI"
            code = _PARTIES.get(row["PartyCode"])
            party_name = None if code or write_in or row["PartyCode"] in ("NPA", "NOP") else party(row["PartyDesc"])[1]
            listed = 6 if write_in else _PARTY_ORDER.get(code or "", 4 if party_name else 5)
            filings.append(Filing(
                day=day, office_id=race, office=shown, family=row["OfficeDesc"].upper(), group=group, reach=reach,
                district=district, name=name, party=code, party_name=party_name, counties=counties, write_in=write_in,
                order=(position[race] * 10 + listed) * 10_000 + index,
            ))
        return filings
