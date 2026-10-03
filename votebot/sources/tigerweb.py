"""District outlines for the map on Your districts, from the US Census's TIGERweb map service.

TIGERweb's "Current" service serves the same district maps the geocoder answers from
("120th Congressional Districts", "2026 State Legislative Districts - Upper"), so a layer is
found by name as census.py does, newest vintage first; each has a "… Labels" twin, skipped
by matching the end of the name. One request per district, by GEOID, with the geometry
simplified on the server to about 50 m. Only the district's number is sent.
"""

from __future__ import annotations

from typing import Any

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec
from . import arcgis_error
from .census import TEXAS_FIPS, vintage

SOURCE = "tigerweb"
DESCRIPTION = (
    "Outlines of your U.S. House, State Senate and State House districts, for the map under Your districts, from "
    "the US Census's TIGERweb. Asked once your ballot is shown, with each district's number, never your address."
)
SERVICE = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Current/MapServer"
REFUSALS = (403, 429)  # answers that pause TIGERweb for Ttls.outlines_backoff
SIMPLIFY_DEG = 0.0005  # about 50 m: shared boundaries still meet when zoomed to a State House district

Ring = list[tuple[float, float]]  # (lon, lat)

# kind -> the end of its layer's name, and the width of the district number in its GEOID
LAYERS = {
    "cd": ("Congressional Districts", 2),
    "sd": ("State Legislative Districts - Upper", 3),
    "hd": ("State Legislative Districts - Lower", 3),
}


def geoid(kind: str, number: int) -> str:
    return TEXAS_FIPS + str(number).zfill(LAYERS[kind][1])


def layer_id(index: dict[str, Any], kind: str) -> int | None:
    """The newest layer whose name ends with the kind's, e.g. "120th Congressional Districts"."""
    suffix = LAYERS[kind][0].lower()
    layers = [layer for layer in index.get("layers") or [] if str(layer.get("name", "")).lower().endswith(suffix)]
    if not layers:
        return None
    return max(layers, key=lambda layer: vintage(layer["name"]))["id"]


def index_spec() -> RequestSpec:
    """The service's layers, to find each kind's by name."""
    return RequestSpec("GET", SERVICE, params={"f": "json"})


def outline_spec(layer: int, kind: str, number: int) -> RequestSpec:
    """One district's shape in lon/lat, simplified to SIMPLIFY_DEG, with no other fields."""
    params = {
        "where": f"GEOID='{geoid(kind, number)}'",
        "outFields": "GEOID",
        "returnGeometry": "true",
        "outSR": "4326",
        "maxAllowableOffset": str(SIMPLIFY_DEG),
        "geometryPrecision": "5",
        "f": "json",
    }
    return RequestSpec("GET", f"{SERVICE}/{layer}/query", params=params)


def rings(answer: dict[str, Any]) -> list[Ring] | None:
    """The first feature's rings (Esri JSON: outer rings and holes in one list), or None."""
    features = answer.get("features") or []
    if not features:
        return None
    found = (features[0].get("geometry") or {}).get("rings") or []
    return [[(float(x), float(y)) for x, y, *_ in ring] for ring in found if len(ring) >= 4] or None


class Tigerweb:
    def __init__(self, cache: HttpCache, ttl: Ttls):
        self.cache = cache
        self.ttl = ttl
        cache.pause_on(SOURCE, REFUSALS, ttl.outlines_backoff)
        cache.check_answers(SOURCE, arcgis_error)

    async def outline(self, kind: str, number: int) -> list[Ring] | None:
        """The district's rings in lon/lat; None when TIGERweb has no such layer or district.
        Raises UpstreamError when it can't be asked, or answers an error, and nothing is cached."""
        index = await self.cache.get_json(SOURCE, index_spec(), ttl=self.ttl.outlines)
        layer = layer_id(index.value, kind)
        if layer is None:
            return None
        got = await self.cache.get_json(SOURCE, outline_spec(layer, kind, number), ttl=self.ttl.outlines)
        return rings(got.value)
