"""Settings-page API (what the server keeps, each voter's own switches), elections list and static pages."""

from __future__ import annotations

import json
import re
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from pallot import enrich
from pallot.__main__ import main
from pallot.api import STATIC_DIR, host_allowed, stamped_page, static_stamp
from pallot.config import DAY
from pallot.http_cache import HttpCache, RequestSpec
from pallot.settings import HEADER
from pallot.text import display_time

from .conftest import ADDRESSES, get_ballot, stream_ballot, switch

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
    assert [s["id"] for s in overview["sources"]] == ["geocoding", "google", "election_precincts", "county_precincts",
                                                       "tigerweb", "osm_tiles", "suggestions", "sos", "key_dates", "wikidata",
                                                       "ballotpedia", "officeholders", "trackaipac", "voteforpeace", "cair", "emgage", "examplepac",
                                                       "mupac", "fec", "tec", "polls"]
    (geocoding, google, precincts, county, outlines, tiles, suggestions, sos, dates, wiki, _, holders, tracker, peace, _, _, example, _,
     fec, tec, polls) = overview["sources"]
    assert (google["toggleable"], google["enabled"]) == (True, True) and "PALLOT_GOOGLE_API_KEY" in google["notice"]
    assert (county["label"], county["toggleable"], county["enabled"]) == (
        "Commissioner & JP precincts (counties)", True, True)
    assert "Harris, Dallas, Tarrant, Travis, Fort Bend, Bexar and Denton" in county["description"]
    assert not [s["id"] for s in overview["sources"] if re.search(r"[a-z)]\. [A-Z]", s["description"])]  # one sentence each
    assert (precincts["label"], precincts["toggleable"], precincts["enabled"], precincts["busy"], precincts["notice"],
            precincts["counts"], precincts["updated"]) == (
        "Election precincts (Texas Legislative Council)", True, True, False, None, [], None)
    assert [s["id"] for s in overview["sources"] if s["frozen"]] == ["examplepac"]
    assert (dates["label"], dates["toggleable"], dates["notice"]) == ("Key election dates (Texas SOS)", True, None)
    assert (outlines["label"], outlines["enabled"]) == ("District map (US Census TIGERweb)", True)
    assert geocoding["toggleable"] is False and sos["enabled"] is True and suggestions["enabled"] is True
    assert tiles["enabled"] is True and example["enabled"] is True
    assert peace["label"] == "Vote for Peace" and peace["counts"] == ["164 Texas candidates", "166 in all"]
    assert set(overview) == {"groups", "sources"}  # nothing to refresh or clear, and no server stats
    assert not {"refresh_confirm", "clear_confirm", "cache", "details", "bundled"} & set(sos)
    assert sos["updated"] is None
    assert tracker["counts"][0].endswith(" Texas entries") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", tracker["updated"])
    assert fec["notice"] is None  # a key of its own: nothing the voter needs to know
    assert tec["notice"] is None and tec["counts"][0].endswith(" candidates and officeholders")
    assert tec["counts"][1].startswith("money raised since ")
    assert (polls["label"], polls["toggleable"], polls["notice"]) == ("Polls (FiftyPlusOne)", True, None)
    assert (holders["label"], holders["toggleable"], holders["enabled"], holders["group"]) == (
        "Seat holders (congress-legislators, Open States)", True, True, "ballot")
    assert (wiki["label"], wiki["toggleable"], wiki["enabled"], wiki["group"]) == ("Wikidata", True, True, "ballot")
    shown = [s["notice"] or "" for s in overview["sources"]] + [c for s in overview["sources"] for c in s["counts"]]
    assert not [text for text in shown if ISO_TIME.search(text)]


def test_times_are_shown_as_people_write_them():
    shown = display_time("2026-09-28T18:25:03+00:00")
    assert re.fullmatch(r"[A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2} [AP]M", shown)
    assert display_time("Mon, 28 Sep 2026 18:25:03 GMT") == shown == display_time(1790619903.0)
    assert display_time(None) is None and display_time("never") is None


def test_a_lookup_is_logged_without_its_address_and_shown_to_no_one(client, logged_calls, caplog):
    first = get_ballot(client)
    assert logged_calls() > 0 and "meta" not in first
    get_ballot(client)
    assert logged_calls() == 0 and "cache hits" in caplog.text and ADDRESSES["capitol"] not in caplog.text
    overview = client.get("/api/sources").json()
    assert ISO_TIME.search(next(s for s in overview["sources"] if s["id"] == "sos")["updated"])
    assert not [s for s in overview["sources"] if {"last_use", "last_lookup"} & set(s)]


def test_switches_are_the_voters_own(client, upstream, tmp_path):
    another_browser = {HEADER: "{}"}
    switch(client, "ballotpedia", False)
    switch(client, "geocoding", False)  # can't be turned off: ignored
    switch(client, "nope", True)  # not a source: ignored
    mine = {s["id"]: s["enabled"] for s in client.get("/api/sources").json()["sources"]}
    assert mine["ballotpedia"] is False and mine["geocoding"] is True
    get_ballot(client)
    assert upstream.count("api4.ballotpedia.org") == 0
    theirs = {s["id"]: s["enabled"] for s in client.get("/api/sources", headers=another_browser).json()["sources"]}
    assert theirs["ballotpedia"] is True  # another browser keeps the defaults
    client.post("/api/ballot", json={"address": ADDRESSES["capitol"]}, headers=another_browser)
    assert upstream.count("api4.ballotpedia.org") > 0
    assert not (tmp_path / "data" / "settings.json").exists()  # nothing is kept on the server


def test_a_header_that_cant_be_read_leaves_the_defaults(client):
    for header in ("not json", '["ballotpedia"]', '{"ballotpedia": "no"}', '{"ballotpedia": 0}'):
        rows = client.get("/api/sources", headers={"X-Pallot-Sources": header}).json()["sources"]
        assert next(s for s in rows if s["id"] == "ballotpedia")["enabled"] is True, header


@pytest.mark.shipped_defaults
def test_ballotpedia_and_vote_for_peace_start_off(client, upstream):
    enabled = {s["id"]: s["enabled"] for s in client.get("/api/sources").json()["sources"]}
    assert enabled["ballotpedia"] is False and enabled["voteforpeace"] is False
    assert all(on for source, on in enabled.items() if source not in {"ballotpedia", "voteforpeace"})
    ballot = get_ballot(client)
    assert upstream.count("api4.ballotpedia.org") == 0
    assert not any(note.startswith("Ballotpedia is off") for note in ballot["notes"])
    assert not any(card["source"] == "voteforpeace" for race in ballot["races"] for c in race["candidates"]
                   for card in c["cards"])


@pytest.mark.shipped_defaults
def test_the_ballot_names_the_sources_pick_by_rule_uses_that_are_off(client):
    switch(client, "suggestions", False)
    first, done = stream_ballot(client)
    assert [s["id"] for s in first["ballot"]["sources_off"]] == ["voteforpeace"]
    assert done["ballot"]["sources_off"] == [{"id": "voteforpeace", "label": "Vote for Peace"}]
    switch(client, "voteforpeace", True)
    switch(client, "polls", False)
    assert [s["id"] for s in get_ballot(client)["sources_off"]] == ["polls"]


def test_sources_are_grouped(client):
    overview = client.get("/api/sources").json()
    assert [(g["id"], g["title"], g["toggle_all"]) for g in overview["groups"]] == [
        ("address", "Address lookup & maps", False), ("official", "Official ballot data", False),
        ("ballot", "Third-party ballot data", False), ("polls", "Third-party polls", False),
        ("scorecards", "Third-party endorsements", True)]
    grouped = {g["id"]: [s["id"] for s in overview["sources"] if s["group"] == g["id"]] for g in overview["groups"]}
    assert grouped == {
        "address": ["geocoding", "google", "election_precincts", "county_precincts", "tigerweb", "osm_tiles", "suggestions"],
        "official": ["sos", "key_dates", "fec", "tec"],
        "ballot": ["wikidata", "ballotpedia", "officeholders"],
        "polls": ["polls"],
        "scorecards": ["trackaipac", "voteforpeace", "cair", "emgage", "examplepac", "mupac"],
    }
    assert not [route.path for route in client.app.routes if "PUT" in getattr(route, "methods", ())]


def test_other_websites_cant_ask_for_a_ballot(client):
    for headers in (
        {"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"},
        {"Sec-Fetch-Site": "same-site", "Origin": "http://testserver:3000"},  # another port on this machine
        {"Origin": "https://evil.example"},  # a browser that doesn't send Sec-Fetch-Site
        {"Origin": "null"},  # a sandboxed page
    ):
        response = client.post("/api/ballot", json={"address": ADDRESSES["capitol"]}, headers=headers)
        assert response.status_code == 403 and "another website" in response.json()["detail"], headers
    own_page = {"Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"}
    assert client.post("/api/ballot", json={"address": ADDRESSES["capitol"]}, headers=own_page).status_code == 200


def test_only_pallots_own_pages_can_use_the_api(client):
    refused = "Refused: Pallot's API only answers Pallot's own pages."
    for site in ("cross-site", "same-site", "none"):
        for path in ("/api/sources", "/api/suggest?q=", "/api/district-outlines?cd=25", "/api/tiles/12/940/1686.png"):
            response = client.get(path, headers={"Sec-Fetch-Site": site})
            assert response.status_code == 403 and response.json()["detail"] == refused, (path, site)
    del client.headers[HEADER]  # a link, a form, an <img>, or a script that doesn't send what api.js does
    for path in ("/api/sources", "/api/config", "/api/endorsements", "/api/elections"):
        assert client.get(path).status_code == 403, path
    assert client.post("/api/ballot", json={"address": ADDRESSES["capitol"]}).status_code == 403
    assert client.get("/api/sources", headers={HEADER: "{}"}).status_code == 200
    del client.headers["Sec-Fetch-Site"]  # the Docker image over plain HTTP, where browsers send no Sec-Fetch-Site
    assert client.get("/api/sources", headers={HEADER: "{}"}).status_code == 200
    assert client.get("/api/sources").status_code == 403


def test_the_maps_tiles_and_the_calendar_file_pass_without_the_pages_header(client):
    del client.headers[HEADER]
    assert client.get("/api/tiles/12/940/1686.png").status_code == 200  # Leaflet's <img>, same origin
    del client.headers["Sec-Fetch-Site"]  # plain HTTP: the referrer decides
    assert client.get("/api/tiles/12/940/1686.png", headers={"Referer": "http://testserver/"}).status_code == 200
    assert client.get("/api/tiles/12/940/1686.png", headers={"Referer": "https://evil.example/"}).status_code == 403
    assert client.get("/api/tiles/12/940/1686.png").status_code == 403
    for headers in ({}, {"Sec-Fetch-Site": "none"}, {"Sec-Fetch-Site": "same-origin"}):  # a bookmark, an email, the page
        assert client.get("/api/key-dates.ics?date=2026-11-03", headers=headers).status_code != 403, headers
    assert client.get("/api/key-dates.ics?date=2026-11-03", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_no_developer_pages_or_server_name(client, monkeypatch):
    for path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
        assert client.get(path).status_code == 404, path
    started: list[dict] = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: started.append(kwargs))
    main([])  # how `uv run pallot` and the Docker image start it
    assert started[0]["server_header"] is False


def test_every_answer_carries_the_security_headers(client):
    for path in ("/", "/settings.html", "/css/app.css", client.app.state.static_prefix + "js/api.js", "/api/config",
                 "/api/nowhere", "/nowhere.html"):
        headers = client.get(path).headers
        assert headers["content-security-policy"].startswith("default-src 'self'; script-src 'self'"), path
        assert "frame-ancestors 'none'" in headers["content-security-policy"], path
        assert headers["x-content-type-options"] == "nosniff", path
        assert headers["referrer-policy"] == "strict-origin-when-cross-origin", path
        assert headers["x-frame-options"] == "DENY", path
    refused = client.get("/api/config", headers={"Sec-Fetch-Site": "cross-site"})
    assert refused.status_code == 403 and refused.headers["x-frame-options"] == "DENY"


def test_only_localhost_ip_addresses_and_allowed_names_are_answered(client):
    for host in ("localhost:8000", "127.0.0.1:8000", "192.168.1.20:8000", "[::1]:8000"):
        assert client.get("/api/sources", headers={"Host": host}).status_code == 200, host
    response = client.get("/", headers={"Host": "rebind.evil.example:8000"})  # DNS rebinding
    assert response.status_code == 400 and "PALLOT_ALLOWED_HOSTS" in response.json()["detail"]
    assert host_allowed("nas.local:8000", ("nas.local",)) and host_allowed("anything.example", ("*",))
    assert not host_allowed("nas.local", ()) and not host_allowed("", ()) and not host_allowed("[::1", ())


def test_settings_cant_refresh_or_clear_what_the_server_keeps(client):
    get_ballot(client)
    for path in ("/api/sources/sos/refresh", "/api/sources/sos/clear", "/api/cache/clear"):
        assert client.post(path).status_code in (404, 405), path
    assert client.put("/api/sources/sos", json={"enabled": False}).status_code in (404, 405)
    assert client.app.state.svc.cache.stats("sos").entries > 0


def test_sboe_portal_down_is_asked_once_until_its_wait_is_over(client, upstream, make_app, logged_calls):
    switch(client, "election_precincts", False)  # it asks the same portal
    upstream.down.add("data.capitol.texas.gov")
    first = get_ballot(client)
    assert first["districts"]["sboe"] is None and any("State Board of Education map" in w for w in first["warnings"])
    get_ballot(client)
    assert upstream.count("plane2106_kml.zip") == 1 and logged_calls() == 0
    geocoding = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "geocoding")
    assert geocoding["notice_tone"] == "warn"
    assert geocoding["notice"].startswith("The last download of the State Board of Education map failed (HTTP 500)")
    upstream.down.clear()
    status, printed = make_app.cache_command("refresh", "geocoding")  # stale: no map kept
    assert status == 0 and "Re-downloaded the State Board of Education map." in printed
    assert get_ballot(client)["districts"]["sboe"] == 5 and upstream.count("plane2106_kml.zip") == 2


def test_voteforpeace_off_leaves_its_cards_out(client):
    switch(client, "voteforpeace", False)
    ballot = get_ballot(client)
    assert not [card for race in ballot["races"] for c in race["candidates"] for card in c["cards"]
                if card["source"] == "voteforpeace"]


PAGES = ["./", "settings.html", "faq.html", "about.html", "privacy.html"]


@pytest.mark.parametrize("path", ["/", "/favicon.svg", "/css/app.css"])  # the scripts: test_frontend_modules.py
def test_static_pages(client, path):
    assert client.get(path).status_code == 200


def test_static_files_are_kept_but_checked_before_each_use(client):
    """At their own addresses (a page or bookmark from before an update), and the pages themselves."""
    for path in ("/js/version.js", "/faq.html"):
        assert client.get(path).headers["cache-control"] == "no-cache", path
    first = client.get("/js/dom.js")
    again = client.get("/js/dom.js", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and again.headers["cache-control"] == "no-cache"
    page = client.get("/")
    again = client.get("/", headers={"If-None-Match": page.headers["etag"]})
    assert again.status_code == 304 and again.headers["cache-control"] == "no-cache"


def test_the_pages_load_their_files_from_a_stamped_prefix_kept_a_year(client):
    """A repeat page view asks for nothing but the page; an update changes the prefix, so no page mixes
    modules from the browser's cache with new ones."""
    prefix = client.app.state.static_prefix
    assert re.fullmatch(r"/s/[0-9a-f]{16}/", prefix)
    for path in ("js/dom.js", "js/version.js", "css/app.css", "favicon.svg", "vendor/leaflet/leaflet.css"):
        response = client.get(prefix + path)
        assert response.status_code == 200 and response.headers["cache-control"] == "public, max-age=31536000, immutable", path
        assert response.content == client.get(f"/{path}").content
    stale = client.get("/s/0123456789abcdef/js/dom.js")  # a page loaded before an update
    assert stale.status_code == 200 and stale.headers["cache-control"] == "no-cache"
    assert client.get(prefix).status_code == 404 and client.get("/s/").status_code == 404


def test_the_pages_name_their_files_under_the_prefix_and_preload_their_modules(client):
    prefix = client.app.state.static_prefix
    html = client.get("/").text
    assert f'<link rel="stylesheet" href="{prefix}vendor/leaflet/leaflet.css">' in html
    assert f'<script type="module" src="{prefix}js/ballot.js"></script>' in html
    preloaded = re.findall(r'<link rel="modulepreload" href="([^"]+)">', html)
    assert {f"{prefix}js/dom.js", f"{prefix}js/version.js", f"{prefix}js/chrome.js"} <= set(preloaded)
    assert f"{prefix}js/ballot.js" not in preloaded and not any("vendor" in ref for ref in preloaded)  # Leaflet: when the map opens
    assert html.index("modulepreload") < html.index("</head>") and 'href="#main"' in html  # links to the page left alone


def test_the_stamp_changes_with_any_static_file_but_the_pages(tmp_path):
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "a.js").write_text('import { b } from "./b.js";\n')
    (tmp_path / "js" / "b.js").write_text("export const b = 1;\n")
    (tmp_path / "index.html").write_text("<p>one</p>")
    stamp = static_stamp(tmp_path, "v1")
    assert static_stamp(tmp_path, "v1") == stamp != static_stamp(tmp_path, "v2")
    (tmp_path / "index.html").write_text("<p>two</p>")
    assert static_stamp(tmp_path, "v1") == stamp
    (tmp_path / "js" / "b.js").write_text("export const b = 2;\n")
    assert static_stamp(tmp_path, "v1") != stamp


def test_a_page_is_stamped_and_preloaded():
    html = ('<head>\r\n  <link rel="icon" href="favicon.svg">\r\n  <link rel="stylesheet" href="https://example.test/a.css">\r\n'
            '  <script type="module" src="js/ballot.js"></script>\r\n</head><a href="faq.html">FAQ</a>')
    stamped = stamped_page(html, STATIC_DIR, "/s/x/")
    assert '<link rel="icon" href="/s/x/favicon.svg">' in stamped and 'href="https://example.test/a.css"' in stamped
    assert '<script type="module" src="/s/x/js/ballot.js"></script>\r\n  <link rel="modulepreload" href="/s/x/js/' in stamped
    assert '<a href="faq.html">' in stamped


def test_responses_are_gzipped_when_the_browser_asks(client):
    plain = client.post("/api/ballot", json={"address": ADDRESSES["capitol"]},
                        headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers
    zipped = client.post("/api/ballot", json={"address": ADDRESSES["capitol"]},
                         headers={"Accept-Encoding": "gzip"})
    assert zipped.headers["content-encoding"] == "gzip" and int(zipped.headers["content-length"]) < len(plain.content) / 4
    assert zipped.json().keys() == plain.json().keys()
    assert client.get("/css/app.css", headers={"Accept-Encoding": "gzip"}).headers["content-encoding"] == "gzip"


def cards(ballot):
    races = ballot["races"] + [race for section in ballot["maybe"] for race in section["races"]]
    return [card for race in races for card in race["cards"] + [c for cand in race["candidates"] for c in cand["cards"]]]


def test_the_page_gets_the_races_first_then_the_cards(client, logged_calls):
    first, last = stream_ballot(client)
    assert first["done"] is False and last["done"] is True
    assert first["ballot"]["races"] and not cards(first["ballot"])
    assert [r["key"] for r in first["ballot"]["races"]] == [r["key"] for r in last["ballot"]["races"]]
    assert cards(last["ballot"]) and first["ballot"]["districts"] == last["ballot"]["districts"]
    assert logged_calls() > 0
    plain = get_ballot(client)
    assert logged_calls() == 0 and plain == last["ballot"]
    stream_ballot(client)
    assert logged_calls() == 0


def test_a_streamed_lookup_that_fails_is_still_an_error_status(client):
    switch(client, "sos", False)
    switch(client, "ballotpedia", False)
    response = client.post("/api/ballot", json={"address": ADDRESSES["capitol"]}, headers={"Accept": "application/x-ndjson"})
    assert response.status_code == 400 and "No ballot source" in response.json()["detail"]


def test_cards_that_fail_after_the_races_are_an_error_line(client, monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(enrich, "run", broken)
    first, last = stream_ballot(client)
    assert first["done"] is False and first["ballot"]["races"]
    assert last == {"error": "Couldn't load money, polls and endorsements."}


def test_the_streamed_ballot_is_gzipped_line_by_line(client):
    response = client.post("/api/ballot", json={"address": ADDRESSES["capitol"]},
                           headers={"Accept": "application/x-ndjson", "Accept-Encoding": "gzip"})
    assert response.headers["content-encoding"] == "gzip" and response.headers["x-accel-buffering"] == "no"
    assert [json.loads(line)["done"] for line in response.text.splitlines()] == [False, True]


@pytest.mark.parametrize("page", PAGES)
def test_every_page_leaves_its_left_pane_and_footer_to_chrome_js_and_its_files_exist(client, page):
    html = client.get(f"/{page}").text
    assert "<footer" not in html
    aside = re.search(r'<aside class="sidebar"[^>]*>(.*?)</aside>', html, re.S).group(1)
    if page == "./":  # the ballot's own parts of the pane: its hint before an address, and the section list
        assert aside.count('data-slot="address"') == 1 and 'id="jump"' in aside and "address-card" not in aside
        assert 'id="lookup-form"' not in aside  # the form is the entry card, in the main area
    else:
        assert not aside.strip()
    entry = {"./": "ballot", "settings.html": "settings", "faq.html": "faq"}.get(page, "page")  # settings.js and faq.js import page.js
    prefix = client.app.state.static_prefix
    assert re.findall(rf'<script type="module" src="{prefix}js/([\w-]+)\.js"></script>', html) == [entry]
    assert f'<link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml">' in html
    local = {ref.split("#")[0] for ref in re.findall(r'(?:href|src)="([^"#:][^":]*)"', html)}
    for ref in local:
        assert client.get(ref if ref.startswith("/") else f"/{ref}").status_code == 200, ref


def test_the_left_pane_links_every_page(client):
    chrome = client.get("/js/chrome.js").text
    assert set(PAGES) <= set(re.findall(r'href: "([^"]+)"', chrome))


@pytest.mark.parametrize("page", ["settings.html", "faq.html"])
def test_long_pages_have_section_chips_for_a_phone(client, page):
    """page.js draws the sections as chips in a page's <nav class="section-chips">."""
    assert '<nav class="section-chips" aria-label=' in client.get(f"/{page}").text


def test_the_faq_has_a_search_box(client):
    html = client.get("/faq.html").text
    assert '<input type="search" id="faq-query"' in html and 'id="faq-search-status" role="status"' in html


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
        kept = {tag: client.app.state.svc.cache.stats(tag).entries for tag in ("suggestions", "osm_tiles", "census")}
    assert kept == {"suggestions": 0, "osm_tiles": 0, "census": 1}  # the address found stays, as a fallback


def test_the_footer_shows_the_running_version(client):
    from pallot import __version__
    from pallot.version import short_commit
    response = client.get("/js/version.js")
    assert response.headers["content-type"].startswith("text/javascript")
    assert response.text == f'export const VERSION = "{__version__}";\nexport const COMMIT = {json.dumps(short_commit())};\n'
