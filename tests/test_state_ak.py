"""Alaska's ballot (states/ak.py), from the Division of Elections' list of candidates, three pages
found by their links, asked through a client that trusts the intermediate its server leaves out,
and its key dates worked out from the Alaska Statutes. tests/fixtures/state_ak_*.html are those
pages without the candidates' contact details (scripts/record_fixtures.py)."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.http_cache import HttpCache
from pallot.states import district_key
from pallot.states import key_dates as state_key_dates
from pallot.states import ak
from pallot.states.ak import AkList

from .bundling import build
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch

HOST = "www.elections.alaska.gov"


def page(number: int | str) -> str:
    return (FIXTURES / f"state_ak_{number}.html").read_text(encoding="utf-8")


def whole_list() -> list:
    found = [f for n in (1, 2, 3) for f in AkList.parse(page(n))]
    return list({(f.office_id, f.name): f for f in found}.values())


def without_races(text: str, pattern: str) -> str:
    return re.sub(rf'<section class="candidates-table"><h4><a id="[^"]*"></a>{pattern}</h4>.*?</section>', "", text,
                  flags=re.S)


def test_the_first_page_links_the_others_and_a_year_without_a_list_has_none():
    assert ak.read_page(page(1))["pages"] == [
        "https://www.elections.alaska.gov/candidates/?election=26genr&frm-page-407=2",
        "https://www.elections.alaska.gov/candidates/?election=26genr&frm-page-407=3",
    ]
    assert AkList.spec(None, dt.date(2028, 11, 7)).url == "https://www.elections.alaska.gov/candidates/?election=28genr"
    assert ak.read_page(page("none")) == {"filings": [], "pages": []}


def test_alaskas_list_has_its_races_parties_write_ins_and_retention_questions():
    found = whole_list()
    races = Counter(f.reach for f in {f.office_id: f for f in found}.values())
    assert races == {"state": 3, "cd": 1, "sd": 10, "hd": 40, "counties": 20}
    assert {f.day for f in found} == {"2026-11-03"}
    governor = [(f.name, f.party, f.party_name, f.write_in) for f in found if f.office_id == "GOVERNOR"]
    assert governor[:3] == [("Dave Bronson and Josh Church", "R", None, False),
                            ("Meda DeWitt and Christopher “Chris” Steere", None, "Nonpartisan", True),
                            ("Jonathan S. “JKT” Kreiss-Tomkins and Zac Johnson", None, "Democrat / Nonpartisan", False)]
    assert ("Treg Taylor and Candi English", "R", None, False) in governor
    senate = {f.name: f for f in found if f.office_id == "US SENATE"}
    assert senate["Dan S. Sullivan"].incumbent and senate["Mary Peltola"].party == "D"
    assert senate["Daniel J. Sullivan Jr."].party == "R" and senate["Sidney “Sid” Hill"].party_name == "Undeclared"
    house = [f for f in found if f.reach == "cd"]
    assert {(f.district, f.office) for f in house} == {("0", "U.S. Representative At Large")}
    assert {f.district for f in found if f.reach == "sd"} == set("ACEGIKMOQS")
    assert {f.district for f in found if f.reach == "hd"} == {str(n) for n in range(1, 41)}
    tobin = next(f for f in found if f.reach == "sd" and f.district == "I")
    assert (tobin.name, tobin.office, tobin.party, tobin.incumbent) == ("Löki Gale Tobin", "State Senator District I", "D", True)
    judges = [f for f in found if f.group == "judicial"]
    assert len(judges) == 21 and all(f.incumbent and f.party is None for f in judges)
    pate = next(f for f in judges if f.reach == "state")
    assert pate.office == "Retain Supreme Court Justice Jude Pate"
    hartz = next(f for f in judges if f.name == "Laura Hartz")
    assert (hartz.office, hartz.district, "ANCHORAGE" in hartz.counties) == (
        "Retain Superior Court Judge Laura Hartz, 3rd Judicial District", "3", True)
    assert district_key("SENATE DISTRICT I") == district_key("I")


def test_a_page_that_isnt_the_list_or_has_a_race_or_row_it_cant_read_is_refused():
    with pytest.raises(ValueError, match="not the Division of Elections"):
        AkList.parse("<html><body>Service Unavailable</body></html>")
    with pytest.raises(ValueError, match="a race it doesn't know: BOROUGH ASSEMBLY"):
        AkList.parse(page(1).replace("SENATE DISTRICT A</h4>", "BOROUGH ASSEMBLY</h4>"))
    with pytest.raises(ValueError, match="no status for"):
        AkList.parse(page(1).replace("(Registered Republican) (Certified)", "", 1))
    withdrawn = AkList.parse(page(1).replace("(Registered Republican) (Certified)", "(Registered Republican) (Withdrawn)", 1))
    assert "Dave Bronson and Josh Church" not in {f.name for f in withdrawn}
    with pytest.raises(ValueError, match="no U.S. House race"):
        ak.whole([f for f in whole_list() if f.reach != "cd"])
    with pytest.raises(ValueError, match="39 State House races, not 40"):
        ak.whole([f for f in whole_list() if f.district != "40"])


def test_an_anchorage_ballot_has_its_races_from_the_list(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "anchorage")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (0, "I", 17)
    names = [race["name"] for race in ballot["races"]]
    assert names[:5] == ["U.S. Senator", "U.S. Representative At Large", "Governor and Lieutenant Governor",
                         "State Senator District I", "State Representative District 17"]
    assert "Retain Supreme Court Justice Jude Pate" in names and "Retain Superior Court Judge Laura Hartz, 3rd Judicial District" in names
    assert not any("4th Judicial District" in name for name in names)
    senate, house = ballot["races"][:2]
    assert senate["source"] == house["source"] == "state_ak" and (senate["seat"], house["seat"]) == ("AK-SEN", "AK-00")
    assert "Nick Begich" in candidate_names(house) and "Mary Peltola" in candidate_names(senate)
    assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
    assert any(card["source"] == "fec" and card["kind"] == "money"
               for race in (senate, house) for c in race["candidates"] for card in c["cards"])
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-04",
        "mail_apply_by": "2026-10-24", "early_voting_start": "2026-10-19", "early_voting_end": None,
        "source": "Alaska Division of Elections", "source_url": "https://www.elections.alaska.gov/", "computed": True,
    }
    assert upstream.count(HOST) == 3
    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        kept = [value for (value,) in db.execute("SELECT value FROM responses WHERE source = 'state_ak'")]
    assert sorted(sorted(json.loads(value)) for value in kept) == [["filings", "pages"]] * 3
    assert not any(re.search(r"PO Box|@|\(907\)", value) for value in kept)
    get_ballot(client, "anchorage")
    assert logged_calls() == 0 and upstream.count(HOST) == 3


def test_an_alaska_page_it_cant_read_or_a_list_short_of_a_race_leaves_the_fecs_races(client, upstream):
    upstream.state_lists[f"{HOST}#2"] = "<html><body>Service Unavailable</body></html>"
    ballot = get_ballot(client, "anchorage")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative At Large")
    assert any("Couldn't load the list of candidates from the Alaska Division of Elections" in w for w in ballot["warnings"])


def test_a_list_without_every_house_district_leaves_the_fecs_races(client, upstream):
    upstream.state_lists[f"{HOST}#3"] = without_races(page(3), "HOUSE DISTRICT 40")
    ballot = get_ballot(client, "anchorage")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Alaska Division of Elections" in w for w in ballot["warnings"])


def test_with_alaskas_list_off_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_ak", False)
    ballot = get_ballot(client, "anchorage")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative At Large")
    assert upstream.count(HOST) == 0


def test_alaskas_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_ak")
    assert outcome.status == "updated" and outcome.answers == 3
    assert outcome.counts == {"races": 74, "candidates": 155}
    text = (tmp_path / "bundles" / "state_ak.json").read_text(encoding="utf-8")
    assert not re.search(r"PO Box|@|\(907\)", text) and upstream.count(HOST) == 3
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "anchorage")
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(HOST) == 3


@pytest.mark.anyio
async def test_alaskas_list_is_asked_through_a_client_that_trusts_its_missing_intermediate(tmp_path):
    import httpx

    from pallot.config import Ttls

    async with httpx.AsyncClient() as client:
        cache = HttpCache(tmp_path / "cache.sqlite3", client)
        AkList(cache, Ttls())
        trusted = cache._client_of("state_ak")
        assert trusted is not client and cache._client_of("state_nj") is client
        await cache.aclose()
    assert trusted.is_closed


@pytest.mark.parametrize("day, register, apply, early", [
    (dt.date(2026, 11, 3), dt.date(2026, 10, 4), dt.date(2026, 10, 24), dt.date(2026, 10, 19)),
    (dt.date(2028, 11, 7), dt.date(2028, 10, 8), dt.date(2028, 10, 28), dt.date(2028, 10, 23)),
])
def test_alaskas_key_dates_are_worked_out_from_its_statutes(day, register, apply, early):
    found = state_key_dates.computed("AK", day)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end, found.state) == (
        register, apply, early, None, "AK")
    assert state_key_dates.computed("AK", dt.date(2027, 11, 2)) is None


def test_alaskas_calendar_file_has_its_dates(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "AK"})
    assert response.status_code == 200 and "alaska-election-2026-11-03.ics" in response.headers["content-disposition"]
    text = response.text.replace("\r\n ", "")
    assert "Polls are open 7 a.m. to 8 p.m." in text and "20261004" in text
