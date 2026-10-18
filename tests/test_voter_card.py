"""A ballot from a voter card's County and Precinct number, without an address, and the races a
ballot leaves out until the voter asks for them."""

from __future__ import annotations

import json

from pallot import counties

from .conftest import TRAVIS_LIST, TRAVIS_QUERY, find_race, get_ballot, switch, travis_rows

CARD = {"county": "Travis", "precinct": 300}


def card_ballot(client, **extra):
    response = client.post("/api/ballot", json={**CARD, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def capitol_everywhere(upstream):
    """The Census answers any point as it answers the Capitol's address."""
    upstream.census_coordinates = "capitol"


def test_counties_by_name():
    assert len(counties.COUNTIES) == 254
    assert counties.find("Travis") == ("Travis", 453) and counties.find("harris county") == ("Harris", 201)
    assert counties.find("De Witt") == ("DeWitt", 123) and counties.find("mclennan") == ("McLennan", 309)
    assert counties.find("Zavala") == ("Zavala", 507) and counties.find("Atlantis") is None


def test_a_voter_card_gives_the_same_ballot_as_the_address(client, upstream):
    capitol_everywhere(upstream)
    card = card_ballot(client)
    assert upstream.count("onelineaddress") == 0 and upstream.count("nominatim") == 0

    address = get_ballot(client)
    d, a = card["districts"], address["districts"]
    assert [d[k] for k in ("cd", "sd", "hd", "sboe", "commissioner", "jp")] == [10, 14, 49, 5, 2, 5]
    assert {k: d[k] for k in ("cd", "sd", "hd", "sboe", "commissioner", "jp", "election_precinct")} == {
        k: a[k] for k in ("cd", "sd", "hd", "sboe", "commissioner", "jp", "election_precinct")}
    assert [r["key"] for r in card["races"]] == [r["key"] for r in address["races"]]
    location = card["location"]
    assert (location["source"], location["matched_address"], location["geocoder"]) == ("voter_card", None, None)
    assert (location["county"], location["city"]) == ("Travis", "Austin")


def test_a_second_lookup_of_the_same_precinct_makes_no_calls(client, upstream, logged_calls):
    capitol_everywhere(upstream)
    first = card_ballot(client)
    calls = len(upstream.calls)
    assert logged_calls() > 0 and first["location"]["source"] == "voter_card"
    card_ballot(client, precinct="0300")  # as the map writes it
    assert logged_calls() == 0 and len(upstream.calls) == calls


def test_while_the_precinct_map_downloads_a_voter_card_gets_the_county_and_the_districts_entered(client, upstream):
    client.app.state.svc.election_precincts.first_wait = 0
    ballot = card_ballot(client, districts={"cd": 10})
    assert upstream.count("geocoding.geo.census.gov") == 0
    assert any(n.startswith("Pallot finds your districts on its precinct map, which is still downloading") for n in ballot["notes"])
    assert find_race(ballot, "U.S. Senator") and find_race(ballot, "County Clerk")
    assert find_race(ballot, "U.S. Representative District 10") and ballot["districts"]["entered"] == ["cd"]
    assert ballot["location"]["lat"] is None and ballot["districts"]["election_precinct"] is None
    assert ballot["left_out"]["missing"][:2] == ["sd", "hd"] and "commissioner" in ballot["left_out"]["missing"]
    assert "Your State House district isn't known" in " ".join(ballot["left_out"]["lines"])


def test_a_precinct_the_map_doesnt_have(client):
    ballot = card_ballot(client, precinct="9999")
    assert any("has no precinct 9999 in Travis County" in w for w in ballot["warnings"])
    assert find_race(ballot, "U.S. Senator")


def test_a_request_needs_an_address_or_a_county_and_precinct(client):
    for body in ({}, {"county": "Travis"}, {"precinct": "300"}, {"address": "", "county": "Travis"}):
        assert client.post("/api/ballot", json=body).status_code == 422, body
    unknown = client.post("/api/ballot", json={"county": "Atlantis", "precinct": "1"})
    assert unknown.status_code == 422 and "no county called" in unknown.json()["detail"]


def test_the_entry_card_config(client):
    config = client.get("/api/config").json()
    assert config["default_entry"] == "address" and config["voter_card"] is True
    assert len(config["counties"]) == 254 and config["counties"][0] == "Anderson"


def test_races_the_districts_dont_settle_are_left_out_without_cards(client, upstream):
    switch(client, "county_precincts", False)
    ballot = get_ballot(client)
    assert ballot["left_out"] == {
        "races": 2 + 6, "missing": ["commissioner", "jp"], "shown": False,
        "lines": ["Your County Commissioner precinct isn't known: 2 races depend on it.",
                  "Your Justice of the Peace precinct isn't known: 6 races depend on it."],
    }
    assert ballot["maybe"] == [] and "County Commissioner Precinct 2" not in json.dumps(ballot)

    shown = get_ballot(client, all_races=True)
    waiting = next(s for s in shown["maybe"] if s["id"] == "precinct")
    assert find_race(shown, "County Commissioner Precinct 2", maybe=True) and shown["left_out"]["shown"]
    assert len(waiting["races"]) == shown["left_out"]["races"]


def test_the_countys_records_settle_a_voter_cards_precincts(client, upstream):
    capitol_everywhere(upstream)
    upstream.arcgis["taxmaps.traviscountytx.gov"][TRAVIS_QUERY] = travis_rows({**TRAVIS_LIST, "300": (4, 3)})
    d = card_ballot(client)["districts"]
    assert (d["commissioner"], d["jp"]) == (4, 3) and d["precinct_sources"]["commissioner"] == "county"
    entered = card_ballot(client, precincts={"commissioner": 1})["districts"]
    assert entered["commissioner"] == 1 and entered["precinct_sources"]["commissioner"] == "you"
