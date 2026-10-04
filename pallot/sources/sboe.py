"""State Board of Education districts, from the Texas Legislative Council's PLANE2106 map.

The Census geocoder doesn't cover SBOE districts, and counties like Harris are split
across several, so we look the point up ourselves: the KML is plain lat/lon, which keeps
this to a ray-casting point-in-polygon test with no GIS libraries. The map is downloaded
once into the data folder, through HttpCache.download, and kept.
"""

from __future__ import annotations

import asyncio
import io
import math
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec, UpstreamError
from ..models import Fact, Tone
from ..text import display_size, display_time
from . import RefreshFailed

SOURCE = "sboe"
PLAN = "PLANE2106"
KML_URL = (
    "https://data.capitol.texas.gov/dataset/ad1ae979-6df9-4322-98cf-6771cc67f02d"
    "/resource/a8a7daf2-ab21-4742-bf56-e1ab697580ea/download/plane2106_kml.zip"
)
HOST = urlsplit(KML_URL).hostname
REFUSALS = (403, 429)  # answers that pause the portal for Ttls.election_precincts_backoff
MAX_BYTES = 20 * 1_048_576  # the map is about 1.9 MB
FAILED_FLAG = f"failed:{SOURCE}"
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
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:  # a SyntaxError, which callers wouldn't expect
        raise ValueError(f"{PLAN} map isn't valid KML ({exc})") from None
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


def read_download(path: Path) -> list[District]:
    """A downloaded map's districts, refused unless it has all of them."""
    districts = parse_zip(path.read_bytes())
    if len({d.number for d in districts}) != DISTRICT_COUNT:
        raise ValueError(f"{PLAN} map has {len(districts)} districts, expected {DISTRICT_COUNT}")
    return districts


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


def _offset(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    """Distance from the point to the segment, in degrees (as TIGERweb's maxAllowableOffset)."""
    (px, py), (ax, ay), (bx, by) = point, start, end
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def simplify(ring: Ring, tolerance: float) -> Ring:
    """Douglas–Peucker: the fewest points that stay within ``tolerance`` of the ring, keeping
    its first and last points (so a closed ring stays closed), rounded to about 1 m."""
    if len(ring) < 3:
        return [(round(x, 5), round(y, 5)) for x, y in ring]
    keep = [False] * len(ring)
    keep[0] = keep[-1] = True
    stack = [(0, len(ring) - 1)]
    while stack:
        first, last = stack.pop()
        worst, index = 0.0, 0
        for i in range(first + 1, last):
            distance = _offset(ring[i], ring[first], ring[last])
            if distance > worst:
                worst, index = distance, i
        if worst > tolerance:
            keep[index] = True
            stack += [(first, index), (index, last)]
    return [(round(x, 5), round(y, 5)) for (x, y), kept in zip(ring, keep) if kept]


def outline(district: District, tolerance: float) -> list[Ring]:
    """The district's outer rings and holes, simplified; rings that shrink below a triangle go."""
    found = (simplify(ring, tolerance) for poly in district.polygons for ring in (poly.outer, *poly.holes))
    return [ring for ring in found if len(ring) >= 4]


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
    """The map kept at ``path``, downloaded by the first lookup that needs it. One that fails
    isn't downloaded again by a lookup for ``Ttls.retry_after``, and a refusal pauses the portal;
    a refresh always tries."""

    def __init__(self, cache: HttpCache, ttl: Ttls, path: Path):
        self.cache = cache
        self.ttl = ttl
        self.path = path
        self.last_error: str | None = None  # why the last download failed, until one succeeds
        self._districts: list[District] | None = None
        self._outlines: dict[tuple[int, float], list[Ring]] = {}
        self._lock = asyncio.Lock()
        self._downloading = False
        cache.pause_on(SOURCE, REFUSALS, ttl.election_precincts_backoff)

    async def district_at(self, lat: float, lon: float) -> int | None:
        return await asyncio.to_thread(locate, await self._load(), lat, lon)

    async def outline(self, number: int, tolerance: float) -> list[Ring] | None:
        """The district's rings for the map, simplified once and kept; None if there's no such district."""
        key = (number, tolerance)
        if key not in self._outlines:
            district = next((d for d in await self._load() if d.number == number), None)
            if district is None:
                return None
            self._outlines[key] = await asyncio.to_thread(outline, district, tolerance)
        return self._outlines[key]

    async def _load(self) -> list[District]:
        """The districts, read once; with no map kept, downloaded, unless the last download
        failed a short while ago (UpstreamError, without asking)."""
        if self._districts is None:
            async with self._lock:
                if self._districts is None:
                    if self.path.exists():
                        self._districts = await asyncio.to_thread(self._read)
                    elif until := self.cache.flag_until(FAILED_FLAG):
                        raise UpstreamError(SOURCE, f"the last download failed ({self.last_error or 'see Settings'}); "
                                                    f"Pallot tries again after {display_time(until)}")
                    else:
                        await self._download()
        return self._districts

    async def warm(self) -> None:
        """Read the map kept, at startup, so the first lookup needn't; never downloads."""
        if self._districts is None and self.path.exists():
            async with self._lock:
                if self._districts is None and self.path.exists():
                    self._districts = await asyncio.to_thread(self._read)

    def _read(self) -> list[District]:
        return parse_zip(self.path.read_bytes())

    async def _download(self) -> None:
        """Fetch the map, check it has every district, then put it in place of the one kept. On
        any failure the map kept stays, and a lookup won't download it again for a while."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        part = self.path.with_name(f".{self.path.name}.part")
        self._downloading = True
        try:
            await self.cache.download(SOURCE, RequestSpec("GET", KML_URL), part, max_bytes=MAX_BYTES, hosts={HOST})
            districts = await asyncio.to_thread(read_download, part)
            os.replace(part, self.path)
        except UpstreamError as exc:
            if exc.until is None:  # asked and failed; while paused, nothing was asked
                self._failed(str(exc).removeprefix(f"{SOURCE}: "), refused=exc.status in REFUSALS)
            raise
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            self._failed(str(exc))
            raise
        except Exception as exc:
            error = ValueError(f"the map couldn't be read ({type(exc).__name__}: {exc})")
            self._failed(str(error))
            raise error from exc
        finally:
            part.unlink(missing_ok=True)
            self._downloading = False
        self.last_error = None
        self._districts, self._outlines = districts, {}

    def _failed(self, error: str, *, refused: bool = False) -> None:
        """Remember why, and keep lookups from downloading again for a while (a refusal pauses
        the portal instead)."""
        self.last_error = error
        if not refused:
            self.cache.set_flag(FAILED_FLAG, SOURCE, self.ttl.retry_after)

    def _missing(self) -> str:
        """When a lookup may download the map again, while none is kept."""
        until = max(filter(None, (self.cache.flag_until(FAILED_FLAG), self.cache.paused_until(SOURCE))), default=None)
        return f"lookups try again after {display_time(until)}" if until else "the next lookup tries again"

    # -- Settings (KeptSource) ----------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._downloading

    def notice(self) -> tuple[str, Tone] | None:
        if self._downloading:
            return "Downloading the State Board of Education map…", "info"
        kept = self.path.exists()
        if paused := self.cache.paused_until(SOURCE):
            then = "the map kept still shows" if kept else "SBOE districts are missing until then"
            return (f"The Texas Legislative Council's portal refused the State Board of Education map, so Pallot "
                    f"won't ask it again until {display_time(paused)}; {then}."), "warn"
        if self.last_error:
            then = "the map kept still shows" if kept else self._missing()
            return f"The last download of the State Board of Education map failed ({self.last_error}); {then}.", "warn"
        return None

    def details(self) -> list[Fact]:
        if not self.path.exists():
            return [Fact(label="SBOE map", value="fetched on the first lookup")]
        downloaded = display_time(self.path.stat().st_mtime)
        return [Fact(label="SBOE map", value=f"downloaded {downloaded} · {display_size(self.size())}")]

    def size(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0

    def stale(self) -> str | None:
        return None if self.path.exists() else "the State Board of Education map isn't downloaded yet"

    async def refresh(self) -> str:
        async with self._lock:
            try:
                await self._download()
            except (UpstreamError, OSError, ValueError, zipfile.BadZipFile) as exc:
                paused = exc.until if isinstance(exc, UpstreamError) else None
                why = f"paused until {display_time(paused)}" if paused else self.last_error
                kept = "kept the old one" if self.path.exists() else self._missing()
                raise RefreshFailed(f"Couldn't re-download the State Board of Education map ({why}); {kept}.") from exc
        return "Re-downloaded the State Board of Education map."

    def clear(self) -> str:
        self._districts, self._outlines, self.last_error = None, {}, None
        self.path.unlink(missing_ok=True)
        self.cache.clear(SOURCE)  # it keeps no responses, only its pause and retry flags
        return "The State Board of Education map will be downloaded again on the next lookup."
