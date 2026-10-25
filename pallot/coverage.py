"""How much of each state's ballot Pallot has, and which sources work where.

A state with an entry in COVERED has its races from its own official list: Texas's from Texas
SOS, with its districts, precincts and their map ("state"); another's from its adapter
(states/adapters.py), every race the list has that the address places ("list"). Every other
state falls back to FEDERAL: the races for Congress, from the people who filed with the FEC,
none of them confirmed on the state's ballot. A state added later gets its own entry, and a
source that goes nationwide leaves ONLY_IN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from trackaipac_cache.models import STATES as STATE_NAMES

from .models import Coverage as CoverageInfo


@dataclass(frozen=True)
class Coverage:
    ballot: Literal["state", "list", "fec"]  # Texas SOS's ballot, another state's official list, or the FEC's filers
    districts: tuple[str, ...]  # the district kinds found from the address and shown: "cd", "sd", …
    precincts: bool  # election, commissioner and JP precincts
    outlines: bool  # the districts' map
    labels: dict[str, str] = field(default_factory=dict)  # a district kind's name in this state: {"hd": "State Assembly"}

    def info(self) -> CoverageInfo:
        return CoverageInfo(ballot=self.ballot, districts=list(self.districts), precincts=self.precincts,
                            outlines=self.outlines, labels=dict(self.labels))


STATES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA",
    "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR",
    "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
})  # the 50 states and DC, whose addresses Pallot covers
NAMES = {code: name for code, name in STATE_NAMES.items() if code in STATES}  # "TX" -> "Texas"
AT_LARGE = frozenset({"AK", "DE", "DC", "ND", "SD", "VT", "WY"})  # one U.S. House seat (DC's delegate), district 0
FEDERAL = Coverage("fec", ("cd",), precincts=False, outlines=False)
LIST = Coverage("list", ("cd", "sd", "hd"), precincts=False, outlines=False)
COVERED = {
    "TX": Coverage("state", ("cd", "sd", "hd", "sboe"), precincts=True, outlines=True),
    "NC": LIST,
    "MI": LIST,
    "PA": LIST,
    "FL": LIST,
    "VA": Coverage("list", ("cd",), precincts=False, outlines=False),  # only its federal list in an even year
    "CA": Coverage("list", ("cd", "sd", "hd"), precincts=False, outlines=False, labels={"hd": "State Assembly"}),
    "AZ": LIST,  # its State Senate and State House districts are both the Legislative District
    "NV": Coverage("list", ("cd", "sd", "hd"), precincts=False, outlines=False, labels={"hd": "State Assembly"}),
    "GA": LIST,
    "WI": Coverage("list", ("cd", "sd", "hd"), precincts=False, outlines=False, labels={"hd": "State Assembly"}),
    "OH": Coverage("list", ("cd",), precincts=False, outlines=False),  # its statewide races; the House race from the FEC
    "IA": LIST,
    "NJ": Coverage("list", ("cd",), precincts=False, outlines=False),  # only U.S. Senate and House in 2026
    "NY": Coverage("list", ("cd", "sd", "hd"), precincts=False, outlines=False, labels={"hd": "State Assembly"}),
    "CO": LIST,
    "WY": LIST,
}

# Sources that only know some states.
ONLY_IN: dict[str, frozenset[str]] = {
    "tec": frozenset({"TX"}),
}


def of(state: str) -> Coverage:
    return COVERED.get(state, FEDERAL)


def works_in(source: str, state: str) -> bool:
    states = ONLY_IN.get(source)
    return states is None or state in states
