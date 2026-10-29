"""US Census geocoder: address -> coordinates, county, congressional and legislative districts.

Its "Current" vintage already carries the districts used on 2026 ballots (the 120th
Congress map and the 2026 state legislative districts). Layer names change between
vintages, so they are matched by name rather than by layer id.

The districts lookup (/geographies) can be down while the rest of the Census answers. Then an
address's point comes from its plain lookup (/locations), and the districts at a point from the
same maps on TIGERweb (tigerweb.Tigerweb.place_at).
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec, UpstreamError

if TYPE_CHECKING:
    from .tigerweb import Tigerweb

log = logging.getLogger("uvicorn.error")

SOURCE = "census"
BASE = "https://geocoding.geo.census.gov/geocoder/geographies"
LOCATIONS = "https://geocoding.geo.census.gov/geocoder/locations"
PARAMS = {"benchmark": "Public_AR_Current", "vintage": "Current_Current", "layers": "all", "format": "json"}
TEXAS_FIPS = "48"
STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09", "DE": "10", "DC": "11",
    "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29", "MT": "30",
    "NE": "31", "NV": "32", "NH": "33", "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46", "TN": "47", "TX": TEXAS_FIPS, "UT": "49",
    "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56",
}


@dataclass(frozen=True)
class Place:
    lat: float
    lon: float
    matched_address: str | None
    state_fips: str | None
    state: str | None  # "TX"
    county: str | None  # "Travis"
    county_fips: str | None  # "453"
    cd: int | None  # 0 for an at-large seat or DC's delegate
    sd: int | str | None  # the district's name where it isn't a number ("Third Suffolk")
    hd: int | str | None
    city: str | None
    school_district: str | None
    block_point: tuple[float, float] | None = None  # the census block's internal point (lat, lon)
    county_name: str | None = None  # "Travis County", "Orleans Parish"


def normalize_address(address: str) -> str:
    return " ".join(address.split()).upper()


class Census:
    def __init__(self, cache: HttpCache, ttl: Ttls, tigerweb: Tigerweb):
        self.cache = cache
        self.ttl = ttl
        self.tigerweb = tigerweb
        cache.pause_on(SOURCE, ttl.geocode_backoff)

    async def geocode(self, address: str) -> Place | None:
        """The address's place. An address placed by the fallback once is placed by it again, with no call."""
        normalized = normalize_address(address)
        spec = RequestSpec("GET", f"{BASE}/onelineaddress", params={"address": normalized, **PARAMS})
        plain = RequestSpec("GET", f"{LOCATIONS}/onelineaddress",
                            params={"address": normalized, "benchmark": PARAMS["benchmark"], "format": "json"})
        if not await self._kept(spec) and await self._kept(plain):
            return await self._geocode_plain(plain)
        try:
            match = await self._match(spec)
        except UpstreamError as exc:
            log.warning("%s; asking its plain lookup and TIGERweb instead", exc)
            try:
                return await self._geocode_plain(plain)
            except UpstreamError:
                raise exc from None
        if match is None:
            return None
        coords = match.get("coordinates") or {}
        return parse_geographies(match.get("geographies") or {}, coords["y"], coords["x"], match.get("matchedAddress"))

    async def at(self, lat: float, lon: float) -> Place | None:
        """The place at the point. A point placed by TIGERweb once is placed by it again, with no call."""
        spec = RequestSpec("GET", f"{BASE}/coordinates", params={"x": f"{lon:.6f}", "y": f"{lat:.6f}", **PARAMS})
        if not await self._kept(spec) and await self.tigerweb.kept_at(lat, lon):
            return await self._at_tigerweb(lat, lon, None)
        try:
            got = await self.cache.get_json(
                SOURCE, spec, ttl=self.ttl.geocode, empty_ttl=self.ttl.geocode_miss, empty_at=("result", "geographies")
            )
        except UpstreamError as exc:
            log.warning("%s; asking TIGERweb instead", exc)
            try:
                return await self._at_tigerweb(lat, lon, None)
            except UpstreamError:
                raise exc from None
        geographies = (got.value.get("result") or {}).get("geographies") or {}
        if not any(geographies.values()):
            return None
        return parse_geographies(geographies, lat, lon, None)

    async def _kept(self, spec: RequestSpec) -> bool:
        return await asyncio.to_thread(self.cache.peek, spec) is not None

    async def _geocode_plain(self, plain: RequestSpec) -> Place | None:
        match = await self._match(plain)
        if match is None:
            return None
        coords = match.get("coordinates") or {}
        return await self._at_tigerweb(coords["y"], coords["x"], match.get("matchedAddress"))

    async def _match(self, spec: RequestSpec) -> dict[str, Any] | None:
        got = await self.cache.get_json(
            SOURCE, spec, ttl=self.ttl.geocode, empty_ttl=self.ttl.geocode_miss, empty_at=("result", "addressMatches")
        )
        matches = (got.value.get("result") or {}).get("addressMatches") or []
        return matches[0] if matches else None

    async def _at_tigerweb(self, lat: float, lon: float, matched: str | None) -> Place | None:
        geographies = await self.tigerweb.place_at(float(lat), float(lon))
        if not any(geographies.values()):
            return None
        return parse_geographies(geographies, lat, lon, matched)


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


def _legislative(entry: dict[str, Any] | None) -> int | str | None:
    """A legislative district's number, or its name where the state names them: "3rd Suffolk"
    is a name, not district 3."""
    name = " ".join(((entry or {}).get("BASENAME") or "").split())
    return int(name) if name.isdigit() else name or None


def _congressional(entry: dict[str, Any] | None) -> int | None:
    """The district's number from its GEOID (state + 2 digits): an at-large district's "00" and
    DC's delegate's "98" are both 0, as the FEC numbers them. BASENAME's number otherwise."""
    code = ((entry or {}).get("GEOID") or "")[2:]
    if len(code) == 2 and code.isdigit():
        return 0 if code == "98" else int(code)
    return _number(entry)


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
        county=(county or {}).get("BASENAME"),
        county_fips=county_geoid[2:] or None,
        county_name=(county or {}).get("NAME"),
        cd=_congressional(_layer(geographies, "Congressional Districts")),
        sd=_legislative(_layer(geographies, "Legislative Districts - Upper")),
        hd=_legislative(_layer(geographies, "Legislative Districts - Lower")),
        city=(city or {}).get("BASENAME"),
        school_district=(school or {}).get("NAME"),
        block_point=_internal_point(_layer(geographies, "Census Blocks")),  # not "Census Block Groups"
    )
