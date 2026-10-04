"""Polls (FiftyPlusOne): which polls count, the race's poll bar and each candidate's Polls tab."""

from __future__ import annotations

import httpx
import pytest
import respx

from pallot.config import Ttls
from pallot.http_cache import HttpCache
from pallot.models import Candidate, Race
from pallot.sources import polls

from .conftest import find_race, get_ballot, last_use

SENATE = Race(key="sen", name="U.S. Senator", group="federal", seat="TX-SEN", source="sos", candidates=[
    Candidate(key="paxton", name="Ken Paxton", party="R"),
    Candidate(key="talarico", name="James Talarico", party="D"),
    Candidate(key="brown", name="Ted Brown", party="L"),
])


def poll(poll_id, pollster, end, *questions, state="Texas"):
    return {"poll_id": str(poll_id), "pollster_id": pollster, "state": state, "end_date": end, "url": f"https://polls.test/{poll_id}",
            "pollster": {"pollster_id": pollster, "display_name": f"Pollster {pollster}"}, "questions": list(questions)}


def question(shares, population="lv", office="U.S. Senate", seat="Class II", cycle=2026, stage="general"):
    answers = [{"pct": pct, "candidate": {"name": name}} for name, pct in shares.items()]
    return {"office_type": office, "seat_name": seat, "population": population, "cycle": cycle, "stage": stage, "answers": answers}


def kept(rows, race=SENATE, kind=polls.SENATE):
    return polls.readings(rows, kind, race, 2026)


def test_a_matchup_that_wont_happen_is_left_out():
    rows = [poll(1, 1, "2026-09-01", question({"James Talarico": 44, "John Cornyn": 45, "Ted Brown": 3}),
                 question({"James Talarico": 46, "Ken Paxton": 43}))]
    [reading] = kept(rows)
    assert reading.shares == {"talarico": 46.0, "paxton": 43.0}


def test_likely_voters_win_and_a_minor_name_off_the_ballot_is_ignored():
    rows = [poll(1, 1, "2026-09-01", question({"James Talarico": 47, "Ken Paxton": 44}, population="rv"),
                 question({"James Talarico": 48, "Ken Paxton": 45, "Someone Else": 2}, population="lv"))]
    [reading] = kept(rows)
    assert (reading.population, reading.shares) == ("lv", {"talarico": 48.0, "paxton": 45.0})


def test_each_pollsters_latest_poll_counts_and_the_median_is_taken():
    rows = [
        poll(1, "a", "2026-06-01", question({"Talarico": 40, "Paxton": 50})),  # superseded by the same pollster
        poll(2, "a", "2026-09-01", question({"Talarico": 48, "Paxton": 44})),
        poll(3, "b", "2026-08-01", question({"Talarico": 46, "Paxton": 45, "Ted Brown": 3})),
        poll(4, "c", "2026-07-01", question({"Talarico": 45, "Paxton": 47})),
        poll(5, "d", "2026-09-10", question({"Talarico": 50, "Paxton": 40}), state="Florida"),  # not ours: filtered earlier
        poll(6, "e", "2025-10-01", question({"Talarico": 30, "Paxton": 60}, cycle=2024)),
        poll(7, "f", "2026-01-01", question({"Talarico": 30, "Paxton": 60}, stage="primary")),
    ]
    readings = kept([row for row in rows if row["state"] == "Texas"])
    assert [r.poll_id for r in readings] == ["2", "3", "4"]  # newest first
    assert polls.medians(SENATE, readings) == {"paxton": 45.0, "talarico": 46.0, "brown": 3.0}
    assert polls.medians(SENATE, readings[:2]) == {"paxton": 44.5, "talarico": 47.0, "brown": 3.0}


def test_a_house_poll_counts_only_for_its_district():
    tx10 = Race(key="h10", name="U.S. Representative District 10", group="federal", seat="TX-10", source="sos",
                candidates=[Candidate(key="gober", name="Chris Gober", party="R"),
                            Candidate(key="rourk", name="Caitlin Rourk", party="D")])
    rows = [poll(1, 1, "2026-08-01", question({"Chris Gober": 48, "Caitlin Rourk": 44}, office="U.S. House", seat="District 10")),
            poll(2, 2, "2026-08-01", question({"Chris Gober": 30, "Caitlin Rourk": 60}, office="U.S. House", seat="District 11"))]
    assert [r.poll_id for r in kept(rows, tx10, polls.HOUSE)] == ["1"]


def test_bar_and_tab_for_a_race():
    readings = kept([poll(1, "a", "2026-09-01", question({"Talarico": 48, "Paxton": 44})),
                     poll(2, "b", "2026-08-01", question({"Talarico": 46, "Paxton": 45}))])
    middle = polls.medians(SENATE, readings)
    bar = polls.race_card(SENATE, readings, middle)
    [breakdown] = bar.breakdowns
    assert (bar.label, bar.as_of, breakdown.unit) == ("FiftyPlusOne", "2026-09-01", "percent")
    assert [(p.label, p.amount, p.note, p.candidate_key) for p in breakdown.parts] == [
        ("Ken Paxton", 44.5, None, "paxton"), ("James Talarico", 47.0, None, "talarico"),
        ("Ted Brown", None, "not in these polls", "brown"),
    ]
    assert "2 polls, Aug 1, 2026 – Sep 1, 2026" in breakdown.note

    tab = polls.candidate_card(SENATE.candidates[1], SENATE, readings, middle["talarico"])
    assert (tab.label, tab.badges, tab.figures) == ("Polls", [], {"poll": 47.0})
    assert bar.figures == {}
    assert [(f.label, f.value, f.url) for f in tab.facts] == [
        ("Median", "47% across 2 polls", None),
        ("Pollster a", "48% · Ken Paxton 44% · Sep 1, 2026 · likely voters", "https://polls.test/1"),
        ("Pollster b", "46% · Ken Paxton 45% · Aug 1, 2026 · likely voters", "https://polls.test/2"),
    ]


@pytest.mark.anyio
async def test_pages_are_read_until_one_comes_back_short(tmp_path):
    first = [poll(n, n, "2026-09-01", state="Ohio") for n in range(polls.PAGE - 1)] + [poll(9999, 1, "2026-09-01")]
    with respx.mock() as router:
        route = router.get(polls.API).mock(side_effect=lambda request: httpx.Response(200, json={
            "data": first if request.url.params["offset"] == "0" else [poll(10000, 2, "2026-09-02"), first[0]]}))
        async with httpx.AsyncClient() as client:
            found = await polls.Polls(HttpCache(tmp_path / "c.sqlite3", client), Ttls()).polls(polls.SENATE)
    assert sorted(row["poll_id"] for row in found) == ["10000", "9999"]
    assert [call.request.url.params["offset"] for call in route.calls] == ["0", "500"]
    assert all("Mozilla" in call.request.headers["user-agent"] for call in route.calls)


@pytest.mark.anyio
async def test_paging_stops_if_the_api_ignores_the_offset(tmp_path):
    same = [poll(n, n, "2026-09-01") for n in range(polls.PAGE)]
    with respx.mock() as router:
        route = router.get(polls.API).mock(return_value=httpx.Response(200, json={"data": same}))
        async with httpx.AsyncClient() as client:
            found = await polls.Polls(HttpCache(tmp_path / "c.sqlite3", client), Ttls()).polls(polls.SENATE)
    assert len(found) == polls.PAGE and route.call_count == 2


# -- through the API, with the recorded lists ------------------------------------------


def test_capitol_ballot_polls(client, upstream):
    ballot = get_ballot(client)
    senate, governor = find_race(ballot, "U.S. Senator"), find_race(ballot, "Governor")

    bar = senate["cards"][-1]
    assert (bar["source"], bar["label"], bar["as_of"]) == ("polls", "FiftyPlusOne", "2026-09-26")
    parts = bar["breakdowns"][0]["parts"]
    assert bar["breakdowns"][0]["unit"] == "percent"
    assert [(p["label"], p["amount"]) for p in parts] == [("Ken Paxton", 45.0), ("James Talarico", 47.0), ("Ted Brown", 3.0)]
    assert [p["candidate_key"] for p in parts] == [c["key"] for c in senate["candidates"]]
    assert [p["amount"] for p in governor["cards"][-1]["breakdowns"][0]["parts"]][:2] == [49.0, 45.0]
    assert not [c for c in find_race(ballot, "U.S. Representative District 10")["cards"] if c["source"] == "polls"]

    talarico = next(c for c in senate["candidates"] if c["name"] == "James Talarico")
    tab = next(card for card in talarico["cards"] if card["source"] == "polls")
    assert tab["badges"] == [] and tab["facts"][0] == {"label": "Median", "value": "47% across 28 polls", "url": None}
    assert tab["facts"][1]["label"] == "Big Data Poll" and tab["facts"][1]["value"].startswith("46.8% · Ken Paxton 44.9%")

    assert upstream.count("fiftyplusone.news") == 3  # one page each of the Senate, House and Governor lists
    assert all("Mozilla" in agent for agent in upstream.polls_agents)
    assert last_use(client, "polls")["status"] == "used"


def test_polls_are_asked_once_a_day(client, upstream):
    get_ballot(client)
    get_ballot(client)
    assert upstream.count("fiftyplusone.news") == 3


def test_a_refusal_pauses_polls_and_the_ballot_still_loads(client, upstream):
    upstream.polls_status = 403
    ballot = get_ballot(client)
    assert "Couldn't load polls from FiftyPlusOne (HTTP 403)." in ballot["warnings"]
    assert not [c for c in find_race(ballot, "U.S. Senator")["cards"] if c["source"] == "polls"]
    assert last_use(client, "polls")["status"] == "error"
    asked = upstream.count("fiftyplusone.news")
    again = get_ballot(client)
    assert upstream.count("fiftyplusone.news") == asked  # paused: not asked again
    assert any("paused until" in w for w in again["warnings"])
    status = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == "polls")
    assert status["notice"].startswith("Paused until") and status["notice_tone"] == "warn"


def test_polls_off(client, upstream):
    client.put("/api/sources/polls", json={"enabled": False})
    ballot = get_ballot(client)
    assert upstream.count("fiftyplusone.news") == 0
    assert not [c for c in find_race(ballot, "U.S. Senator")["cards"] if c["source"] == "polls"]
    assert last_use(client, "polls")["status"] == "off"
