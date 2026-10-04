"""Commissioner and justice of the peace precincts, from the county's own records of its
election precincts.

Election Code §42.005 keeps each election precinct inside one commissioner precinct and one
justice precinct, so the election precinct found on the Texas Legislative Council's map settles
both. There's no statewide list: each county publishes its own, on its own ArcGIS server. Most
of these publish a table, a row per election precinct with its commissioner and JP precincts,
which must list exactly the map's precincts, or it could be another year's. A county that only
publishes maps of its commissioner and JP precincts gets points spread through the election
precinct, kept INSET_M from its edges, which must all fall in one of them.

Each county's service and layer are found by name, newest year first, never a proposal, and
downloaded whole, cached like any request, so nothing about the voter is sent.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Literal

from ..config import Ttls
from ..http_cache import Cached, HttpCache, RequestSpec, UpstreamError
from . import arcgis_error
from .election_precincts import ElectionPrecincts, contains, display_name
from .sboe import Ring

SOURCE = "county_precincts"
LABEL = "Commissioner & JP precincts"
REFUSALS = (403, 429)  # answers that pause every county's server for Ttls.county_precincts_backoff
INSET_M = 50.0  # metres from the precinct's edges: against Dallas's and Harris's lists, 3 wrong at 10 m, none at 25
PAGE = 1000  # rows asked for at a time
MOST_PAGES = 20
COMMISSIONER, JP = "commissioner", "jp"
TOP = {COMMISSIONER: 4, JP: 99}  # the highest number each can have
KIND_NAMES = {COMMISSIONER: "commissioner", JP: "justice of the peace"}
_UNADOPTED = re.compile(r"proposed|draft", re.IGNORECASE)
_NUMBER = re.compile(r"[A-Za-z]{0,3}\s*0*(\d{1,2})")  # "3", "03", "P03" (Travis's commissioner), "J03" (its JP)

Method = Literal["table", "maps"]


@dataclass(frozen=True)
class Layer:
    """Where a county keeps a layer: the REST folder listing its services, the service's name and
    type, and the layer's name in it. Names are patterns for the whole name, in any case; a group
    in one, a year, ranks the vintages, newest first."""

    folder: str
    service: str
    server: str  # "FeatureServer" or "MapServer"
    name: str = ".*"


@dataclass(frozen=True)
class Table:
    """A layer with a row per election precinct, and the fields holding its numbers."""

    layer: Layer
    precinct: str
    commissioner: str
    jp: str | None = None  # None: the county publishes no JP precinct per election precinct


@dataclass(frozen=True)
class Areas:
    """A layer of a county's commissioner or JP precincts as polygons, and the field holding each
    one's number."""

    layer: Layer
    number: str


@dataclass(frozen=True)
class County:
    fips: int
    name: str
    table: Table | None = None
    commissioner: Areas | None = None  # maps, for counties whose table doesn't have the field
    jp: Areas | None = None

    @property
    def method(self) -> Method:
        return "table" if self.table else "maps"


COUNTIES = {county.fips: county for county in (
    County(201, "Harris", Table(
        Layer("https://services.arcgis.com/su8ic9KbA7PYVxPS/arcgis/rest/services", r"VPCTs_(\d{4})", "FeatureServer"),
        "VPCT_txt", "Comm__Cour", "JP_Constab")),
    County(113, "Dallas", Table(
        Layer("https://services3.arcgis.com/zqe2kwz79KUqUvxC/arcgis/rest/services", r"Election_Precincts_(\d{4})",
              "FeatureServer"),
        "NewPrcnt", "Comm", "JP")),
    County(439, "Tarrant", Table(
        Layer("https://mapit.tarrantcounty.com/arcgis/rest/services/Dynamic", "Dynamic/VotingPrecinct", "MapServer",
              "Voting Precincts"),
        "Pct_Char", "Commish", "JP")),
    County(453, "Travis", Table(
        Layer("https://taxmaps.traviscountytx.gov/arcgis/rest/services", "Precincts", "FeatureServer"),
        "Precinct", "Commissioner", "JPConstable")),
    # Fort Bend's JP precincts aren't published by election precinct, or as a public map.
    County(157, "Fort Bend", Table(
        Layer("https://gisportal.fortbendcountytx.gov/arcgis/rest/services/InteractiveMap",
              "InteractiveMap/Elections_Public", "FeatureServer", r"Voter Precincts (\d{4})"),
        "PRECINCTID", "COMM_PRECI")),
    County(29, "Bexar",
           commissioner=Areas(Layer("https://maps.bexar.org/arcgis/rest/services", "CommissionerPrecincts", "MapServer",
                                    "Commissioner Precincts"), "Comm"),
           jp=Areas(Layer("https://maps.bexar.org/arcgis/rest/services", "JusticeofthePeace", "MapServer", "Precincts"),
                    "Precinct")),
    # Denton's precinct layer has a "Comm" field, but it's the precinct number's first digit (9 for 9100 to 9304).
    County(121, "Denton",
           commissioner=Areas(Layer("https://gis.dentoncounty.gov/arcgis/rest/services", "PoliticalBoundaries_GC",
                                    "MapServer", "Commissioner Precincts"), "COMMISH"),
           jp=Areas(Layer("https://gis.dentoncounty.gov/arcgis/rest/services", "PoliticalBoundaries_GC", "MapServer",
                          "JP / Constable"), "JP_C")),
)}
DESCRIPTION = (
    "Your commissioner and justice of the peace precincts, from your election precinct and your county's own records: "
    "the lists of their election precincts that Harris, Dallas, Tarrant, Travis and Fort Bend counties publish (Fort "
    "Bend's has commissioner precincts only), and Bexar and Denton counties' maps of their commissioner and JP "
    "precincts. A county's list or maps are downloaded whole, at most once a week, when you look up an address there; "
    "your address is never sent. Needs \"Election precincts\" on."
)


@dataclass(frozen=True)
class Area:
    number: int
    rings: list[Ring]  # (lon, lat), outer rings and holes alike
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class Found:
    """What the county's records settle for the voter's election precinct."""

    county: County
    numbers: dict[str, int]  # "commissioner", "jp"
    unsettled: dict[str, str]  # kind -> why not, as the start of a sentence


def number(value: Any, top: int) -> int | None:
    """A precinct's number as a county writes it: 3, 3.0, "3", "03", "P03" or "J03"; None unless
    it's 1 to ``top``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        found = int(value) if float(value).is_integer() else None
    else:
        match = _NUMBER.fullmatch(str(value or "").strip())
        found = int(match.group(1)) if match else None
    return found if found is not None and 1 <= found <= top else None


def _text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return "" if value is None else str(value).strip()


def pick(items: Any, pattern: str, *, server: str | None = None) -> dict[str, Any] | None:
    """The newest of a listing's services (of type ``server``) or a service's layers whose name
    matches ``pattern``, ranked by its group (a year); never a proposal or a draft."""
    best, best_rank = None, -1
    for item in items if isinstance(items, list) else ():
        name = str(item.get("name") or "") if isinstance(item, dict) else ""
        match = re.fullmatch(pattern, name, re.IGNORECASE)
        if not match or _UNADOPTED.search(name) or (server and item.get("type") != server):
            continue
        rank = int(match.group(1)) if match.groups() and (match.group(1) or "").isdigit() else 0
        if rank > best_rank:
            best, best_rank = item, rank
    return best


def services_root(folder: str) -> str:
    """ "https://host/arcgis/rest/services" from a folder's address under it."""
    end = folder.find("/rest/services")
    return folder[:end + len("/rest/services")] if end >= 0 else folder


def read_table(county: County, table: Table, rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Each election precinct's numbers, by its name as the voter reads it ("300"). The whole table
    is refused (ValueError) for a row without a precinct, a number out of range, or a precinct
    listed twice with different numbers."""
    fields = {COMMISSIONER: table.commissioner, **({JP: table.jp} if table.jp else {})}
    found: dict[str, dict[str, int]] = {}
    for row in rows:
        name = display_name(_text(row.get(table.precinct)))
        if not name:
            raise ValueError(f"{county.name} County's list of election precincts has a row without a precinct")
        numbers = {}
        for kind, field in fields.items():
            numbers[kind] = number(row.get(field), TOP[kind])
            if numbers[kind] is None:
                raise ValueError(f"{county.name} County's list gives precinct {name} {KIND_NAMES[kind]} precinct "
                                 f"{row.get(field)!r}")
        if found.setdefault(name, numbers) != numbers:
            raise ValueError(f"{county.name} County's list has precinct {name} twice, with different numbers")
    return found


def same_precincts(county: County, table: dict[str, dict[str, int]], codes: frozenset[str]) -> None:
    """Refuse (ValueError) a list that isn't of the precinct map's precincts: another year's could
    put a voter in a precinct with the same name somewhere else."""
    mine = {display_name(code) for code in codes}
    if set(table) != mine:
        only_list, only_map = len(set(table) - mine), len(mine - set(table))
        raise ValueError(f"{county.name} County's list of election precincts isn't the precinct map's ({only_list} only "
                         f"on its list, {only_map} only on the map), so it may be another year's")


def read_areas(county: County, kind: str, areas: Areas, features: list[dict[str, Any]]) -> list[Area]:
    """The county's commissioner or JP precincts as polygons; the whole map is refused (ValueError)
    for a feature without a number in range or without rings."""
    found = []
    for feature in features:
        value = (feature.get("attributes") or {}).get(areas.number)
        n = number(value, TOP[kind])
        rings = [[(float(x), float(y)) for x, y, *_ in ring]
                 for ring in (feature.get("geometry") or {}).get("rings") or [] if len(ring) >= 4]
        if n is None or not rings:
            what = f"precinct {value!r}" if n is None else f"precinct {n} without a shape"
            raise ValueError(f"{county.name} County's map of its {KIND_NAMES[kind]} precincts has {what}")
        xs, ys = [x for ring in rings for x, _ in ring], [y for ring in rings for _, y in ring]
        found.append(Area(n, rings, (min(xs), min(ys), max(xs), max(ys))))
    return found


def settle(areas: list[Area], points: list[tuple[float, float]]) -> int | str:
    """The number of the one area that holds every point, or why there's none: "small" (no
    points) or "straddles"."""
    if not points:
        return "small"
    found: set[int] = set()
    for lon, lat in points:
        found |= {
            area.number for area in areas
            if area.bbox[0] <= lon <= area.bbox[2] and area.bbox[1] <= lat <= area.bbox[3]
            and contains(area.rings, lon, lat)
        } or {0}  # in none of them
        if len(found) > 1 or 0 in found:
            return "straddles"
    return found.pop()


def _why(county: County, kind: str, reason: str) -> str:
    what = KIND_NAMES[kind]
    if reason == "small":
        return f"Your election precinct is too small to place on {county.name} County's map of its {what} precincts"
    if reason == "differ":
        return f"The two election precincts your address could be in are in different {what} precincts"
    return f"Your election precinct isn't wholly inside one of {county.name} County's {what} precincts on its map"


class CountyPrecincts:
    """The counties in ``counties``: their lists and maps, cached as responses, and kept parsed
    per stored copy, so each is read in a thread once."""

    def __init__(self, cache: HttpCache, ttl: Ttls, precincts: ElectionPrecincts,
                 counties: dict[int, County] = COUNTIES):
        self.cache = cache
        self.ttl = ttl
        self.precincts = precincts
        self.counties = counties
        self._parsed: dict[tuple[int, str], tuple[tuple[str, ...], Any]] = {}  # (county, what) -> (copies read, parsed)
        cache.pause_on(SOURCE, REFUSALS, ttl.county_precincts_backoff)
        cache.check_answers(SOURCE, arcgis_error)

    async def at(self, county_fips: int, codes: tuple[str, ...]) -> Found | None:
        """What the county's records say for the election precinct ``codes`` (as the precinct map
        writes it), or for the two an address near a line could be in, where a number counts
        only when both give it. None for a county Pallot has no records of. Raises
        UpstreamError when the county's server can't be asked, or answers an error, and nothing
        good is cached, and ValueError or OSError when its records or the precinct map can't be
        read."""
        county = self.counties.get(county_fips)
        if county is None or not codes:
            return None
        numbers: dict[str, int] = {}
        unsettled: dict[str, str] = {}

        def agree(kind: str, found: list[int | str]) -> None:
            if all(isinstance(n, int) for n in found) and len(set(found)) == 1:
                numbers[kind] = int(found[0])
            else:
                reason = next((n for n in found if isinstance(n, str)), "differ")
                unsettled[kind] = _why(county, kind, reason)

        if county.table:
            table = await self._table(county, county.table)
            same_precincts(county, table, await self.precincts.codes(county.fips))
            rows = [table[display_name(code)] for code in codes]
            for kind in rows[0]:
                agree(kind, [row[kind] for row in rows])
        for kind, areas in ((COMMISSIONER, county.commissioner), (JP, county.jp)):
            if areas is None or kind in numbers or kind in unsettled:
                continue
            shapes = await self._areas(county, kind, areas)
            found = []
            for code in codes:
                points = await self.precincts.interior(county.fips, code, INSET_M)
                found.append(await asyncio.to_thread(settle, shapes, points))
            agree(kind, found)
        return Found(county, numbers, unsettled)

    # -- fetching ---------------------------------------------------------------------------

    async def _get(self, county: County, spec: RequestSpec, part: str) -> Cached:
        """The answer to ``spec``, which must have ``part``. An ArcGIS error, answered with a 200,
        is refused by the cache's check (arcgis_error), so it never replaces a good copy."""
        try:
            got = await self.cache.get_json(SOURCE, spec, ttl=self.ttl.county_precincts)
        except UpstreamError as exc:
            message = str(exc).removeprefix(f"{SOURCE}: ")
            raise UpstreamError(SOURCE, f"{county.name} County's map server: {message}", exc.status, exc.until) from exc
        if not isinstance(got.value, dict) or not got.value.get(part):
            raise ValueError(f"{county.name} County's map server answered no {part}")
        return got

    async def _layer(self, county: County, layer: Layer) -> str:
        """The address of the newest layer ``layer`` describes."""
        listing = await self._get(county, RequestSpec("GET", layer.folder, params={"f": "json"}), "services")
        service = pick(listing.value["services"], layer.service, server=layer.server)
        if service is None:
            raise ValueError(f"{county.name} County's map server has no service named like {layer.service}")
        url = f"{services_root(layer.folder)}/{service['name']}/{layer.server}"
        info = await self._get(county, RequestSpec("GET", url, params={"f": "json"}), "layers")
        found = pick(info.value["layers"], layer.name)
        if found is None:
            raise ValueError(f"{county.name} County's {service['name']} has no layer named like {layer.name}")
        return f"{url}/{found['id']}"

    async def _features(
        self, county: County, layer: Layer, params: dict[str, str]
    ) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
        """Every feature of the layer, a page at a time, and which stored copies they came from."""
        url = await self._layer(county, layer)
        features: list[dict[str, Any]] = []
        copies: list[str] = []
        for _ in range(MOST_PAGES):
            spec = RequestSpec("GET", f"{url}/query", params={
                **params, "where": "1=1", "resultOffset": str(len(features)), "resultRecordCount": str(PAGE),
                "f": "json",
            })
            got = await self._get(county, spec, "features")
            features += got.value["features"]
            copies.append(f"{spec.key}@{got.fetched_at}")
            if not got.value.get("exceededTransferLimit"):
                return features, tuple(copies)
        raise ValueError(f"{county.name} County's layer has more than {MOST_PAGES * PAGE:,} features")

    async def _parse(self, county: County, what: str, copies: tuple[str, ...], read: Any, *args: Any) -> Any:
        """read(*args) in a thread, once per set of stored copies."""
        kept = self._parsed.get((county.fips, what))
        if kept and kept[0] == copies:
            return kept[1]
        parsed = await asyncio.to_thread(read, *args)
        self._parsed[(county.fips, what)] = (copies, parsed)
        return parsed

    async def _table(self, county: County, table: Table) -> dict[str, dict[str, int]]:
        fields = ",".join(f for f in (table.precinct, table.commissioner, table.jp) if f)
        features, copies = await self._features(county, table.layer, {
            "outFields": fields, "returnGeometry": "false", "orderByFields": table.precinct,
        })
        rows = [feature.get("attributes") or {} for feature in features]
        return await self._parse(county, "table", copies, read_table, county, table, rows)

    async def _areas(self, county: County, kind: str, areas: Areas) -> list[Area]:
        features, copies = await self._features(county, areas.layer, {
            "outFields": areas.number, "returnGeometry": "true", "outSR": "4326", "geometryPrecision": "6",
        })
        return await self._parse(county, kind, copies, read_areas, county, kind, areas, features)
