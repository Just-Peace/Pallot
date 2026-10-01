"""Election precincts, the "Pct" on a voter registration certificate, from the Texas
Legislative Council's precinct maps.

The Census has no election precincts, but the TLC collects every county's after each statewide
election and publishes them on its CKAN portal (the ``precincts`` dataset). The portal's index,
cached like any request, says which map is newest; that map is downloaded once into the data
folder, and again only when the index lists a newer one. A general election's map only comes
out after that election, and counties can only redraw precincts in March or April of odd years,
so the newest map, a primary's or a general's, serves the elections after it.

The map is a shapefile in a Lambert conformal conic projection, read with the standard library:
the projection's parameters come from its .prj, and records are read by seek, so only their
bounding boxes stay in memory.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import re
import shutil
import struct
import threading
import time
import uuid
import zipfile
from dataclasses import asdict, dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlsplit

from ..config import Ttls
from ..fsutil import write_text_atomic
from ..http_cache import HttpCache, RequestSpec, UpstreamError, current_calls
from ..models import Fact, Tone
from ..text import display_size, display_time
from . import RefreshFailed
from .sboe import Ring, _inside, _offset, simplify

SOURCE = "election_precincts"
LABEL = "Election precincts"
DESCRIPTION = (
    "Your election precinct, the \"Pct\" on your voter registration certificate, and its outline on the map, from "
    "the Texas Legislative Council's map of every county's voting precincts. The newest map is downloaded once, and "
    "again only when the Council publishes a newer one. Your address is never sent."
)
INDEX_URL = "https://data.capitol.texas.gov/api/3/action/package_show"
DATASET = "precincts"
HOST = urlsplit(INDEX_URL).hostname
REFUSALS = (403, 429)  # answers that pause the portal for Ttls.election_precincts_backoff
SIMPLIFY_DEG = 0.00005  # about 5 m: a precinct is a few streets across, drawn at street level
FIRST_WAIT = 20.0  # seconds the first lookup waits for the first map, beside the other sources
FIELDS = ("CNTY", "PREC")  # the county's FIPS code, and its name for the precinct ("0300")
SHAPEFILE = ("shp", "shx", "dbf")
MAP_FILE = "map.json"

BBox = tuple[float, float, float, float]  # min x, min y, max x, max y, in the map's projection


def _t(phi: float, e: float) -> float:
    return math.tan(math.pi / 4 - phi / 2) / ((1 - e * math.sin(phi)) / (1 + e * math.sin(phi))) ** (e / 2)


def _m(phi: float, e: float) -> float:
    return math.cos(phi) / math.sqrt(1 - (e * math.sin(phi)) ** 2)


@dataclass(frozen=True)
class Lambert:
    """A Lambert conformal conic with two standard parallels (EPSG method 9802), in metres;
    angles in degrees."""

    a: float  # the ellipsoid's semi-major axis
    inverse_flattening: float
    false_easting: float
    false_northing: float
    central_meridian: float
    parallel_1: float
    parallel_2: float
    origin_latitude: float

    @cached_property
    def _cone(self) -> tuple[float, float, float, float]:
        """e, n, aF and the radius at the origin's latitude (EPSG Guidance Note 7-2)."""
        f = 1 / self.inverse_flattening
        e = math.sqrt(2 * f - f * f)
        p1, p2, p0 = (math.radians(v) for v in (self.parallel_1, self.parallel_2, self.origin_latitude))
        n = (math.log(_m(p1, e)) - math.log(_m(p2, e))) / (math.log(_t(p1, e)) - math.log(_t(p2, e)))
        af = self.a * _m(p1, e) / (n * _t(p1, e) ** n)
        return e, n, af, af * _t(p0, e) ** n

    def project(self, lat: float, lon: float) -> tuple[float, float]:
        e, n, af, r0 = self._cone
        r = af * _t(math.radians(lat), e) ** n
        theta = n * math.radians(lon - self.central_meridian)
        return self.false_easting + r * math.sin(theta), self.false_northing + r0 - r * math.cos(theta)

    def unproject(self, x: float, y: float) -> tuple[float, float]:
        """(lon, lat), as a Ring holds them."""
        e, n, af, r0 = self._cone
        dx, dy = x - self.false_easting, r0 - (y - self.false_northing)
        theta = math.atan2(dx, dy) if n > 0 else math.atan2(-dx, -dy)
        t = (math.copysign(math.hypot(dx, dy), n) / af) ** (1 / n)
        phi = math.pi / 2 - 2 * math.atan(t)
        for _ in range(6):
            s = e * math.sin(phi)
            phi = math.pi / 2 - 2 * math.atan(t * ((1 - s) / (1 + s)) ** (e / 2))
        return self.central_meridian + math.degrees(theta / n), math.degrees(phi)


_NUMBER = r"\s*([-+\d.eE]+)"


def read_prj(text: str) -> Lambert:
    """The projection a .prj (ESRI WKT) describes. Only a Lambert conformal conic with two
    standard parallels, in metres from Greenwich, is read; anything else is refused rather than
    misread, so a map in a new projection keeps the old one."""
    projection = re.search(r'PROJECTION\["([^"]+)"\]', text)
    if not projection or projection.group(1).lower() not in ("lambert_conformal_conic", "lambert_conformal_conic_2sp"):
        raise ValueError(f"the map's projection is {projection.group(1) if projection else 'missing'}, not Lambert "
                         "conformal conic")
    spheroid = re.search(rf'SPHEROID\["[^"]*",{_NUMBER},{_NUMBER}', text)
    primem = re.search(rf'PRIMEM\["[^"]*",{_NUMBER}\]', text)
    units = re.findall(rf'UNIT\["([^"]+)",{_NUMBER}\]', text)
    params = {name.lower(): float(value) for name, value in re.findall(rf'PARAMETER\["([^"]+)",{_NUMBER}\]', text)}
    if not units or units[-1][0].lower() not in ("meter", "metre") or float(units[-1][1]) != 1:
        raise ValueError("the map's projection isn't in metres")
    if not spheroid or (primem and float(primem.group(1)) != 0) or params.get("scale_factor", 1) != 1:
        raise ValueError("the map's projection has an ellipsoid, meridian or scale VoteBot can't read")
    try:
        return Lambert(
            a=float(spheroid.group(1)),
            inverse_flattening=float(spheroid.group(2)),
            false_easting=params["false_easting"],
            false_northing=params["false_northing"],
            central_meridian=params["central_meridian"],
            parallel_1=params["standard_parallel_1"],
            parallel_2=params["standard_parallel_2"],
            origin_latitude=params["latitude_of_origin"],
        )
    except KeyError as exc:
        raise ValueError(f"the map's projection has no {exc.args[0]}") from None


# -- the shapefile ----------------------------------------------------------------------------


def _unpack(fmt: str, data: bytes) -> tuple[Any, ...]:
    """struct.unpack, with a file cut short being a ValueError like any other bad map."""
    try:
        return struct.unpack(fmt, data)
    except struct.error:
        raise ValueError("the map's files are cut short") from None


@dataclass(frozen=True, slots=True)
class Record:
    county: int  # FIPS, as Place.county_fips
    code: str  # the county's name for the precinct, as the map writes it ("0300")
    offset: int  # where its shape starts in the .shp
    bbox: BBox


def read_dbf(path: Path) -> list[tuple[int, str] | None]:
    """Each record's CNTY and PREC, in order; None for a record marked deleted."""
    with path.open("rb") as fh:
        count, header_length, record_length = _unpack("<IHH", fh.read(32)[4:12])
        fields: dict[str, tuple[int, int]] = {}
        start = 1  # each record begins with its deletion flag
        while (field := fh.read(32)) and field[0] != 0x0D:
            fields[field[:11].split(b"\0", 1)[0].decode("ascii", "replace").upper()] = (start, field[16])
            start += field[16]
        missing = [name for name in FIELDS if name not in fields]
        if missing:
            raise ValueError(f"the map has no {' or '.join(missing)} field")
        fh.seek(header_length)
        data = fh.read(count * record_length)
    (c0, c_len), (p0, p_len) = fields["CNTY"], fields["PREC"]
    rows: list[tuple[int, str] | None] = []
    for i in range(0, count * record_length, record_length):
        if data[i:i + 1] == b"*":
            rows.append(None)
            continue
        county = data[i + c0:i + c0 + c_len].decode("ascii", "replace").strip()
        try:
            rows.append((int(float(county)), data[i + p0:i + p0 + p_len].decode("utf-8", "replace").strip()))
        except ValueError:
            raise ValueError(f"the map's CNTY {county!r} isn't a county code") from None
    return rows


def read_offsets(path: Path) -> list[int]:
    """Where each record starts in the .shp, from the .shx."""
    data = path.read_bytes()
    return [2 * struct.unpack_from(">i", data, i)[0] for i in range(100, len(data) - 7, 8)]


def read_index(shp: Path, shx: Path, dbf: Path) -> dict[int, list[Record]]:
    """Every precinct's record, by county. Only polygons (shape type 5) are read."""
    rows = read_dbf(dbf)
    offsets = read_offsets(shx)
    if len(rows) != len(offsets):
        raise ValueError(f"the map's .dbf has {len(rows)} records and its .shx {len(offsets)}")
    index: dict[int, list[Record]] = {}
    with shp.open("rb", buffering=1 << 20) as fh:  # records come in order, so most seeks stay in the buffer
        for row, offset in zip(rows, offsets):
            fh.seek(offset + 8)
            shape, *bbox = _unpack("<i4d", fh.read(36))
            if row is None or shape == 0:  # deleted, or a null shape
                continue
            if shape != 5:
                raise ValueError(f"the map has a shape of type {shape}, not polygons (5)")
            index.setdefault(row[0], []).append(Record(row[0], row[1], offset, tuple(bbox)))
    if not index:
        raise ValueError("the map has no precincts")
    return index


def read_rings(fh: BinaryIO, offset: int) -> list[Ring]:
    """One record's parts, outer rings and holes alike, as (x, y) in the map's projection."""
    fh.seek(offset + 44)
    parts_count, points_count = _unpack("<ii", fh.read(8))
    parts = _unpack(f"<{parts_count}i", fh.read(4 * parts_count))
    flat = _unpack(f"<{2 * points_count}d", fh.read(16 * points_count))
    points = list(zip(flat[0::2], flat[1::2]))
    return [points[start:end] for start, end in zip(parts, (*parts[1:], points_count))]


def contains(rings: list[Ring], x: float, y: float) -> bool:
    """Even-odd over every ring, so holes and pieces need no telling apart."""
    return sum(_inside(x, y, ring) for ring in rings) % 2 == 1


def display_name(code: str) -> str:
    """How the precinct is written for the voter: "0300" is 300; "101A" stays as it is."""
    return (code.lstrip("0") or "0") if code.isdigit() else code


def interior_points(rings: list[Ring], inset: float, *, most: int = 16) -> list[tuple[float, float]]:
    """Points spread through the rings (even-odd), each at least ``inset`` from every edge, in the
    rings' own units: a 9×9 grid over their box, or 27×27 when that finds none, at most ``most``
    of them, taken evenly. Empty for a shape too small or narrow."""
    xs = [x for ring in rings for x, _ in ring]
    ys = [y for ring in rings for _, y in ring]
    if not xs:
        return []
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    edges = [(a, b) for ring in rings for a, b in zip(ring, [*ring[1:], ring[0]])]
    for grid in (9, 27):
        found = [
            (x, y)
            for i in range(grid) for j in range(grid)
            if contains(rings, x := x0 + (i + 0.5) * (x1 - x0) / grid, y := y0 + (j + 0.5) * (y1 - y0) / grid)
            and all(_offset((x, y), a, b) >= inset for a, b in edges)
        ]
        if found:
            return found[::-(-len(found) // most)]
    return []


# -- the portal's index ---------------------------------------------------------------------


@dataclass(frozen=True)
class Resource:
    """A map the portal lists."""

    name: str  # "Precincts26P.zip"
    url: str
    description: str  # "2026 Primary Election Voting Precincts Shapefile"
    created: str
    last_modified: str
    size: int  # bytes, which the download must match

    @property
    def label(self) -> str:
        return re.sub(r"\s*shapefile\s*$", "", self.description, flags=re.IGNORECASE) or self.name

    @property
    def primary(self) -> bool:
        return "primary" in self.description.lower()

    @property
    def rank(self) -> tuple[int, bool, str]:
        """Newest last: the election's year, a general's map after a primary's, then the upload,
        so an older election's map uploaded later doesn't win."""
        year = re.search(r"\b(?:19|20)\d\d\b", self.description)
        return int(year.group()) if year else 0, not self.primary, self.created

    def newer_than(self, other: Resource) -> bool:
        return self.rank > other.rank or (self.name == other.name and self.last_modified > other.last_modified)


def index_spec() -> RequestSpec:
    return RequestSpec("GET", INDEX_URL, params={"id": DATASET})


def newest(index: Any) -> Resource | None:
    """The newest map the portal's index lists: a shapefile zip on the portal itself."""
    found = []
    resources = ((index.get("result") if isinstance(index, dict) else None) or {}).get("resources") or []
    for item in resources:
        url = str(item.get("url") or "")
        where = urlsplit(url)
        if str(item.get("format") or "").upper() != "SHP" or not where.path.lower().endswith(".zip"):
            continue
        if where.scheme != "https" or where.hostname != HOST:
            continue
        try:
            size = int(item.get("size") or 0)
        except (TypeError, ValueError):
            continue
        if size > 0:
            found.append(Resource(
                name=str(item.get("name") or where.path.rsplit("/", 1)[-1]),
                url=url,
                description=str(item.get("description") or ""),
                created=str(item.get("created") or ""),
                last_modified=str(item.get("last_modified") or ""),
                size=size,
            ))
    return max(found, key=lambda resource: resource.rank, default=None)


# -- answers --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Found:
    code: str  # as the map writes it ("0300"): asks for the outline
    name: str  # as the voter reads it ("300")
    county: int
    label: str  # the map's: "2026 Primary Election Voting Precincts"
    primary: bool  # a primary's map, which normally carries over to the general


@dataclass(frozen=True)
class Answer:
    found: Found | None = None
    between: tuple[str, ...] = ()  # the two precincts an address near a line could be in
    reason: str | None = None  # why nothing was found: "between" or "outside"
    codes: tuple[str, ...] = ()  # as the map writes them: the precinct found, or the two near a line


class StillDownloading(Exception):
    """The first map is still downloading; it carries on, and a later lookup has it."""

    def __init__(self, size: int):
        super().__init__(f"the precinct map ({size:,} bytes) is still downloading")
        self.size = size


@dataclass(frozen=True)
class Stored:
    """The map kept, as map.json describes it."""

    resource: Resource
    stem: str  # its files are <stem>.shp, .shx and .dbf
    downloaded_at: float
    projection: Lambert

    def file(self, folder: Path, ext: str) -> Path:
        return folder / f"{self.stem}.{ext}"


def _failed_flag(resource: Resource) -> str:
    return f"failed:{SOURCE}:{resource.name}:{resource.last_modified}"


def _members(archive: zipfile.ZipFile) -> dict[str, str]:
    """The zip's .shp, .shx, .dbf and .prj, which must share one name."""
    found: dict[str, dict[str, str]] = {}
    for name in archive.namelist():
        stem, dot, ext = name.rpartition(".")
        if dot and ext.lower() in (*SHAPEFILE, "prj"):
            found.setdefault(stem, {})[ext.lower()] = name
    complete = [files for files in found.values() if len(files) == len(SHAPEFILE) + 1]
    if len(complete) != 1:
        raise ValueError("the download isn't one shapefile with its .shp, .shx, .dbf and .prj")
    return complete[0]


def _retrieved(task: asyncio.Future[None]) -> None:
    if not task.cancelled():
        task.exception()  # marked retrieved even if no one waited for it


class ElectionPrecincts:
    """The map kept in ``folder``. map.json names it, and its files sit beside it under a name of
    their own, so a new map takes over when map.json is rewritten. Reads take ``_lock`` and open
    the .shp each time, so a swap or a Clear never meets an open file.

    One download runs at a time, whoever starts it. One that fails isn't started again by a
    lookup until the index lists a changed map, or for a week (15 minutes while no map is kept);
    Refresh always tries."""

    def __init__(self, cache: HttpCache, ttl: Ttls, folder: Path, *, first_wait: float = FIRST_WAIT):
        self.cache = cache
        self.ttl = ttl
        self.folder = folder
        self.first_wait = first_wait
        self.last_error: str | None = None  # why the last download failed, until one succeeds
        self._lock = threading.Lock()
        self._stored: Stored | None = None
        self._index: dict[int, list[Record]] | None = None
        self._outlines: dict[tuple[int, str], list[Ring]] = {}
        self._interiors: dict[tuple[int, str, float], list[tuple[float, float]]] = {}
        self._task: asyncio.Future[None] | None = None
        cache.pause_on(SOURCE, REFUSALS, ttl.election_precincts_backoff)
        self._tidy()

    # -- lookups ----------------------------------------------------------------------------

    async def at(self, county: int, point: tuple[float, float], block: tuple[float, float] | None) -> Answer:
        """The precinct of an address in ``county`` (FIPS): the one that holds its point and its
        census block's internal point (lat, lon). Without a block point, the address's alone.
        Raises StillDownloading while the first map downloads, UpstreamError when the portal
        can't be asked and no map is kept, and OSError or ValueError when the map can't be read."""
        stored = await self._ready()
        stats = current_calls()
        if stats:
            stats.used(SOURCE, stored.downloaded_at)
        return await asyncio.to_thread(self._locate, county, point, block)

    async def outline(self, county: int, code: str) -> list[Ring] | None:
        """The precinct's rings in lon/lat, simplified to SIMPLIFY_DEG once and kept; None when no
        map is kept or it has no such precinct. Never downloads."""
        kept = self._outlines.get((county, code))
        return kept if kept is not None else await asyncio.to_thread(self._outline, county, code)

    async def codes(self, county: int) -> frozenset[str]:
        """The codes of the county's precincts on the map kept ("0300"). Raises ValueError when no
        map is kept."""
        return await asyncio.to_thread(self._codes, county)

    async def interior(self, county: int, code: str, inset: float) -> list[tuple[float, float]]:
        """Points spread through the precinct, each at least ``inset`` metres from its edges, as
        (lon, lat): what a county's maps of its commissioner and JP precincts are checked
        against. Worked out once from the full map and kept; empty when the precinct is too
        small or narrow. Raises ValueError when no map is kept."""
        kept = self._interiors.get((county, code, inset))
        return kept if kept is not None else await asyncio.to_thread(self._interior, county, code, inset)

    def _locate(self, county: int, point: tuple[float, float], block: tuple[float, float] | None) -> Answer:
        with self._lock:
            stored, index = self._loaded()
            records = index.get(county, [])
            with stored.file(self.folder, "shp").open("rb") as fh:

                def holding(lat: float, lon: float) -> set[str]:
                    x, y = stored.projection.project(lat, lon)
                    return {
                        r.code for r in records
                        if r.bbox[0] <= x <= r.bbox[2] and r.bbox[1] <= y <= r.bbox[3]
                        and contains(read_rings(fh, r.offset), x, y)
                    }

                mine = holding(*point)
                theirs = holding(*block) if block else mine
        if len(mine) != 1 or len(theirs) != 1:
            return Answer(reason="outside")
        if mine != theirs:
            return Answer(between=(display_name(*mine), display_name(*theirs)), reason="between",
                          codes=(*mine, *theirs))
        (code,) = mine
        found = Found(code, display_name(code), county, stored.resource.label, stored.resource.primary)
        return Answer(found, codes=(code,))

    def _rings(self, county: int, code: str) -> tuple[Stored, list[Ring]] | None:
        """The precinct's rings in the map's projection, from the full map; None when no map is
        kept or it has no such precinct."""
        with self._lock:
            if self._stored_now() is None:
                return None
            stored, index = self._loaded()
            records = [r for r in index.get(county, ()) if r.code == code]
            if not records:
                return None
            with stored.file(self.folder, "shp").open("rb") as fh:
                return stored, [ring for r in records for ring in read_rings(fh, r.offset)]

    def _outline(self, county: int, code: str) -> list[Ring] | None:
        found = self._rings(county, code)
        if found is None:
            return None
        stored, rings = found
        lonlat = ([stored.projection.unproject(x, y) for x, y in ring] for ring in rings)
        outline = [ring for ring in (simplify(ring, SIMPLIFY_DEG) for ring in lonlat) if len(ring) >= 4]
        with self._lock:
            if self._stored is stored:  # not when a newer map or a Clear came meanwhile
                self._outlines[(county, code)] = outline
        return outline

    def _codes(self, county: int) -> frozenset[str]:
        with self._lock:
            _, index = self._loaded()
            return frozenset(r.code for r in index.get(county, ()))

    def _interior(self, county: int, code: str, inset: float) -> list[tuple[float, float]]:
        found = self._rings(county, code)
        if found is None:
            raise ValueError(f"the precinct map has no precinct {code} in county {county}")
        stored, rings = found
        points = [stored.projection.unproject(x, y) for x, y in interior_points(rings, inset)]
        with self._lock:
            if self._stored is stored:
                self._interiors[(county, code, inset)] = points
        return points

    def _loaded(self) -> tuple[Stored, dict[int, list[Record]]]:
        """The map kept and its index, read once; the caller holds _lock."""
        stored = self._stored_now()
        if stored is None:
            raise ValueError("no precinct map is kept")
        if self._index is None:
            self._index = read_index(*(stored.file(self.folder, ext) for ext in SHAPEFILE))
        return stored, self._index

    # -- the map kept -----------------------------------------------------------------------

    def stored(self) -> Stored | None:
        """The map kept. Once known, without waiting for _lock, so the event loop never waits on a
        thread reading the map."""
        stored = self._stored
        if stored is not None:
            return stored
        with self._lock:
            return self._stored_now()

    def _stored_now(self) -> Stored | None:
        """map.json, read once, if its files are there; the caller holds _lock."""
        if self._stored is None:
            try:
                raw = json.loads((self.folder / MAP_FILE).read_text(encoding="utf-8"))
                stored = Stored(Resource(**raw["resource"]), raw["stem"], float(raw["downloaded_at"]),
                                Lambert(**raw["projection"]))
            except (OSError, ValueError, KeyError, TypeError):
                return None
            if all(stored.file(self.folder, ext).exists() for ext in SHAPEFILE):
                self._stored = stored
        return self._stored

    def downloaded_at(self) -> float | None:
        stored = self.stored()
        return stored.downloaded_at if stored else None

    def size(self) -> int:
        """Bytes in the folder, a download under way included."""
        if not self.folder.exists():
            return 0
        return sum(p.stat().st_size for p in self.folder.iterdir() if p.is_file())

    @property
    def busy(self) -> bool:
        """A download running, whoever started it."""
        return self._task is not None and not self._task.done()

    def newest_listed(self) -> Resource | None:
        """The newest map in the index VoteBot has kept, without asking the portal (for Settings)."""
        kept = self.cache.peek(index_spec())
        return newest(kept.value) if kept else None

    def clear(self) -> str:
        """Remove the map; the next lookup downloads it again. Settings refuses while downloading."""
        with self._lock:
            self._stored, self._index, self._outlines, self._interiors = None, None, {}, {}
            if self.folder.exists():
                for path in self.folder.iterdir():
                    if path.is_file():
                        path.unlink(missing_ok=True)
        self.last_error = None
        return "The precinct map will be downloaded again on the next lookup."

    def _tidy(self) -> None:
        """Remove what an interrupted download or swap left behind."""
        stored = self.stored()
        keep = {MAP_FILE, *(stored.file(self.folder, ext).name for ext in SHAPEFILE)} if stored else {MAP_FILE}
        if self.folder.exists():
            for path in self.folder.iterdir():
                if path.is_file() and path.name not in keep:
                    path.unlink(missing_ok=True)

    # -- Settings (KeptSource) ----------------------------------------------------------------

    def notice(self) -> tuple[str, Tone] | None:
        if self.busy:
            return "Downloading the precinct map…", "info"
        if self.last_error:
            kept = "the map kept still shows" if self.stored() else "Refresh tries again"
            return f"The last download of the precinct map failed ({self.last_error}); {kept}.", "warn"
        return None

    def details(self) -> list[Fact]:
        stored, listed = self.stored(), self.newest_listed()
        kept = (
            f"“{stored.resource.label}”, downloaded {display_time(stored.downloaded_at)} · {display_size(self.size())}"
            if stored else "downloaded on the first lookup"
        )
        return [
            Fact(label="Map kept", value=kept),
            Fact(label="Newest on the portal", value=f"“{listed.label}” · {display_size(listed.size)}" if listed else "not asked yet"),
        ]

    def refresh_size(self) -> int | None:
        listed = self.newest_listed()
        return listed.size if listed else None

    async def refresh(self) -> str:
        """update(), with a failure worded for Settings."""
        try:
            return await self.update()
        except (UpstreamError, OSError, ValueError, zipfile.BadZipFile) as exc:  # nothing was replaced
            why = str(exc).removeprefix(f"{SOURCE}: ")
            kept = "kept the old one" if self.stored() else "the next lookup will try again later"
            raise RefreshFailed(f"Couldn't download the precinct map ({why}); {kept}.") from exc

    # -- downloading ------------------------------------------------------------------------

    async def update(self) -> str:
        """For Refresh: download the newest map if it's newer than the one kept, even one that
        failed before, and say what happened."""
        resource = await self._newest()
        if resource is None:
            return "The Texas Legislative Council's portal lists no precinct map."
        stored = await asyncio.to_thread(self.stored)
        if stored and not resource.newer_than(stored.resource):
            return f"The precinct map “{stored.resource.label}” is already the newest."
        await asyncio.shield(self._start(resource))
        return f"Downloaded the precinct map “{resource.label}” ({resource.size / 1_048_576:.1f} MB)."

    async def aclose(self) -> None:
        """Stop a download still running (at shutdown); its partial file is removed. One already
        unpacking finishes in its thread, which then removes the zip."""
        task, self._task = self._task, None
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def _newest(self) -> Resource | None:
        got = await self.cache.get_json(SOURCE, index_spec(), ttl=self.ttl.election_precincts)
        return newest(got.value)

    async def _ready(self) -> Stored:
        """The map kept, after starting a newer one's download in the background; with none kept,
        the first one, waited for up to ``first_wait`` seconds by the lookup that starts it."""
        stored = await asyncio.to_thread(self.stored)
        if stored:
            try:
                resource = await self._newest()
            except UpstreamError:
                return stored
            if resource and resource.newer_than(stored.resource) and not self._failed(resource):
                self._start(resource)
            return stored
        resource = await self._newest()
        if resource is None:
            raise ValueError("the Texas Legislative Council's portal lists no precinct map")
        if self.busy:  # only the lookup that starts it waits: a reload meanwhile goes on at once
            raise StillDownloading(resource.size)
        if self._failed(resource):
            until = self.cache.flag_until(_failed_flag(resource))
            raise UpstreamError(SOURCE, f"the last download failed ({self.last_error or 'see Settings'}); "
                                        f"VoteBot tries again after {display_time(until)}")
        task = self._start(resource)
        try:
            await asyncio.wait_for(asyncio.shield(task), self.first_wait)
        except asyncio.TimeoutError:
            raise StillDownloading(resource.size) from None
        stored = await asyncio.to_thread(self.stored)
        if stored is None:
            raise ValueError("the precinct map was cleared")
        return stored

    def _failed(self, resource: Resource) -> bool:
        return self.cache.flag_until(_failed_flag(resource)) is not None

    def _start(self, resource: Resource) -> asyncio.Future[None]:
        """The download running, or a new one of ``resource``."""
        if not self.busy:
            self._task = asyncio.ensure_future(self._download(resource))
            self._task.add_done_callback(_retrieved)
        return self._task

    async def _download(self, resource: Resource) -> None:
        """Fetch ``resource``, check it, and put it in place of the map kept. On any failure the
        map kept stays, and a lookup won't start ``resource`` again for a while."""
        self.folder.mkdir(parents=True, exist_ok=True)
        part = self.folder / f".{uuid.uuid4().hex}.zip.part"
        try:
            try:
                got = await self.cache.download(SOURCE, RequestSpec("GET", resource.url), part,
                                                max_bytes=resource.size, hosts={HOST})
                if got != resource.size:
                    raise ValueError(f"the download was {got:,} bytes, not the {resource.size:,} the portal lists")
            except BaseException:
                part.unlink(missing_ok=True)
                raise
            # Cancelling (shutdown) can't stop a thread, so the thread removes the zip once it's unpacked.
            await asyncio.to_thread(self._install, resource, part)
        except Exception as exc:
            known = isinstance(exc, (UpstreamError, OSError, ValueError, zipfile.BadZipFile))
            error = exc if known else ValueError(f"the map couldn't be unpacked ({type(exc).__name__}: {exc})")
            self.last_error = str(error).removeprefix(f"{SOURCE}: ")
            refused = isinstance(exc, UpstreamError) and (exc.until or exc.status in REFUSALS)
            if not refused:  # a refusal pauses the whole source instead
                wait = self.ttl.election_precincts if self.stored() else self.ttl.retry_after
                self.cache.set_flag(_failed_flag(resource), SOURCE, wait)
            if known:
                raise
            raise error from exc
        self.last_error = None

    def _install(self, resource: Resource, part: Path) -> None:
        """Check the zip and unpack it under a new name, then point map.json at it and remove the
        old map, and the zip. Until map.json is rewritten, the map kept is untouched."""
        try:
            self._unzip(resource, part)
        finally:
            part.unlink(missing_ok=True)

    def _unzip(self, resource: Resource, part: Path) -> None:
        stem = f"{Path(resource.name).stem}-{uuid.uuid4().hex[:8]}"
        new = {ext: self.folder / f"{stem}.{ext}" for ext in SHAPEFILE}
        try:
            with zipfile.ZipFile(part) as archive:
                members = _members(archive)
                if sum(archive.getinfo(members[ext]).file_size for ext in SHAPEFILE) > 4 * resource.size:
                    raise ValueError("the download unpacks to more than 4 times its size")
                projection = read_prj(archive.read(members["prj"]).decode("utf-8", "replace"))
                for ext, path in new.items():
                    with archive.open(members[ext]) as source, path.open("wb") as target:
                        shutil.copyfileobj(source, target, 1 << 20)
            index = read_index(*new.values())
        except BaseException:
            for path in new.values():
                path.unlink(missing_ok=True)
            raise
        stored = Stored(resource, stem, time.time(), projection)
        with self._lock:
            old = self._stored_now()
            write_text_atomic(self.folder / MAP_FILE, json.dumps({
                "resource": asdict(resource), "stem": stem, "downloaded_at": stored.downloaded_at,
                "projection": asdict(projection),
            }, indent=1) + "\n")
            self._stored, self._index, self._outlines, self._interiors = stored, index, {}, {}
            if old and old.stem != stem:
                for ext in SHAPEFILE:
                    old.file(self.folder, ext).unlink(missing_ok=True)
