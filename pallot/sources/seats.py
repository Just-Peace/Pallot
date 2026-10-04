"""Lists of candidates that name each one's office in their own words (Vote for Peace's ratings,
the endorsement lists), matched to the ballot's races. An entry's office and district are read as
a seat spelled the way the ballot's races are (entry_seats, race_seat): the TEC's spelling for a
state office, Congress as "TX-37", and a county, precinct or city office as its county. In one
race an entry goes to one candidate, the closest name (match_entries).
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Hashable

from ..matching import FIRST_LAST, FULL, INITIAL, NameIndex, match_person
from ..models import Match, Race
from ..offices import OfficeScope
from .ballotpedia import BpBallot
from .tec import bp_seat, tec_seat

_PARTIES = {
    "DEMOCRAT": "D", "DEMOCRATIC": "D", "REPUBLICAN": "R", "LIBERTARIAN": "L", "GREEN": "G", "INDEPENDENT": "I",
    "D": "D", "R": "R", "L": "L", "G": "G", "I": "I",
}
_TITLE = re.compile(r"^(?:DR|MR|MRS|MS|HON)\.?\s+", re.IGNORECASE)
_US = r"^U\.?\s?S\.?\s+"
_STATEWIDE = (
    (r"^(?:LT\.?|LIEUTENANT) GOVERNOR\b", "LTGOVERNOR"),
    (r"^GOVERNOR\b", "GOVERNOR"),
    (r"\bATTORNEY GENERAL\b", "ATTYGEN"),
    (r"\bCOMPTROLLER\b", "COMPTROLLER"),
    (r"\bLAND COMMISSIONER\b", "LANDCOMM"),
    (r"\bAGRICULTURE COMMISSIONER\b", "AGRICULTUR"),
    (r"\bRAILROAD COMMISSIONER\b", "RRCOMM"),
)


def _num(text: str | int | None) -> int | None:
    found = re.search(r"\d+", str(text or ""))
    return int(found.group()) if found else None


def without_title(name: str) -> str:
    """ "Dr. Eliz Markowitz" -> "Eliz Markowitz", for indexing."""
    return _TITLE.sub("", name)


def entry_seats(entry: dict[str, Any]) -> set[str]:
    """The seats an entry names, spelled as the ballot's races are: "U.S. Representative" (or
    "U.S. House") and "37" is "TX-37", "TX State Senator" and "sd-9" is "STATESEN:9", "Harris
    District County Court Judge" and "228" is "JUDGEDIST:228", a county's office "COUNTY:HARRIS".
    A court named without its place ("TX Supreme Court Justice") is any place on that court:
    "JUSTICE_SC:*" (see fit). Reads ``state``, ``office_title``, ``district``, ``level`` and
    ``jurisdiction``."""
    state = entry.get("state") or ""
    office = re.sub(r"^(?:TX|TEXAS)\s+", "", " ".join((entry.get("office_title") or "").upper().split()))
    number = _num(entry.get("district"))
    seats: set[str] = set()
    if re.match(_US + r"SENAT(?:E|OR)\b", office):
        seats.add(f"{state}-SEN")
    elif re.match(_US + r"(?:REPRESENTATIVE|HOUSE)\b", office) and number is not None:
        seats.add(f"{state}-{number:02d}")
    elif re.search(r"\bSTATE (?:REPRESENTATIVE|HOUSE)\b", office) and number is not None:
        seats.add(f"STATEREP:{number}")
    elif re.search(r"\bSTATE SENAT(?:E|OR)\b", office) and number is not None:
        seats.add(f"STATESEN:{number}")
    elif "BOARD OF EDUCATION" in office:
        seats.add(f"STATEEDU:{number}" if number is not None else "STATEEDU:*")
    elif "SUPREME COURT" in office:
        seats |= {"CHIEFJUSTICE_SC"} if "CHIEF" in office else {"JUSTICE_SC:*", "CHIEFJUSTICE_SC"}
    elif "COURT OF CRIMINAL APPEALS" in office:
        seats |= {"PRESIDINGJUDGE_COCA"} if "PRESIDING" in office else {"JUDGE_COCA:*", "PRESIDINGJUDGE_COCA"}
    elif "APPELLATE" in office or "COURT OF APPEALS" in office:
        if number is None:
            seats |= {"JUSTICE_COA:*", "CHIEFJUSTICE_COA:*"}
        else:
            seats |= {f"JUSTICE_COA:{number}:*", f"CHIEFJUSTICE_COA:{number}"}
    elif "DISTRICT" in office and ("JUDGE" in office or "COURT" in office) and number is not None:
        seats.add(f"JUDGEDIST:{number}")
    else:
        seats |= {code for pattern, code in _STATEWIDE if re.search(pattern, office)}
    if entry.get("level") in ("county", "local", "special_district") and entry.get("jurisdiction"):
        seats.add(f"COUNTY:{entry['jurisdiction'].upper()}")
    county = re.match(r"^(.+?) COUNTY\b", office)  # "Harris County Treasurer", which Vote for Peace files as statewide
    if county and "DISTRICT" not in county.group(1) and entry.get("level") != "federal":
        seats.add(f"COUNTY:{county.group(1)}")
    return seats


def fit(seats: set[str], seat: str | None) -> set[str]:
    """An entry's seats, with a court named without its place ("JUSTICE_SC:*") standing for
    the race's own place on that court."""
    return {seat if s.endswith("*") and seat and seat.startswith(s[:-1]) else s for s in seats}


def race_seat(race: Race, scope: OfficeScope | None, bp_race: Any, county: str | None) -> str | None:
    """The race's seat in entry_seats' spelling: Congress's own, a state office's as the TEC
    spells it, or else (a county, precinct or city office) the voter's county."""
    if race.seat:
        return race.seat
    seat = tec_seat(scope, county) if scope else bp_seat(bp_race, county) if bp_race else None
    if seat is None and race.group in ("county", "precinct", "local", "judicial") and county:
        return f"COUNTY:{county.upper()}"
    return seat


def party_code(entry: dict[str, Any]) -> str | None:
    return _PARTIES.get((entry.get("party") or "").upper())


def office_text(entry: dict[str, Any]) -> str:
    """ "U.S. Representative, District 37"."""
    office = entry.get("office_title") or "an office it doesn't name"
    number = _num(entry.get("district"))
    return f"{office}, District {number}" if number is not None else office


_RULES = (FULL, FIRST_LAST, INITIAL)
_LAST_NAME = len(_RULES)  # match_person's "last name, in the same seat"


def _strength(match: Match) -> int:
    """How closely the name matched: the full name first, a last name in the seat last."""
    return next((rank for rank, rule in enumerate(_RULES) if match.method.startswith(rule)), _LAST_NAME)


def match_entries(
    index: NameIndex,
    races: list[Race],
    scopes: dict[str, OfficeScope],
    county: str | None,
    bp_ballot: BpBallot | None,
    *,
    source: str,
    entry_id: str,
) -> dict[str, tuple[dict[str, Any], Match]]:
    """Candidate key -> (entry, match), in any race. A race's seat comes from race_seat, so a
    name found for another seat or county is only "likely". One entry goes to one candidate in a
    race: "Kristen Hawkins" is also "K Hawkins", as Kyle Hawkins in the same race is, so the
    strongest match by name takes it, and a tie leaves it unmatched. A county seat is every office
    in the county, so there a last name alone ("Ebony Williams" for LaShawn Williams) isn't a
    match. ``source`` names the list in a match's notes; ``entry_id`` is the entries' unique key."""
    bp_races = {f"bp:{r.id}": r for r in bp_ballot.races} if bp_ballot else {}
    out: dict[str, tuple[dict[str, Any], Match]] = {}
    for race in races:
        seat = race_seat(race, scopes.get(race.key), bp_races.get(race.key), county)
        claims: dict[Hashable, list[tuple[int, str, dict[str, Any], Match]]] = defaultdict(list)
        for candidate in race.candidates:
            found = match_person(
                index, candidate.name, candidate.party, seat,
                seats_of=lambda entry: fit(entry_seats(entry), seat), party_of=party_code, source=source,
                seat_text=office_text, name_of=lambda entry: entry.get("name"),
            )
            if found and not (_strength(found[1]) == _LAST_NAME and seat and seat.startswith("COUNTY:")):
                entry, match = found
                claims[entry[entry_id]].append((_strength(match), candidate.key, entry, match))
        for claimed in claims.values():
            best = min(strength for strength, *_ in claimed)
            winners = [claim for claim in claimed if claim[0] == best]
            if len(winners) == 1:
                _, key, entry, match = winners[0]
                out[key] = (entry, match)
    return out
