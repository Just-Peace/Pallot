from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from votebot.http_cache import HttpCache, RequestSpec, UpstreamError, track_calls, value_is_empty

pytestmark = pytest.mark.anyio

URL = "https://api.example.test/data"
SPEC = RequestSpec("GET", URL, params={"q": "x"})


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


async def test_second_call_comes_from_the_cache(tmp_path):
    with respx.mock() as router:
        route = router.get(URL).mock(return_value=httpx.Response(200, json={"n": 1}))
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client)
            stats = track_calls()
            first = await cache.get_json("demo", SPEC, ttl=60)
            second = await cache.get_json("demo", SPEC, ttl=60)
    assert first.value == second.value == {"n": 1}
    assert route.call_count == 1
    assert (stats.external_calls, stats.cache_hits) == (1, 1)


async def test_cache_survives_a_restart(tmp_path):
    with respx.mock() as router:
        route = router.get(URL).mock(return_value=httpx.Response(200, json=[1, 2, 3]))
        async with httpx.AsyncClient() as client:
            await HttpCache(tmp_path / "c.sqlite3", client).get_json("demo", SPEC, ttl=60)
            again = await HttpCache(tmp_path / "c.sqlite3", client).get_json("demo", SPEC, ttl=60)
    assert again.value == [1, 2, 3]
    assert route.call_count == 1


async def test_expired_entries_are_fetched_again(tmp_path):
    clock = Clock()
    with respx.mock() as router:
        route = router.get(URL).mock(side_effect=[httpx.Response(200, json={"v": 1}), httpx.Response(200, json={"v": 2})])
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
            assert (await cache.get_json("demo", SPEC, ttl=60)).value == {"v": 1}
            clock.now += 59
            assert (await cache.get_json("demo", SPEC, ttl=60)).value == {"v": 1}
            clock.now += 2
            assert (await cache.get_json("demo", SPEC, ttl=60)).value == {"v": 2}
    assert route.call_count == 2


async def test_empty_results_use_the_short_lifetime(tmp_path):
    clock = Clock()
    empty = {"result": {"addressMatches": []}}
    with respx.mock() as router:
        route = router.get(URL).mock(return_value=httpx.Response(200, json=empty))
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
            await cache.get_json("demo", SPEC, ttl=1000, empty_ttl=10, empty_at=("result", "addressMatches"))
            clock.now += 11
            await cache.get_json("demo", SPEC, ttl=1000, empty_ttl=10, empty_at=("result", "addressMatches"))
    assert route.call_count == 2


async def test_concurrent_requests_share_one_fetch(tmp_path):
    async def slow(request):
        await asyncio.sleep(0.05)
        return httpx.Response(200, json={"ok": True})

    with respx.mock() as router:
        route = router.get(URL).mock(side_effect=slow)
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client)
            results = await asyncio.gather(*(cache.get_json("demo", SPEC, ttl=60) for _ in range(10)))
    assert {r.value["ok"] for r in results} == {True}
    assert route.call_count == 1


async def test_failed_refresh_serves_the_old_copy(tmp_path):
    clock = Clock()
    with respx.mock() as router:
        router.get(URL).mock(side_effect=[httpx.Response(200, json={"v": "old"}), httpx.Response(503)])
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
            await cache.get_json("demo", SPEC, ttl=60)
            clock.now += 120
            stats = track_calls()
            got = await cache.get_json("demo", SPEC, ttl=60)
    assert got.value == {"v": "old"} and got.stale
    assert stats.stale_sources == {"demo"}


async def test_a_failed_request_is_not_retried_for_a_while(tmp_path):
    clock = Clock()
    with respx.mock() as router:
        route = router.get(URL).mock(
            side_effect=[httpx.Response(200, json={"v": "old"}), httpx.Response(503), httpx.Response(200, json={"v": "new"})]
        )
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, retry_after=300, clock=clock)
            await cache.get_json("demo", SPEC, ttl=60)
            clock.now += 120
            assert (await cache.get_json("demo", SPEC, ttl=60)).stale  # the 503: the old copy
            clock.now += 200
            stats = track_calls()
            again = await cache.get_json("demo", SPEC, ttl=60)  # within retry_after: not asked
            assert again.value == {"v": "old"} and again.stale
            assert stats.external_calls == 0 and stats.stale_sources == {"demo"}
            clock.now += 101
            assert (await cache.get_json("demo", SPEC, ttl=60)).value == {"v": "new"}
    assert route.call_count == 3


async def test_a_refusal_pauses_the_source_even_with_a_copy(tmp_path):
    clock = Clock()
    other = RequestSpec("GET", URL, params={"q": "other"})
    with respx.mock() as router:
        route = router.get(URL).mock(side_effect=[httpx.Response(200, json={"v": 1}), httpx.Response(429)])
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
            cache.pause_on("demo", {429}, 3600)
            await cache.get_json("demo", SPEC, ttl=60)
            clock.now += 120
            assert (await cache.get_json("demo", SPEC, ttl=60)).stale  # the 429: the old copy, and a pause
            assert cache.paused_until("demo") == clock.now + 3600
            assert (await cache.get_json("demo", SPEC, ttl=60)).value == {"v": 1}  # paused: still served
            with pytest.raises(UpstreamError) as caught:
                await cache.get_json("demo", other, ttl=60)  # paused, and nothing stored for it
            assert caught.value.until == clock.now + 3600
    assert route.call_count == 2


async def test_refresh_stops_when_the_source_pauses(tmp_path):
    clock = Clock()
    specs = [RequestSpec("GET", URL, params={"q": str(n)}) for n in range(3)]
    with respx.mock() as router:
        route = router.get(URL).mock(side_effect=[*(httpx.Response(200, json={"n": n}) for n in range(3)), httpx.Response(429)])
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
            cache.pause_on("demo", {429}, 3600)
            for spec in specs:
                await cache.get_json("demo", spec, ttl=60)
            report = await cache.refresh("demo", concurrency=1)
            assert (report.refreshed, report.failed, report.skipped) == (0, 1, 2)
            assert report.paused_until == clock.now + 3600
            again = await cache.refresh("demo")
            assert (again.refreshed, again.failed, again.skipped) == (0, 0, 3)
    assert route.call_count == 4


async def test_a_clear_while_a_row_is_read_is_not_an_error(tmp_path):
    """Another process on the same file clears the cache just as a row is read: the reader
    gets the copy it read, not a crash."""
    with respx.mock() as router:
        route = router.get(URL).mock(return_value=httpx.Response(200, json={"v": 1}))
        async with httpx.AsyncClient() as client:
            writer = HttpCache(tmp_path / "c.sqlite3", client)
            await writer.get_json("demo", SPEC, ttl=60)

            class ClearingClock(Clock):  # get_json asks the time right after reading the row
                def __call__(self) -> float:
                    writer.clear("demo")
                    return super().__call__()

            reader = HttpCache(tmp_path / "c.sqlite3", client, clock=ClearingClock())  # nothing in memory yet
            assert (await reader.get_json("demo", SPEC, ttl=60)).value == {"v": 1}
    assert route.call_count == 1


async def test_failure_with_nothing_cached_raises(tmp_path):
    with respx.mock() as router:
        router.get(URL).mock(return_value=httpx.Response(403))
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client)
            with pytest.raises(UpstreamError) as caught:
                await cache.get_json("demo", SPEC, ttl=60)
    assert caught.value.status == 403 and caught.value.source == "demo"


async def test_stats_clear_and_refresh_per_source(tmp_path):
    clock = Clock()
    other = RequestSpec("POST", URL, json={"id": 1})
    with respx.mock() as router:
        get_route = router.get(URL).mock(side_effect=[httpx.Response(200, json={"v": 1}), httpx.Response(200, json={"v": 2})])
        router.post(URL).mock(return_value=httpx.Response(200, json=[]))
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
            await cache.get_json("a", SPEC, ttl=60)
            await cache.get_json("b", other, ttl=60)
            assert cache.stats("a").entries == 1 and cache.stats("b").entries == 1
            clock.now += 100
            assert cache.stats("a").expired == 1

            report = await cache.refresh("a")
            assert (report.refreshed, report.failed) == (1, 0)
            assert get_route.call_count == 2
            assert cache.stats("a").expired == 0
            assert (await cache.get_json("a", SPEC, ttl=60)).value == {"v": 2}

            assert cache.clear("b") == 1
            assert cache.stats("b").entries == 0 and cache.stats("a").entries == 1
            assert cache.clear() == 1


async def test_flags_expire_and_clear_with_their_source(tmp_path):
    clock = Clock()
    async with httpx.AsyncClient() as client:
        cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
        cache.set_flag("paused", "demo", ttl=60)
        assert cache.flag_until("paused") == clock.now + 60
        clock.now += 61
        assert cache.flag_until("paused") is None
        cache.set_flag("paused", "demo", ttl=60)
        cache.clear("demo")
        assert cache.flag_until("paused") is None


def test_value_is_empty_follows_the_path():
    assert value_is_empty([])
    assert value_is_empty({"result": {"addressMatches": []}}, ("result", "addressMatches"))
    assert not value_is_empty({"result": {"addressMatches": [1]}}, ("result", "addressMatches"))
    assert value_is_empty({"result": None}, ("result", "addressMatches"))
