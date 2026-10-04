"""Startup reads the kept maps and name indexes in the background, without asking anyone."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pallot import settings

from .conftest import get_ballot


def warmed(client: TestClient) -> FastAPI:
    """The app, once its warm-up has finished."""
    app = client.app
    task: asyncio.Task[None] = app.state.warm_up

    async def done() -> None:
        await asyncio.shield(task)

    client.portal.call(done)
    return app


def test_warm_up_reads_what_is_kept_without_external_calls(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client)
    calls = len(upstream.calls)
    with TestClient(make_app()) as client:
        svc = warmed(client).state.svc
        assert len(upstream.calls) == calls
        assert svc.sboe._districts is not None and svc.election_precincts._index is not None
        assert {"filers", "outside"} <= svc.tec._indexes.keys() and "TX" in svc.trackaipac._indexes
        assert "TX" in svc.voteforpeace._indexes
        assert get_ballot(client)["meta"]["external_calls"] == 0
    assert len(upstream.calls) == calls


def test_warm_up_never_downloads_a_missing_map(make_app, upstream, tmp_path):
    with TestClient(make_app()) as client:
        svc = warmed(client).state.svc
        assert upstream.calls == []
        assert svc.sboe._districts is None and not (tmp_path / "data" / "plane2106_kml.zip").exists()
        assert svc.election_precincts._index is None and svc.election_precincts.stored() is None
        assert "TX" in svc.trackaipac._indexes  # the bundled snapshots are always kept


def test_warm_up_skips_sources_off_by_default(make_app, upstream, monkeypatch):
    with TestClient(make_app()) as client:
        get_ballot(client)
    for source in ("election_precincts", "tec", "trackaipac", "voteforpeace"):
        monkeypatch.setitem(settings.DEFAULT_SOURCES, source, False)
    with TestClient(make_app()) as client:
        svc = warmed(client).state.svc
        assert svc.election_precincts._index is None
        assert svc.tec._indexes == {} and svc.trackaipac._indexes == {} and svc.voteforpeace._indexes == {}
        assert svc.sboe._districts is not None  # the ballot can't do without it, so it has no switch


def test_a_lookup_during_the_warm_up_reads_each_map_once(make_app, upstream, monkeypatch):
    from pallot.sources import election_precincts, sboe

    with TestClient(make_app()) as client:
        get_ballot(client)
    reads = {"index": 0, "sboe": 0}
    read_index, parse_zip = election_precincts.read_index, sboe.parse_zip

    def counted_index(*args):
        reads["index"] += 1
        return read_index(*args)

    def counted_zip(data):
        reads["sboe"] += 1
        return parse_zip(data)

    monkeypatch.setattr(election_precincts, "read_index", counted_index)
    monkeypatch.setattr(sboe, "parse_zip", counted_zip)
    with TestClient(make_app()) as client:
        assert get_ballot(client)["meta"]["external_calls"] == 0
        warmed(client)
    assert reads == {"index": 1, "sboe": 1}
