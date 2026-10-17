"""Address suggestions (Google's Places Autocomplete): what's sent, which predictions become
suggestions, and the /api/suggest route."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pallot.sources.suggestions import normalize, parse, request, wanted

from .conftest import GOOGLE_KEY, SUGGEST, switch


@pytest.fixture
def keyed(make_app):
    with TestClient(make_app(google_key=GOOGLE_KEY)) as test_client:
        yield test_client


def labels(*texts: str) -> list[str]:
    return [s.label for s in parse({"suggestions": [{"placePrediction": {"text": {"text": t}}} for t in texts]})]


def test_addresses_anywhere_in_the_us_without_the_country():
    assert labels("1100 Congress Avenue, Austin, TX, USA", "501 N 3rd St, Harrisburg, PA, USA") == [
        "1100 Congress Avenue, Austin, TX", "501 N 3rd St, Harrisburg, PA"]
    assert labels(*[f"{n} Main St, Austin, TX, USA" for n in range(1, 9)])[4:] == ["5 Main St, Austin, TX"]
    assert parse({}) == [] and parse({"suggestions": [{"queryPrediction": {}}]}) == []


def test_what_is_worth_asking_about_and_what_is_sent():
    assert normalize("  1100   Congress Ave, ") == "1100 congress ave"
    assert wanted("1100 congress") and wanted("12b main st")
    assert not wanted("1100") and not wanted("1100 c") and not wanted("congress ave")
    sent = request("1100 congr")
    assert sent.method == "POST" and sent.json["input"] == "1100 congr" and sent.json["includedRegionCodes"] == ["us"]
    assert not sent.headers  # the key goes in HttpCache's source headers, never in the request or its key


def test_suggest_route(keyed, upstream):
    assert keyed.get("/api/suggest", params={"q": ""}).json() == {"enabled": True, "suggestions": []}
    assert keyed.get("/api/suggest", params={"q": "1100 c"}).json()["suggestions"] == []
    assert upstream.count("places.googleapis.com") == 0

    first = keyed.get("/api/suggest", params={"q": "1100 Congress  Ave"}).json()
    assert [s["label"] for s in first["suggestions"]][:3] == [
        "1100 Congress Avenue, Austin, TX", "1100 Congress Ave, Houston, TX", "1100 South Congress Avenue, Austin, TX",
    ]
    assert "1100 Congress Avenue, Sacramento, CA" in [s["label"] for s in first["suggestions"]]  # not only Texas
    again = keyed.get("/api/suggest", params={"q": SUGGEST["congress"]}).json()
    assert again == first and upstream.count("places.googleapis.com") == 1  # the same text, cached
    assert upstream.google_keys == [GOOGLE_KEY]

    row = next(s for s in keyed.get("/api/sources").json()["sources"] if s["id"] == "suggestions")
    assert row["enabled"] and row["updated"] and keyed.app.state.svc.cache.stats("suggestions").entries == 1
    assert row["label"] == "Address suggestions (Google)"


def test_without_a_google_key_nothing_is_suggested_or_listed(client, upstream):
    assert client.get("/api/suggest", params={"q": SUGGEST["congress"]}).json() == {"enabled": False, "suggestions": []}
    assert upstream.count("places.googleapis.com") == 0
    assert "suggestions" not in {s["id"] for s in client.get("/api/sources").json()["sources"]}


def test_suggestions_off_ask_nobody(make_app, upstream):
    with TestClient(make_app(google_key=GOOGLE_KEY)) as keyed:
        switch(keyed, "suggestions", False)
        answer = keyed.get("/api/suggest", params={"q": SUGGEST["congress"]}).json()
    assert answer == {"enabled": False, "suggestions": []} and upstream.count("places.googleapis.com") == 0


def test_a_refusal_pauses_suggestions_quietly(keyed, upstream):
    upstream.suggestions_status = 429
    assert keyed.get("/api/suggest", params={"q": SUGGEST["congress"]}).json() == {"enabled": True, "suggestions": []}
    assert keyed.get("/api/suggest", params={"q": SUGGEST["duval"]}).json()["suggestions"] == []
    assert upstream.count("places.googleapis.com") == 1  # paused after the first refusal
    row = next(s for s in keyed.get("/api/sources").json()["sources"] if s["id"] == "suggestions")
    assert row["notice_tone"] == "warn" and "Paused until" in row["notice"]
    google = next(s for s in keyed.get("/api/sources").json()["sources"] if s["id"] == "google")
    assert google["notice"] is None  # the geocoding fallback isn't paused


def test_suggestions_stop_at_their_daily_cap(make_app, upstream):
    with TestClient(make_app(google_key=GOOGLE_KEY, suggest_daily_max=1)) as keyed:
        assert keyed.get("/api/suggest", params={"q": SUGGEST["congress"]}).json()["suggestions"]
        assert keyed.get("/api/suggest", params={"q": SUGGEST["duval"]}).json()["suggestions"] == []
    assert upstream.count("places.googleapis.com") == 1
