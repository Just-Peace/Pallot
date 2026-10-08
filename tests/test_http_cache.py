from __future__ import annotations

import asyncio
import sqlite3
import time

import httpx
import pytest
import respx

from pallot.http_cache import HttpCache, KeyRest, RefreshReport, RequestSpec, UpstreamError, track_calls, value_is_empty

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


async def test_images_are_kept_as_bytes(tmp_path):
    png = b"\x89PNG\r\n\x1a\n\x00\xff"
    with respx.mock() as router:
        route = router.get(URL).mock(return_value=httpx.Response(200, content=png, headers={"content-type": "image/png"}))
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client)
            assert (await cache.get_bytes("demo", SPEC, ttl=60)).value == png
            again = await HttpCache(tmp_path / "c.sqlite3", client).get_bytes("demo", SPEC, ttl=60)  # a restart
            assert again.value == png and route.call_count == 1
            assert (await cache.refresh("demo")).refreshed == 1  # re-fetched as bytes
            assert (await cache.get_bytes("demo", SPEC, ttl=60)).value == png
    assert SPEC.key != RequestSpec("GET", URL, params={"q": "x"}, as_bytes=True).key
    assert RequestSpec.loads(RequestSpec("GET", URL, as_bytes=True).dumps()).as_bytes


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


async def test_calls_to_one_source_are_spaced_out(tmp_path):
    asked: list[tuple[str, float]] = []

    def answer(request):
        asked.append((request.url.params["q"], time.monotonic()))
        return httpx.Response(200, json={})

    with respx.mock() as router:
        router.get(URL).mock(side_effect=answer)
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, min_interval={"demo": 0.2})
            await asyncio.gather(
                *(cache.get_json("demo", RequestSpec("GET", URL, params={"q": f"demo{n}"}), ttl=60) for n in range(3)),
                cache.get_json("other", RequestSpec("GET", URL, params={"q": "other"}), ttl=60),
            )
    assert [q for q, _ in asked].index("other") <= 1  # another source doesn't wait behind demo's queue
    demo = [at for q, at in asked if q.startswith("demo")]
    assert len(demo) == 3 and all(later - earlier >= 0.18 for earlier, later in zip(demo, demo[1:]))


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


async def test_shared_keys_take_turns_and_rest_when_refused(tmp_path):
    clock = Clock()
    sent: list[str] = []
    answers = {"a": 200, "b": 200, "c": 200}

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers["x-key"])
        return httpx.Response(answers[request.headers["x-key"]], json={"v": 1})

    def spec(n: int) -> RequestSpec:
        return RequestSpec("GET", URL, params={"q": str(n)})

    with respx.mock() as router:
        router.get(URL).mock(side_effect=answer)
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
            cache.share_keys("demo", "X-Key", ["a", "b", "c"], {429: 3600, 403: 60})
            for n in range(4):
                await cache.get_json("demo", spec(n), ttl=60)
            assert sent == ["a", "b", "c", "a"]
            answers.update(b=429, c=403)
            sent.clear()
            assert (await cache.get_json("demo", spec(4), ttl=60)).value == {"v": 1}
            assert sent == ["b", "c", "a"] and cache.paused_until("demo") is None
            assert cache.key_rests("demo") == [None, KeyRest(429, clock.now + 3600), KeyRest(403, clock.now + 60)]
            sent.clear()
            await cache.get_json("demo", spec(5), ttl=60)
            assert sent == ["a"]  # b and c rest
            clock.now += 61
            answers.update(a=429, c=429)
            sent.clear()
            with pytest.raises(UpstreamError) as caught:
                await cache.get_json("demo", spec(6), ttl=60)
            assert sent == ["c", "a"] and caught.value.status == 429  # c's turn came after a's, and its rest is over
            assert caught.value.until == cache.paused_until("demo") == clock.now - 61 + 3600  # b's rest ends first
            with pytest.raises(UpstreamError):
                await cache.get_json("demo", spec(7), ttl=60)
            assert sent == ["c", "a"]  # paused: nothing sent
            cache.share_keys("demo", "X-Key", ["d"], {429: 3600})  # a new key isn't resting
            answers["d"] = 200
            assert cache.paused_until("demo") is None
            await cache.get_json("demo", spec(7), ttl=60)
            assert sent[-1] == "d"
    with sqlite3.connect(tmp_path / "c.sqlite3") as db:
        names = [name for (name,) in db.execute("SELECT name FROM flags")]
    assert sorted(name.split(":")[3] for name in names if name.startswith("rest:demo:")) == ["403", "429", "429", "429"]


async def test_seeded_answers_fill_in_but_never_replace_a_newer_copy(tmp_path):
    clock = Clock()
    older, newer = RequestSpec("GET", URL, params={"q": "older"}), RequestSpec("GET", URL, params={"q": "newer"})
    with respx.mock() as router:
        route = router.get(URL).mock(return_value=httpx.Response(200, json={"v": "live"}))
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
            await cache.get_json("demo", older, ttl=60)
            clock.now += 10
            await cache.get_json("demo", newer, ttl=60)
            snapshot = [(older, {"v": "bundled"}), (newer, {"v": "bundled"}), (SPEC, {"v": "bundled"})]
            assert cache.seed("demo", snapshot, clock.now - 5, ttl=60) == 2  # not newer: it was fetched after the snapshot
            assert (await cache.get_json("demo", newer, ttl=60)).value == {"v": "live"}
            assert cache.seed("demo", snapshot, clock.now + 1, ttl=60) == 3
            assert (await cache.get_json("demo", SPEC, ttl=60)).value == {"v": "bundled"}
            clock.now += 62
            assert (await cache.get_json("demo", SPEC, ttl=60)).value == {"v": "live"}  # stale: asked again
    assert route.call_count == 3


@pytest.fixture
def waits(monkeypatch):
    """asyncio.sleep moves the test's Clock on instead of waiting; returns (clock, the waits asked for)."""
    clock, asked = Clock(), []
    real_sleep = asyncio.sleep

    async def sleep(seconds: float) -> None:
        if seconds > 0:
            asked.append(seconds)
            clock.now += seconds
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    return clock, asked


async def test_each_key_keeps_under_its_limit_and_a_burst_goes_at_once(tmp_path, waits):
    clock, asked = waits
    sent: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers["x-key"])
        return httpx.Response(200, json={"v": 1})

    with respx.mock() as router:
        router.get(URL).mock(side_effect=answer)
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
            cache.share_keys("demo", "X-Key", ["a", "b"], {429: 120}, limit=(2, 60))
            for n in range(6):
                await cache.get_json("demo", RequestSpec("GET", URL, params={"q": str(n)}), ttl=60)
    assert sent == ["a", "b", "a", "b", "a", "b"]
    assert asked == [60]  # the fifth waits out a's minute, which b's ends with


async def test_refresh_goes_at_its_own_pace_and_waits_out_a_rate_limit(tmp_path, waits):
    clock, asked = waits
    answers = iter([200, 200, 200, 429, 200, 200, 200])

    with respx.mock() as router:
        router.get(URL).mock(side_effect=lambda request: httpx.Response(next(answers), json={"v": 1}))
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
            for n in range(3):
                await cache.get_json("demo", RequestSpec("GET", URL, params={"q": str(n)}), ttl=60)
            cache.share_keys("demo", "X-Key", ["a"], {429: 120, 403: 3600}, limit=(55, 60), refresh_limit=(1, 2))
            report = await cache.refresh("demo", concurrency=1)
    # the refresh's first request is rate limited: a's rest (120 s) is waited out, then each request goes 2 s apart
    assert report == RefreshReport(refreshed=3, failed=0)
    assert asked[0] == 121 and all(wait == pytest.approx(2) for wait in asked[1:])


async def test_refresh_doesnt_wait_out_a_long_rest(tmp_path, waits):
    clock, asked = waits
    with respx.mock() as router:
        router.get(URL).mock(side_effect=[httpx.Response(200, json={"v": 1}), httpx.Response(200, json={"v": 2}),
                                          httpx.Response(403)])
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
            for n in range(2):
                await cache.get_json("demo", RequestSpec("GET", URL, params={"q": str(n)}), ttl=60)
            cache.share_keys("demo", "X-Key", ["a"], {429: 120, 403: 3600})
            report = await cache.refresh("demo", concurrency=1)
    assert (report.refreshed, report.failed, report.skipped) == (0, 1, 1) and asked == []
    assert report.paused_until == clock.now + 3600


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


def refuse_errors(value) -> str | None:
    return value["error"] if "error" in value else None


async def test_an_answer_its_check_refuses_never_replaces_a_good_copy(tmp_path):
    clock = Clock()
    with respx.mock() as router:
        route = router.get(URL).mock(side_effect=[
            httpx.Response(200, json={"v": "old"}), httpx.Response(200, json={"error": "Layer not found"}),
            httpx.Response(200, json={"v": "new"}),
        ])
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, retry_after=300, clock=clock)
            cache.check_answers("demo", refuse_errors)
            await cache.get_json("demo", SPEC, ttl=60)
            clock.now += 120
            stats = track_calls()
            got = await cache.get_json("demo", SPEC, ttl=60)  # the error: the good copy, marked stale
            assert got.value == {"v": "old"} and got.stale and stats.stale_sources == {"demo"}
            assert cache.peek(SPEC).value == {"v": "old"}
            clock.now += 200
            assert (await cache.get_json("demo", SPEC, ttl=60)).stale  # within retry_after: not asked
            assert route.call_count == 2
            clock.now += 101
            assert (await cache.get_json("demo", SPEC, ttl=60)).value == {"v": "new"}
    assert route.call_count == 3


async def test_a_refused_answer_with_no_good_copy_is_kept_for_retry_after(tmp_path):
    clock = Clock()
    with respx.mock() as router:
        route = router.get(URL).mock(side_effect=[
            httpx.Response(200, json={"error": "Layer not found"}), httpx.Response(200, json={"error": "Busy"}),
            httpx.Response(200, json={"v": 1}),
        ])
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, retry_after=300, clock=clock)
            cache.check_answers("demo", refuse_errors)
            for _ in range(2):  # the second is the kept answer: not asked
                with pytest.raises(UpstreamError, match="^demo: Layer not found$") as caught:
                    await cache.get_json("demo", SPEC, ttl=3600)
                assert caught.value.status is None and caught.value.until is None
            assert route.call_count == 1
            clock.now += 301
            with pytest.raises(UpstreamError, match="Busy"):  # a refused copy is no fallback for another
                await cache.get_json("demo", SPEC, ttl=3600)
            clock.now += 301
            assert (await cache.get_json("demo", SPEC, ttl=3600)).value == {"v": 1}
            clock.now += 3000
            assert (await cache.get_json("demo", SPEC, ttl=3600)).value == {"v": 1}  # kept its own ttl
    assert route.call_count == 3


async def test_refresh_keeps_the_old_copy_when_its_answer_is_refused(tmp_path):
    with respx.mock() as router:
        router.get(URL).mock(side_effect=[
            httpx.Response(200, json={"v": 1}), httpx.Response(200, json={"error": "Busy"}),
        ])
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client)
            cache.check_answers("demo", refuse_errors)
            await cache.get_json("demo", SPEC, ttl=60)
            report = await cache.refresh("demo")
            assert (report.refreshed, report.failed) == (0, 1) and report.errors == (f"{URL}: Busy",)
            assert (await cache.get_json("demo", SPEC, ttl=60)).value == {"v": 1}


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


async def test_a_download_is_streamed_to_a_file_and_not_stored(tmp_path):
    body = b"map" * 1000
    with respx.mock() as router:
        route = router.get(URL).mock(return_value=httpx.Response(200, content=body))
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client)
            stats = track_calls()
            assert await cache.download("demo", SPEC, tmp_path / "map.zip", max_bytes=len(body)) == len(body)
    assert (tmp_path / "map.zip").read_bytes() == body and route.call_count == 1
    assert stats.external_calls == 1 and cache.stats("demo").entries == 0


async def test_a_refused_download_pauses_the_source(tmp_path):
    with respx.mock() as router:
        route = router.get(URL).mock(return_value=httpx.Response(403))
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client)
            cache.pause_on("demo", {403}, 60)
            with pytest.raises(UpstreamError) as refused:
                await cache.download("demo", SPEC, tmp_path / "map.zip", max_bytes=100)
            assert refused.value.status == 403 and cache.paused_until("demo")
            with pytest.raises(UpstreamError) as paused:
                await cache.download("demo", SPEC, tmp_path / "map.zip", max_bytes=100)
    assert paused.value.until and route.call_count == 1 and not (tmp_path / "map.zip").exists()


async def test_a_download_past_its_size_or_off_its_host_leaves_no_file(tmp_path):
    async def unsized():
        for _ in range(3):
            yield b"x" * 600

    with respx.mock() as router:
        router.get(URL).mock(return_value=httpx.Response(200, content=b"x" * 1200))  # says how long it is
        router.get("https://api.example.test/unsized").mock(return_value=httpx.Response(200, content=unsized()))
        router.get("https://api.example.test/moved").mock(
            return_value=httpx.Response(302, headers={"location": "https://elsewhere.test/map.zip"}))
        router.get("https://elsewhere.test/map.zip").mock(return_value=httpx.Response(200, content=b"x"))
        async with httpx.AsyncClient(follow_redirects=True) as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client)
            for url, why in ((URL, "larger than 1,000 bytes"), ("https://api.example.test/unsized", "larger than 1,000 bytes"),
                             ("https://api.example.test/moved", "redirected to elsewhere.test")):
                with pytest.raises(UpstreamError, match=why):
                    await cache.download("demo", RequestSpec("GET", url), tmp_path / "map.zip", max_bytes=1000,
                                         hosts={"api.example.test"})
                assert not (tmp_path / "map.zip").exists()


async def test_peek_reads_what_is_kept_without_asking(tmp_path):
    with respx.mock() as router:
        route = router.get(URL).mock(return_value=httpx.Response(200, json={"n": 1}))
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client)
            assert cache.peek(SPEC) is None
            fetched = await cache.get_json("demo", SPEC, ttl=60)
            assert cache.peek(SPEC) == fetched and route.call_count == 1


def test_value_is_empty_follows_the_path():
    assert value_is_empty([])
    assert value_is_empty({"result": {"addressMatches": []}}, ("result", "addressMatches"))
    assert not value_is_empty({"result": {"addressMatches": [1]}}, ("result", "addressMatches"))
    assert value_is_empty({"result": None}, ("result", "addressMatches"))


async def test_prune_forgets_old_suggestions_and_addresses_not_found(tmp_path):
    clock = Clock()
    async with httpx.AsyncClient() as client:
        cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)

        def store(source, q, value, ttl=10, empty_ttl=None, empty_at=()):
            cache._store(RequestSpec("GET", URL, params={"q": q}), source, value, clock.now, ttl, empty_ttl, empty_at)

        store("suggestions", "old", {"data": {"Results": [1]}})
        store("census", "not found", [], ttl=100, empty_ttl=10)
        store("census", "found", [1], ttl=100, empty_ttl=10)
        store("demo", "other source", [1])
        cache.set_flag("paused:suggestions", "suggestions", 5)
        clock.now += 170
        store("suggestions", "expired lately", {"data": {"Results": []}})  # expires at +180, less than 50 s before the cutoff
        clock.now += 30

        assert cache.prune({"suggestions"}, {"census"}, older_than=50) == 2
        assert [cache.stats(s).entries for s in ("suggestions", "census", "demo")] == [1, 1, 1]
        assert cache._db.execute("SELECT value FROM responses WHERE source = 'census'").fetchone()[0] == "[1]"  # the found one
        assert cache._db.execute("SELECT COUNT(*) FROM flags").fetchone()[0] == 0
        assert cache.prune({"suggestions"}, {"census"}, older_than=50) == 0


def _in_cache_files(tmp_path, text: str) -> list[str]:
    return [p.name for p in tmp_path.glob("c.sqlite3*") if text.encode() in p.read_bytes()]


async def test_clear_leaves_no_readable_copy_in_the_files(tmp_path):
    async with httpx.AsyncClient() as client:
        cache = HttpCache(tmp_path / "c.sqlite3", client)
        for source, q in (("suggestions", "1234 Zanzibar Lane"), ("census", "5678 Quokka Court"), ("demo", "Wombat Way")):
            cache._store(RequestSpec("GET", URL, params={"q": q}), source, {"echo": q}, time.time(), 60, None, ())
        assert _in_cache_files(tmp_path, "Zanzibar") and _in_cache_files(tmp_path, "Quokka")

        assert cache.clear("suggestions") == 1
        assert _in_cache_files(tmp_path, "Zanzibar") == []
        assert _in_cache_files(tmp_path, "Quokka")
        assert cache.clear() == 2
        assert _in_cache_files(tmp_path, "Quokka") == [] and _in_cache_files(tmp_path, "Wombat") == []


async def test_prune_leaves_no_readable_copy_in_the_files(tmp_path):
    clock = Clock()
    async with httpx.AsyncClient() as client:
        cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
        cache._store(RequestSpec("GET", URL, params={"q": "1234 Zanzibar"}), "suggestions", {"x": 1}, clock.now, 10, None, ())
        cache._store(RequestSpec("GET", URL, params={"q": "5678 Quokka"}), "demo", {"x": 1}, clock.now, 10, None, ())
        clock.now += 100
        assert cache.prune({"suggestions"}, (), older_than=50) == 1
        assert _in_cache_files(tmp_path, "Zanzibar") == []
        assert _in_cache_files(tmp_path, "Quokka")


async def test_dates_and_stats_are_read_from_covering_indexes(tmp_path):
    async with httpx.AsyncClient() as client:
        cache = HttpCache(tmp_path / "c.sqlite3", client)
        statements: list[str] = []
        cache._db.set_trace_callback(statements.append)
        cache.peek(SPEC)
        cache.stats("demo")
        cache._db.set_trace_callback(None)
        plans = [" ".join(str(row[-1]) for row in cache._db.execute(f"EXPLAIN QUERY PLAN {sql}")) for sql in statements]
    assert "COVERING INDEX responses_key_dates" in plans[0]
    assert "COVERING INDEX responses_source_stats" in plans[1]


async def test_a_value_held_in_memory_is_not_read_again(tmp_path):
    with respx.mock() as router:
        router.get(URL).mock(return_value=httpx.Response(200, json={"n": 1}))
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client)
            await cache.get_json("demo", SPEC, ttl=60)
            statements: list[str] = []
            cache._db.set_trace_callback(statements.append)
            assert (await cache.get_json("demo", SPEC, ttl=60)).value == {"n": 1}
    assert statements and not any("SELECT value" in sql for sql in statements)


async def test_a_newer_copy_stored_elsewhere_replaces_the_one_in_memory(tmp_path):
    clock = Clock()
    with respx.mock() as router:
        router.get(URL).mock(side_effect=[httpx.Response(200, json={"v": 1}), httpx.Response(200, json={"v": 2})])
        async with httpx.AsyncClient() as client:
            reader = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
            assert (await reader.get_json("demo", SPEC, ttl=60)).value == {"v": 1}
            clock.now += 1
            await HttpCache(tmp_path / "c.sqlite3", client, clock=clock).refresh("demo")  # another process
            again = await reader.get_json("demo", SPEC, ttl=60)
    assert (again.value, again.fetched_at) == ({"v": 2}, clock.now)


async def test_images_are_not_kept_in_memory(tmp_path):
    with respx.mock() as router:
        router.get(URL).mock(return_value=httpx.Response(200, content=b"\x89PNG"))
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client)
            await cache.get_bytes("demo", SPEC, ttl=60)
            assert (await cache.get_bytes("demo", SPEC, ttl=60)).value == b"\x89PNG"
    assert not cache._memory and cache._memory_used == 0


async def test_memory_keeps_the_most_recent_values_up_to_its_size(tmp_path):
    specs = [RequestSpec("GET", URL, params={"q": str(n)}) for n in range(3)]
    with respx.mock() as router:
        router.get(URL).mock(return_value=httpx.Response(200, json="x" * 98))  # 100 bytes stored
        async with httpx.AsyncClient() as client:
            cache = HttpCache(tmp_path / "c.sqlite3", client, memory_bytes=250)
            for spec in specs:
                await cache.get_json("demo", spec, ttl=60)
            assert list(cache._memory) == [specs[1].key, specs[2].key] and cache._memory_used == 200
            await cache.get_json("demo", specs[0], ttl=60)  # read from the database, and kept again
            assert list(cache._memory) == [specs[2].key, specs[0].key] and cache._memory_used == 200
            cache.clear("demo")
            assert not cache._memory and cache._memory_used == 0
            big = HttpCache(tmp_path / "c.sqlite3", client, memory_bytes=50)
            await big.get_json("demo", specs[0], ttl=60)
    assert not big._memory  # larger than the whole budget
