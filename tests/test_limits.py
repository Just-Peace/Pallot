"""What bounds one client on a public Pallot: per-client rate limits, the cap on lookups at once,
Google's daily cap and the cap on what's kept per address."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from pallot import __main__ as main, enrich
from pallot.api import wait_words
from pallot.config import Config, load_config
from pallot.http_cache import HttpCache, RequestSpec, UpstreamError
from pallot.limits import ClientLimits, Limiter, Rate, RateLimits, budget, parse_rate
from pallot.services import prune

from .conftest import ADDRESSES, GOOGLE_KEY, NEW_STREET, get_ballot, stream_ballot, switch
from .test_http_cache import Clock
from .test_osm_tiles import capitol_point, tile_at

VOTER, NEIGHBOUR = "203.0.113.5", "198.51.100.7"
PROXY = ("10.0.0.1", 50000)
TIGHT = RateLimits(ballot=Rate(2, 3600), suggest=Rate(3, 60), outlines=None, tiles=Rate(1, 60))


def test_rates_are_written_as_a_count_per_period():
    assert parse_rate("30/hour") == Rate(30, 3600)
    assert parse_rate("600/10min") == Rate(600, 600)
    assert parse_rate(" 5 / 30s ") == Rate(5, 30)
    assert parse_rate("2/days") == Rate(2, 86400) and parse_rate("100/2h") == Rate(100, 7200)
    assert parse_rate("0") is parse_rate("off") is parse_rate("0/hour") is None
    for wrong in ("30", "30/fortnight", "lots/hour", "30/0h"):
        with pytest.raises(ValueError):
            parse_rate(wrong)


def test_a_bucket_refills_over_its_period_and_says_how_long_to_wait():
    clock = Clock()
    limiter = Limiter(Rate(2, 60), clock)
    assert limiter.take("a") == limiter.take("a") == 0
    assert limiter.take("a") == pytest.approx(30)
    assert limiter.take("b") == 0  # each client has its own
    clock.now += 30
    assert limiter.take("a") == 0 and limiter.take("a") == pytest.approx(30)


def test_idle_clients_are_forgotten(monkeypatch):
    clock = Clock()
    limiter = Limiter(Rate(2, 60), clock)
    for client in "ab":
        limiter.take(client)
    clock.now += 30
    limiter.take("a")
    limiter.take("a")
    clock.now += 30  # b is full again, a isn't
    limiter.take("c")
    assert set(limiter.buckets) == {"a", "c"}
    monkeypatch.setattr("pallot.limits.MAX_CLIENTS", 2)
    clock.now += 40  # both full again, and too many to wait for the next sweep
    limiter.take("d")
    assert set(limiter.buckets) == {"d"}


def test_only_requests_that_can_ask_outside_sources_spend_a_budget():
    assert budget("POST", "/api/ballot") == "ballot" and budget("GET", "/api/ballot") is None
    assert budget("GET", "/api/suggest") == "suggest" and budget("GET", "/api/district-outlines") == "outlines"
    assert budget("GET", "/api/tiles/12/1/2.png") == "tiles"
    assert budget("GET", "/api/sources") is None and budget("GET", "/") is None


def test_this_machine_is_never_limited():
    limits = ClientLimits(RateLimits(ballot=Rate(1, 3600)))
    for host in ("127.0.0.1", "::1", "127.0.0.1", "::1"):
        assert limits.wait("POST", "/api/ballot", host) == 0
    assert limits.wait("POST", "/api/ballot", "203.0.113.5") == 0
    assert limits.wait("POST", "/api/ballot", "203.0.113.5") == 3600


def test_the_wait_is_said_in_seconds_or_minutes():
    assert [wait_words(n) for n in (1, 45, 60, 61, 3600)] == ["1 second", "45 seconds", "1 minute", "2 minutes", "60 minutes"]


def behind(app, proxy: str = "10.0.0.1") -> ProxyHeadersMiddleware:
    """``app`` behind a proxy at ``proxy`` that it trusts, as uvicorn runs it with PALLOT_TRUSTED_PROXIES."""
    return ProxyHeadersMiddleware(app, trusted_hosts=proxy)


def ask(client: TestClient, path: str, frm: str = VOTER, **params) -> httpx.Response:
    headers = {"X-Forwarded-For": frm}
    if path == "/api/ballot":
        return client.post(path, json={"address": ADDRESSES[params.get("address", "capitol")]}, headers=headers)
    return client.get(path, params=params, headers=headers)


def test_a_client_past_its_budget_is_asked_to_wait(make_app, upstream):
    with TestClient(behind(make_app(rate_limits=TIGHT)), client=PROXY) as client:
        assert ask(client, "/api/ballot").status_code == 200
        assert ask(client, "/api/ballot", address="ut").status_code == 200
        refused = ask(client, "/api/ballot")
        assert refused.status_code == 429 and refused.headers["retry-after"] == "1800"
        assert refused.json()["detail"] == "Too many requests from your connection. Please wait 30 minutes and try again."
        asked = len(upstream.calls)
        assert ask(client, "/api/ballot", address="harris").status_code == 429
        assert len(upstream.calls) == asked  # refused before anything was asked
        assert ask(client, "/api/ballot", NEIGHBOUR).status_code == 200  # each client has its own budget

        for _ in range(3):
            assert ask(client, "/api/suggest", q="1100 Congress Ave").status_code == 200
        assert ask(client, "/api/suggest", q="1100 Congress Ave").status_code == 429  # a budget of its own
        z, x, y = tile_at(14, *capitol_point())
        assert ask(client, f"/api/tiles/{z}/{x}/{y}.png").status_code == 200
        assert ask(client, f"/api/tiles/{z}/{x}/{y}.png").status_code == 429
        for _ in range(5):
            assert ask(client, "/api/district-outlines", cd=37).status_code == 200  # no limit set
        assert ask(client, "/api/sources").status_code == 200  # asks no one

        for _ in range(4):
            assert ask(client, "/api/ballot", "127.0.0.1").status_code == 200  # this machine isn't limited


def test_a_client_that_isnt_the_proxy_cant_claim_another_address(make_app):
    """uvicorn reads X-Forwarded-For only from PALLOT_TRUSTED_PROXIES (its forwarded_allow_ips)."""
    with TestClient(behind(make_app(rate_limits=TIGHT)), client=(VOTER, 50000)) as client:
        for claimed in ("192.0.2.1", "192.0.2.2"):
            assert ask(client, "/api/ballot", claimed).status_code == 200
        assert ask(client, "/api/ballot", "192.0.2.3").status_code == 429  # all counted as the voter's own


def test_the_server_trusts_the_proxies_the_setting_names(monkeypatch):
    ran = {}
    monkeypatch.setattr(main.uvicorn, "run", lambda *args, **kwargs: ran.update(kwargs))
    monkeypatch.setenv("PALLOT_TRUSTED_PROXIES", "10.0.0.0/8")
    main.main([])
    assert ran["forwarded_allow_ips"] == "10.0.0.0/8"
    assert load_config({}).trusted_proxies == "127.0.0.1"


def test_the_limits_come_from_the_environment():
    config = load_config({"PALLOT_LIMIT_BALLOT": "5/min", "PALLOT_LIMIT_TILES": "off", "PALLOT_MAX_LOOKUPS": "2",
                          "PALLOT_GOOGLE_DAILY_MAX": "0", "PALLOT_ADDRESSES_MAX_MB": "10"})
    assert config.rate_limits == RateLimits(ballot=Rate(5, 60), tiles=None)
    assert (config.max_lookups, config.google_daily_max, config.addresses_max_bytes) == (2, 0, 10 << 20)
    defaults = load_config({})
    assert defaults.rate_limits == RateLimits() and defaults.max_lookups == 8 and defaults.google_daily_max == 300
    with pytest.raises(ValueError):
        load_config({"PALLOT_LIMIT_SUGGEST": "lots"})


def test_a_lookup_past_the_cap_on_lookups_at_once_is_turned_away(make_app):
    with TestClient(make_app(max_lookups=1)) as client:
        lookups = client.app.state.lookups
        client.portal.call(lookups.acquire)  # another voter's lookup
        busy = client.post("/api/ballot", json={"address": ADDRESSES["capitol"]})
        assert busy.status_code == 503 and busy.headers["retry-after"] == "5"
        assert "busy" in busy.json()["detail"]
        client.portal.call(lookups.release)
        get_ballot(client)
        get_ballot(client)  # its place was given back


def test_a_streamed_lookup_holds_its_place_until_its_cards_are_added(make_app, monkeypatch):
    held = []
    run = enrich.run

    async def watched(*args, **kwargs):
        held.append(client.app.state.lookups.locked())
        return await run(*args, **kwargs)

    monkeypatch.setattr(enrich, "run", watched)
    with TestClient(make_app(max_lookups=1)) as client:
        stream_ballot(client)
        assert held == [True]
        stream_ballot(client)  # and gives it back after
        switch(client, "sos", False)
        switch(client, "ballotpedia", False)
        assert client.post("/api/ballot", json={"address": ADDRESSES["capitol"]}).status_code == 400
        assert not client.app.state.lookups.locked()  # a lookup that fails gives it back too


@pytest.mark.anyio
async def test_a_capped_source_is_paused_until_the_day_turns(tmp_path):
    clock = Clock()
    clock.now = 86400 * 20_000 + 3600  # 1 AM UTC
    url = "https://geocode.example.test/address"
    with respx.mock() as router:
        route = router.get(url).mock(return_value=httpx.Response(200, json={"results": [1]}))
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
            cache.cap_daily("google", 2)
            for q in ("a", "b"):
                await cache.get_json("google", RequestSpec("GET", url, params={"q": q}), ttl=60)
            assert cache.paused_until("google") == 86400 * 20_001
            with pytest.raises(UpstreamError):
                await cache.get_json("google", RequestSpec("GET", url, params={"q": "c"}), ttl=60)
            assert route.call_count == 2

            clock.now = 86400 * 20_001 + 60  # the next day, after a restart
            cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
            cache.cap_daily("google", 2)
            await cache.get_json("google", RequestSpec("GET", url, params={"q": "c"}), ttl=60)
            assert route.call_count == 3 and cache.paused_until("google") is None
            cache.set_flag("paused:google", "google", 0)  # a restart counts what was sent today
            await cache.get_json("google", RequestSpec("GET", url, params={"q": "d"}), ttl=60)
            assert HttpCache(tmp_path / "c.sqlite3", client, clock=clock).paused_until("google") == 86400 * 20_002


def test_settings_says_why_google_is_paused(make_app, upstream):
    with TestClient(make_app(google_key=GOOGLE_KEY, google_daily_max=1)) as client:
        switch(client, "ballotpedia", False)
        assert get_ballot(client, NEW_STREET)["location"]["geocoder"] == "google"
        row = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "google")
        assert "today's lookups ran out" in row["notice"]


@pytest.mark.anyio
async def test_each_per_address_source_is_kept_under_its_cap(tmp_path):
    clock = Clock()
    async with httpx.AsyncClient() as client:
        cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
        for source in ("census", "ballotpedia", "fec"):
            for n in range(4):
                clock.now += 1
                cache._store(RequestSpec("GET", "https://x.test", params={"s": source, "n": n}), source,
                             {"pad": "x" * 1000}, clock.now, 10**6, None, ())
        prune(cache, Config(data_dir=tmp_path, addresses_max_bytes=2500))
        assert [cache.stats(s).entries for s in ("census", "ballotpedia", "fec")] == [2, 2, 4]
        kept = cache._db.execute("SELECT request FROM responses WHERE source = 'census'").fetchall()
        assert all('"n": 2' in row[0] or '"n": 3' in row[0] for row in kept)  # the newest
