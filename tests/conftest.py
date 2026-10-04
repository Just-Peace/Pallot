"""Shared setup: recorded API responses (tests/fixtures, see scripts/record_fixtures.py)
served through respx, made-up SBOE and precinct maps and counties' lists of their precincts, and a
Pallot app on a temp data dir
with "today" pinned, no waits between calls to a source, an FEC API key, the TrackAIPAC,
Vote for Peace and Texas Ethics Commission fixture snapshots, and a made-up endorsement list
(tests/fixtures/endorsements) in place of the ones that come with Pallot."""

from __future__ import annotations

import copy
import datetime as dt
import functools
import io
import json
import re
import struct
import zipfile
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from pallot.api import create_app
from pallot.config import Config
from pallot.sources import ballotpedia, suggestions
from pallot.sources.census import normalize_address
from pallot.sources.election_precincts import read_prj

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = dt.date(2026, 9, 27)
FEC_KEY = "test-fec-key"
ADDRESSES = {
    "capitol": "1100 Congress Ave, Austin, TX 78701",
    "ut": "110 Inner Campus Dr, Austin, TX 78712",
    "harris": "1001 Preston St, Houston, TX 77002",
    "mopac": "13500 N Mopac Expy, Austin, TX 78728",
    "dc": "1600 Pennsylvania Ave NW, Washington, DC 20500",
    "hd93": "93 Test Lane, Austin, TX 78701",  # made up: the Capitol's geography, but State House District 93
}
SUGGEST = {"congress": "1100 congress ave", "duval": "4512 duval st"}  # as in scripts/record_fixtures.py
PNG = b"\x89PNG\r\n\x1a\n" + b"a map tile"  # what the tile server answers: only its bytes matter


@functools.cache
def fixture_bytes(name: str) -> bytes | None:
    """A recorded response, read from disk once per process; None if there's no such file."""
    path = FIXTURES / name
    return path.read_bytes() if path.exists() else None


def load(name: str) -> Any:
    raw = fixture_bytes(name)
    if raw is None:
        raise AssertionError(f"no fixture {name}")
    return json.loads(raw)


@functools.cache
def capitol_point() -> tuple[float, float]:
    coords = load("census_capitol.json")["result"]["addressMatches"][0]["coordinates"]
    return coords["y"], coords["x"]


def hd93_census() -> dict[str, Any]:
    data = copy.deepcopy(load("census_capitol.json"))
    geographies = data["result"]["addressMatches"][0]["geographies"]
    lower = next(name for name in geographies if "Legislative Districts - Lower" in name)
    geographies[lower][0]["BASENAME"] = "93"
    return data


@functools.cache
def sboe_zip() -> bytes:
    """A 15-district map: District 5 boxes in Austin, District 4 boxes in downtown Houston,
    the rest are tiny squares far away."""

    def placemark(number: int, x0: float, y0: float, x1: float, y1: float) -> str:
        ring = f"{x0},{y0},0 {x1},{y0},0 {x1},{y1},0 {x0},{y1},0 {x0},{y0},0"
        return (f"<Placemark><name>District {number}</name><MultiGeometry><Polygon><outerBoundaryIs>"
                f"<LinearRing><coordinates>{ring}</coordinates></LinearRing></outerBoundaryIs></Polygon>"
                "</MultiGeometry></Placemark>")

    marks = [placemark(5, -98.2, 30.0, -97.4, 30.7), placemark(4, -95.6, 29.6, -95.2, 29.9)]
    marks += [placemark(n, -104.0 + n * 0.1, 31.0, -103.95 + n * 0.1, 31.05) for n in range(1, 16) if n not in (4, 5)]
    kml = ('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
           + "".join(marks) + "</Document></kml>")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("PlanE2106.kml", kml)
    return buffer.getvalue()


# The Texas Legislative Council's precinct maps are in this projection (EPSG:3081); its .prj, as they ship it.
PRJ = (
    'PROJCS["NAD_1983_Lambert_Conformal_Conic",GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",'
    'SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Lambert_Conformal_Conic"],PARAMETER["False_Easting",1000000.0],PARAMETER["False_Northing",1000000.0],'
    'PARAMETER["Central_Meridian",-100.0],PARAMETER["Standard_Parallel_1",27.41666666666667],'
    'PARAMETER["Standard_Parallel_2",34.91666666666666],PARAMETER["Latitude_Of_Origin",31.16666666666667],'
    'UNIT["Meter",1.0]]'
)
PROJECTION = read_prj(PRJ)
TRAVIS, HARRIS, ANDERSON = 453, 201, 1  # county FIPS codes
# Where the made-up precincts are, besides the fixture addresses': (lat, lon).
TWO_PIECES = (30.35, -97.95)
HOLE = (30.40, -97.80)  # 0400, with 401A filling its hole
OVERLAP = (30.45, -97.85)  # 0500 and 0501 overlap east of here
LINE = (30.50, -97.80)  # 0600 west of here, 0601 east


def nudge(point: tuple[float, float], east: float = 0.0, north: float = 0.0) -> tuple[float, float]:
    """The (lat, lon) so many metres east and north of ``point``, in the precinct map's projection."""
    x, y = PROJECTION.project(*point)
    lon, lat = PROJECTION.unproject(x + east, y + north)
    return lat, lon


def census_points(name: str) -> tuple[tuple[float, float], tuple[float, float]]:
    """A recorded address's point, and its census block's internal point."""
    match = load(f"census_{name}.json")["result"]["addressMatches"][0]
    block = match["geographies"]["2020 Census Blocks"][0]
    return (match["coordinates"]["y"], match["coordinates"]["x"]), (float(block["INTPTLAT"]), float(block["INTPTLON"]))


def box(center: tuple[float, float], west: float, south: float, east: float, north: float) -> list[tuple[float, float]]:
    """A rectangle in metres around ``center``, clockwise as a shapefile's outer rings go."""
    x, y = PROJECTION.project(*center)
    return [(x - west, y - south), (x - west, y + north), (x + east, y + north), (x + east, y - south), (x - west, y - south)]


def square(center: tuple[float, float], half: float) -> list[tuple[float, float]]:
    return box(center, half, half, half, half)


def middle(points: tuple[tuple[float, float], ...]) -> tuple[float, float]:
    return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)


def precincts() -> list[tuple[int, str, list[list[tuple[float, float]]]]]:
    """(county, PREC, rings in metres): each exact fixture address's two points in one precinct,
    then a precinct in two pieces, one with a hole another fills, two that overlap and two
    that meet, and another county's precinct over the Capitol."""
    return [
        (TRAVIS, "0300", [square(middle(census_points("capitol")), 400)]),
        (TRAVIS, "0312", [square(middle(census_points("ut")), 300)]),
        (HARRIS, "0890", [square(middle(census_points("harris")), 400)]),
        (ANDERSON, "0001", [square(census_points("capitol")[0], 3000)]),
        (TRAVIS, "0101", [square(TWO_PIECES, 200), square(nudge(TWO_PIECES, 1000), 200)]),
        (TRAVIS, "0400", [square(HOLE, 1000), square(HOLE, 300)[::-1]]),
        (TRAVIS, "401A", [square(HOLE, 300)]),
        (TRAVIS, "0500", [square(OVERLAP, 300)]),
        (TRAVIS, "0501", [square(nudge(OVERLAP, 400), 300)]),
        (TRAVIS, "0600", [box(LINE, 600, 300, 0, 300)]),
        (TRAVIS, "0601", [box(LINE, 0, 300, 600, 300)]),
    ]


def precincts_zip(records: list[tuple[int, str, list[list[tuple[float, float]]]]] | None = None, *,
                  prj: str | None = PRJ, shape_type: int = 5) -> bytes:
    """A precinct map as the TLC zips it: .shp, .shx, .dbf (CNTY, COLOR and PREC), .prj and the
    files Pallot skips."""
    records = precincts() if records is None else records
    shapes, index, offset = [], [], 100
    for number, (_, _, rings) in enumerate(records, 1):
        points = [point for ring in rings for point in ring]
        starts = [sum(len(r) for r in rings[:i]) for i in range(len(rings))]
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        content = (struct.pack("<i4dii", shape_type, min(xs), min(ys), max(xs), max(ys), len(rings), len(points))
                   + struct.pack(f"<{len(starts)}i", *starts) + struct.pack(f"<{2 * len(points)}d", *sum(points, ())))
        shapes.append(struct.pack(">ii", number, len(content) // 2) + content)
        index.append(struct.pack(">ii", offset // 2, len(content) // 2))
        offset += 8 + len(content)

    def header(length: int) -> bytes:
        return struct.pack(">7i", 9994, 0, 0, 0, 0, 0, length // 2) + struct.pack("<2i8d", 1000, shape_type, *[0.0] * 8)

    fields = [("CNTY", b"N", 3), ("COLOR", b"N", 2), ("PREC", b"C", 6)]
    dbf = struct.pack("<4BIHH20x", 3, 126, 9, 30, len(records), 32 * (len(fields) + 1) + 1, 1 + sum(f[2] for f in fields))
    dbf += b"".join(struct.pack("<11sc4xBB14x", name.encode(), kind, length, 0) for name, kind, length in fields) + b"\r"
    dbf += b"".join(b" " + str(county).rjust(3).encode() + b" 1" + code.ljust(6).encode() for county, code, _ in records)
    files = {
        "Precincts26P.shp": header(offset) + b"".join(shapes),
        "Precincts26P.shx": header(100 + 8 * len(index)) + b"".join(index),
        "Precincts26P.dbf": dbf + b"\x1a",
        "Precincts26P.cpg": b"UTF-8",
        "Precincts26P.shp.xml": b"<metadata/>",
    }
    if prj is not None:
        files["Precincts26P.prj"] = prj.encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


@functools.cache
def election_precincts_zip() -> bytes:
    return precincts_zip()


# The made-up map's Travis and Harris precincts in each county's list of them: election precinct ->
# (commissioner, JP). The Capitol's 300 is in JP precinct 5, as Ballotpedia has it; 600 and 601,
# either side of LINE, share a commissioner precinct and not a JP one.
TRAVIS_LIST = {"300": (2, 5), "312": (1, 2), "101": (3, 3), "400": (4, 4), "401A": (4, 4), "500": (2, 1), "501": (2, 1),
               "600": (3, 3), "601": (3, 4)}
HARRIS_LIST = {"0890": (1, 1)}
TRAVIS_QUERY = "/arcgis/rest/services/Precincts/FeatureServer/0/query"
HARRIS_QUERY = "/su8ic9KbA7PYVxPS/arcgis/rest/services/VPCTs_2026/FeatureServer/2/query"


def travis_rows(numbers: dict[str, tuple[Any, Any]] = TRAVIS_LIST) -> list[dict[str, Any]]:
    """Travis County's list as its Tax Office writes it: "P02" for commissioner precinct 2, "J05" for JP 5."""
    return [{"attributes": {"Precinct": code, "Commissioner": f"P{c:02d}" if isinstance(c, int) else c,
                            "JPConstable": f"J{j:02d}" if isinstance(j, int) else j}}
            for code, (c, j) in numbers.items()]


def harris_rows(numbers: dict[str, tuple[Any, Any]] = HARRIS_LIST) -> list[dict[str, Any]]:
    return [{"attributes": {"VPCT_txt": code, "Comm__Cour": c, "JP_Constab": j}} for code, (c, j) in numbers.items()]


def precincts_index(size: int, *, newer: dict[str, Any] | None = None) -> dict[str, Any]:
    """The recorded index of the portal's precinct maps, every map's size set to ``size`` (the
    made-up map's, so the size check passes), plus a ``newer`` resource if given."""
    index = load("election_precincts_index.json")
    for resource in index["result"]["resources"]:
        if resource["format"] == "SHP":
            resource["size"] = size
    if newer:
        index["result"]["resources"].append(newer)
    return index


def _file(name: str, default: Any = None) -> httpx.Response:
    raw = fixture_bytes(name)
    if raw is None:
        if default is None:
            raise AssertionError(f"no fixture {name}")
        return httpx.Response(200, json=default)
    return httpx.Response(200, content=raw, headers={"content-type": "application/json"})


class Upstream:
    """Answers every outbound request from the recorded fixtures and remembers what was asked."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.down: set[str] = set()  # hosts that answer HTTP 500
        self.refusing: dict[str, int] = {}  # host -> the status it refuses every request with, e.g. 429
        self.ballotpedia_status: int | None = None
        self.ballotpedia_edit: Callable[[dict[str, Any]], None] | None = None  # changes the Capitol's ballot before it's sent
        self.fec_status: int | None = None  # e.g. 429 when over the hourly limit
        self.fec_keys: set[str | None] = set()  # the X-Api-Key values the FEC was sent
        self.suggestions_status: int | None = None  # e.g. 429 when Ballotpedia's address search throttles us
        self.polls_status: int | None = None  # e.g. 403 when FiftyPlusOne refuses us
        self.polls_agents: set[str | None] = set()  # the User-Agents FiftyPlusOne was sent
        self.key_dates_status: int | None = None  # e.g. 403 when the SOS website refuses us
        self.tigerweb_status: int | None = None  # e.g. 429 when TIGERweb throttles us
        self.tigerweb_answer: dict[str, Any] | None = None  # e.g. an ArcGIS error, which comes with a 200
        self.tiles_status: int | None = None  # e.g. 403 when OpenStreetMap's tile server blocks us
        self.tile_agents: set[str | None] = set()  # the User-Agents the tile server was sent
        self.precincts_status: int | None = None  # e.g. 429 when the TLC's portal throttles us
        self.precinct_map: bytes | None = None  # the precinct zip served (default: election_precincts_zip())
        self.precinct_index: dict[str, Any] | None = None  # the portal's index (default: sized to the map)
        self.extra_candidates: dict[int, list[dict[str, Any]]] = {}  # election id -> rows added to its statewide list
        self.candidates_down: set[int] = set()  # election ids whose statewide candidate list answers HTTP 500
        self.county_status: int | None = None  # e.g. 403 when a county's map server refuses us
        # A county's ArcGIS server: host -> path -> its answer, a dict as is or a layer's features, paged as ArcGIS
        # pages them. The lists of services are recorded; the lists of precincts are made up, from the made-up map.
        self.arcgis: dict[str, dict[str, Any]] = {
            "taxmaps.traviscountytx.gov": {
                "/arcgis/rest/services": load("county_precincts_travis_services.json"),
                "/arcgis/rest/services/Precincts/FeatureServer": load("county_precincts_travis_service.json"),
                TRAVIS_QUERY: travis_rows(),
            },
            "services.arcgis.com": {
                "/su8ic9KbA7PYVxPS/arcgis/rest/services": load("county_precincts_harris_services.json"),
                "/su8ic9KbA7PYVxPS/arcgis/rest/services/VPCTs_2026/FeatureServer": load("county_precincts_harris_service.json"),
                HARRIS_QUERY: harris_rows(),
            },
        }
        self._addresses = {normalize_address(a): name for name, a in ADDRESSES.items()}

    def count(self, host_part: str) -> int:
        return sum(host_part in call for call in self.calls)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        self.calls.append(f"{request.method} {url.host}{url.path}")
        if url.host in self.down:
            return httpx.Response(500)
        if url.host in self.refusing:
            return httpx.Response(self.refusing[url.host])
        params = url.params
        if url.host == "geocoding.geo.census.gov":
            if url.path.endswith("/onelineaddress"):
                name = self._addresses.get(params["address"])
                if name == "hd93":
                    return httpx.Response(200, json=hd93_census())
                return _file(f"census_{name}.json") if name else httpx.Response(200, json={"result": {"addressMatches": []}})
            return _file("census_coords_mopac.json")
        if url.host == "nominatim.openstreetmap.org":
            return _file("nominatim_mopac.json") if self._addresses.get(params["q"]) == "mopac" else httpx.Response(200, json=[])
        if url.host == "goelect.txelections.civixapps.com":
            path = url.path
            if "/getElectionsByYear/" in path:
                return _file(f"sos_elections_{path.rsplit('/', 1)[1]}.json", default=[])
            for suffix, name in (("getAllRegions", "sos_regions.json"), ("getPoliticalParties", "sos_parties.json"),
                                 ("getCandidateStatus", "sos_statuses.json"),
                                 ("getDeclarationStatus", "sos_declarations.json")):
                if path.endswith(suffix):
                    return _file(name)
            body = json.loads(request.content)
            if path.endswith("getCandidateBallotOrder"):
                return _file(f"sos_ballot_{body['electionId']}_{body['countyId']}.json", default=[])
            if path.endswith("findQualifiedCandidates"):
                if body["electionId"] in self.candidates_down:
                    return httpx.Response(500)
                extra = self.extra_candidates.get(body["electionId"])
                if extra:
                    return httpx.Response(200, json=load(f"sos_candidates_{body['electionId']}.json") + extra)
                return _file(f"sos_candidates_{body['electionId']}.json", default=[])
        if url.host == "api4.ballotpedia.org" and url.path == "/address_autocomplete":
            if self.suggestions_status:
                return httpx.Response(self.suggestions_status)
            if request.headers.get("origin") != ballotpedia.ORIGIN:
                return httpx.Response(403, json={"success": False, "data": {}, "message": "Insufficient privileges."})
            name = next((name for name, text in SUGGEST.items()
                         if suggestions.query(suggestions.normalize(text)) == params["location"]), None)
            return _file(f"suggestions_{name}.json") if name else httpx.Response(200, json={"success": True, "data": {"Results": []}})
        if url.host == "api4.ballotpedia.org":
            if self.ballotpedia_status:
                return httpx.Response(self.ballotpedia_status)
            if request.headers.get("origin") != ballotpedia.ORIGIN:
                return httpx.Response(403)
            lat, lon = capitol_point()
            if params["lat"] == f"{lat:.5f}" and params["long"] == f"{lon:.5f}":
                if self.ballotpedia_edit:
                    payload = load("ballotpedia_capitol.json")
                    self.ballotpedia_edit(payload)
                    return httpx.Response(200, json=payload)
                return _file("ballotpedia_capitol.json")
            return httpx.Response(200, json={"success": True, "data": {"districts": [], "elections": []}})
        if url.host == "data.capitol.texas.gov":
            if url.path.endswith("/package_show") or "/download/precincts" in url.path:
                if self.precincts_status:
                    return httpx.Response(self.precincts_status)
                served = self.precinct_map or election_precincts_zip()
                if url.path.endswith("/package_show"):
                    return httpx.Response(200, json=self.precinct_index or precincts_index(len(served)))
                return httpx.Response(200, content=served, headers={"content-type": "application/zip"})
            return httpx.Response(200, content=sboe_zip())
        if url.host == "api.open.fec.gov":
            return self._fec(request)
        if url.host == "fiftyplusone.news":
            self.polls_agents.add(request.headers.get("user-agent"))
            if self.polls_status:
                return httpx.Response(self.polls_status, json={"error": "Forbidden"})
            if params["offset"] != "0":  # every recorded list fits on its first page
                return httpx.Response(200, json={"success": True, "data": []})
            return _file(f"polls_{params['filterValue']}.json", default={"success": True, "data": []})
        if url.host == "www.sos.state.tx.us" and url.path == "/elections/voter/important-election-dates.shtml":
            if self.key_dates_status:
                return httpx.Response(self.key_dates_status)
            return httpx.Response(200, content=fixture_bytes("sos_key_dates.html"),
                                  headers={"content-type": "text/html"})
        if url.host == "tigerweb.geo.census.gov":
            if self.tigerweb_status:
                return httpx.Response(self.tigerweb_status)
            if self.tigerweb_answer is not None:
                return httpx.Response(200, json=self.tigerweb_answer)
            if url.path.endswith("/MapServer"):
                return _file("tigerweb_layers.json")
            geoid = re.fullmatch(r"GEOID='(\d+)'", params["where"]).group(1)
            return _file(f"tigerweb_{geoid}.json", default={"features": []})
        if url.host == "tile.openstreetmap.org":
            self.tile_agents.add(request.headers.get("user-agent"))
            if self.tiles_status:
                return httpx.Response(self.tiles_status)
            return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
        if url.host in self.arcgis:
            return self._arcgis(request)
        raise AssertionError(f"unexpected request: {request.method} {url}")

    def _arcgis(self, request: httpx.Request) -> httpx.Response:
        if self.county_status:
            return httpx.Response(self.county_status)
        answer = self.arcgis[request.url.host].get(request.url.path)
        if answer is None:
            raise AssertionError(f"unexpected county request: {request.url}")
        if isinstance(answer, list):
            params = request.url.params
            start, count = int(params.get("resultOffset", 0)), int(params.get("resultRecordCount", 1000))
            page: dict[str, Any] = {"features": answer[start:start + count]}
            if start + count < len(answer):
                page["exceededTransferLimit"] = True
            return httpx.Response(200, json=page)
        return httpx.Response(200, json=answer)

    def _fec(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        assert "api_key" not in params, "the FEC key travels in a header, never in the URL"
        self.fec_keys.add(request.headers.get("x-api-key"))
        if self.fec_status:
            return httpx.Response(self.fec_status, json={"error": {"code": "OVER_RATE_LIMIT"}})
        path, empty = request.url.path.removeprefix("/v1"), {"results": []}
        if path == "/elections/":
            office = params["office"]
            return _file("fec_elections_senate.json" if office == "senate" else f"fec_elections_house_{params['district']}.json",
                         default=empty)
        if path.startswith("/candidate/") and path.endswith("/totals/"):
            return _file(f"fec_totals_{path.split('/')[2]}.json", default=empty)
        for suffix, name in (("/schedule_a/by_size/by_candidate/", "by_size"), ("/schedule_a/by_state/by_candidate/", "by_state"),
                             ("/schedule_e/by_candidate/", "outside")):
            if path.endswith(suffix):
                return _file(f"fec_{name}_{params['candidate_id']}.json", default=empty)
        if path.endswith("/schedule_a/by_employer/"):
            return _file(f"fec_by_employer_{params['committee_id']}.json", default=empty)
        raise AssertionError(f"unexpected FEC request: {request.url}")


class FakeRefreshResult:
    def summary(self) -> str:
        return "updated 2026-09-27.json: sources changed: congress; 1 added, 0 removed, 0 modified"


@pytest.fixture
def upstream():
    handler = Upstream()
    with respx.mock(assert_all_called=False) as router:
        router.route().mock(side_effect=handler)
        yield handler


class FakeTecResult:
    def summary(self) -> str:
        return "updated snapshot 2026-09-27: 2 candidates and officeholders with reports since Nov 6, 2024 (read the zip)"


@pytest.fixture
def make_app(tmp_path, upstream):
    """make_app(data_dir=None, refresh=None, tec_refresh=None, voteforpeace_refresh=None, fec_key=FEC_KEY,
    endorsements_dir=FIXTURES / "endorsements") -> a new app; call again on the same dir to 'restart'. It answers to
    TestClient's host name, testserver."""
    refreshed: list[Path] = []
    tec_refreshed: list[dict[str, Any]] = []

    def fake_refresh(*, data_dir):
        refreshed.append(Path(data_dir))
        return FakeRefreshResult()

    def fake_voteforpeace_refresh(*, data_dir):
        return "updated 2026-10-04.json: 1 added, 0 removed, 0 modified"

    def fake_tec_refresh(**kwargs):
        tec_refreshed.append(kwargs)
        return FakeTecResult()

    def build(data_dir: Path | None = None, refresh=None, tec_refresh=None, voteforpeace_refresh=None,
              fec_key: str = FEC_KEY, endorsements_dir: Path = FIXTURES / "endorsements"):
        return create_app(
            Config(data_dir=data_dir or tmp_path / "data", fec_api_key=fec_key, allowed_hosts=("testserver",)),
            today=lambda: TODAY,
            trackaipac_bundled=FIXTURES / "trackaipac",
            trackaipac_refresh=refresh or fake_refresh,
            voteforpeace_bundled=FIXTURES / "voteforpeace",
            voteforpeace_refresh=voteforpeace_refresh or fake_voteforpeace_refresh,
            tec_bundled=FIXTURES / "tec",
            tec_refresh=tec_refresh or fake_tec_refresh,
            endorsements_dir=endorsements_dir,
            min_interval={},
        )

    build.refreshed = refreshed
    build.tec_refreshed = tec_refreshed
    return build


@pytest.fixture
def client(make_app):
    with TestClient(make_app()) as test_client:
        yield test_client


def get_ballot(client: TestClient, address: str = "capitol", **extra: Any) -> dict[str, Any]:
    response = client.post("/api/ballot", json={"address": ADDRESSES.get(address, address), **extra})
    assert response.status_code == 200, response.text
    return response.json()


def last_use(client: TestClient, source_id: str) -> dict[str, Any] | None:
    """How the last lookup used a source, as the Settings page shows it."""
    return next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == source_id)["last_use"]


def find_race(ballot: dict[str, Any], name: str, *, maybe: bool = False) -> dict[str, Any] | None:
    races = [r for s in ballot["maybe"] for r in s["races"]] if maybe else ballot["races"]
    return next((r for r in races if r["name"] == name), None)


def candidate_names(race: dict[str, Any]) -> list[str]:
    return [c["name"] for c in race["candidates"]]
