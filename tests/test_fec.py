"""FEC: matching the ballot to the FEC's lists, the shared DEMO_KEY, the rate limit, and
keeping the API key out of the cache."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from votebot.matching import NameIndex, last_first, match_person
from votebot.sources import fec
from votebot.text import display_org, money, money_short

from .conftest import FEC_KEY, find_race, get_ballot, last_use, load


def test_names_written_last_name_first():
    assert last_first("PAXTON, WARREN KENNETH JR.") == "WARREN KENNETH PAXTON JR."
    assert last_first("CORNYN, JOHN SEN") == "JOHN CORNYN"
    assert last_first("Lucero, Homero R. (Mr.)") == "Homero R. Lucero"
    assert last_first("Gutierrez, Rolando (The Honorable)") == "Rolando Gutierrez"
    assert last_first("Texans for Jane") == "Texans for Jane"


def race_index() -> NameIndex:
    index = NameIndex()
    for row in fec._campaigns(load("fec_elections_house_10.json")["results"]):
        index.add(last_first(row["candidate_name"]), row)
    return index


def test_one_row_per_campaign():
    rows = load("fec_elections_house_10.json")["results"]
    eckhardt = [r for r in rows if r["candidate_name"].startswith("ECKHARDT")]
    assert len(eckhardt) == 2 and len({r["candidate_pcc_id"] for r in eckhardt}) == 1  # one campaign, two IDs
    assert len([r for r in fec._campaigns(rows) if r["candidate_name"].startswith("ECKHARDT")]) == 1


def test_a_nickname_the_fec_keeps_as_a_middle_name_is_a_likely_match():
    index = NameIndex()
    for row in load("fec_elections_senate.json")["results"]:
        index.add(last_first(row["candidate_name"]), row)
    row, match = match_person(index, "Ken Paxton", "R", "TX-SEN", seats_of=lambda _row: {"TX-SEN"},
                              party_of=lambda r: fec.party_code(r["party_full"]), source="the FEC",
                              name_of=lambda r: r["candidate_name"])
    assert row["candidate_id"] == "S6TX00388"
    assert (match.confidence, match.method) == ("likely", "last name, in the same seat")
    assert "PAXTON, WARREN KENNETH JR." in match.note


def test_someone_else_with_the_name_in_another_party_is_left_out():
    index = race_index()
    assert match_person(index, "Chris Gober", "D", "TX-10", seats_of=lambda _row: {"TX-10"},
                        party_of=lambda r: fec.party_code(r["party_full"]))[1].confidence == "likely"
    assert match_person(index, "Nobody Here", None, "TX-10", seats_of=lambda _row: {"TX-10"}) is None


def test_cycle_and_period():
    import datetime as dt

    assert fec.cycle_of(dt.date(2026, 11, 3)) == 2026 and fec.cycle_of(dt.date(2027, 5, 1)) == 2028
    assert fec.period("TX-SEN", 2026) == "2021–26" and fec.period("TX-10", 2026) == "2025–26"
    assert fec.party_code("DEMOCRATIC PARTY") == "D" and fec.party_code("WRITE-IN") is None


def test_money_for_badges():
    assert (money_short(68560930.42), money_short(542119.97), money_short(7459.52), money_short(950)) == (
        "$68.6M", "$542K", "$7.5K", "$950")
    assert money_short(999_700) == "$1M" and money_short(0) == "$0"
    assert money(219959) == "$219,959" and money(1234.56) == "$1,235"
    assert display_org("LONE STAR RISING PAC") == "Lone Star Rising PAC"
    assert display_org("NRCC") == "NRCC" and display_org("TEXANS FOR SENATOR JOHN CORNYN INC.") == "Texans for Senator John Cornyn Inc."


def test_employers_that_say_nothing_are_left_out():
    rows = [{"employer": "NULL", "total": 1100000.0, "count": 686}, {"employer": "Not employed", "total": 900.0},
            {"employer": "UNIVERSITY OF TEXAS", "total": 83800.0, "count": 522}]
    assert [p.label for p in fec._employers(rows, 2026).parts] == ["University of Texas"]


def test_demo_key_shows_totals_only(make_app, upstream):
    with TestClient(make_app(fec_key="DEMO_KEY")) as client:
        ballot = get_ballot(client)
        overview = client.get("/api/sources").json()
    senate = find_race(ballot, "U.S. Senator")
    assert senate["cards"]  # the race comparison needs only the race list
    assert [s["title"] for s in senate["cards"][0]["comparison"]["sections"]] == ["Totals"]
    card = next(c for c in senate["candidates"][1]["cards"] if c["source"] == "fec")
    assert card["badges"][0]["text"] == "FEC: raised $68.6M" and card["breakdowns"] == []
    assert card["figures"]["raised"] == 68560930.42 and "outside_for" not in card["figures"]  # not asked for, so not 0
    assert any("VOTEBOT_FEC_API_KEY" in note for note in ballot["notes"])
    assert all("/elections/" in call for call in upstream.calls if "open.fec.gov" in call)
    assert upstream.fec_keys == {"DEMO_KEY"}
    fec_row = next(s for s in overview["sources"] if s["id"] == "fec")
    assert fec_row["notice_tone"] == "warn" and "DEMO_KEY" in fec_row["notice"]


def test_hourly_limit_pauses_the_fec_and_keeps_the_ballot(make_app, upstream):
    upstream.fec_status = 429
    with TestClient(make_app()) as client:
        ballot = get_ballot(client)
        assert find_race(ballot, "U.S. Senator")["candidates"]
        assert any("FEC" in w for w in ballot["warnings"])
        assert last_use(client, "fec")["status"] == "error"
        asked = upstream.count("open.fec.gov")
        upstream.fec_status = None
        again = get_ballot(client)  # paused: nothing cached, so no FEC cards, and no new request
        assert upstream.count("open.fec.gov") == asked
        assert any("paused" in w for w in again["warnings"])
        overview = client.get("/api/sources").json()
    assert "rate limit" in next(s for s in overview["sources"] if s["id"] == "fec")["notice"]


def test_a_rate_limit_on_a_cached_answer_pauses_the_fec_too(make_app, upstream, tmp_path):
    with TestClient(make_app()) as client:
        get_ballot(client)
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        db.execute("UPDATE responses SET expires_at = 0 WHERE source = 'fec'")
    upstream.fec_status = 429
    with TestClient(make_app()) as client:
        ballot = get_ballot(client)  # the old copies still show, and the FEC is paused
        asked = upstream.count("open.fec.gov")
        assert asked and find_race(ballot, "U.S. Senator")["cards"]
        assert "rate limit" in next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "fec")["notice"]
        with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
            db.execute("DELETE FROM flags WHERE name LIKE 'retry:%'")  # only the pause holds the FEC back now
        get_ballot(client)
        assert upstream.count("open.fec.gov") == asked


def test_paused_fec_still_serves_what_it_has(make_app, upstream, tmp_path):
    with TestClient(make_app()) as client:
        get_ballot(client)
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        db.execute("INSERT INTO flags (name, source, expires_at) VALUES ('paused:fec', 'fec', 9e12)")
    with TestClient(make_app()) as client:
        ballot = get_ballot(client)
    senate = find_race(ballot, "U.S. Senator")
    assert senate["cards"] and not any("FEC" in w for w in ballot["warnings"])


def test_a_refused_key_is_explained(make_app, upstream):
    upstream.fec_status = 403
    with TestClient(make_app()) as client:
        ballot = get_ballot(client)
    assert any("VOTEBOT_FEC_API_KEY" in w for w in ballot["warnings"])


def test_the_key_is_sent_but_never_stored(make_app, upstream, tmp_path):
    with TestClient(make_app()) as client:
        get_ballot(client)
    assert upstream.fec_keys == {FEC_KEY}
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        stored = db.execute("SELECT request FROM responses WHERE source = 'fec'").fetchall()
    assert stored and not any(FEC_KEY in request for (request,) in stored)


def test_fec_off(client):
    client.put("/api/sources/fec", json={"enabled": False})
    ballot = get_ballot(client)
    assert [card["source"] for card in find_race(ballot, "U.S. Senator")["cards"]] == ["polls"]
    assert last_use(client, "fec")["status"] == "off"
