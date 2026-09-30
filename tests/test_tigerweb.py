"""District outlines for the map (TIGERweb, plus the SBOE map): finding the layers, reading
the rings, and GET /api/district-outlines."""

from __future__ import annotations

import pytest

from votebot.sources import tigerweb
from votebot.sources.sboe import _inside

from .conftest import capitol_point, load

CAPITOL = {"cd": 10, "sd": 14, "hd": 49, "sboe": 5}


def inside(rings, lat: float, lon: float) -> bool:
    """Even-odd over every ring, as the map fills them."""
    return sum(_inside(lon, lat, ring) for ring in rings) % 2 == 1


def outlines(client, **numbers):
    response = client.get("/api/district-outlines", params=numbers)
    assert response.status_code == 200, response.text
    return response.json()


# -- reading TIGERweb -------------------------------------------------------------------------


def test_layers_are_found_by_the_end_of_their_name():
    index = load("tigerweb_layers.json")
    assert [tigerweb.layer_id(index, kind) for kind in ("cd", "sd", "hd")] == [54, 56, 58]
    made_up = {"layers": [
        {"id": 1, "name": "119th Congressional Districts"},
        {"id": 2, "name": "120th Congressional Districts Labels"},
        {"id": 3, "name": "120th Congressional Districts"},
    ]}
    assert tigerweb.layer_id(made_up, "cd") == 3  # the newest, and not its labels
    assert tigerweb.layer_id(made_up, "sd") is None


def test_geoids():
    assert [tigerweb.geoid("cd", 10), tigerweb.geoid("cd", 1), tigerweb.geoid("sd", 14), tigerweb.geoid("hd", 49)] == [
        "4810", "4801", "48014", "48049",
    ]


def test_rings():
    found = tigerweb.rings(load("tigerweb_48049.json"))
    assert len(found) == 1 and found[0][0] == found[0][-1]
    assert inside(found, *capitol_point())
    assert tigerweb.rings({"features": []}) is None


# -- through the API ------------------------------------------------------------------------


def test_the_capitols_outlines_are_asked_once(client, upstream):
    got = outlines(client, **CAPITOL)
    assert [(o["kind"], o["number"]) for o in got["outlines"]] == list(CAPITOL.items())
    assert got["notes"] == []
    lat, lon = capitol_point()
    assert all(inside(o["rings"], lat, lon) for o in got["outlines"])
    assert upstream.count("tigerweb") == 4  # the layer list, then one request per district
    assert got["meta"]["external_calls"] == 5  # and the SBOE map, downloaded on first use

    again = outlines(client, **CAPITOL)
    assert again["outlines"] == got["outlines"]
    assert again["meta"]["external_calls"] == 0 and upstream.count("tigerweb") == 4


def test_only_what_is_asked(client, upstream):
    empty = outlines(client)
    assert empty["outlines"] == [] and empty["notes"] == [] and upstream.calls == []
    got = outlines(client, hd=49)
    assert [o["kind"] for o in got["outlines"]] == ["hd"]
    assert upstream.count("data.capitol.texas.gov") == 0


def test_a_district_tigerweb_does_not_have(client, upstream):
    got = outlines(client, hd=150)
    assert got["outlines"] == [] and got["notes"] == ["No outline found for State House District 150."]


def test_tigerweb_off(client, upstream):
    client.put(f"/api/sources/{tigerweb.SOURCE}", json={"enabled": False})
    got = outlines(client, **CAPITOL)
    assert [o["kind"] for o in got["outlines"]] == ["sboe"]
    assert got["notes"] == ["U.S. House, State Senate and State House outlines are turned off in Settings."]
    assert upstream.count("tigerweb") == 0


def test_tigerweb_down_still_draws_the_sboe_district(client, upstream):
    upstream.down.add("tigerweb.geo.census.gov")
    got = outlines(client, **CAPITOL)
    assert [o["kind"] for o in got["outlines"]] == ["sboe"]
    assert got["notes"] == [
        "The US Census's map service isn't responding, so U.S. House District 10 isn't drawn.",
        "The US Census's map service isn't responding, so State Senate District 14 isn't drawn.",
        "The US Census's map service isn't responding, so State House District 49 isn't drawn.",
    ]


def test_a_refusal_pauses_tigerweb(client, upstream):
    upstream.tigerweb_status = 429
    outlines(client, **CAPITOL)
    got = outlines(client, **CAPITOL)
    assert got["notes"][0] == "The US Census's map service is paused, so U.S. House District 10 isn't drawn."
    assert upstream.count("tigerweb") == 1  # the three districts shared the one refused request
    status = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == tigerweb.SOURCE)
    assert status["notice"].startswith("Paused until") and status["notice_tone"] == "warn"


@pytest.mark.parametrize("numbers", [{"cd": 39}, {"sd": 32}, {"hd": 0}, {"sboe": 16}, {"cd": "ten"}])
def test_numbers_out_of_range_are_refused(client, upstream, numbers):
    assert client.get("/api/district-outlines", params=numbers).status_code == 422
    assert upstream.calls == []


def test_refresh_and_clear_outlines(client, upstream):
    outlines(client, **CAPITOL)
    refreshed = client.post(f"/api/sources/{tigerweb.SOURCE}/refresh").json()["message"]
    assert refreshed == "Refreshed 4 cached responses." and upstream.count("tigerweb") == 8
    assert client.post(f"/api/sources/{tigerweb.SOURCE}/clear").json()["message"] == "Cleared 4 cached responses."
    outlines(client, **CAPITOL)
    assert upstream.count("tigerweb") == 12
