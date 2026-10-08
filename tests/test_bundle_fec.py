"""The FEC's bundle (bundles/fec.py): what it holds, and lookups served from it."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3

from fastapi.testclient import TestClient

from bundles import store
from pallot.config import Config

from .bundling import NOW, answers, build, notice
from .conftest import FEC_KEY, get_ballot


def build_fec(tmp_path, key: str = FEC_KEY, now: dt.datetime = NOW):
    return build(tmp_path, "fec", config=Config(data_dir=tmp_path / "data", fec_api_key=key), now=now)


def test_the_bundle_holds_what_a_lookup_asks_the_fec(tmp_path, upstream):
    outcome = build_fec(tmp_path)
    assert outcome.status == "updated" and outcome.counts["races"] == 14 and outcome.answers > 14  # the fixture's seats
    text = (tmp_path / "bundles" / "fec.json").read_text()
    found = json.loads(text)["answers"]
    meta = store.read_meta(tmp_path / "bundles")["fec"]
    assert len(found) == outcome.answers == meta["answers"] == len(text.splitlines()) - 2  # one answer per line
    urls = [answer["request"]["url"] for answer in found]
    assert urls.count("https://api.open.fec.gov/v1/elections/") == 14  # each seat's race list
    assert any("/candidate/" in url for url in urls)  # and the breakdowns of the candidates on the ballot
    assert meta["last_checked"] == meta["last_refresh"] == NOW.isoformat()
    assert FEC_KEY not in text


def test_an_unchanged_bundle_only_notes_when_it_was_checked(tmp_path, upstream):
    build_fec(tmp_path)
    written = (tmp_path / "bundles" / "fec.json").read_text()
    later = NOW + dt.timedelta(days=1)
    assert build_fec(tmp_path, now=later).status == "no_changes"
    meta = store.read_meta(tmp_path / "bundles")["fec"]
    assert meta["last_checked"] == later.isoformat() and meta["last_refresh"] == NOW.isoformat()
    assert (tmp_path / "bundles" / "fec.json").read_text() == written


def test_nothing_is_written_when_a_call_fails_or_without_a_key(tmp_path, upstream):
    upstream.fec_status = 500
    failed = build_fec(tmp_path)
    assert failed.status == "failed" and "FEC calls failed" in failed.detail
    assert "PALLOT_FEC_API_KEY" in build_fec(tmp_path, key="DEMO_KEY").detail
    assert not (tmp_path / "bundles").exists()


def test_a_lookup_asks_the_fec_nothing_the_bundle_has(tmp_path, upstream, make_app):
    build_fec(tmp_path)
    asked = upstream.count("open.fec.gov")
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client)
        said = notice(client, "fec")
    senate = next(r for r in ballot["races"] if r["name"] == "U.S. Senator")
    assert senate["cards"] and upstream.count("open.fec.gov") == asked
    assert said.startswith(f"Came with {len(answers(tmp_path, 'fec')):,} answers, checked ")


def test_a_stale_bundle_is_asked_again_and_a_newer_copy_is_kept(tmp_path, upstream, make_app):
    build_fec(tmp_path, now=NOW - dt.timedelta(days=8))  # past Ttls.fec_bundle
    asked = upstream.count("open.fec.gov")
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        get_ballot(client)
    assert upstream.count("open.fec.gov") > asked
    query = ("SELECT MIN(fetched_at) FROM responses WHERE source = 'fec' AND request LIKE '%elections%'"
             " AND request LIKE '%senate%'")
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        newest = db.execute(query).fetchone()[0]
    with TestClient(make_app(bundles=tmp_path / "bundles")):  # a restart loads the bundle again
        pass
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        assert db.execute(query).fetchone()[0] == newest  # the live answer, newer than the bundle's, stays
