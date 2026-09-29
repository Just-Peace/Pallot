"""State Board of Education districts, from the Texas Legislative Council's PLANE2106 map.

The Census geocoder doesn't cover SBOE districts, and counties like Harris are split
across several, so we look the point up ourselves: the KML is plain lat/lon, which keeps
this to a ray-casting point-in-polygon test with no GIS libraries. The map is downloaded
once into the data folder and kept.
"""

from __future__ import annotations

import asyncio
import io
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..fsutil import write_bytes_atomic
from ..http_cache import current_calls

PLAN = "PLANE2106"
KML_URL = (
    "https://data.capitol.texas.gov/dataset/ad1ae979-6df9-4322-98cf-6771cc67f02d"
    "/resource/a8a7daf2-ab21-4742-bf56-e1ab697580ea/download/plane2106_kml.zip"
)
DISTRICT_COUNT = 15
TOLERANCE_M = 200  # geocoders can land a few meters off; accept the nearest district within this

Ring = list[tuple[float, float]]  # (lon, lat)
BBox = tuple[float, float, float, float]  # min lon, min lat, max lon, max lat


@dataclass(frozen=True)
class Polygon:
    outer: Ring
    holes: tuple[Ring, ...]
    bbox: BBox


@dataclass(frozen=True)
class District:
    number: int
    polygons: tuple[Polygon, ...]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _ring(element: ET.Element | None) -> Ring:
    if element is None or not element.text:
        return []
    points = []
    for chunk in element.text.split():
        lon, lat, *_ = chunk.split(",")
        points.append((float(lon), float(lat)))
    return points


def _bbox(ring: Ring) -> BBox:
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return min(lons), min(lats), max(lons), max(lats)


def parse_kml(data: bytes) -> list[District]:
    root = ET.fromstring(data)
    districts = []
    for placemark in (el for el in root.iter() if _local(el.tag) == "Placemark"):
        name = next((el.text or "" for el in placemark if _local(el.tag) == "name"), "")
        number = re.search(r"\d+", name)
        if not number:
            continue
        polygons = []
        for polygon in (el for el in placemark.iter() if _local(el.tag) == "Polygon"):
            outer: Ring = []
            holes: list[Ring] = []
            for boundary in polygon:
                coords = next((el for el in boundary.iter() if _local(el.tag) == "coordinates"), None)
                if _local(boundary.tag) == "outerBoundaryIs":
                    outer = _ring(coords)
                elif _local(boundary.tag) == "innerBoundaryIs":
                    holes.append(_ring(coords))
            if outer:
                polygons.append(Polygon(outer, tuple(holes), _bbox(outer)))
        districts.append(District(int(number.group()), tuple(polygons)))
    return districts


def parse_zip(data: bytes) -> list[District]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".kml")]
        if not names:
            raise ValueError(f"{PLAN} download has no .kml file")
        return parse_kml(archive.read(names[0]))


def _inside(lon: float, lat: float, ring: Ring) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _distance_m(lat: float, lon: float, ring: Ring) -> float:
    """Meters from the point to the ring's edge (local flat-earth approximation)."""
    kx = 111_320 * math.cos(math.radians(lat))
    ky = 110_540
    best = math.inf
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        ax, ay = (x1 - lon) * kx, (y1 - lat) * ky
        bx, by = (x2 - lon) * kx, (y2 - lat) * ky
        dx, dy = bx - ax, by - ay
        length = dx * dx + dy * dy
        t = 0.0 if length == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def locate(districts: list[District], lat: float, lon: float, tolerance_m: float = TOLERANCE_M) -> int | None:
    for district in districts:
        for poly in district.polygons:
            x0, y0, x1, y1 = poly.bbox
            if x0 <= lon <= x1 and y0 <= lat <= y1 and _inside(lon, lat, poly.outer):
                if not any(_inside(lon, lat, hole) for hole in poly.holes):
                    return district.number
    margin = tolerance_m / 90_000  # degrees, generous
    nearest: tuple[float, int] | None = None
    for district in districts:
        for poly in district.polygons:
            x0, y0, x1, y1 = poly.bbox
            if x0 - margin <= lon <= x1 + margin and y0 - margin <= lat <= y1 + margin:
                distance = _distance_m(lat, lon, poly.outer)
                if nearest is None or distance < nearest[0]:
                    nearest = (distance, district.number)
    return nearest[1] if nearest and nearest[0] <= tolerance_m else None


class SboeMap:
    def __init__(self, path: Path, client: httpx.AsyncClient):
        self.path = path
        self._client = client
        self._districts: list[District] | None = None
        self._lock = asyncio.Lock()

    async def district_at(self, lat: float, lon: float) -> int | None:
        return locate(await self._load(), lat, lon)

    async def _load(self) -> list[District]:
        if self._districts is None:
            async with self._lock:
                if self._districts is None:
                    if not self.path.exists():
                        await self.download()
                    self._districts = await asyncio.to_thread(parse_zip, self.path.read_bytes())
        return self._districts

    async def download(self) -> None:
        """Fetch the map, check it parses into all districts, then replace the stored copy."""
        stats = current_calls()
        if stats:
            stats.called("sboe")
        response = await self._client.get(KML_URL, follow_redirects=True)
        response.raise_for_status()
        districts = await asyncio.to_thread(parse_zip, response.content)
        if len({d.number for d in districts}) != DISTRICT_COUNT:
            raise ValueError(f"{PLAN} map has {len(districts)} districts, expected {DISTRICT_COUNT}")
        write_bytes_atomic(self.path, response.content)
        self._districts = districts

    def clear(self) -> None:
        self._districts = None
        self.path.unlink(missing_ok=True)

    def downloaded_at(self) -> float | None:
        return self.path.stat().st_mtime if self.path.exists() else None

    def size(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0
