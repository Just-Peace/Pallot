"""How much of each state's ballot Pallot has, and which sources work where.

A state with an entry in COVERED has its races from its own official list: Texas's from Texas
SOS, with its districts, precincts and their map ("state"); another's from its adapter
(states/adapters.py), every race the list has that the address places ("list"). Every other
state falls back to FEDERAL: the races for Congress, from the people who filed with the FEC,
none of them confirmed on the state's ballot. A state added later gets its own entry, and a
source that goes nationwide leaves ONLY_IN.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import Coverage as CoverageInfo


@dataclass(frozen=True)
class Coverage:
    ballot: Literal["state", "list", "fec"]  # Texas SOS's ballot, another state's official list, or the FEC's filers
    districts: tuple[str, ...]  # the district kinds found from the address and shown: "cd", "sd", …
    precincts: bool  # election, commissioner and JP precincts
    outlines: bool  # the districts' map

    def info(self) -> CoverageInfo:
        return CoverageInfo(ballot=self.ballot, districts=list(self.districts), precincts=self.precincts,
                            outlines=self.outlines)


STATES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA",
    "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR",
    "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
})  # the 50 states and DC, whose addresses Pallot covers
FEDERAL = Coverage("fec", ("cd",), precincts=False, outlines=False)
LIST = Coverage("list", ("cd", "sd", "hd"), precincts=False, outlines=False)
COVERED = {
    "TX": Coverage("state", ("cd", "sd", "hd", "sboe"), precincts=True, outlines=True),
    "NC": LIST,
    "MI": LIST,
}

# Sources that only know some states. A ballot with no state (a test's) counts as Texas's.
ONLY_IN: dict[str, frozenset[str]] = {
    "tec": frozenset({"TX"}),
    "polls": frozenset({"TX"}),
    "wikidata": frozenset({"TX"}),
}


def of(state: str | None) -> Coverage:
    return COVERED.get(state or "", FEDERAL)


def works_in(source: str, state: str | None) -> bool:
    states = ONLY_IN.get(source)
    return states is None or (state or "TX") in states
