"""Address suggestions (Ballotpedia's address search): what's sent, which results become
suggestions, and the /api/suggest route."""

from __future__ import annotations

from fastapi.testclient import TestClient

from votebot.sources.suggestions import normalize, parse, query, wanted

from .conftest import SUGGEST


def labels(*texts: str) -> list[str]:
    return [s.label for s in parse([{"Text": text, "PlaceId": "x"} for text in texts])]


def test_only_texas_addresses_without_the_country():
    assert labels(
        "1100 Congress Ave, Austin, TX, 78701, USA",
        "1100 Congress Ave, Cincinnati, OH, 45246, USA",
        "1001 TX-249, Houston, TX, 77038, USA",
        "12 Ranch Rd, Marfa, TX, USA",
    ) == ["1100 Congress Ave, Austin, TX 78701", "1001 TX-249, Houston, TX 77038", "12 Ranch Rd, Marfa, TX"]
    assert labels(*[f"{n} Main St, Austin, TX, 78701, USA" for n in range(1, 9)])[4:] == ["5 Main St, Austin, TX 78701"]
    assert parse([{"PlaceId": "x"}]) == []


def test_what_is_worth_asking_about_and_what_is_sent():
    assert normalize("  1100   Congress Ave, ") == "1100 congress ave"
    assert wanted("1100 congress") and wanted("12b main st")
    assert not wanted("1100") and not wanted("1100 c") and not wanted("congress ave")
    assert query("1100 congr") == "tx 1100 congr"
    assert query("1100 congress ave, austin, tx 78701") == "1100 congress ave, austin, tx 78701"
    assert query("1100 congress ave austin texas") == "1100 congress ave austin texas"


def test_suggest_route(client, upstream):
    assert client.get("/api/suggest", params={"q": ""}).json() == {"enabled": True, "suggestions": []}
    assert client.get("/api/suggest", params={"q": "1100 c"}).json()["suggestions"] == []
    assert upstream.count("address_autocomplete") == 0

    first = client.get("/api/suggest", params={"q": "1100 Congress  Ave"}).json()
    assert [s["label"] for s in first["suggestions"]] == [
        "1100 Congress Ave, Austin, TX 78701", "1100 Congress Ave, Houston, TX 77002", "1100 Congress Ave S, Austin, TX 78704",
    ]
    again = client.get("/api/suggest", params={"q": SUGGEST["congress"]}).json()
    assert again == first and upstream.count("address_autocomplete") == 1  # the same text, cached

    row = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "suggestions")
    assert row["enabled"] and row["cache"]["entries"] == 1 and row["refresh_confirm"]
    assert upstream.count("myvote") == 0  # the ballot's endpoint wasn't asked


def test_suggestions_off_ask_nobody(make_app, upstream):
    with TestClient(make_app()) as client:
        client.put("/api/sources/suggestions", json={"enabled": False})
        answer = client.get("/api/suggest", params={"q": SUGGEST["congress"]}).json()
    assert answer == {"enabled": False, "suggestions": []} and upstream.count("address_autocomplete") == 0


def test_a_refusal_pauses_suggestions_quietly(client, upstream):
    upstream.suggestions_status = 429
    assert client.get("/api/suggest", params={"q": SUGGEST["congress"]}).json() == {"enabled": True, "suggestions": []}
    assert client.get("/api/suggest", params={"q": SUGGEST["duval"]}).json()["suggestions"] == []
    assert upstream.count("address_autocomplete") == 1  # paused after the first refusal
    row = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "suggestions")
    assert row["notice_tone"] == "warn" and "Paused until" in row["notice"]
    ballotpedia = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "ballotpedia")
    assert ballotpedia["notice"] is None  # the ballot's own endpoint isn't paused
