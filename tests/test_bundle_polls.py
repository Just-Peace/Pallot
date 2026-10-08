"""FiftyPlusOne's bundle (bundles/polls.py): the poll lists a lookup asks for."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pallot.config import DAY

from .bundling import build, entry, lifetimes
from .conftest import get_ballot, last_use


def test_a_lookup_with_the_polls_bundled_asks_fiftyplusone_nothing(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "polls")
    assert outcome.status == "updated" and outcome.answers == 3 and outcome.counts["senate"] and outcome.counts["governor"]
    assert upstream.count("fiftyplusone.news") == 3 and all("Mozilla" in agent for agent in upstream.polls_agents)
    assert entry("polls").cadence == "daily" and lifetimes(tmp_path, "polls") == {2 * DAY}
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client)
        assert last_use(client, "polls")["calls"] == 0
    senate = next(r for r in ballot["races"] if r["name"] == "U.S. Senator")
    assert any(c["source"] == "polls" for c in senate["cards"])
    assert upstream.count("fiftyplusone.news") == 3


def test_a_refused_poll_list_writes_no_polls(tmp_path, upstream):
    upstream.polls_status = 403
    outcome = build(tmp_path, "polls")
    assert outcome.status == "failed" and "FiftyPlusOne" in outcome.detail
    assert upstream.count("fiftyplusone.news") == 1 and not (tmp_path / "bundles").exists()
