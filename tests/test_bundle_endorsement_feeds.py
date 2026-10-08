"""The live endorsement lists' bundles (bundles/endorsement_feeds.py), one per feed."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from bundles import store
from pallot.config import DAY

from .bundling import build_all, entry, lifetimes, notice
from .conftest import FEED_TOKEN, get_ballot, last_use, switch

FEEDS = ("mupac", "cair", "emgage")
FEED_HOSTS = {"mupac": "muslimsunitedpac.com", "cair": "cairactionguide.org", "emgage": "candidates.emgagepac.org"}


def feed_cards(ballot, source: str) -> dict[str, dict]:
    return {p["name"]: c for r in ballot["races"] for p in r["candidates"] for c in p["cards"] if c["source"] == source}


def test_a_lookup_with_the_feeds_bundled_asks_their_sites_nothing(tmp_path, upstream, make_app):
    outcomes = build_all(tmp_path, FEEDS)
    assert all(o.status == "updated" and o.answers == 1 and o.counts["texas"] for o in outcomes.values())
    asked = {source: upstream.count(host) for source, host in FEED_HOSTS.items()}
    assert asked == {"mupac": 1, "cair": 1, "emgage": 2} and upstream.feed_tokens == [FEED_TOKEN]  # Emgage's page first
    for source in FEEDS:
        assert entry(source).cadence == "daily" and lifetimes(tmp_path, source) == {2 * DAY}
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "ut")
        assert all(last_use(client, source)["calls"] == 0 for source in FEEDS)
        said = notice(client, "emgage")
    assert all("Greg Casar" in feed_cards(ballot, source) for source in FEEDS)
    assert {source: upstream.count(host) for source, host in FEED_HOSTS.items()} == asked
    assert "a lookup fetches it again once it's 2 days old. Came with 1 answer, checked " in said


def test_emgages_bundle_keeps_neither_its_page_nor_its_token(tmp_path, upstream):
    build_all(tmp_path, FEEDS)
    text = (tmp_path / "bundles" / "emgage.json").read_text()
    [answer] = json.loads(text)["answers"]
    assert answer["request"] == {"method": "GET", "url": "https://candidates.emgagepac.org/api/v2/donation-page/"
                                                         "SupportOurCandidates", "params": None}
    assert FEED_TOKEN not in text and "RequestVerificationToken" not in text and "<html" not in text.lower()
    shipped = (store.PACKAGE_DATA_DIR / "emgage.json").read_text(encoding="utf-8")
    assert "RequestVerificationToken" not in shipped and "<html" not in shipped.lower()


def test_a_bundled_feed_switched_off_stays_off_the_ballot(tmp_path, upstream, make_app):
    build_all(tmp_path, FEEDS)
    asked = upstream.count(FEED_HOSTS["mupac"])
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        switch(client, "mupac", False)
        ballot = get_ballot(client, "ut")
        assert last_use(client, "mupac")["status"] == "off"
    assert not feed_cards(ballot, "mupac") and "Greg Casar" in feed_cards(ballot, "cair")
    assert upstream.count(FEED_HOSTS["mupac"]) == asked


def test_a_failing_feed_is_left_out_and_the_others_bundled(tmp_path, upstream):
    upstream.feed_page_status = 403  # Emgage's page, for its token
    outcomes = build_all(tmp_path, FEEDS)
    assert outcomes["emgage"].status == "failed" and "Emgage PAC" in outcomes["emgage"].detail
    assert outcomes["mupac"].status == outcomes["cair"].status == "updated"
    assert upstream.count(FEED_HOSTS["emgage"]) == 1 and not (tmp_path / "bundles" / "emgage.json").exists()
    assert "emgage" not in store.read_meta(tmp_path / "bundles")
