"""pallot-cache (maintain.py): checking, refreshing, pruning and rebuilding what the server keeps,
from the host, on the same data folder, while the server may be running."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import sqlite3
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from pallot import maintain
from pallot.api import keep_pruning
from pallot.config import DAY, Config
from pallot.http_cache import HttpCache, RequestSpec
from pallot.services import prune

from .conftest import get_ballot, last_use, load


def rows(client: TestClient) -> dict[str, dict]:
    return {s["id"]: s for s in client.get("/api/sources").json()["sources"]}


def expire(data_dir, source: str) -> int:
    """Make every row of ``source`` past its lifetime, as if it had been fetched long ago."""
    with sqlite3.connect(data_dir / "cache.sqlite3") as db:
        return db.execute("UPDATE responses SET expires_at = 0 WHERE source = ?", (source,)).rowcount


def test_check_lists_what_is_kept_and_what_is_stale_without_asking_anyone(client, make_app, upstream, tmp_path):
    get_ballot(client)
    expired = expire(tmp_path / "data", "sos")
    calls = len(upstream.calls)
    status, printed = make_app.cache_command("check")
    assert status == 0 and len(upstream.calls) == calls
    assert "Texas Secretary of State (Texas SOS) [sos]" in printed
    sos = printed.split("[sos]\n", 1)[1].split("\n", 1)[0]
    assert f"{expired} stale" in sos and "saved responses" in sos
    assert "Street map (OpenStreetMap) [osm_tiles]\n  Nothing saved.\n  Only fetched as it's used: pruned, never refreshed." in printed
    assert "A frozen list that came with Pallot" in printed and printed.endswith(" MB.") or printed.endswith(" KB.")
    assert make_app.cache_command("check", "sos")[1].startswith("Texas Secretary of State (Texas SOS) [sos]\n")


def test_an_unknown_source_is_refused(make_app, capsys):
    status, printed = make_app.cache_command("refresh", "nope")
    assert status == 2 and printed == "" and "Unknown source nope. The sources are: geocoding," in capsys.readouterr().err


def test_soft_refresh_asks_again_only_what_is_stale(client, make_app, upstream, tmp_path):
    get_ballot(client)
    status, printed = make_app.cache_command("refresh")
    assert status == 0 and "Texas Secretary of State (Texas SOS): nothing past its lifetime." in printed
    assert "TrackAIPAC: nothing past its lifetime." in printed and not make_app.refreshed  # a snapshot is never stale
    expired = expire(tmp_path / "data", "sos")
    asked = upstream.count("goelect")
    status, printed = make_app.cache_command("refresh", "sos")
    assert status == 0 and printed == f"Texas Secretary of State (Texas SOS): Refreshed {expired} saved responses."
    assert upstream.count("goelect") == asked + expired
    assert rows(client)["sos"]["cache"]["expired"] == 0
    assert get_ballot(client)["meta"]["external_calls"] == 0  # the running server reads the new copies


def test_hard_refresh_asks_everything_again_and_refreshes_the_snapshots(client, make_app, upstream):
    get_ballot(client)
    sos = rows(client)["sos"]["cache"]["entries"]
    asked = upstream.count("goelect")
    status, printed = make_app.cache_command("hard-refresh")
    assert status == 0
    assert f"Texas Secretary of State (Texas SOS): Refreshed {sos} saved responses." in printed
    assert upstream.count("goelect") == asked + sos
    assert "Address lookup & districts: Refreshed" in printed and "Re-downloaded the State Board of Education map." in printed
    assert "TrackAIPAC: updated" in printed and make_app.refreshed
    assert "Texas Ethics Commission (TEC): updated snapshot" in printed and make_app.tec_refreshed
    assert "Vote for Peace: updated" in printed
    assert "Street map" not in printed and "Address suggestions" not in printed  # never refreshed in bulk
    assert "Example PAC" not in printed and "Muslims United PAC endorsements: Refreshed 1 saved response." in printed


def test_a_failed_refresh_keeps_the_old_copy_and_says_so(client, make_app, upstream, tmp_path):
    get_ballot(client)
    upstream.down.add("data.capitol.texas.gov")
    status, printed = make_app.cache_command("hard-refresh", "geocoding")
    assert status == 1
    assert "Couldn't re-download the State Board of Education map (HTTP 500); kept the old one." in printed
    assert (tmp_path / "data" / "plane2106_kml.zip").exists()


def test_a_failed_snapshot_refresh_changes_nothing(client, make_app):
    def broken(*, data_dir):
        raise RuntimeError("site is down")

    status, printed = make_app.cache_command("hard-refresh", "trackaipac", refresh=broken)
    assert status == 1 and printed.startswith("TrackAIPAC: TrackAIPAC refresh failed; nothing changed. site is down")
    assert client.app.state.svc.trackaipac.document()["snapshot"] == load("trackaipac/current.json")["snapshot"]


def test_rebuild_deletes_everything_and_fetches_it_again(client, make_app, upstream, tmp_path):
    get_ballot(client)
    client.get("/api/tiles/12/940/1686.png")
    before = rows(client)
    current = tmp_path / "data" / "trackaipac" / "current.json"
    current.write_text(json.dumps({"snapshot": "refreshed", "candidates": []}))
    status, printed = make_app.cache_command("rebuild")
    assert status == 0 and printed.startswith("Deleted ")
    assert "Address lookup & districts, Election precincts (Texas Legislative Council)" in printed
    after = rows(client)
    assert after["sos"]["cache"]["entries"] == before["sos"]["cache"]["entries"]
    assert after["osm_tiles"]["cache"]["entries"] == 0  # only fetched as it's viewed
    assert json.loads(current.read_text())["snapshot"] == "refreshed"  # a snapshot isn't deleted
    assert (tmp_path / "data" / "plane2106_kml.zip").exists()
    assert client.app.state.svc.election_precincts.stored() is not None
    assert get_ballot(client)["meta"]["external_calls"] == 0


def test_rebuild_can_reset_the_snapshots_and_one_source_alone(client, make_app, tmp_path):
    get_ballot(client)
    current = tmp_path / "data" / "trackaipac" / "current.json"
    current.write_text(json.dumps({"snapshot": "edited", "candidates": []}))
    fec = rows(client)["fec"]["cache"]["entries"]
    status, printed = make_app.cache_command("rebuild", "trackaipac", "sos", reset_snapshots=True)
    assert status == 0 and printed.startswith("Deleted ")
    assert "TrackAIPAC: updated" in printed and "FEC" not in printed
    assert client.app.state.svc.trackaipac.document()["snapshot"] == load("trackaipac/current.json")["snapshot"]
    assert rows(client)["fec"]["cache"]["entries"] == fec


def test_rebuild_can_delete_the_saved_addresses_without_sending_them_again(client, make_app, upstream, tmp_path):
    get_ballot(client)
    asked = upstream.count("geocoding.geo.census.gov")
    status, printed = make_app.cache_command("rebuild", "geocoding", "suggestions", delete_only=True)
    assert status == 0 and printed == ("Deleted 1 saved response, and what Address lookup & districts kept in files.")
    assert upstream.count("geocoding.geo.census.gov") == asked
    assert rows(client)["geocoding"]["cache"]["entries"] == 0
    assert not (tmp_path / "data" / "plane2106_kml.zip").exists()
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        assert not db.execute("SELECT 1 FROM responses WHERE request LIKE '%1100%Congress%'").fetchall()


def test_the_rebuild_command_asks_first(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    assert maintain.main(["rebuild"]) == 1
    assert capsys.readouterr().out == "Nothing was deleted.\n"


def test_prune_deletes_only_what_is_no_use_and_keeps_tiles_under_their_cap(tmp_path):
    long_ago, now = time.time() - 90 * DAY, time.time()
    cache = HttpCache(tmp_path / "cache.sqlite3", httpx.AsyncClient())
    stored = (("osm_tiles", "old", long_ago), ("osm_tiles", "a", now - 3), ("osm_tiles", "b", now - 2),
              ("osm_tiles", "c", now - 1), ("suggestions", "old", long_ago), ("ballotpedia", "old", long_ago),
              ("fec", "old", long_ago))
    for source, q, at in stored:
        cache._store(RequestSpec("GET", "https://example.test/", params={"q": q, "s": source}), source, "x" * 100, at,
                     7 * DAY, None, ())
    config = Config(data_dir=tmp_path, tiles_max_bytes=210)  # two tiles of 102 bytes
    assert prune(cache, config) == 3  # the old tile, the old suggestion, and the oldest tile past the cap
    assert cache.stats("osm_tiles").entries == 2 and cache.stats("osm_tiles").oldest == pytest.approx(now - 2)
    assert cache.stats("suggestions").entries == 0
    assert cache.stats("ballotpedia").entries == 1 and cache.stats("fec").entries == 1  # third-party copies stay
    cache.close()


def test_prune_command_and_the_running_server_keep_pruning(client, make_app, upstream):
    client.get("/api/tiles/12/940/1686.png")
    status, printed = make_app.cache_command("prune")
    assert status == 0 and printed.startswith("Pruned 0 saved responses; the cache went from ")
    svc = client.app.state.svc
    assert svc.cache.stats("osm_tiles").entries == 1  # fresh, and under its cap
    svc.config = dataclasses.replace(svc.config, tiles_max_bytes=1)

    async def one_round() -> None:
        task = asyncio.create_task(keep_pruning(svc, every=0.01))
        for _ in range(100):
            await asyncio.sleep(0.01)
            if not svc.cache.stats("osm_tiles").entries:
                break
        task.cancel()

    client.portal.call(one_round)
    assert svc.cache.stats("osm_tiles").entries == 0
