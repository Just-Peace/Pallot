"""Address suggestions (Photon): which results become suggestions, and the /api/suggest route."""

from __future__ import annotations

from fastapi.testclient import TestClient

from votebot.sources.photon import normalize, suggestions, wanted

from .conftest import SUGGEST, load


def feature(kind: str, street: str | None = None, name: str | None = None, number: str | None = None,
            city: str | None = "Austin", postcode: str | None = "78701", state: str = "Texas", **more: str) -> dict:
    props = {"type": kind, "street": street, "name": name, "housenumber": number, "city": city, "postcode": postcode,
             "state": state, "countrycode": "US", **more}
    return {"properties": {k: v for k, v in props.items() if v is not None}}


def labels(features: list[dict], text: str) -> list[tuple[str, bool]]:
    return [(s.label, s.street_only) for s in suggestions(features, normalize(text))]


def test_only_streets_that_match_what_was_typed():
    # Photon's answer is mostly shops and museums on Congress and South Congress, plus a bus
    # stop on Oltorf and a bridge on a hike-and-bike trail, none at number 1100.
    assert labels(load("photon_congress.json")["features"], SUGGEST["congress"]) == [
        ("1100 Congress Avenue, Austin, TX", True),
        ("1100 South Congress Avenue, Austin, TX", True),
    ]
    # Houses numbered 4512 on St Francis Avenue, 21st Street and South 1st Street don't match "duval".
    assert labels(load("photon_duval.json")["features"], SUGGEST["duval"]) == [("4512 Duval Street, Austin, TX", True)]


def test_a_house_with_the_typed_number_is_a_full_address_and_comes_first():
    found = [
        feature("street", name="Congress Avenue", osm_value="primary"),
        feature("house", street="Congress Avenue", number="700"),
    ]
    assert labels(found, "700 congress ave") == [("700 Congress Avenue, Austin, TX 78701", False)]


def test_other_states_paths_and_places_without_a_town_are_left_out():
    found = [
        feature("street", name="Congress Avenue", state="Oklahoma"),
        feature("street", name="Congress Trail", osm_value="footway"),
        feature("street", name="Congress Road", city=None, postcode=None),
        feature("city", name="Congress"),
        feature("street", name="Congress Lane", city=None, postcode="78620"),
    ]
    assert labels(found, "12 congress") == [("12 Congress Lane, TX 78620", True)]


def test_a_half_typed_street_still_matches_but_the_city_alone_does_not():
    found = [feature("street", name="Congress Avenue"), feature("street", name="Austin Avenue")]
    assert labels(found, "1100 congr") == [("1100 Congress Avenue, Austin, TX", True)]
    assert labels(found, "1100 ave austin") == []


def test_what_is_worth_asking_about():
    assert normalize("  1100   Congress Ave, ") == "1100 congress ave"
    assert wanted("1100 congress") and wanted("12b main st")
    assert not wanted("1100") and not wanted("1100 c") and not wanted("congress ave")


def test_suggest_route(client, upstream):
    assert client.get("/api/suggest", params={"q": ""}).json() == {"enabled": True, "suggestions": []}
    assert client.get("/api/suggest", params={"q": "1100 c"}).json()["suggestions"] == []
    assert upstream.count("photon") == 0

    first = client.get("/api/suggest", params={"q": "1100 Congress Ave  Austin"}).json()
    assert first["suggestions"][0] == {"label": "1100 Congress Avenue, Austin, TX", "street_only": True}
    again = client.get("/api/suggest", params={"q": "1100 congress ave austin"}).json()
    assert again == first and upstream.count("photon") == 1  # the same text, cached

    row = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "photon")
    assert row["enabled"] and row["cache"]["entries"] == 1 and row["refresh_confirm"]


def test_suggestions_off_ask_nobody(make_app, upstream):
    with TestClient(make_app()) as client:
        client.put("/api/sources/photon", json={"enabled": False})
        answer = client.get("/api/suggest", params={"q": SUGGEST["congress"]}).json()
    assert answer == {"enabled": False, "suggestions": []} and upstream.count("photon") == 0


def test_a_refusal_pauses_photon_quietly(client, upstream):
    upstream.photon_status = 429
    assert client.get("/api/suggest", params={"q": SUGGEST["congress"]}).json() == {"enabled": True, "suggestions": []}
    assert client.get("/api/suggest", params={"q": SUGGEST["duval"]}).json()["suggestions"] == []
    assert upstream.count("photon") == 1  # paused after the first refusal
    row = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "photon")
    assert row["notice_tone"] == "warn" and "Paused until" in row["notice"]
