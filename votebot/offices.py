"""Classify Texas SOS office names into the part of the state each race covers.

The county ballot-order data lists every race touching a county; this is what lets us
keep only the ones for the voter's own districts. Judicial and DA districts in Texas are
made of whole counties, so any other state-regional ("SR") office covers the whole
county; only congressional, legislative and SBOE districts split counties.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Collection

_UNEXPIRED = re.compile(r"\s*-\s*UNEXPIRED TERM\s*$")

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("us_senate", re.compile(r"^U\. ?S\. SENATOR$")),
    ("cd", re.compile(r"^U\. ?S\. REPRESENTATIVE,? DISTRICT (\d+)$")),
    ("sd", re.compile(r"^STATE SENATOR,? DISTRICT (\d+)$")),
    ("hd", re.compile(r"^STATE REPRESENTATIVE,? DISTRICT (\d+)$")),
    ("sboe", re.compile(r"^MEMBER,? STATE BOARD OF EDUCATION,? DISTRICT (\d+)$")),
    ("commissioner", re.compile(r"^COUNTY COMMISSIONER,? PRECINCT (?:NO\.? ?)?(\d+)\b")),
    ("jp", re.compile(r"^JUSTICE OF THE PEACE,? PRECINCT (?:NO\.? ?)?(\d+)\b")),
    ("constable", re.compile(r"^(?:COUNTY )?CONSTABLE,? PRECINCT (?:NO\.? ?)?(\d+)\b")),
)

# cdOfficeType -> kind, for names that match no pattern above.
_BY_OFFICE_TYPE = {"FD": "federal_other", "SW": "statewide", "SR": "whole_county", "CW": "countywide", "CR": "precinct_other"}

GROUP_OF_KIND = {
    "us_senate": "federal",
    "cd": "federal",
    "federal_other": "federal",
    "statewide": "state",
    "sd": "legislature",
    "hd": "legislature",
    "sboe": "legislature",
    "whole_county": "judicial",
    "countywide": "county",
    "commissioner": "precinct",
    "jp": "precinct",
    "constable": "precinct",
    "precinct_other": "precinct",
}

DISTRICT_KINDS = ("cd", "sd", "hd", "sboe")  # vary within a county; we know the voter's from their address
PRECINCT_KINDS = ("commissioner", "jp", "constable")  # vary within a county; known only from the voter or Ballotpedia

KIND_LABELS = {
    "cd": "U.S. House",
    "sd": "State Senate",
    "hd": "State House",
    "sboe": "State Board of Education",
    "commissioner": "County Commissioner",
    "jp": "Justice of the Peace",
    "constable": "Constable",
}


@dataclass(frozen=True)
class OfficeScope:
    kind: str
    number: int | None
    unexpired: bool
    name: str  # without the county prefix and the unexpired-term suffix

    @property
    def group(self) -> str:
        return GROUP_OF_KIND[self.kind]

    @property
    def seat(self) -> str | None:
        """Congressional seat in the "TX-10" / "TX-SEN" form other sources use."""
        if self.kind == "us_senate":
            return "TX-SEN"
        if self.kind == "cd" and self.number is not None:
            return f"TX-{self.number:02d}"
        return None


def clean_office_name(name: str, county_names: Collection[str] = ()) -> tuple[str, bool]:
    """Drop a "TRAVIS - " county prefix (only for real county names) and the unexpired-term
    suffix; return (name, unexpired)."""
    text = " ".join(name.split()).upper()
    prefix, sep, rest = text.partition(" - ")
    if sep and prefix in county_names:
        text = rest
    unexpired = bool(_UNEXPIRED.search(text))
    return _UNEXPIRED.sub("", text), unexpired


def classify(name: str, office_type: str | None, county_names: Collection[str] = ()) -> OfficeScope:
    text, unexpired = clean_office_name(name, county_names)
    for kind, pattern in _PATTERNS:
        match = pattern.match(text)
        if match:
            return OfficeScope(kind, int(match.group(1)) if match.groups() else None, unexpired, text)
    kind = _BY_OFFICE_TYPE.get((office_type or "").upper(), "countywide")
    return OfficeScope(kind, None, unexpired, text)
