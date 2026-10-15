"""Wikidata's bundle (bundles/wikidata.py): the list of Texas officeholders."""

from __future__ import annotations

from fastapi.testclient import TestClient

from bundles import wikidata as wikidata_bundle
from pallot.config import DAY

from .bundling import answers, build, came_with, entry, lifetimes
from .conftest import find_race, get_ballot


def test_a_lookup_with_the_list_bundled_asks_only_for_the_details(tmp_path, upstream, make_app, monkeypatch):
    monkeypatch.setattr(wikidata_bundle, "MIN_PEOPLE", 10)  # the fixture keeps a few dozen of the 600-odd
    outcome = build(tmp_path, "wikidata")
    assert outcome.status == "updated" and outcome.answers == 1 and outcome.counts["people"] > 10
    assert "VALUES" not in answers(tmp_path, "wikidata")[0]["request"]["params"]["query"]  # no ballot's details
    assert entry("wikidata").cadence == "weekly" and lifetimes(tmp_path, "wikidata") == {14 * DAY}
    asked = upstream.count("query.wikidata.org")
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client)
        said = came_with(client, "wikidata")
    abbott = next(c for c in find_race(ballot, "Governor")["candidates"] if c["name"] == "Greg Abbott")
    assert any(card["source"] == "wikidata" for card in abbott["cards"])
    assert upstream.count("query.wikidata.org") == asked + 1  # the details only
    assert said.startswith("Came with 1 answers, checked ") or said.startswith("Came with 1 answer, checked ")


def test_too_short_a_list_writes_nothing(tmp_path, upstream):
    outcome = build(tmp_path, "wikidata")
    assert outcome.status == "failed" and "only" in outcome.detail
    assert not (tmp_path / "bundles").exists()


def test_a_refused_list_writes_nothing(tmp_path, upstream):
    upstream.wikidata_status = 403
    outcome = build(tmp_path, "wikidata")
    assert outcome.status == "failed" and "Texas officeholders" in outcome.detail
