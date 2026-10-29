"""Florida: the Division of Elections' candidate extract for an election ("20261103-GEN"), one
tab-separated file of the state's candidates, asked for with the download page's form
(https://dos.elections.myflorida.com/candidates/downloadcanlist.asp, which shows its layout).

Each row is a candidate with a status: only the qualified (QUA) are on the ballot; the defeated
in the primary, withdrawn, unopposed (elected without a vote) and the rest aren't. Districts are
numbers (Juris1num), a circuit judge's group the second (Juris2num). Supreme Court justices and
appeals judges stand for retention, each a race of their own. County and city candidates file
with the counties, so they aren't in it; nor is where a special district is, so those are left out.

Florida's key dates, for its general election (F.S. 100.031: the first Tuesday after the first
Monday of November in an even year): registration closes the twenty-ninth day before (97.055(1)(a));
any voter can vote by mail, a request reaching the Supervisor of Elections by 5 p.m. on the twelfth
day before (101.62(2)), and the ballot must reach the Supervisor by 7 p.m. on Election Day (101.67);
early voting runs from the tenth day before through the third day before, and a county may add days
from the fifteenth day before or the second (101.657(1)(d)); polls are open 7 a.m. to 7 p.m.
(100.011). There's no registration on Election Day.
"""

from __future__ import annotations

import csv
import datetime as dt
import functools
import io
from typing import Any

from ..http_cache import RequestSpec
from ..sources.fec import race_name
from . import Filing, Office, StateList, counties_of, ordinal, party
from .dates import Counts, Guide

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
    return counties_of(_CIRCUITS, circuits)


def _number(text: str) -> int | None:
    return int(text) if text.strip().isdigit() else None


def _kind(row: dict[str, str], name: str) -> Office | None:
    """A candidate's row's race, its family the list's office, or None for an office the list
    doesn't place (a special district's)."""
    code, first, second = row["OfficeCode"], _number(row["Juris1num"]), _number(row["Juris2num"])

    def race(office_id: str, shown: str, group: str, reach: str, district: int | None = None,
             counties: tuple[str, ...] = ()) -> Office:
        return Office(office_id, shown, row["OfficeDesc"].upper(), group, reach,
                      str(district) if district else None, counties, retention=code in ("SCJ", "DCA"))

    judge = functools.partial(race, group="judicial", reach="counties", district=first)
    if code == "USS":
        return race(code, race_name("FL", None), "federal", "state")
    if code == "USR" and first:
        return race(f"{code} {first}", race_name("FL", first), "federal", "cd", first)
    if code == "STS" and first:
        return race(f"{code} {first}", f"State Senator District {first}", "legislature", "sd", first)
    if code == "STR" and first:
        return race(f"{code} {first}", f"State Representative District {first}", "legislature", "hd", first)
    if code in _STATEWIDE:
        return race(code, _STATEWIDE[code], "state", "state")
    if code == "SCJ":
        return race(f"{code} {name}", f"Retain Supreme Court Justice {name}", "judicial", "state")
    if code == "DCA" and first in _APPEALS:
        return judge(f"{code} {first} {name}", f"Retain {ordinal(first)} District Court of Appeal Judge {name}",
                     counties=_counties(_APPEALS[first]))
    if code == "CTJ" and first in _CIRCUITS:
        return judge(f"{code} {first} {second}",
                     f"Circuit Judge, {ordinal(first)} Circuit" + (f", Group {second}" if second else ""),
                     counties=_counties((first,)))
    if code in ("STA", "PUB") and first in _CIRCUITS:
        return judge(f"{code} {first}", f"{'State Attorney' if code == 'STA' else 'Public Defender'}, "
                     f"{ordinal(first)} Circuit", counties=_counties((first,)))
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
        races = {(row["OfficeCode"], kind.office_id) for *_, row, kind in kept}
        position = {race: i for i, (_, race) in enumerate(sorted(races, key=lambda r: (_BALLOT.index(r[0]), r[1])))}
        filings = []
        for index, day, name, row, race in kept:
            write_in = row["PartyCode"] == "WRI"
            code = _PARTIES.get(row["PartyCode"])
            party_name = None if code or write_in or row["PartyCode"] in ("NPA", "NOP") else party(row["PartyDesc"])[1]
            listed = 6 if write_in else _PARTY_ORDER.get(code or "", 4 if party_name else 5)
            filings.append(race.filing(
                day=day, name=name, party=code, party_name=party_name, write_in=write_in,
                order=(position[race.office_id] * 10 + listed) * 10_000 + index,
            ))
        return filings


GUIDE = Guide(
    name="Florida",
    source="Florida Division of Elections",
    url="https://dos.fl.gov/elections/",
    computed=True,
    registration_url="https://registertovoteflorida.gov/",
    mail_url="https://dos.fl.gov/elections/for-voters/voting/vote-by-mail/",
    register="The last day to register to vote in {election} in Florida. There's no registration on Election Day.",
    mail_summary="Vote-by-mail request due",
    mail="If you vote by mail in {election}, your request must reach your county Supervisor of Elections by 5 p.m. "
         "today. Your ballot must reach the Supervisor by 7 p.m. on Election Day; one that arrives later isn't "
         "counted. Any voter can vote by mail; how to ask:",
    early_where="Your county Supervisor of Elections lists the places and hours, and may add days before or after "
                "these.",
    credit="Dates worked out from Florida's election law; more from the Florida Division of Elections",
    poll_hours="7 a.m. – 7 p.m.",
    check_url="https://registration.elections.myflorida.com/CheckVoterStatus",
    check_hint="Florida's voter information lookup (Division of Elections): your registration and your polling place",
    where_url="https://dos.fl.gov/elections/contacts/supervisor-of-elections/",
    where_hint="Every county's Supervisor of Elections (Florida Division of Elections); yours publishes where and when "
               "you can vote",
    mail_label="How to ask",
    mail_eligibility="Any registered voter can vote by mail, no reason needed. Your ballot must reach your county "
                     "Supervisor of Elections by 7 p.m. on Election Day.",
    mail_deadline="Your request must reach your Supervisor of Elections by 5 p.m. on ",
    local_office="Your county Supervisor of Elections",
)
RULE = Counts(29, 12, 10, 3).rule("FL")
