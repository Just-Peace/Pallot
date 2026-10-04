"""Settings-page API, elections list and static pages."""

from __future__ import annotations

import json
import re
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from pallot.api import host_allowed
from pallot.config import DAY
from pallot.http_cache import HttpCache, RequestSpec
from pallot.text import display_time

from .conftest import ADDRESSES, get_ballot, last_use, load

ISO_TIME = re.compile(r"\d{4}-\d{2}-\d{2}(T|$)")  # what the voter shouldn't have to read


def test_elections_list(client):
    response = client.get("/api/elections")
    assert "cache-control" not in response.headers
    dates = response.json()
    assert [d["date"] for d in dates] == ["2026-11-03"]
    assert [e["id"] for e in dates[0]["elections"]] == [53815, 66734, 66618]
    assert dates[0]["has_primaries"] is False


def test_sources_overview(client):
    overview = client.get("/api/sources").json()
    assert [s["id"] for s in overview["sources"]] == ["geocoding", "election_precincts", "county_precincts", "tigerweb",
                                                       "osm_tiles", "suggestions", "sos", "key_dates", "ballotpedia",
                                                       "trackaipac", "voteforpeace", "fec", "tec", "polls"]
    geocoding, precincts, county, outlines, tiles, suggestions, sos, dates, _, tracker, peace, fec, tec, polls = overview["sources"]
    assert (county["label"], county["toggleable"], county["enabled"], county["refresh_confirm"]) == (
        "Commissioner & JP precincts (counties)", True, True, None)
    assert "Harris, Dallas, Tarrant, Travis and Fort Bend" in county["description"]
    assert (precincts["label"], precincts["toggleable"], precincts["enabled"], precincts["busy"], precincts["notice"]) == (
        "Election precincts (Texas Legislative Council)", True, True, False, None)
    assert "(a large file)" in precincts["refresh_confirm"]  # its size once Pallot has seen the portal's list
    assert [(f["label"], f["value"]) for f in precincts["details"]] == [
        ("Map kept", "downloaded on the first lookup"), ("Newest on the portal", "not asked yet")]
    assert tiles["refreshable"] is False and all(s["refreshable"] for s in overview["sources"] if s is not tiles)
    assert (dates["label"], dates["toggleable"], dates["notice"]) == ("Key election dates (Texas SOS)", True, None)
    assert (outlines["label"], outlines["enabled"], outlines["refresh_confirm"]) == ("District map (US Census TIGERweb)", True, None)
    assert geocoding["toggleable"] is False and sos["enabled"] is True and suggestions["enabled"] is True
    assert geocoding["refresh_confirm"] and "1 GB" in tec["refresh_confirm"] and sos["refresh_confirm"] is None
    assert tracker["clear_label"] == tec["clear_label"] == "Reset to the snapshot that came with Pallot"
    assert tracker["resettable"] and peace["resettable"] and tec["resettable"] and not sos["resettable"]
    assert (peace["label"], peace["refresh_label"], peace["refresh_confirm"]) == (
        "Vote for Peace", "Refresh from voteforpeace.info", None)
    assert [(f["label"], f["value"]) for f in peace["details"]][3:] == [("Texas candidates", "164"), ("All candidates", "166")]
    assert tec["clear_confirm"].startswith("Throw away the refreshed Texas Ethics Commission (TEC) data")
    assert sos["clear_confirm"].startswith("Clear everything cached from Texas Secretary of State (Texas SOS)?")
    assert "The TrackAIPAC, Vote for Peace and Texas Ethics Commission (TEC) data go back" in overview["clear_all_confirm"]
    assert overview["last_lookup"] is None and sos["last_use"] is None
    assert {"Snapshot", "Texas entries"} <= {f["label"] for f in tracker["details"]}
    assert fec["notice"] == "Using your api.data.gov key." and fec["notice_tone"] == "info"
    assert tec["notice"] and {"Snapshot", "Money raised since"} <= {f["label"] for f in tec["details"]}
    assert (polls["label"], polls["toggleable"], polls["notice"]) == ("Polls (FiftyPlusOne)", True, None)
    shown = [s["notice"] or "" for s in overview["sources"]] + [f["value"] for s in overview["sources"] for f in s["details"]]
    assert not [text for text in shown if ISO_TIME.search(text)]


def test_times_are_shown_as_people_write_them():
    shown = display_time("2026-09-28T18:25:03+00:00")
    assert re.fullmatch(r"[A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2} [AP]M", shown)
    assert display_time("Mon, 28 Sep 2026 18:25:03 GMT") == shown == display_time(1790619903.0)
    assert display_time(None) is None and display_time("never") is None


def test_settings_shows_the_last_lookup(client):
    get_ballot(client)
    first = {s["id"]: s for s in client.get("/api/sources").json()["sources"]}
    assert first["sos"]["last_use"]["calls"] > 0 and first["sos"]["cache"]["entries"] > 0
    get_ballot(client)
    overview = client.get("/api/sources").json()
    assert overview["last_lookup"]["external_calls"] == 0 and overview["last_lookup"]["cache_hits"] > 0
    rows = {s["id"]: s for s in overview["sources"]}
    assert rows["sos"]["last_use"]["status"] == "used" and rows["sos"]["last_use"]["calls"] == 0
    assert rows["trackaipac"]["last_use"]["as_of"] == load("trackaipac/current.json")["snapshot"]
    assert overview["total_bytes"] > 0


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


def test_a_failed_sboe_download_keeps_the_old_map(client, upstream, tmp_path):
    get_ballot(client)
    upstream.down.add("data.capitol.texas.gov")
    response = client.post("/api/sources/geocoding/refresh")
    assert response.status_code == 200
    message = response.json()["message"]
    assert message.startswith("Refreshed")
    assert "Couldn't re-download the State Board of Education map (HTTP 500); kept the old one." in message
    assert (tmp_path / "data" / "plane2106_kml.zip").exists()


def test_sboe_portal_down_is_asked_once_until_clear(client, upstream):
    client.put("/api/sources/election_precincts", json={"enabled": False})  # it asks the same portal
    upstream.down.add("data.capitol.texas.gov")
    first = get_ballot(client)
    assert first["districts"]["sboe"] is None and any("State Board of Education map" in w for w in first["warnings"])
    second = get_ballot(client)
    assert upstream.count("plane2106_kml.zip") == 1 and second["meta"]["external_calls"] == 0
    geocoding = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "geocoding")
    assert geocoding["notice_tone"] == "warn"
    assert geocoding["notice"].startswith("The last download of the State Board of Education map failed (HTTP 500)")
    client.post("/api/sources/geocoding/clear")
    upstream.down.clear()
    assert get_ballot(client)["districts"]["sboe"] == 5 and upstream.count("plane2106_kml.zip") == 2


def test_other_websites_cant_use_the_settings_actions(client):
    get_ballot(client)
    for headers in (
        {"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"},
        {"Sec-Fetch-Site": "same-site", "Origin": "http://testserver:3000"},  # another port on this machine
        {"Origin": "https://evil.example"},  # a browser that doesn't send Sec-Fetch-Site
        {"Origin": "null"},  # a sandboxed page
    ):
        response = client.post("/api/cache/clear", headers=headers)
        assert response.status_code == 403 and "another website" in response.json()["detail"], headers
    assert next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "sos")["cache"]["entries"] > 0
    own_page = {"Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"}
    assert client.post("/api/cache/clear", headers=own_page).status_code == 200
    assert client.get("/api/sources", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200  # CORS hides the answer


def test_only_localhost_ip_addresses_and_allowed_names_are_answered(client):
    for host in ("localhost:8000", "127.0.0.1:8000", "192.168.1.20:8000", "[::1]:8000"):
        assert client.get("/api/sources", headers={"Host": host}).status_code == 200, host
    response = client.get("/", headers={"Host": "rebind.evil.example:8000"})  # DNS rebinding
    assert response.status_code == 400 and "PALLOT_ALLOWED_HOSTS" in response.json()["detail"]
    assert host_allowed("nas.local:8000", ("nas.local",)) and host_allowed("anything.example", ("*",))
    assert not host_allowed("nas.local", ()) and not host_allowed("", ()) and not host_allowed("[::1", ())


def test_trackaipac_refresh_and_reset(make_app, tmp_path):
    with TestClient(make_app()) as client:
        message = client.post("/api/sources/trackaipac/refresh").json()["message"]
        assert message.startswith("updated")
        current = tmp_path / "data" / "trackaipac" / "current.json"
        current.write_text(json.dumps({"snapshot": "edited", "candidates": []}))
        tracker = client.app.state.svc.trackaipac
        assert tracker.document()["snapshot"] == "edited"
        assert client.post("/api/sources/trackaipac/clear").status_code == 200
        assert tracker.document()["snapshot"] == load("trackaipac/current.json")["snapshot"]


def test_trackaipac_refresh_failure_changes_nothing(make_app):
    def broken(*, data_dir):
        raise RuntimeError("site is down")

    with TestClient(make_app(refresh=broken)) as client:
        response = client.post("/api/sources/trackaipac/refresh")
        assert response.status_code == 502 and "nothing changed" in response.json()["detail"]
        tracker = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "trackaipac")
    assert tracker["notice_tone"] == "warn" and "site is down" in tracker["notice"]


def test_voteforpeace_refresh_and_reset(make_app, tmp_path):
    with TestClient(make_app()) as client:
        assert client.post("/api/sources/voteforpeace/refresh").json()["message"].startswith("updated")
        current = tmp_path / "data" / "voteforpeace" / "current.json"
        current.write_text(json.dumps({"snapshot": "edited", "candidates": []}))
        peace = client.app.state.svc.voteforpeace
        assert peace.document()["snapshot"] == "edited"
        assert client.post("/api/sources/voteforpeace/clear").status_code == 200
        assert peace.document()["snapshot"] == load("voteforpeace/current.json")["snapshot"]


def test_voteforpeace_off_leaves_its_cards_out(client):
    assert client.put("/api/sources/voteforpeace", json={"enabled": False}).status_code == 200
    ballot = get_ballot(client)
    assert not [card for race in ballot["races"] for c in race["candidates"] for card in c["cards"]
                if card["source"] == "voteforpeace"]
    assert last_use(client, "voteforpeace")["status"] == "off"


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


PAGES = ["./", "settings.html", "faq.html", "about.html", "privacy.html"]


@pytest.mark.parametrize("path", ["/", "/favicon.svg", "/css/app.css"])  # the scripts: test_frontend_modules.py
def test_static_pages(client, path):
    assert client.get(path).status_code == 200


def test_static_files_are_kept_but_checked_before_each_use(client):
    """After an update, no page mixes modules from the browser's cache with new ones."""
    first = client.get("/js/dom.js")
    assert first.headers["cache-control"] == "no-cache" and first.headers["etag"]
    again = client.get("/js/dom.js", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and again.headers["cache-control"] == "no-cache"
    assert client.get("/").headers["cache-control"] == "no-cache"


def test_responses_are_gzipped_when_the_browser_asks(client):
    plain = client.post("/api/ballot", json={"address": ADDRESSES["capitol"]},
                        headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers
    zipped = client.post("/api/ballot", json={"address": ADDRESSES["capitol"]},
                         headers={"Accept-Encoding": "gzip"})
    assert zipped.headers["content-encoding"] == "gzip" and int(zipped.headers["content-length"]) < len(plain.content) / 4
    assert zipped.json().keys() == plain.json().keys()
    assert client.get("/css/app.css", headers={"Accept-Encoding": "gzip"}).headers["content-encoding"] == "gzip"


@pytest.mark.parametrize("page", PAGES)
def test_every_page_leaves_its_left_pane_and_footer_to_chrome_js_and_its_files_exist(client, page):
    html = client.get(f"/{page}").text
    assert "<footer" not in html
    aside = re.search(r'<aside class="sidebar"[^>]*>(.*?)</aside>', html, re.S).group(1)
    if page == "./":  # the ballot's own parts of the pane: its form and status line, and the section list
        assert aside.count('data-slot="address"') == 2 and 'id="jump"' in aside and "address-card" not in aside
    else:
        assert not aside.strip()
    entry = {"./": "ballot", "settings.html": "settings"}.get(page, "page")  # settings.js imports page.js
    assert re.findall(r'<script type="module" src="js/([\w-]+)\.js"></script>', html) == [entry]
    assert '<link rel="icon" href="favicon.svg" type="image/svg+xml">' in html
    local = {ref.split("#")[0] for ref in re.findall(r'(?:href|src)="([^"#:][^":]*)"', html)}
    for ref in local:
        assert client.get(f"/{ref}").status_code == 200, ref


def test_the_left_pane_links_every_page(client):
    chrome = client.get("/js/chrome.js").text
    assert set(PAGES) <= set(re.findall(r'href: "([^"]+)"', chrome))


@pytest.mark.parametrize("page", [p for p in PAGES if p != "./"])
def test_every_other_page_has_sections_for_the_left_pane(client, page):
    """page.js lists each <section> in <main> by the heading it's labelled by."""
    html = client.get(f"/{page}").text
    main = re.search(r'<main id="main"[^>]*>(.*)</main>', html, re.S).group(1)
    labelled = re.findall(r'^      <section [^>]*aria-labelledby="([\w-]+)"', main, re.M)
    assert len(labelled) >= 2
    for heading_id in labelled:
        assert re.search(rf'<h2 [^>]*id="{heading_id}"', main), heading_id


def test_a_refusal_pauses_ballotpedia_and_settings_says_until_when(client, upstream):
    upstream.ballotpedia_status = 403
    get_ballot(client)  # from Texas SOS alone
    row = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "ballotpedia")
    assert row["notice_tone"] == "warn" and row["notice"].startswith("Paused until ")
    assert row["notice"].endswith(" after Ballotpedia refused a request; ballots it already sent still show.")


def test_startup_deletes_old_suggestions_and_addresses_not_found(make_app, tmp_path):
    long_ago = time.time() - 90 * DAY
    cache = HttpCache(tmp_path / "data" / "cache.sqlite3", httpx.AsyncClient(), clock=lambda: long_ago)
    for source, q, value in (("suggestions", "1100 congress", {"data": {"Results": [1]}}), ("osm_tiles", "12/940/1686", "iVBORw=="),
                             ("census", "nowhere", {"result": {}}), ("census", "capitol", {"result": {"addressMatches": [1]}})):
        cache._store(RequestSpec("GET", "https://example.test/", params={"q": q}), source, value, long_ago,
                     30 * DAY, DAY, ("result", "addressMatches"))
    cache.close()
    with TestClient(make_app()) as client:
        rows = {s["id"]: s["cache"]["entries"] for s in client.get("/api/sources").json()["sources"]}
    assert (rows["suggestions"], rows["osm_tiles"], rows["geocoding"]) == (0, 0, 1)  # the address found stays, as a fallback


def test_the_footer_shows_the_running_version(client):
    from pallot import __version__
    from pallot.version import short_commit
    response = client.get("/js/version.js")
    assert response.headers["content-type"].startswith("text/javascript")
    assert response.text == f'export const VERSION = "{__version__}";\nexport const COMMIT = {json.dumps(short_commit())};\n'
