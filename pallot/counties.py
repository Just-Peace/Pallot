"""The counties of every state and DC, for a voter card's County: the Census's 2020 list
(data/counties.json, from national_county2020.txt), with each county's FIPS code. Texas SOS's
county ids run in the same alphabetical order (find_county)."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path

FILE = Path(__file__).parent / "data" / "counties.json"
KINDS = (" City and Borough", " Census Area", " Planning Region", " Municipality", " Borough", " Parish", " County",
         " city")  # what the Census adds to a county's name: "Orleans Parish", "Baltimore city"


@dataclass(frozen=True)
class County:
    name: str  # as the Census's geocoder names it: "Travis", "Orleans"
    full_name: str  # "Travis County", "Orleans Parish", "Baltimore city"
    fips: int  # 453


@cache
def _states() -> dict[str, dict]:
    return json.loads(FILE.read_text(encoding="utf-8"))


def state_names() -> dict[str, str]:
    """Every state's name by its postal code, in the order the entry card lists them."""
    return {code: state["name"] for code, state in sorted(_states().items(), key=lambda item: item[1]["name"])}


def _base(full_name: str) -> str:
    return next((full_name.removesuffix(kind) for kind in KINDS if full_name.endswith(kind)), full_name)


def counties(state: str) -> list[County]:
    found = _states().get(state, {}).get("counties", {})
    return [County(_base(name), name, int(fips)) for fips, name in found.items()]


def _plain(name: str) -> str:
    """ "De Witt County" and "dewitt", "Doña Ana" and "dona ana" alike: plain letters only, without the word "County"."""
    letters = unicodedata.normalize("NFKD", name.strip().lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", re.sub(r"\s+county\s*$", "", letters))


@cache
def _by_name(state: str) -> dict[str, County]:
    """A county by its full name, or by its short one where no other county has it: "Baltimore"
    is Baltimore County, "Baltimore city" the city."""
    found: dict[str, County] = {}
    for county in counties(state):
        found.setdefault(_plain(county.name), county)
    for county in counties(state):
        found[_plain(county.full_name)] = county
    return found


def find(state: str, name: str) -> County | None:
    """The county a voter typed in a state; None for no such county."""
    return _by_name(state).get(_plain(name))
