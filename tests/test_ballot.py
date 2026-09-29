"""Whole-ballot scenarios through the API, against recorded responses."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from .conftest import ADDRESSES, candidate_names, find_race, get_ballot, last_use


def sources_of(candidate):
    return [card["source"] for card in candidate["cards"]]


def test_capitol_ballot(client):
    ballot = get_ballot(client)

    assert ballot["election_date"] == "2026-11-03"
    assert [e["name"] for e in ballot["elections"]] == ["2026 November General Election"]  # specials don't apply here
    d = ballot["districts"]
    assert (d["county_id"], d["cd"], d["sd"], d["hd"], d["sboe"]) == (227, 10, 14, 49, 5)
    assert (d["jp"], d["constable"], d["commissioner"], d["precinct_source"]) == (5, 5, None, "ballotpedia")
    assert ballot["location"]["county"] == "Travis" and ballot["location"]["city"] == "Austin"
    assert (ballot["location"]["state"], ballot["location"]["state_name"]) == ("TX", "Texas")

    senate = find_race(ballot, "U.S. Senator")
    assert candidate_names(senate)[:3] == ["Ken Paxton", "James Talarico", "Ted Brown"]
    assert [c["ballot_position"] for c in senate["candidates"]] == [1, 2, 3]
    assert senate["candidates"][0]["party_name"] == "Republican"

    house = [r["name"] for r in ballot["races"] if r["name"].startswith("U.S. Representative")]
    assert house == ["U.S. Representative District 10"]
    assert [r["name"] for r in ballot["races"] if r["name"].startswith("State Representative")] == ["State Representative District 49"]
    assert [r["name"] for r in ballot["races"] if "Board of Education" in r["name"]] == ["Member, State Board of Education, District 5"]
    assert not [r for r in ballot["races"] if r["name"].startswith("State Senator")]
    assert any("State Senate District 14" in note for note in ballot["notes"])

    assert find_race(ballot, "Justice of the Peace Precinct 5")
    assert not [r for r in ballot["races"] if "Constable" in r["name"]]  # precinct 4's race isn't ours
    assert {r["name"] for r in ballot["maybe"][0]["races"]} == {"County Commissioner Precinct 2", "County Commissioner Precinct 4"}
    assert find_race(ballot, "District Judge, 147th Judicial District")  # whole-county judicial races stay

    assert find_race(ballot, "Austin City Council District 9")["source"] == "ballotpedia"
    special = next(s for s in ballot["maybe"] if s["id"] == "special")
    assert all(r["group"] == "local" for r in special["races"]) and any(r["seats"] > 1 for r in special["races"])

    paxton = senate["candidates"][0]
    assert sources_of(paxton) == ["sos", "ballotpedia", "trackaipac", "fec"]
    tap = paxton["cards"][2]
    assert tap["match"]["confidence"] == "exact"
    watchlist = next(b for b in tap["badges"] if b["text"].startswith("TrackAIPAC watchlist"))
    assert watchlist["text"] == "TrackAIPAC watchlist $0" and watchlist["url"].endswith("/candidates")
    profile = next(b for b in paxton["cards"][1]["badges"] if b["text"] == "Ballotpedia profile")
    assert profile["url"].startswith("https://ballotpedia.org/")
    sos_card = paxton["cards"][0]
    assert {"Name on ballot", "Filing status", "Occupation"} <= {f["label"] for f in sos_card["facts"]}
    assert paxton["photo_url"]  # from Ballotpedia

    statuses = {s["id"]: (s["last_use"] or {}).get("status") for s in client.get("/api/sources").json()["sources"]}
    assert statuses == {"geocoding": "used", "photon": None, "sos": "used", "ballotpedia": "used", "trackaipac": "used",
                        "fec": "used", "tec": statuses["tec"]}  # suggestions are only asked for while typing
    assert ballot["warnings"] == []


def test_federal_races_get_fec_money(client):
    ballot = get_ballot(client)
    senate, house = find_race(ballot, "U.S. Senator"), find_race(ballot, "U.S. Representative District 10")

    [comparison] = senate["cards"]
    assert comparison["source"] == "fec" and comparison["url"].endswith("/elections/senate/TX/2026/")
    raised = {p["label"]: p["amount"] for p in comparison["breakdowns"][0]["parts"]}
    assert raised == {"Ken Paxton": 9248698.53, "James Talarico": 68560930.42, "Ted Brown": 7459.52}
    assert [p["candidate_key"] for p in comparison["breakdowns"][0]["parts"]] == [c["key"] for c in senate["candidates"]]
    assert [p["label"] for p in house["cards"][0]["breakdowns"][0]["parts"]] == ["Chris Gober", "Caitlin Rourk"]

    talarico = next(c for c in senate["candidates"] if c["name"] == "James Talarico")
    fec = next(card for card in talarico["cards"] if card["source"] == "fec")
    assert fec["match"]["confidence"] == "exact" and fec["as_of"] == "2026-06-30"
    assert [b["text"] for b in fec["badges"]] == ["FEC: raised $68.6M", "Outside spending: $4.1M for · $705K against"]
    assert fec["badges"][0]["url"] == "https://www.fec.gov/data/candidate/S6TX00479/?cycle=2026&election_full=true"
    assert [b["title"] for b in fec["breakdowns"]] == [
        "Where the money came from", "Donations by size", "Where donors live", "Top donors' employers", "Outside spending",
    ]
    sources = fec["breakdowns"][0]
    assert sum(p["amount"] for p in sources["parts"]) == pytest.approx(sources["total"], abs=1)
    assert any("Senate" in link["label"] for link in fec["links"])  # personal financial disclosures

    paxton = next(card for card in senate["candidates"][0]["cards"] if card["source"] == "fec")
    assert paxton["match"]["confidence"] == "likely" and "Warren Kenneth Paxton" in paxton["match"]["note"]
    assert paxton["breakdowns"] == []  # only Talarico's breakdown calls were recorded
    assert not [card for race in ballot["races"] if not race["seat"] for card in race["cards"] if card["source"] == "fec"]


def test_federal_race_comparison(client):
    senate = find_race(get_ballot(client), "U.S. Senator")
    paxton, talarico, brown = keys = [c["key"] for c in senate["candidates"]]
    comparison = senate["cards"][0]["comparison"]
    assert comparison["candidates"] == keys and comparison["as_of"][talarico] == "2026-06-30"
    sections = {s["title"]: s for s in comparison["sections"]}
    assert list(sections) == ["Totals", "Where the money came from", "Donations by size", "Where donors live",
                              "Top donors' employers", "Outside spending"]

    totals = {r["label"]: [v["amount"] for v in r["values"]] for r in sections["Totals"]["rows"]}
    assert totals["Raised"] == [9248698.53, 68560930.42, 7459.52]
    assert totals["Outside spending for them"][1] == pytest.approx(4.1e6, rel=0.05)
    assert totals["Outside spending against them"][1] == pytest.approx(705e3, rel=0.01)

    where = sections["Where the money came from"]
    assert [v["amount"] for v in where["rows"][0]["values"]][::2] == [None, None]  # only Talarico's details were recorded
    assert where["totals"] == {talarico: 68560930.42}
    home = sections["Where donors live"]
    assert [r["label"] for r in home["rows"]] == ["Texas", "Other states"]
    assert sum(r["values"][1]["amount"] for r in home["rows"]) == pytest.approx(home["totals"][talarico])
    assert all(r["values"][1]["count"] for r in home["rows"])
    assert list(sections["Top donors' employers"]["columns"]) == [talarico]
    assert {e["note"] for e in sections["Outside spending"]["columns"][talarico]} == {"for", "against"}


def test_repeat_lookups_make_no_external_calls_even_after_a_restart(make_app, upstream):
    with TestClient(make_app()) as client:
        first = get_ballot(client)
        calls_after_first = len(upstream.calls)
        again = get_ballot(client)
    assert first["meta"]["external_calls"] > 0
    assert again["meta"]["external_calls"] == 0 and len(upstream.calls) == calls_after_first

    with TestClient(make_app()) as client:  # same data dir
        after_restart = get_ballot(client)
    assert after_restart["meta"]["external_calls"] == 0
    assert len(upstream.calls) == calls_after_first


def test_harris_county_gets_exactly_one_sboe_race(client):
    client.put("/api/sources/ballotpedia", json={"enabled": False})
    ballot = get_ballot(client, "harris")
    assert ballot["districts"]["sboe"] == 4 and ballot["districts"]["county_id"] == 101
    sboe = [r["name"] for r in ballot["races"] if "Board of Education" in r["name"]]
    assert sboe == ["Member, State Board of Education, District 4"]
    assert find_race(ballot, "Member, State Board of Education, District 4")["unexpired"] is True


def test_special_election_comes_from_the_statewide_list_when_the_county_has_no_ballot_order(client):
    ballot = get_ballot(client, "hd93")
    race = find_race(ballot, "State Representative District 93")
    assert race is not None and race["unexpired"] and race["election_id"] == 66734
    assert race["candidates"] and all(c["ballot_position"] is None for c in race["candidates"])
    assert "2026 Special Election House District 93" in [e["name"] for e in ballot["elections"]]
    assert not find_race(ballot, "State Representative District 49")  # the Capitol's own district is filtered out


def test_ballotpedia_off(client):
    client.put("/api/sources/ballotpedia", json={"enabled": False})
    ballot = get_ballot(client)
    assert not [r for r in ballot["races"] if r["source"] == "ballotpedia"]
    maybe = {s["id"]: [r["name"] for r in s["races"]] for s in ballot["maybe"]}
    assert "Justice of the Peace Precinct 5" in maybe["precinct"]
    assert "special" not in maybe
    assert last_use(client, "ballotpedia")["status"] == "off"
    senate = find_race(ballot, "U.S. Senator")
    assert sources_of(senate["candidates"][0]) == ["sos", "trackaipac", "fec"]


def test_state_source_off_uses_ballotpedia_for_everything(client, upstream):
    client.put("/api/sources/sos", json={"enabled": False})
    ballot = get_ballot(client)
    assert upstream.count("goelect") == 0
    assert ballot["elections"][0]["name"] == "Ballotpedia sample ballot"
    senate = find_race(ballot, "U.S. Senate Texas")
    assert senate["seat"] == "TX-SEN" and senate["candidates"][0]["ballot_position"] is None
    assert any(c["write_in"] for c in senate["candidates"])
    assert "trackaipac" in sources_of(next(c for c in senate["candidates"] if c["name"] == "Ken Paxton"))
    assert find_race(ballot, "Travis County Justice of the Peace Precinct 5")["group"] == "precinct"


def test_no_ballot_source_is_an_error(client):
    client.put("/api/sources/sos", json={"enabled": False})
    client.put("/api/sources/ballotpedia", json={"enabled": False})
    response = client.post("/api/ballot", json={"address": ADDRESSES["capitol"]})
    assert response.status_code == 400 and "Settings" in response.json()["detail"]


def test_entered_precincts_narrow_the_ballot(client):
    ballot = get_ballot(client, precincts={"commissioner": 2})
    assert find_race(ballot, "County Commissioner Precinct 2")
    assert not find_race(ballot, "County Commissioner Precinct 4")
    assert ballot["districts"]["precinct_source"] == "you"
    assert "precinct" not in [s["id"] for s in ballot["maybe"]]


def test_nominatim_fallback_is_marked_approximate(client):
    client.put("/api/sources/ballotpedia", json={"enabled": False})
    ballot = get_ballot(client, "mopac")
    assert ballot["location"]["geocoder"] == "nominatim" and ballot["location"]["approximate"]
    assert any("approximately" in w for w in ballot["warnings"])
    assert ballot["districts"]["county_id"] == 227


def test_outside_texas_is_refused(client):
    response = client.post("/api/ballot", json={"address": ADDRESSES["dc"]})
    assert response.status_code == 422 and "Texas" in response.json()["detail"]


def test_unknown_address(client):
    response = client.post("/api/ballot", json={"address": "Nowhere Street 123"})
    assert response.status_code == 422


def test_ballotpedia_refusal_degrades_gracefully(client, upstream):
    upstream.ballotpedia_status = 403
    ballot = get_ballot(client)
    assert find_race(ballot, "U.S. Senator")
    assert not find_race(ballot, "Austin City Council District 9")
    assert last_use(client, "ballotpedia")["status"] == "error"
    assert any("Ballotpedia" in w for w in ballot["warnings"])


def test_state_site_down_with_nothing_cached(client, upstream):
    client.put("/api/sources/ballotpedia", json={"enabled": False})
    upstream.down.add("goelect.txelections.civixapps.com")
    response = client.post("/api/ballot", json={"address": ADDRESSES["capitol"]})
    assert response.status_code == 502


def test_state_site_down_later_serves_the_cached_copy(make_app, upstream, tmp_path):
    config_dir = tmp_path / "data"
    with TestClient(make_app(config_dir)) as client:
        get_ballot(client)
    # expire everything, then take the state site down
    import sqlite3

    with sqlite3.connect(config_dir / "cache.sqlite3") as db:
        db.execute("UPDATE responses SET expires_at = 0")
    upstream.down.add("goelect.txelections.civixapps.com")
    with TestClient(make_app(config_dir)) as client:
        ballot = get_ballot(client)
        asked = upstream.count("goelect")
        get_ballot(client)  # the failed requests aren't retried yet: their old copies serve again
        assert upstream.count("goelect") == asked
        sos = last_use(client, "sos")
    assert find_race(ballot, "U.S. Senator")
    assert sos["status"] == "stale" and sos["calls"] == 0


def test_a_ballot_reads_each_state_list_once(client, monkeypatch):
    cache = client.app.state.svc.cache
    asked: list[str] = []
    original = cache.get_json

    async def counting(source, spec, **kwargs):
        asked.append(spec.url)
        return await original(source, spec, **kwargs)

    monkeypatch.setattr(cache, "get_json", counting)
    get_ballot(client)
    for suffix in ("getAllRegions", "getPoliticalParties", "getCandidateStatus", "getDeclarationStatus"):
        assert sum(url.endswith(suffix) for url in asked) == 1, suffix
