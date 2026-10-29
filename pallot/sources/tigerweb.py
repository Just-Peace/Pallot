"""District outlines for the map on Your districts, from the US Census's TIGERweb map service.

TIGERweb's "Current" service serves the same district maps the geocoder answers from
("120th Congressional Districts", "2026 State Legislative Districts - Upper"), so a layer is
found by name as census.py does, newest vintage first; each has a "… Labels" twin, skipped
by matching the end of the name. One request per district, by GEOID (the state's FIPS code and
the district's number), or by the state and the district's name where it isn't a number (Alaska's
lettered State Senate districts, Massachusetts's "Third Suffolk"), with the geometry simplified on
the server to about 50 m. Only the state and the district are sent.

When the geocoder's own districts lookup errors, census.py asks TIGERweb for them instead (place_at): one
identify request at the point, across the layers the geocoder answers from, whose features carry the
same fields its geographies do. Those answers are kept per point under POINTS, part of the address
lookup rather than the map, so the District map switch doesn't turn them off.

A state whose U.S. House map for this election isn't the Current service's (GOVERNING) has its
district, and its outline, from the service that has the map in force: one more identify request
at the address's point, kept the same way.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec
from . import arcgis_error
from .census import STATE_FIPS, vintage
from .sboe import Ring

SOURCE = "tigerweb"
POINTS = "census_points"  # the districts at a point, when the geocoder can't give them
DESCRIPTION = (
    "Outlines of your U.S. House, State Senate and State House districts, in any state, for the map, from the US "
    "Census's TIGERweb."
)
SERVICE = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Current/MapServer"
# States whose U.S. House map in force differs from the Current service's -> the service with it.
# Missouri's 2025 map (the Current "120th Congressional Districts") was held back by a referendum
# petition, which goes to its voters on November 3, 2026 as Proposition A; the Missouri Supreme
# Court ordered the 2026 election held on its 2022 map, the "119th Congressional Districts" of the
# ACS 2024 service. Look again once the referendum is decided.
GOVERNING = {"MO": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2024/MapServer"}
SIMPLIFY_DEG = 0.0005  # about 50 m: shared boundaries still meet when zoomed to a State House district

# kind -> the end of its layer's name, and the width of the district number in its GEOID
LAYERS = {
    "cd": ("Congressional Districts", 2),
    "sd": ("State Legislative Districts - Upper", 3),
    "hd": ("State Legislative Districts - Lower", 3),
}
# what census.parse_geographies reads, as words in a layer's name
PLACE_LAYERS = ("States", "Counties", "Congressional Districts", "State Legislative Districts", "Incorporated Places",
                "School Districts", "Census Blocks")


def geoid(kind: str, number: int, state: str = "TX") -> str:
    """The district's GEOID: DC's delegate, district 0 as the FEC numbers it, is "98"."""
    code = "98" if kind == "cd" and state == "DC" else str(number).zfill(LAYERS[kind][1])
    return STATE_FIPS[state] + code


def where(kind: str, number: int | str, state: str = "TX") -> str:
    """The query for one district: by GEOID where it's a number, else by the state and its name."""
    if isinstance(number, int):
        return f"GEOID='{geoid(kind, number, state)}'"
    name = number.replace("'", "''")
    return f"STATE='{STATE_FIPS[state]}' AND BASENAME='{name}'"


def layer_id(index: dict[str, Any], kind: str) -> int | None:
    """The newest layer whose name ends with the kind's, e.g. "120th Congressional Districts"."""
    suffix = LAYERS[kind][0].lower()
    layers = [layer for layer in index.get("layers") or [] if str(layer.get("name", "")).lower().endswith(suffix)]
    if not layers:
        return None
    return max(layers, key=lambda layer: vintage(layer["name"]))["id"]


def index_spec(service: str = SERVICE) -> RequestSpec:
    """The service's layers, to find each kind's by name."""
    return RequestSpec("GET", service, params={"f": "json"})


def service_of(kind: str, state: str) -> str:
    """The service with ``state``'s map in force for a kind of district."""
    return GOVERNING.get(state, SERVICE) if kind == "cd" else SERVICE


def outline_spec(layer: int, kind: str, number: int | str, state: str = "TX") -> RequestSpec:
    """One district's shape in lon/lat, simplified to SIMPLIFY_DEG, with no other fields."""
    params = {
        "where": where(kind, number, state),
        "outFields": "GEOID",
        "returnGeometry": "true",
        "outSR": "4326",
        "maxAllowableOffset": str(SIMPLIFY_DEG),
        "geometryPrecision": "5",
        "f": "json",
    }
    return RequestSpec("GET", f"{service_of(kind, state)}/{layer}/query", params=params)


def rings(answer: dict[str, Any]) -> list[Ring] | None:
    """The first feature's rings (Esri JSON: outer rings and holes in one list), or None."""
    features = answer.get("features") or []
    if not features:
        return None
    found = (features[0].get("geometry") or {}).get("rings") or []
    return [[(float(x), float(y)) for x, y, *_ in ring] for ring in found if len(ring) >= 4] or None


def place_layer_ids(index: dict[str, Any]) -> list[int]:
    """Every layer parse_geographies reads, all vintages, and none of their "… Labels" twins (nor
    the Virgin Islands' "Estates", which only end like "States")."""
    wanted = re.compile(r"\b(?:" + "|".join(PLACE_LAYERS) + r")\b", re.IGNORECASE)
    return sorted(
        layer["id"] for layer in index.get("layers") or []
        if not str(layer.get("name", "")).endswith(" Labels") and wanted.search(str(layer.get("name", "")))
    )


def identify_spec(layers: list[int], lat: float, lon: float, service: str = SERVICE) -> RequestSpec:
    """The features of ``layers`` under the point, without their shapes. Identify wants a map's
    extent and size, which with no tolerance only need to hold the point."""
    x, y = f"{lon:.6f}", f"{lat:.6f}"
    params = {
        "geometry": f"{x},{y}",
        "geometryType": "esriGeometryPoint",
        "sr": "4326",
        "layers": "all:" + ",".join(str(layer) for layer in layers),
        "tolerance": "0",
        "mapExtent": f"{lon - 0.001:.6f},{lat - 0.001:.6f},{lon + 0.001:.6f},{lat + 0.001:.6f}",
        "imageDisplay": "100,100,96",
        "returnGeometry": "false",
        "f": "json",
    }
    return RequestSpec("GET", f"{service}/identify", params=params)


def geographies(answer: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Identify's features as the geocoder lists its geographies: each layer's name -> its features' fields."""
    found: dict[str, list[dict[str, Any]]] = {}
    for result in answer.get("results") or []:
        found.setdefault(str(result.get("layerName", "")), []).append(result.get("attributes") or {})
    return found


class Tigerweb:
    def __init__(self, cache: HttpCache, ttl: Ttls):
        self.cache = cache
        self.ttl = ttl
        cache.pause_on(SOURCE, ttl.outlines_backoff)
        cache.check_answers(SOURCE, arcgis_error)
        cache.pause_on(POINTS, ttl.geocode_backoff)
        cache.check_answers(POINTS, arcgis_error)

    async def place_at(self, lat: float, lon: float) -> dict[str, list[dict[str, Any]]]:
        """The geographies at the point, as the geocoder's are keyed, empty outside the US. Raises
        UpstreamError when TIGERweb can't be asked or answers an error."""
        index = await self.cache.get_json(SOURCE, index_spec(), ttl=self.ttl.outlines)
        got = await self.cache.get_json(
            POINTS, identify_spec(place_layer_ids(index.value), lat, lon), ttl=self.ttl.geocode,
            empty_ttl=self.ttl.geocode_miss, empty_at=("results",),
        )
        return geographies(got.value)

    async def house_at(self, state: str, lat: float, lon: float) -> dict[str, list[dict[str, Any]]] | None:
        """The U.S. House district at the point on ``state``'s map in force, as the geocoder keys its
        geographies (empty off the map); None for a state whose map is the Current service's. Raises
        UpstreamError when TIGERweb can't be asked or answers an error."""
        service = GOVERNING.get(state)
        if service is None:
            return None
        index = await self.cache.get_json(SOURCE, index_spec(service), ttl=self.ttl.outlines)
        layer = layer_id(index.value, "cd")
        if layer is None:
            return {}
        got = await self.cache.get_json(
            POINTS, identify_spec([layer], lat, lon, service), ttl=self.ttl.geocode,
            empty_ttl=self.ttl.geocode_miss, empty_at=("results",),
        )
        return geographies(got.value)

    async def kept_at(self, lat: float, lon: float) -> bool:
        """Whether place_at's answer for the point is stored, fresh or not, without asking anyone."""
        index = await asyncio.to_thread(self.cache.peek, index_spec())
        if index is None:
            return False
        spec = identify_spec(place_layer_ids(index.value), lat, lon)
        return await asyncio.to_thread(self.cache.peek, spec) is not None

    async def outline(self, kind: str, number: int | str, state: str = "TX") -> list[Ring] | None:
        """The district's rings in lon/lat; None when TIGERweb has no such layer or district.
        Raises UpstreamError when it can't be asked, or answers an error, and nothing is cached."""
        index = await self.cache.get_json(SOURCE, index_spec(service_of(kind, state)), ttl=self.ttl.outlines)
        layer = layer_id(index.value, kind)
        if layer is None:
            return None
        got = await self.cache.get_json(SOURCE, outline_spec(layer, kind, number, state), ttl=self.ttl.outlines)
        return rings(got.value)
