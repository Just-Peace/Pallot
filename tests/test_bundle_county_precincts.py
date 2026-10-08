"""The counties' bundle (bundles/county_precincts.py): commissioner and JP precinct records."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pallot.config import DAY
from pallot.sources import county_precincts as cp

from .bundling import build, entry, lifetimes
from .conftest import HARRIS, TRAVIS, get_ballot, last_use

DALLAS = 113
COUNTY_HOSTS = ("traviscountytx", "services.arcgis.com", "services3.arcgis.com")  # Travis's, Harris's, Dallas's


def build_counties(tmp_path, monkeypatch):
    """The county records' bundle, of Harris, Dallas and Travis only (the fixtures have Harris's and Travis's)."""
    monkeypatch.setattr(cp, "COUNTIES", {fips: cp.COUNTIES[fips] for fips in (HARRIS, DALLAS, TRAVIS)})
    return build(tmp_path, "county_precincts")


def county_calls(upstream) -> int:
    return sum(upstream.count(host) for host in COUNTY_HOSTS)


def test_a_lookup_with_the_county_records_bundled_asks_the_county_nothing(tmp_path, upstream, make_app, monkeypatch):
    upstream.down.add("services3.arcgis.com")
    outcome = build_counties(tmp_path, monkeypatch)
    assert outcome.status == "updated" and outcome.counts == {"counties": 2, "missing": 1}  # Dallas's server is down
    assert outcome.answers == 6 and upstream.count("traviscountytx") == 3  # each county's index, layers and one page
    assert entry("county_precincts").cadence == "weekly" and lifetimes(tmp_path, "county_precincts") == {14 * DAY}
    asked = upstream.count("traviscountytx")
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client)
        assert last_use(client, cp.SOURCE)["calls"] == 0
    assert (ballot["districts"]["commissioner"], ballot["districts"]["jp"]) == (2, 5)
    assert upstream.count("traviscountytx") == asked


def test_a_county_refusing_stops_the_build(tmp_path, upstream, monkeypatch):
    upstream.county_status = 403
    outcome = build_counties(tmp_path, monkeypatch)
    assert outcome.status == "failed" and "paused" in outcome.detail
    assert county_calls(upstream) == 1 and not (tmp_path / "bundles").exists()


def test_an_arcgis_error_writes_no_county_records(tmp_path, upstream, monkeypatch):
    upstream.down.add("services3.arcgis.com")
    upstream.arcgis["taxmaps.traviscountytx.gov"]["/arcgis/rest/services"] = {"error": {"code": 400, "message": "Bad"}}
    outcome = build_counties(tmp_path, monkeypatch)
    assert outcome.status == "failed" and "Travis County's map server answered an ArcGIS error" in outcome.detail
    assert not (tmp_path / "bundles").exists()


def test_most_counties_down_writes_no_county_records(tmp_path, upstream, monkeypatch):
    upstream.down |= {"services3.arcgis.com", "taxmaps.traviscountytx.gov"}
    outcome = build_counties(tmp_path, monkeypatch)
    assert outcome.status == "failed" and "most counties" in outcome.detail and "Dallas" in outcome.detail
    assert not (tmp_path / "bundles").exists()
