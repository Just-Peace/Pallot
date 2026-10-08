"""TIGERweb's bundle (bundles/tigerweb.py): every Texas district's outline, as a lookup asks for it."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pallot.config import DAY

from .bundling import build, entry, lifetimes, notice


def test_a_lookup_with_the_outlines_bundled_asks_tigerweb_nothing(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "tigerweb")
    assert upstream.count("tigerweb") == 1 + 38 + 31 + 150  # the index, then every district once
    assert outcome.status == "updated" and outcome.counts == {"cd": 1, "sd": 1, "hd": 2, "missing": 215}  # the fixtures' (48014 twice)
    assert outcome.answers == 5  # districts with no shape are left out, and asked live
    assert entry("tigerweb").cadence == "weekly" and lifetimes(tmp_path, "tigerweb") == {37 * DAY}
    asked = upstream.count("tigerweb")
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        got = client.get("/api/district-outlines", params={"cd": 10, "sd": 14, "hd": 49}).json()
        said = notice(client, "tigerweb")
    assert [(o["kind"], o["number"]) for o in got["outlines"]] == [("cd", 10), ("sd", 14), ("hd", 49)]
    assert got["meta"]["external_calls"] == 0 and upstream.count("tigerweb") == asked
    assert said.startswith("Came with 5 answers, checked ")


def test_a_refused_outline_writes_no_outlines(tmp_path, upstream):
    upstream.tigerweb_status = 429
    outcome = build(tmp_path, "tigerweb")
    assert outcome.status == "failed" and "TIGERweb" in outcome.detail
    assert not (tmp_path / "bundles").exists()
