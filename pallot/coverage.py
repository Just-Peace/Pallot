"""How much of each state's ballot Pallot has, and which sources work where.

A state with an entry in COVERED has its races from its own official list: Texas's from Texas
SOS, with its districts and precincts ("state"); another's from its adapter
(states/adapters.py), every race the list has that the address places ("list"). Every other
state falls back to FEDERAL: the races for Congress, from the people who filed with the FEC,
none of them confirmed on the state's ballot. Every state shows its State Senate and State House
districts, named as it names them (CHAMBERS). A state added later gets its own entry, and a
source that goes nationwide leaves ONLY_IN.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

from trackaipac_cache.models import STATES as STATE_NAMES

from .models import Coverage as CoverageInfo


@dataclass(frozen=True)
class Coverage:
    ballot: Literal["state", "list", "fec"]  # Texas SOS's ballot, another state's official list, or the FEC's filers
    districts: tuple[str, ...]  # the district kinds found from the address and shown: "cd", "sd", …
    precincts: bool  # election, commissioner and JP precincts
    labels: dict[str, str] = field(default_factory=dict)  # a district kind's name in this state: {"hd": "State Assembly"}

    def info(self) -> CoverageInfo:
        return CoverageInfo(ballot=self.ballot, districts=list(self.districts), precincts=self.precincts,
                            labels=dict(self.labels))


STATES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA",
    "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR",
    "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
})  # the 50 states and DC, whose addresses Pallot covers
NAMES = {code: name for code, name in STATE_NAMES.items() if code in STATES}  # "TX" -> "Texas"
AT_LARGE = frozenset({"AK", "DE", "DC", "ND", "SD", "VT", "WY"})  # one U.S. House seat (DC's delegate), district 0
FEDERAL = Coverage("fec", ("cd", "sd", "hd"), precincts=False)
LIST = Coverage("list", ("cd", "sd", "hd"), precincts=False)
COVERED = {
    "TX": Coverage("state", ("cd", "sd", "hd", "sboe"), precincts=True),
    "NC": LIST,
    "MI": LIST,
    "PA": LIST,
    "FL": LIST,
    "VA": LIST,  # Congress in an even year; the General Assembly and statewide offices in an odd one
    "CA": LIST,
    "AZ": LIST,  # its State Senate and State House districts are both the Legislative District
    "NV": LIST,
    "GA": LIST,
    "WI": LIST,
    "OH": LIST,  # its statewide races; the House race from the FEC
    "IA": LIST,
    "NJ": LIST,  # Congress in an even year; the State Senate and General Assembly in an odd one
    "NY": LIST,
    "CO": LIST,
    "WY": LIST,
    "IL": LIST,
    "AK": LIST,  # its State Senate districts are letters
    "ME": LIST,  # without its county offices
    "NE": LIST,  # its one house, the Legislature, is "sd" (CHAMBERS)
    "NM": LIST,  # its State Senate up only in a vacancy's district in 2026
    "WA": LIST,  # its State Senate and State House districts are both the Legislative District
    "IN": LIST,  # with its county offices and courts
    "MD": LIST,  # its House of Delegates subdistricts (1A, 1B) are the Census's, one to three seats each
    "MO": LIST,  # its U.S. House district on its 2022 map, not the geocoder's (tigerweb.GOVERNING)
    "SC": LIST,  # its State Senate up only in a presidential year
    "KY": LIST,  # its State Senate's even-numbered half up in 2026; the statewide offices in an odd year
    "OK": LIST,  # only its contested races: an unopposed candidate isn't on the ballot
    "KS": LIST,  # its State Board of Education placed by the four Senate districts of each
    "MT": LIST,  # its Public Service Commission placed by the twenty House districts of each
    "SD": LIST,  # two Representatives a district, but one each in House subdistricts 26A, 26B, 28A and 28B
    "HI": LIST,  # only its contested races: a candidate unopposed after the primary is elected then
    "ND": LIST,  # its odd-numbered districts up in 2026, with an unexpired House seat in 20, 26 and 42
    "DE": LIST,  # with its county offices elected countywide
    "VT": LIST,  # its State Senate and State House districts are named ("Chittenden Central", "Addison-Rutland")
    "MS": LIST,  # its Legislature elected in odd years: only special elections in 2026
    "AR": LIST,  # all 100 House districts and about half the Senate's up in 2026
    "MN": LIST,  # both chambers up in 2026; the House's districts lettered halves of the Senate's ("1A", "1B")
    "NH": LIST,  # its House districts named by county ("Hillsborough 12"); a floterial placed by its base districts
    "TN": LIST,  # all 99 House districts and the Senate's odd-numbered half up in 2026; its U.S. House map of 2026
}

# Each state's own name for a chamber's districts, or None where it has no such chamber: the
# Census places every address in both, but Nebraska's one house is its "upper", and DC has none.
CHAMBERS: dict[str, dict[str, str | None]] = {
    **{state: {"hd": "State Assembly"} for state in ("CA", "NV", "NY", "WI")},
    "NJ": {"hd": "General Assembly"},
    **{state: {"hd": "House of Delegates"} for state in ("MD", "VA", "WV")},
    "NE": {"sd": "Legislature", "hd": None},
    "DC": {"sd": None, "hd": None},
}

# Sources that only know some states.
ONLY_IN: dict[str, frozenset[str]] = {
    "tec": frozenset({"TX"}),
}


def _chambered(cover: Coverage, state: str) -> Coverage:
    """``cover`` in ``state``: without a chamber it doesn't have, and with its own names for them."""
    chambers = CHAMBERS.get(state)
    if not chambers:
        return cover
    districts = tuple(kind for kind in cover.districts if chambers.get(kind, kind) is not None)
    labels = {**cover.labels, **{kind: name for kind, name in chambers.items() if name and kind in districts}}
    return replace(cover, districts=districts, labels=labels)


def of(state: str) -> Coverage:
    return _chambered(COVERED.get(state, FEDERAL), state)


def federal(state: str) -> Coverage:
    """The FEC's races for Congress in ``state``, for a state whose own list can't be had."""
    return _chambered(FEDERAL, state)

def works_in(source: str, state: str) -> bool:
    states = ONLY_IN.get(source)
    return states is None or state in states
