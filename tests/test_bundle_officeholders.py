"""The seat holders' bundle (bundles/officeholders.py): congress-legislators' and Open States' lists."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pallot.config import DAY

from .bundling import answers, build, entry, lifetimes, notice
from .conftest import get_ballot


def holder_calls(upstream) -> int:
    return upstream.count("unitedstates.github.io") + upstream.count("data.openstates.org")


def test_a_lookup_with_the_seat_holders_bundled_asks_neither_list(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "officeholders")
    assert outcome.status == "updated" and outcome.answers == 2 and outcome.counts["congress"] and outcome.counts["legislature"]
    assert [a["request"].get("as_text", False) for a in answers(tmp_path, "officeholders")] == [True, False]  # Open States' CSV, congress's JSON
    assert entry("officeholders").cadence == "weekly" and lifetimes(tmp_path, "officeholders") == {14 * DAY}
    asked = holder_calls(upstream)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client)
        said = notice(client, "officeholders")
    assert next(r for r in ballot["races"] if r["name"] == "U.S. Senator")["holder"]["name"] == "John Cornyn"
    assert next(r for r in ballot["races"] if r["name"] == "State Representative District 49")["holder"]
    assert holder_calls(upstream) == asked
    assert said.startswith("Came with 2 answers, checked ")


def test_a_refused_list_writes_no_seat_holders(tmp_path, upstream):
    upstream.officeholders_status = 403
    outcome = build(tmp_path, "officeholders")
    assert outcome.status == "failed" and "seat holders" in outcome.detail
    assert not (tmp_path / "bundles").exists()
