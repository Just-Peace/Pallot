"""A member of Congress's bills from Congress.gov (sources/congress_gov.py), in their In Congress tab."""

from __future__ import annotations

import httpx
import pytest

from pallot.config import Config
from pallot.http_cache import HttpCache, RequestSpec
from pallot.services import prune
from pallot.sources import congress_gov

from .conftest import FEC_KEY, find_race, get_ballot, load, switch
from .test_http_cache import Clock


def paxton_holds_the_seat(upstream) -> None:
    """Cornyn's record as Paxton's, so the Senate race has its member of Congress on the ballot."""
    members = load("officeholders_congress.json")
    cornyn = next(m for m in members if m["name"].get("official_full") == "John Cornyn")
    cornyn["name"] = {"first": "Warren", "last": "Paxton", "official_full": "Warren Kenneth Paxton", "nickname": "Ken"}
    upstream.congress_members = members


def paxton(ballot):
    return next(c for c in find_race(ballot, "U.S. Senator")["candidates"] if c["name"] == "Ken Paxton")


def test_the_member_running_again_gets_their_bills(client, upstream, logged_calls):
    paxton_holds_the_seat(upstream)
    [card] = [c for c in paxton(get_ballot(client))["cards"] if c["source"] == "congress_gov"]
    assert (card["kind"], card["label"], card["match"]["method"]) == ("record", "In Congress", "name")
    sponsored, cosponsored = card["lists"]
    assert (sponsored["title"], cosponsored["title"]) == ("Sponsored", "Cosponsored")
    assert sponsored["total"] == load("congress_gov_C001056_sponsored.json")["pagination"]["count"]
    first = sponsored["items"][0]
    assert first["url"] == "https://www.congress.gov/bill/119th-congress/senate-resolution/948"
    assert first["meta"] == "S.Res. 948 · Sep 30, 2026" and first["note"].startswith("Sep 30, 2026 Submitted in the Senate")
    assert card["links"] == [{"label": "All their bills on Congress.gov",
                              "url": "https://www.congress.gov/member/warren-kenneth-paxton/C001056"}]
    assert upstream.count("api.congress.gov") == 2 and set(upstream.congress_gov_keys) == {FEC_KEY}

    get_ballot(client)
    assert logged_calls() == 0 and upstream.count("api.congress.gov") == 2


def test_nobody_else_is_asked_about(client, upstream):
    ballot = get_ballot(client)  # the seats' holders aren't on this ballot
    assert upstream.count("api.congress.gov") == 0
    assert not [card for r in ballot["races"] for c in r["candidates"] for card in c["cards"] if card["source"] == "congress_gov"]


def test_off_with_its_switch_or_the_seat_holders(client, upstream):
    paxton_holds_the_seat(upstream)
    switch(client, "congress_gov", False)
    assert not [c for c in paxton(get_ballot(client))["cards"] if c["source"] == "congress_gov"]
    switch(client, "congress_gov", True)
    switch(client, "officeholders", False)
    assert not [c for c in paxton(get_ballot(client))["cards"] if c["source"] == "congress_gov"]
    assert upstream.count("api.congress.gov") == 0


def test_a_refusal_leaves_the_ballot_with_a_warning(client, upstream):
    paxton_holds_the_seat(upstream)
    upstream.congress_gov_status = 429
    ballot = get_ballot(client)
    assert "Congress.gov isn't answering right now, so some members' bills aren't shown." in ballot["warnings"]
    assert not [c for c in paxton(ballot)["cards"] if c["source"] == "congress_gov"]
    assert paxton(ballot)["incumbent"]


def test_an_amendment_isnt_listed():
    bill = {"congress": 119, "number": "12", "type": "HR", "title": "A bill", "introducedDate": "2026-01-05"}
    assert congress_gov.bill_item(bill).url == "https://www.congress.gov/bill/119th-congress/house-bill/12"
    assert congress_gov.bill_item({"congress": 119, "amendmentNumber": "3", "type": None}) is None


@pytest.mark.anyio
async def test_its_answers_go_at_the_first_prune_once_expired(tmp_path):
    clock = Clock()
    async with httpx.AsyncClient() as client:
        cache = HttpCache(tmp_path / "c.sqlite3", client, clock=clock)
        for source in ("congress_gov", "fec"):
            cache._store(RequestSpec("GET", f"https://example.test/{source}"), source, {"x": 1}, clock.now, 10, None, ())
        assert prune(cache, Config(data_dir=tmp_path)) == 0  # still fresh
        clock.now += 11
        prune(cache, Config(data_dir=tmp_path))
        assert [cache.stats(s).entries for s in ("congress_gov", "fec")] == [0, 1]  # the FEC's stays, to show when it's down
