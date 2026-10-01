"""US Census geocoder: address -> coordinates, county, congressional and legislative districts.

Its "Current" vintage already carries the districts used on 2026 ballots (the 120th
Congress map and the 2026 state legislative districts). Layer names change between
vintages, so they are matched by name rather than by layer id.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec

SOURCE = "census"
BASE = "https://geocoding.geo.census.gov/geocoder/geographies"
PARAMS = {"benchmark": "Public_AR_Current", "vintage": "Current_Current", "layers": "all", "format": "json"}
TEXAS_FIPS = "48"


@dataclass(frozen=True)
class Place:
    lat: float
    lon: float
    matched_address: str | None
    state_fips: str | None
    state: str | None  # "TX"
    state_name: str | None  # "Texas"
    county: str | None  # "Travis"
    county_fips: str | None  # "453"
    cd: int | None
    sd: int | None
    hd: int | None
    city: str | None
    school_district: str | None
    block_point: tuple[float, float] | None = None  # the census block's internal point (lat, lon)


def normalize_address(address: str) -> str:
    return " ".join(address.split()).upper()


class Census:
    def __init__(self, cache: HttpCache, ttl: Ttls):
        self.cache = cache
        self.ttl = ttl

    async def geocode(self, address: str) -> Place | None:
        spec = RequestSpec("GET", f"{BASE}/onelineaddress", params={"address": normalize_address(address), **PARAMS})
        got = await self.cache.get_json(
            SOURCE, spec, ttl=self.ttl.geocode, empty_ttl=self.ttl.geocode_miss, empty_at=("result", "addressMatches")
        )
        matches = (got.value.get("result") or {}).get("addressMatches") or []
        if not matches:
            return None
        match = matches[0]
        coords = match.get("coordinates") or {}
        return parse_geographies(match.get("geographies") or {}, coords["y"], coords["x"], match.get("matchedAddress"))

    async def at(self, lat: float, lon: float) -> Place | None:
        spec = RequestSpec("GET", f"{BASE}/coordinates", params={"x": f"{lon:.6f}", "y": f"{lat:.6f}", **PARAMS})
        got = await self.cache.get_json(
            SOURCE, spec, ttl=self.ttl.geocode, empty_ttl=self.ttl.geocode_miss, empty_at=("result", "geographies")
        )
        geographies = (got.value.get("result") or {}).get("geographies") or {}
        if not any(geographies.values()):
            return None
        return parse_geographies(geographies, lat, lon, None)


def vintage(layer_name: str) -> int:
    """Leading number of a layer name ("120th Congressional…", "2026 State…"), newest first."""
    match = re.match(r"(\d+)", layer_name)
    return int(match.group(1)) if match else 0


def _layer(geographies: dict[str, list[dict[str, Any]]], needle: str) -> dict[str, Any] | None:
    names = [name for name, entries in geographies.items() if needle.lower() in name.lower() and entries]
    if not names:
        return None
    return geographies[max(names, key=vintage)][0]


def _number(entry: dict[str, Any] | None) -> int | None:
    match = re.search(r"\d+", (entry or {}).get("BASENAME") or "")
    return int(match.group()) if match else None


def _internal_point(entry: dict[str, Any] | None) -> tuple[float, float] | None:
    try:
        return float(entry["INTPTLAT"]), float(entry["INTPTLON"])
    except (TypeError, KeyError, ValueError):
        return None


def parse_geographies(geographies: dict[str, Any], lat: float, lon: float, matched: str | None) -> Place:
    county = _layer(geographies, "Counties")
    state = _layer(geographies, "States")
    county_geoid = (county or {}).get("GEOID") or ""
    school = _layer(geographies, "Unified School Districts") or _layer(geographies, "School Districts")
    city = _layer(geographies, "Incorporated Places")
    return Place(
        lat=float(lat),
        lon=float(lon),
        matched_address=matched,
        state_fips=(state or {}).get("STATE") or (state or {}).get("GEOID") or county_geoid[:2] or None,
        state=(state or {}).get("STUSAB"),
        state_name=(state or {}).get("NAME"),
        county=(county or {}).get("BASENAME"),
        county_fips=county_geoid[2:] or None,
        cd=_number(_layer(geographies, "Congressional Districts")),
        sd=_number(_layer(geographies, "Legislative Districts - Upper")),
        hd=_number(_layer(geographies, "Legislative Districts - Lower")),
        city=(city or {}).get("BASENAME"),
        school_district=(school or {}).get("NAME"),
        block_point=_internal_point(_layer(geographies, "Census Blocks")),  # not "Census Block Groups"
    )
