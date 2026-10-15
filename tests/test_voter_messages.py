"""What a voter reads names the source and what still works, never the host's setup or a source's raw
error: with the sources failing, no answer under /api/ names a variable, a key, .env or an HTTP status.
The cause goes to the server log."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from pallot.limits import Rate, RateLimits

from .conftest import ADDRESSES

LEAKS = ("PALLOT_", ".env", "DEMO_KEY", "restart", "HTTP 5", "Error)")
CENSUS, SOS = "geocoding.geo.census.gov", "goelect.txelections.civixapps.com"


class AllBut(set):
    """Upstream.down for every host but ``up``."""

    def __init__(self, *up: str):
        super().__init__()
        self.up = set(up)

    def __contains__(self, host: object) -> bool:
        return host not in self.up


def leaks(answer: Any) -> list[str]:
    """Every string in the answer that shows the host's setup or a raw error."""
    if isinstance(answer, dict):
        return [found for value in answer.values() for found in leaks(value)]
    if isinstance(answer, list):
        return [found for value in answer for found in leaks(value)]
    return [answer] if isinstance(answer, str) and any(word in answer for word in LEAKS) else []


def answers(client: TestClient) -> dict[str, Any]:
    """What every /api/ route answers, by route."""
    def body(response) -> Any:
        return response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text

    return {
        "ballot": body(client.post("/api/ballot", json={"address": ADDRESSES["capitol"]})),
        "voter card": body(client.post("/api/ballot", json={"county": "Travis", "precinct": "101"})),
        "sources": body(client.get("/api/sources")),
        "config": body(client.get("/api/config")),
        "elections": body(client.get("/api/elections")),
        "key dates": body(client.get("/api/key-dates.ics", params={"date": "2026-11-03"})),
        "outlines": body(client.get("/api/district-outlines", params={"cd": 37, "sboe": 5})),
        "tile": body(client.get("/api/tiles/12/940/1686.png")),
        "suggest": body(client.get("/api/suggest", params={"q": "1100 Congress"})),
        "endorsements": body(client.get("/api/endorsements")),
        "no address": body(client.post("/api/ballot", json={})),
        "short address": body(client.post("/api/ballot", json={"address": "1"})),
        "bad districts": body(client.post("/api/ballot", json={"address": ADDRESSES["capitol"], "districts": {"cd": 99}})),
        "wrong host": body(client.get("/api/sources", headers={"Host": "rebind.example"})),
    }


def test_failing_sources_are_named_without_their_cause(make_app, upstream, caplog):
    upstream.down = AllBut(CENSUS, SOS)
    with TestClient(make_app(fec_key="DEMO_KEY")) as client:
        found = answers(client)
    ballot = found["ballot"]
    assert "Ballotpedia isn't answering right now, so city and school races aren't shown." in ballot["warnings"]
    assert "Wikidata isn't answering right now, so its profiles aren't shown." in ballot["warnings"]
    assert not {route: leaks(answer) for route, answer in found.items() if leaks(answer)}
    assert "HTTP 500" in caplog.text and "PALLOT_FEC_API_KEY" in caplog.text and "PALLOT_ALLOWED_HOSTS" in caplog.text


def test_a_lookup_nothing_answers_says_so_plainly(make_app, upstream, caplog):
    upstream.down = AllBut()
    with TestClient(make_app(fec_extra_keys=("second-key",))) as client:
        found = answers(client)
    assert found["ballot"] == {"detail": "The address lookup isn't answering right now. Try again in a minute."}
    assert found["elections"] == {"detail": "Texas SOS isn't answering right now. Try again in a minute."}
    assert found["no address"] == {"detail": "Enter an address, or your county and precinct number."}
    assert found["short address"] == {"detail": "Enter your street address, with the city or ZIP code."}
    assert found["bad districts"] == {"detail": "Check the district numbers you entered."}
    assert found["wrong host"] == {"detail": "Pallot isn't available at this address."}
    assert not {route: leaks(answer) for route, answer in found.items() if leaks(answer)}
    assert "HTTP 500" in caplog.text


def test_refusals_say_so_plainly(make_app):
    with TestClient(make_app(max_lookups=1, rate_limits=RateLimits(ballot=Rate(1, 3600)))) as client:
        lookups = client.app.state.lookups
        client.portal.call(lookups.acquire)  # another voter's lookup
        busy = client.post("/api/ballot", json={"address": ADDRESSES["capitol"]})
        client.portal.call(lookups.release)
        found = {
            "busy": busy,
            "too many": client.post("/api/ballot", json={"address": ADDRESSES["capitol"]}),
            "another site": client.post("/api/ballot", json={}, headers={"Sec-Fetch-Site": "cross-site"}),
            "not a page": client.get("/api/sources", headers={"Sec-Fetch-Site": "none"}),
        }
    assert {route: answer.status_code for route, answer in found.items()} == {
        "busy": 503, "too many": 429, "another site": 403, "not a page": 403}
    details = {route: answer.json() for route, answer in found.items()}
    assert not {route: leaks(answer) for route, answer in details.items() if leaks(answer)}
