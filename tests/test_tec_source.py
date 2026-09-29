"""Texas Ethics Commission: which races it covers, matching filers to the ballot, the cards,
and refresh/reset from Settings. The candidates here are made up."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from votebot.models import Candidate, Race
from votebot.offices import classify
from votebot.sources import tec

from .conftest import FIXTURES, get_ballot, load

WINDOW = "2024-11-06"


def jane(**extra):
    return {
        "id": "00000001", "type": "COH", "name": "Jane Doe", "first": "Jane", "last": "Doe", "short": "Janie",
        "seek": {"office": "STATEREP", "district": "49"},
        "totals": {"raised": 4000.0, "unitemized": 400.0, "spent": 700.0, "cash": 7000.0, "loans": 1000.0, "reports": 2,
                   "as_of": "2025-06-30",
                   "latest": {"type": "SEMIJUL", "name": "July semiannual report", "period_end": "2025-06-30",
                              "filed": "2025-07-15"}},
        "by_kind": {"INDIVIDUAL": {"amount": 3100.0, "count": 3}, "ENTITY": {"amount": 500.0, "count": 1}},
        "by_state": {"TX": 2900.0, "other": 700.0},
        "sizes": [{"amount": 400.0, "count": 1}, {"amount": 3200.0, "count": 3}, {"amount": 0.0, "count": 0},
                  {"amount": 0.0, "count": 0}, {"amount": 0.0, "count": 0}],
        "top_donors": [{"name": "PAT SMITH", "kind": "INDIVIDUAL", "city": "AUSTIN", "state": "TX", "employer": "ACME",
                        "occupation": "CEO", "amount": 2400.0, "count": 2},
                       {"name": "Teachers PAC", "kind": "ENTITY", "city": "Austin", "state": "TX", "amount": 500.0, "count": 1},
                       {"name": "Lee Far", "kind": "INDIVIDUAL", "city": "Oakland", "state": "CA", "employer": "N/A",
                        "occupation": "Retired", "amount": 200.0, "count": 1}],
        **extra,
    }


OUTSIDE = {"name": "Jane Doe", "first": "Jane", "last": "Doe", "seek": {"office": "STATEREP", "district": "49"},
           "total": 2300.0, "count": 3, "spenders": [{"name": "Texans for Jane", "amount": 2000.0, "count": 2},
                                        {"name": "Other Group", "amount": 300.0, "count": 1}]}


def snapshot_dir(tmp_path, filers, outside=()):
    folder = tmp_path / "tec"
    folder.mkdir()
    (folder / "current.json").write_text(json.dumps({"snapshot": "2026-09-27", "window": {"start": WINDOW},
                                                     "filers": list(filers), "outside": list(outside)}), encoding="utf-8")
    return folder


@pytest.mark.parametrize(
    ("office", "office_type", "county", "seat"),
    [
        ("STATE REPRESENTATIVE DISTRICT 49", "SR", "TRAVIS", "STATEREP:49"),
        ("STATE SENATOR, DISTRICT 14", "SR", "TRAVIS", "STATESEN:14"),
        ("MEMBER, STATE BOARD OF EDUCATION, DISTRICT 5", "SR", "TRAVIS", "STATEEDU:5"),
        ("GOVERNOR", "SW", "TRAVIS", "GOVERNOR"),
        ("LIEUTENANT GOVERNOR", "SW", "TRAVIS", "LTGOVERNOR"),
        ("COMMISSIONER OF THE GENERAL LAND OFFICE", "SW", "TRAVIS", "LANDCOMM"),
        ("RAILROAD COMMISSIONER - UNEXPIRED TERM", "SW", "TRAVIS", "RRCOMM"),
        ("JUSTICE, SUPREME COURT, PLACE 2", "SW", "TRAVIS", "JUSTICE_SC:2"),
        ("PRESIDING JUDGE, COURT OF CRIMINAL APPEALS", "SW", "TRAVIS", "PRESIDINGJUDGE_COCA"),
        ("JUSTICE, 3RD COURT OF APPEALS DISTRICT, PLACE 4", "SR", "TRAVIS", "JUSTICE_COA:3:4"),
        ("CHIEF JUSTICE, 15TH COURT OF APPEALS DISTRICT", "SW", "TRAVIS", "CHIEFJUSTICE_COA:15"),
        ("DISTRICT JUDGE, 147TH JUDICIAL DISTRICT", "SR", "TRAVIS", "JUDGEDIST:147"),
        ("DISTRICT ATTORNEY, 53RD JUDICIAL DISTRICT", "SR", "TRAVIS", "DISTATTY:53"),
        ("TRAVIS - JUDGE, COUNTY COURT AT LAW NO. 7", "CW", "TRAVIS", None),  # files with the county
        ("TRAVIS - SHERIFF", "CW", "TRAVIS", None),
        ("TRAVIS - JUSTICE OF THE PEACE, PRECINCT NO. 5", "CR", "TRAVIS", None),
    ],
)
def test_ballot_offices_as_tec_seats(office, office_type, county, seat):
    assert tec.tec_seat(classify(office, office_type, {"TRAVIS"}), county) == seat


def test_tec_offices_as_seats():
    assert tec.seat_key("STATEREP", "049") == "STATEREP:49"
    assert tec.seat_key("RRCOMM_UNEXPIRED") == "RRCOMM"
    assert tec.seat_key("DISTATTY_MULTI", "53") == "DISTATTY:53"
    assert tec.seat_key("JUDGEDIST_FAMILY", "322") == "JUDGEDIST:322"
    assert tec.seat_key("JUDGESTATCO", county="Travis") == "JUDGESTATCO:TRAVIS"
    assert tec.seat_key("STATEREP") is None and tec.seat_key("OTHER") is None
    assert tec.office_text({"office": "STATEREP", "district": "49"}) == "State Representative, District 49"


def race(name, candidates, group="legislature", key="sos:1:1"):
    return Race(key=key, name=name, group=group, source="sos",
                candidates=[Candidate(key=f"{key}:{i}", name=n) for i, n in enumerate(candidates)])


def test_cards_for_a_state_race(tmp_path):
    source = tec.Tec(tmp_path / "data", bundled_dir=snapshot_dir(tmp_path, [jane()], [OUTSIDE]))
    source.ensure_seeded()
    rep = race("State Representative District 49", ["Janie Doe", "Juan Perez"])
    jp = race("Justice of the Peace Precinct 5", ["Jane Doe"], group="precinct", key="sos:1:2")
    scopes = {rep.key: classify("STATE REPRESENTATIVE DISTRICT 49", "SR"), jp.key: classify("JUSTICE OF THE PEACE, PRECINCT 5", "CR")}
    cards = tec.cards(source, [rep, jp], scopes, "Travis")

    assert set(cards.candidates) == {"sos:1:1:0"}  # not Juan Perez (not filed), not the JP race (files locally)
    card = cards.candidates["sos:1:1:0"]
    assert (card.match.confidence, card.match.method) == ("exact", "full name + seat STATEREP:49")  # via her nickname
    assert [b.text for b in card.badges] == ["TEC: raised $4K", "Outside spending: $2.3K"]
    assert "Nov 6, 2024" in card.badges[0].hint and "00000001" in card.badges[0].hint
    facts = {f.label: f.value for f in card.facts}
    assert facts["Cash on hand"] == "$7,000 on Jun 30, 2025" and facts["Outstanding loans"] == "$1,000"
    assert facts["Running for"] == "State Representative, District 49"
    assert facts["Latest report"] == "July semiannual report, through Jun 30, 2025 (filed Jul 15, 2025)"
    where, largest, sizes, states, outside = card.breakdowns
    assert [(p.label, p.amount) for p in where.parts] == [
        ("Small donations (unitemized)", 400.0), ("Individuals", 3100.0), ("PACs, businesses and other groups", 500.0)]
    assert where.total == 4000.0
    assert [(p.label, p.note) for p in largest.parts] == [
        ("Pat Smith", "Austin, TX · Acme (CEO)"), ("Teachers PAC", "Austin, TX"), ("Lee Far", "Oakland, CA · Retired")]
    assert [p.label for p in sizes.parts] == ["Under $500", "$500 to $4,999"] and "$400" in sizes.note
    assert [p.label for p in states.parts] == ["Texas", "Other states"]
    assert [p.label for p in outside.parts] == ["Texans for Jane", "Other Group"] and "doesn't record" in outside.note
    assert card.as_of == "2025-06-30"

    comparison = cards.races[rep.key]
    [money] = comparison.breakdowns
    assert money.title == "Money raised since Nov 6, 2024"
    assert [(p.label, p.amount, p.note) for p in money.parts] == [
        ("Janie Doe", 4000.0, "$7K on hand"), ("Juan Perez", None, "not found in TEC data")]
    assert rep.key in cards.races and jp.key not in cards.races


def juan():
    return {
        "id": "00000009", "type": "COH", "name": "Juan Perez", "first": "Juan", "last": "Perez",
        "seek": {"office": "STATEREP", "district": "49"},
        "totals": {"raised": 1000.0, "unitemized": 0.0, "spent": 100.0, "cash": 900.0, "reports": 1, "as_of": "2025-01-15"},
        "by_kind": {"INDIVIDUAL": {"amount": 750.0, "count": 2}, "ENTITY": {"amount": 250.0, "count": 1}},
        "by_state": {"TX": 1000.0}, "by_state_count": {"TX": 3},
        "sizes": [{"amount": 1000.0, "count": 3}, {"amount": 0.0, "count": 0}, {"amount": 0.0, "count": 0},
                  {"amount": 0.0, "count": 0}, {"amount": 0.0, "count": 0}],
        "top_donors": [{"name": "Pat Smith", "kind": "INDIVIDUAL", "city": "Fresno", "state": "CA", "amount": 750.0, "count": 2},
                       {"name": "TEACHERS PAC", "kind": "ENTITY", "city": "Austin", "state": "TX", "amount": 250.0, "count": 1}],
    }


def test_race_comparison(tmp_path):
    source = tec.Tec(tmp_path / "data", bundled_dir=snapshot_dir(tmp_path, [jane(), juan()], [OUTSIDE]))
    source.ensure_seeded()
    rep = race("State Representative District 49", ["Jane Doe", "Juan Perez", "Kim Lee"])
    cards = tec.cards(source, [rep], {rep.key: classify("STATE REPRESENTATIVE DISTRICT 49", "SR")}, "Travis")
    jane_key, juan_key, _ = (c.key for c in rep.candidates)

    comparison = cards.races[rep.key].comparison
    assert comparison.candidates == [jane_key, juan_key]  # not Kim Lee, who hasn't filed
    assert comparison.as_of == {jane_key: "2025-06-30", juan_key: "2025-01-15"}
    sections = {s.title: s for s in comparison.sections}
    assert list(sections) == ["Totals", "Where the money came from", "Itemized donations by size", "Where donors live",
                              "Largest donors", "Outside spending naming them"]

    totals = {r.label: [(v.amount, v.count) for v in r.values] for r in sections["Totals"].rows}
    assert totals == {
        "Raised": [(4000.0, None), (1000.0, None)], "Spent": [(700.0, None), (100.0, None)],
        "Cash on hand": [(7000.0, None), (900.0, None)], "Outstanding loans": [(1000.0, None), (None, None)],
        "Itemized donations": [(3600.0, 4), (1000.0, 3)], "Outside spending naming them": [(2300.0, 3), (0.0, 0)],
    }
    where = sections["Where the money came from"]
    assert [r.label for r in where.rows] == ["Small donations (unitemized)", "Individuals", "PACs, businesses and other groups"]
    assert [(v.amount, v.count) for v in where.rows[1].values] == [(3100.0, 3), (750.0, 2)]
    assert [v.amount for v in where.rows[0].values] == [400.0, 0.0]  # Juan has none
    assert where.totals == {jane_key: 4000.0, juan_key: 1000.0}
    assert [(v.amount, v.count) for v in sections["Where donors live"].rows[0].values] == [(2900.0, None), (1000.0, 3)]

    donors = sections["Largest donors"].columns
    assert [(d.label, d.shared_with) for d in donors[jane_key]] == [
        ("Pat Smith", []), ("Teachers PAC", [juan_key]), ("Lee Far", [])]  # Juan's Pat Smith lives in California
    assert [(d.label, d.shared_with) for d in donors[juan_key]] == [("Pat Smith", []), ("Teachers PAC", [jane_key])]
    assert donors[jane_key][1].match_key == donors[juan_key][1].match_key and donors[jane_key][0].match_key is None
    assert list(sections["Outside spending naming them"].columns) == [jane_key]

    # The Details tab's breakdown shows how many donations, too.
    where_from = cards.candidates[jane_key].breakdowns[0]
    assert [p.count for p in where_from.parts] == [None, 3, 1]


def test_same_name_for_another_seat_is_only_likely(tmp_path):
    source = tec.Tec(tmp_path / "data", bundled_dir=snapshot_dir(tmp_path, [jane()]))
    source.ensure_seeded()
    senate = race("State Senator, District 14", ["Jane Doe"])
    cards = tec.cards(source, [senate], {senate.key: classify("STATE SENATOR, DISTRICT 14", "SR")}, "Travis")
    match = cards.candidates["sos:1:1:0"].match
    assert match.confidence == "likely" and "State Representative, District 49" in match.note


def test_two_filers_with_the_name_are_told_apart_by_seat(tmp_path):
    other = jane(id="00000002", seek={"office": "STATEREP", "district": "12"}, totals={"raised": 1.0})
    source = tec.Tec(tmp_path / "data", bundled_dir=snapshot_dir(tmp_path, [jane(), other]))
    source.ensure_seeded()
    rep = race("State Representative District 49", ["Jane Doe"])
    cards = tec.cards(source, [rep], {rep.key: classify("STATE REPRESENTATIVE DISTRICT 49", "SR")}, "Travis")
    assert cards.candidates["sos:1:1:0"].facts[-1].value == "00000001"
    unknown_seat = race("Some State Office", ["Jane Doe"], group="state")
    assert not tec.cards(source, [unknown_seat], {}, "Travis").candidates  # two Jane Does and no seat to decide


def test_no_snapshot_means_no_cards(tmp_path):
    source = tec.Tec(tmp_path / "data", bundled_dir=tmp_path / "missing")
    assert not source.ensure_seeded()
    rep = race("State Representative District 49", ["Jane Doe"])
    assert not tec.cards(source, [rep], {}, "Travis").candidates


def test_reset_keeps_a_downloaded_zip(tmp_path):
    source = tec.Tec(tmp_path / "data", bundled_dir=snapshot_dir(tmp_path, [jane()]))
    source.ensure_seeded()
    source.local_zip.write_bytes(b"zip")
    (tmp_path / "data" / "current.json").write_text('{"snapshot": "edited", "filers": []}', encoding="utf-8")
    source.reset()
    assert source.document()["snapshot"] == "2026-09-27" and source.local_zip.exists()


def test_refresh_and_reset_from_settings(make_app, tmp_path):
    with TestClient(make_app()) as client:
        message = client.post("/api/sources/tec/refresh").json()["message"]
        assert message.startswith("updated snapshot")
        assert client.post("/api/sources/tec/clear").json()["message"].startswith("Back to the snapshot bundled with tec_cache")
    [call] = make_app.tec_refreshed
    assert call == {"data_dir": tmp_path / "data" / "tec", "zip_path": None}


def test_a_failed_refresh_changes_nothing_and_says_why(make_app):
    def blocked(**_kwargs):
        raise RuntimeError("TEC's download server refused the request (HTTP 403)")

    with TestClient(make_app(tec_refresh=blocked)) as client:
        response = client.post("/api/sources/tec/refresh")
        assert response.status_code == 502 and "nothing changed" in response.json()["detail"]
        tec_row = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "tec")
    assert tec_row["notice_tone"] == "warn" and "HTTP 403" in tec_row["notice"]


@pytest.mark.skipif(not load("tec/current.json").get("filers") if (FIXTURES / "tec" / "current.json").exists() else True,
                    reason="no TEC fixture yet (scripts/record_fixtures.py --only tec)")
def test_capitol_ballot_state_races_get_tec_money(client):
    ballot = get_ballot(client)
    with_tec = [r for r in ballot["races"] if any(c["source"] == "tec" for c in r["cards"])]
    assert with_tec and all(r["group"] in ("state", "legislature", "judicial") for r in with_tec)
    assert not [r for r in ballot["races"] if r["group"] in ("federal", "precinct", "local")
                and any(c["source"] == "tec" for cand in r["candidates"] for c in cand["cards"])]
