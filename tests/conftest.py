"""Shared setup: recorded API responses (tests/fixtures, see scripts/record_fixtures.py)
served through respx, and a VoteBot app on a temp data dir with "today" pinned, an FEC
API key, and the TrackAIPAC and Texas Ethics Commission fixture snapshots."""

from __future__ import annotations

import copy
import datetime as dt
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from votebot.api import create_app
from votebot.config import Config
from votebot.sources import ballotpedia, photon
from votebot.sources.census import normalize_address

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
SUGGEST = {"congress": "1100 congress ave austin", "duval": "4512 duval st"}  # as in scripts/record_fixtures.py


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def capitol_point() -> tuple[float, float]:
    coords = load("census_capitol.json")["result"]["addressMatches"][0]["coordinates"]
    return coords["y"], coords["x"]


def hd93_census() -> dict[str, Any]:
    data = copy.deepcopy(load("census_capitol.json"))
    geographies = data["result"]["addressMatches"][0]["geographies"]
    lower = next(name for name in geographies if "Legislative Districts - Lower" in name)
    geographies[lower][0]["BASENAME"] = "93"
    return data


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


def _file(name: str, default: Any = None) -> httpx.Response:
    path = FIXTURES / name
    if not path.exists():
        if default is None:
            raise AssertionError(f"no fixture {name}")
        return httpx.Response(200, json=default)
    return httpx.Response(200, content=path.read_bytes(), headers={"content-type": "application/json"})


class Upstream:
    """Answers every outbound request from the recorded fixtures and remembers what was asked."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.down: set[str] = set()  # hosts that answer HTTP 500
        self.ballotpedia_status: int | None = None
        self.fec_status: int | None = None  # e.g. 429 when over the hourly limit
        self.fec_keys: set[str | None] = set()  # the X-Api-Key values the FEC was sent
        self.photon_status: int | None = None  # e.g. 429 when Photon throttles us
        self.polls_status: int | None = None  # e.g. 403 when FiftyPlusOne refuses us
        self.polls_agents: set[str | None] = set()  # the User-Agents FiftyPlusOne was sent
        self._addresses = {normalize_address(a): name for name, a in ADDRESSES.items()}

    def count(self, host_part: str) -> int:
        return sum(host_part in call for call in self.calls)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        self.calls.append(f"{request.method} {url.host}{url.path}")
        if url.host in self.down:
            return httpx.Response(500)
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
                return _file(f"sos_candidates_{body['electionId']}.json", default=[])
        if url.host == "api4.ballotpedia.org":
            if self.ballotpedia_status:
                return httpx.Response(self.ballotpedia_status)
            if request.headers.get("origin") != ballotpedia.ORIGIN:
                return httpx.Response(403)
            lat, lon = capitol_point()
            if params["lat"] == f"{lat:.5f}" and params["long"] == f"{lon:.5f}":
                return _file("ballotpedia_capitol.json")
            return httpx.Response(200, json={"success": True, "data": {"districts": [], "elections": []}})
        if url.host == "photon.komoot.io":
            if self.photon_status:
                return httpx.Response(self.photon_status)
            name = next((name for name, text in SUGGEST.items() if photon.normalize(text) == params["q"]), None)
            return _file(f"photon_{name}.json") if name else httpx.Response(200, json={"type": "FeatureCollection", "features": []})
        if url.host == "data.capitol.texas.gov":
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
        raise AssertionError(f"unexpected request: {request.method} {url}")

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
    """make_app(data_dir=None, refresh=None, tec_refresh=None, fec_key=FEC_KEY) -> a new app;
    call again on the same dir to 'restart'."""
    refreshed: list[Path] = []
    tec_refreshed: list[dict[str, Any]] = []

    def fake_refresh(*, data_dir):
        refreshed.append(Path(data_dir))
        return FakeRefreshResult()

    def fake_tec_refresh(**kwargs):
        tec_refreshed.append(kwargs)
        return FakeTecResult()

    def build(data_dir: Path | None = None, refresh=None, tec_refresh=None, fec_key: str = FEC_KEY):
        return create_app(
            Config(data_dir=data_dir or tmp_path / "data", fec_api_key=fec_key),
            today=lambda: TODAY,
            trackaipac_bundled=FIXTURES / "trackaipac",
            trackaipac_refresh=refresh or fake_refresh,
            tec_bundled=FIXTURES / "tec",
            tec_refresh=tec_refresh or fake_tec_refresh,
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
