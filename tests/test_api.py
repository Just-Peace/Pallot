"""Settings-page API, elections list, TrackAIPAC data and static pages."""

from __future__ import annotations

import json
import re
import threading

import pytest
from fastapi.testclient import TestClient

from .conftest import get_ballot, load


def test_elections_list(client):
    dates = client.get("/api/elections").json()
    assert [d["date"] for d in dates] == ["2026-11-03"]
    assert [e["id"] for e in dates[0]["elections"]] == [53815, 66734, 66618]
    assert dates[0]["has_primaries"] is False


def test_sources_overview(client):
    overview = client.get("/api/sources").json()
    assert [s["id"] for s in overview["sources"]] == ["geocoding", "sos", "ballotpedia", "trackaipac"]
    geocoding, sos, _, tracker = overview["sources"]
    assert geocoding["toggleable"] is False and sos["enabled"] is True
    assert tracker["clear_label"] == "Reset to bundled snapshot"
    assert {"Snapshot", "Texas entries"} <= {f["label"] for f in tracker["details"]}


def test_toggles_persist_across_restarts(make_app, tmp_path):
    with TestClient(make_app()) as client:
        response = client.put("/api/sources/ballotpedia", json={"enabled": False})
        assert response.status_code == 200
        assert next(s for s in response.json()["sources"] if s["id"] == "ballotpedia")["enabled"] is False
        assert client.put("/api/sources/geocoding", json={"enabled": False}).status_code == 400
        assert client.put("/api/sources/nope", json={"enabled": False}).status_code == 404
    assert json.loads((tmp_path / "data" / "settings.json").read_text())["sources"]["ballotpedia"] is False
    with TestClient(make_app()) as client:
        assert next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "ballotpedia")["enabled"] is False


def test_refresh_and_clear_a_cached_source(client, upstream):
    get_ballot(client)
    sos_before = upstream.count("goelect")
    stats = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "sos")["cache"]
    assert stats["entries"] > 0

    message = client.post("/api/sources/sos/refresh").json()["message"]
    assert message.startswith(f"Refreshed {stats['entries']} cached responses")
    assert upstream.count("goelect") == sos_before + stats["entries"]

    assert client.post("/api/sources/sos/clear").json()["message"].startswith("Cleared")
    assert next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "sos")["cache"]["entries"] == 0
    assert get_ballot(client)["meta"]["external_calls"] > 0  # fetched again


def test_clear_geocoding_also_drops_the_sboe_map(client, tmp_path):
    get_ballot(client)
    assert (tmp_path / "data" / "plane2106_kml.zip").exists()
    client.post("/api/sources/geocoding/clear")
    assert not (tmp_path / "data" / "plane2106_kml.zip").exists()


def test_clear_everything(client):
    get_ballot(client)
    assert client.post("/api/cache/clear").status_code == 200
    overview = client.get("/api/sources").json()
    assert all(s["cache"]["entries"] == 0 for s in overview["sources"])


def test_trackaipac_refresh_and_reset(make_app, tmp_path):
    with TestClient(make_app()) as client:
        message = client.post("/api/sources/trackaipac/refresh").json()["message"]
        assert message.startswith("updated")
        current = tmp_path / "data" / "trackaipac" / "current.json"
        current.write_text(json.dumps({"snapshot": "edited", "candidates": []}))
        assert client.get("/api/sources/trackaipac/data").json()["snapshot"] == "edited"
        assert client.post("/api/sources/trackaipac/clear").status_code == 200
        assert client.get("/api/sources/trackaipac/data").json()["snapshot"] == load("trackaipac/current.json")["snapshot"]


def test_trackaipac_refresh_failure_changes_nothing(make_app):
    def broken(*, data_dir):
        raise RuntimeError("site is down")

    with TestClient(make_app(refresh=broken)) as client:
        response = client.post("/api/sources/trackaipac/refresh")
        assert response.status_code == 502 and "nothing changed" in response.json()["detail"]


def test_a_second_refresh_while_one_runs_is_refused(make_app):
    started, release = threading.Event(), threading.Event()

    def slow(*, data_dir):
        started.set()
        release.wait(5)
        return "done"

    with TestClient(make_app(refresh=slow)) as client:
        results = {}
        worker = threading.Thread(target=lambda: results.update(first=client.post("/api/sources/trackaipac/refresh")))
        worker.start()
        assert started.wait(5)
        second = client.post("/api/sources/trackaipac/refresh")
        release.set()
        worker.join(5)
    assert second.status_code == 409
    assert results["first"].status_code == 200


def test_trackaipac_data_with_etag(client):
    response = client.get("/api/sources/trackaipac/data?state=tx")
    body = response.json()
    assert body["candidates"] and {p["state"] for p in body["candidates"]} == {"TX"}
    etag = response.headers["etag"]
    assert client.get("/api/sources/trackaipac/data?state=tx", headers={"If-None-Match": etag}).status_code == 304
    assert client.get("/api/sources/trackaipac/data").headers["etag"] != etag


PAGES = ["./", "settings.html", "faq.html", "about.html", "privacy.html"]


@pytest.mark.parametrize("path", ["/", "/js/ballot.js", "/js/settings.js", "/js/page.js", "/js/address.js", "/js/icons.js", "/js/search.js", "/css/app.css"])
def test_static_pages(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("page", PAGES)
def test_every_page_has_the_same_left_pane_and_its_files_exist(client, page):
    html = client.get(f"/{page}").text
    navs = re.findall(r'<nav class="side-section site-nav[^"]*".*?</nav>', html, re.S)
    # "Your ballot" at the top with the address under it; the other pages at the bottom
    assert [re.findall(r'href="([^"]+)"', nav) for nav in navs] == [PAGES[:1], PAGES[1:]]
    assert html.index(navs[0]) < html.index('id="address-card"') < html.index(navs[1])
    assert re.findall(r'href="([^"]+)" aria-current="page"', "".join(navs)) == [page]
    local = {ref.split("#")[0] for ref in re.findall(r'(?:href|src)="([^"#:][^":]*)"', html)}
    for ref in local:
        assert client.get(f"/{ref}").status_code == 200, ref
