"""fec_cache: building the bundled snapshot of the FEC's answers, and Pallot loading it at startup."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from fec_cache import store
from fec_cache.refresh import RefreshError, refresh
from pallot.config import Config

from .conftest import FEC_KEY, TODAY, get_ballot

NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)  # the cache's clock is the real one


def build(tmp_path, key: str = FEC_KEY, now: dt.datetime = NOW, **kwargs):
    config = Config(data_dir=tmp_path / "data", fec_api_key=key)
    return refresh(data_dir=tmp_path / "snapshot", config=config, today=lambda: TODAY, now=now, min_interval={}, **kwargs)


def test_the_snapshot_holds_what_a_lookup_asks_the_fec(tmp_path, upstream):
    result = build(tmp_path)
    assert result.status == "updated" and result.races == 14 and result.answers > result.races  # the fixture's seats
    current = json.loads((tmp_path / "snapshot" / "current.json").read_text())
    meta = json.loads((tmp_path / "snapshot" / "meta.json").read_text())
    assert current["snapshot"] == NOW.date().isoformat() and len(current["answers"]) == result.answers == meta["answers"]
    urls = [answer["request"]["url"] for answer in current["answers"]]
    assert urls.count("https://api.open.fec.gov/v1/elections/") == 14  # each seat's race list
    assert any("/candidate/" in url for url in urls)  # and the breakdowns of the candidates on the ballot
    assert meta["last_checked"] == meta["last_refresh"] == NOW.isoformat()
    assert FEC_KEY not in (tmp_path / "snapshot" / "current.json").read_text()


def test_an_unchanged_snapshot_only_notes_when_it_was_checked(tmp_path, upstream):
    build(tmp_path)
    written = (tmp_path / "snapshot" / "current.json").read_text()
    later = NOW + dt.timedelta(days=1)
    assert build(tmp_path, now=later).status == "no_changes"
    meta = json.loads((tmp_path / "snapshot" / "meta.json").read_text())
    assert meta["last_checked"] == later.isoformat() and meta["last_refresh"] == NOW.isoformat()
    assert (tmp_path / "snapshot" / "current.json").read_text() == written


def test_nothing_is_written_when_a_call_fails_or_without_a_key(tmp_path, upstream):
    upstream.fec_status = 500
    with pytest.raises(RefreshError, match="FEC calls failed"):
        build(tmp_path)
    with pytest.raises(RefreshError, match="PALLOT_FEC_API_KEY"):
        build(tmp_path, key="DEMO_KEY")
    assert not (tmp_path / "snapshot").exists()


def test_a_lookup_asks_the_fec_nothing_the_snapshot_has(tmp_path, upstream, make_app):
    build(tmp_path)
    asked = upstream.count("open.fec.gov")
    with TestClient(make_app(fec_bundled=tmp_path / "snapshot")) as client:
        ballot = get_ballot(client)
        notice = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "fec")["notice"]
    senate = next(r for r in ballot["races"] if r["name"] == "U.S. Senator")
    assert senate["cards"] and upstream.count("open.fec.gov") == asked
    assert notice.startswith(f"Came with {len(store.load(tmp_path / 'snapshot').answers):,} of the FEC's answers")


def test_a_stale_snapshot_is_asked_again_and_a_newer_copy_is_kept(tmp_path, upstream, make_app):
    build(tmp_path, now=NOW - dt.timedelta(days=8))  # past Ttls.fec
    asked = upstream.count("open.fec.gov")
    with TestClient(make_app(fec_bundled=tmp_path / "snapshot")) as client:
        get_ballot(client)
    assert upstream.count("open.fec.gov") > asked
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        newest = db.execute("SELECT MIN(fetched_at) FROM responses WHERE source = 'fec' AND request LIKE '%elections%'"
                            " AND request LIKE '%senate%'").fetchone()[0]
    with TestClient(make_app(fec_bundled=tmp_path / "snapshot")):  # a restart loads the snapshot again
        pass
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        after = db.execute("SELECT MIN(fetched_at) FROM responses WHERE source = 'fec' AND request LIKE '%elections%'"
                           " AND request LIKE '%senate%'").fetchone()[0]
    assert after == newest  # the live answer, newer than the snapshot's, stays
