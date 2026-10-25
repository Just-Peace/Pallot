"""Smoke test against the real services: python -m pytest -m live"""

from __future__ import annotations

import csv
import datetime as dt
import os
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from tec_cache.models import ZIP_URL
from tec_cache.parse import REQUIRED, lines
from tec_cache.remote_zip import RemoteZip
from pallot.api import create_app
from pallot.services import MIN_INTERVAL
from pallot.config import DEMO_KEY, Config, Ttls, load_config
from pallot.http_cache import HttpCache, track_calls
from pallot.sources import ca_key_dates, fec, key_dates, officeholders, polls, wikidata
from pallot.sources.county_precincts import COUNTIES, CountyPrecincts
from pallot.sources.election_precincts import ElectionPrecincts, read_dbf
from pallot.sources.endorsement_feeds import make_feeds
from pallot.sources.sboe import _inside
from pallot import counties
from pallot.states.ak import AkList
from pallot.states.ca import CaList
from pallot.states.co import CoList
from pallot.states.ga import GaList
from pallot.states.nj import NjList

from .conftest import census_points, switch

pytestmark = [pytest.mark.live, pytest.mark.xdist_group("live")]  # one worker, so one call at a time
FEC_KEY = load_config().fec_api_key  # from the environment or .env


@pytest.fixture(scope="module")
def precinct_map_dir(tmp_path_factory) -> Path:
    """One folder for the Texas Legislative Council's precinct map, so these tests download it once."""
    return tmp_path_factory.mktemp("election_precincts")


def test_capitol_ballot_live(tmp_path, logged_calls):
    with TestClient(create_app(Config(data_dir=tmp_path / "data", fec_api_key=FEC_KEY, allowed_hosts=("testserver",)))) as client:
        switch(client, "election_precincts", False)  # its own test downloads the map, once
        response = client.post("/api/ballot", json={"address": "1100 Congress Ave, Austin, TX 78701"})
        assert response.status_code == 200, response.text
        ballot = response.json()
        client.post("/api/ballot", json={"address": "1100 Congress Ave, Austin, TX 78701"})

    d = ballot["districts"]
    assert (d["cd"], d["hd"], d["sboe"]) == (10, 49, 5)
    names = [r["name"] for r in ballot["races"]]
    assert "U.S. Senator" in names and "U.S. Representative District 10" in names
    assert logged_calls("district outlines") == 0


@pytest.mark.skipif(FEC_KEY == DEMO_KEY, reason="needs PALLOT_FEC_API_KEY (DEMO_KEY runs out fast)")
def test_fec_race_totals_live():
    response = httpx.get(
        f"{fec.API}/elections/",
        params={"office": "senate", "state": "TX", "cycle": "2026", "election_full": "true", "per_page": "100"},
        headers={"X-Api-Key": FEC_KEY},
        timeout=60,
    )
    response.raise_for_status()
    rows = response.json()["results"]
    assert rows and {"candidate_id", "candidate_name", "candidate_pcc_id", "total_receipts",
                     "cash_on_hand_end_period", "coverage_end_date"} <= set(rows[0])


def test_tec_export_still_has_what_we_read():
    """Two requests, since TEC blocks bursts: the zip's directory, then filers.csv's header."""
    with RemoteZip(ZIP_URL, pause=5) as remote:
        members = remote.directory().members
        assert {"filers.csv", "cover.csv", "cand.csv"} <= set(members)
        assert any(name.startswith("contribs_") for name in members)
        for _member, chunks in remote.read(["filers.csv"]):
            header = next(csv.reader(lines(chunks)))
            break
    assert set(REQUIRED["filers"]) <= set(header)


def test_suggestions_live(tmp_path):
    """Google's Places Autocomplete suggests addresses in and outside Texas (needs PALLOT_GOOGLE_API_KEY)."""
    key = os.environ.get("PALLOT_GOOGLE_API_KEY", "").strip()
    if not key:
        pytest.skip("needs PALLOT_GOOGLE_API_KEY")
    config = Config(data_dir=tmp_path / "data", allowed_hosts=("testserver",), google_api_key=key)
    with TestClient(create_app(config)) as client:
        houston = client.get("/api/suggest", params={"q": "1001 preston st houston"}).json()
        harrisburg = client.get("/api/suggest", params={"q": "501 n 3rd st harrisburg"}).json()
    assert houston["enabled"] and any("Preston" in s["label"] and "Houston" in s["label"] for s in houston["suggestions"])
    assert any(s["label"].endswith("Harrisburg, PA") for s in harrisburg["suggestions"])


def test_polls_live():
    """FiftyPlusOne still answers a browser's User-Agent, in the shape polls.py reads."""
    response = httpx.get(polls.API, headers=polls.HEADERS, timeout=60, params={
        "offset": "0", "limit": str(polls.PAGE), "filterValue": polls.SENATE, "sortBy": "created_at", "dir": "DESC"})
    response.raise_for_status()
    texas = polls.of_state(response.json()["data"], "TX")
    assert texas and texas[0]["pollster_id"] and texas[0]["end_date"]
    answers = [a for row in texas for q in row["questions"] for a in q["answers"]]
    assert any(a["candidate"]["name"] and isinstance(a["pct"], (int, float)) for a in answers)


def test_officeholders_live():
    """Both lists of seat holders still come in the shape officeholders.py reads: every Texas seat, near enough."""
    response = httpx.get(officeholders.CONGRESS, timeout=60, follow_redirects=True)
    response.raise_for_status()
    congress = officeholders.congress_holders(response.json(), "TX")
    assert len([h for h in congress if h.seat == "TX-SEN"]) == 2 and len(congress) >= 36
    assert all(h.party and h.started and h.ends for h in congress)
    response = httpx.get(officeholders.LEGISLATURE.format(state="tx"), timeout=60, follow_redirects=True)
    response.raise_for_status()
    legislature = officeholders.legislature_holders(response.text)
    assert len([h for h in legislature if h.seat.startswith("STATESEN:")]) >= 28
    assert len([h for h in legislature if h.seat.startswith("STATEREP:")]) >= 140
    assert all(h.party for h in legislature)


def test_wikidata_live():
    """Wikidata's query service still lists Texas's officeholders with their seats, and their details."""
    agent = {"User-Agent": Config.user_agent}
    spec = wikidata.people_spec()
    response = httpx.get(spec.url, params=spec.params, headers={**spec.headers, **agent}, timeout=90)
    response.raise_for_status()
    people = wikidata.people_from(response.json())
    assert len(people) >= 400
    seats = {seat for person in people for seat in person.seats}
    assert "TX-SEN" in seats and "GOVERNOR" in seats and len([s for s in seats if s.startswith("TX-")]) >= 30
    spec = wikidata.details_spec(["Q5605224"])
    response = httpx.get(spec.url, params=spec.params, headers={**spec.headers, **agent}, timeout=60)
    response.raise_for_status()
    abbott = wikidata.details_from(response.json())["Q5605224"]
    assert abbott.photo and abbott.article and abbott.party


def test_key_dates_live():
    """The Texas SOS's Important Election Dates page still parses into elections with deadlines."""
    response = httpx.get(key_dates.URL, timeout=60, follow_redirects=True)
    response.raise_for_status()
    found = key_dates.parse(response.text)
    assert found and all(d.register_by and d.register_by < d.day for d in found)
    assert any(d.early_start and d.early_end and d.mail_apply_by for d in found)


def test_california_key_dates_live():
    """The California SOS's election dates page still answers scripts and parses into elections with deadlines."""
    response = httpx.get(ca_key_dates.URL, headers={"User-Agent": Config.user_agent}, timeout=60, follow_redirects=True)
    response.raise_for_status()
    found = ca_key_dates.parse(response.text)
    assert found and all(d.register_by and d.register_by < d.day for d in found)


def test_district_outlines_live(tmp_path, logged_calls):
    """TIGERweb still names its layers as the geocoder does, and the Capitol's districts come back
    as rings around it; asked again, from the cache."""
    with TestClient(create_app(Config(data_dir=tmp_path / "data", allowed_hosts=("testserver",)))) as client:
        params = {"cd": 10, "sd": 14, "hd": 49, "sboe": 5}
        got = client.get("/api/district-outlines", params=params).json()
        client.get("/api/district-outlines", params=params)
    assert [o["kind"] for o in got["outlines"]] == ["cd", "sd", "hd", "sboe"] and got["notes"] == []
    lat, lon = 30.27644, -97.73975  # the Capitol, as the Census places it
    assert all(sum(_inside(lon, lat, ring) for ring in o["rings"]) % 2 for o in got["outlines"])
    assert logged_calls() == 0


def test_street_map_tile_live(tmp_path):
    """One OpenStreetMap tile over Austin, through Pallot, which OpenStreetMap still serves to
    Pallot's User-Agent; asked again, from the cache."""
    with TestClient(create_app(Config(data_dir=tmp_path / "data", allowed_hosts=("testserver",)))) as client:
        first = client.get("/api/tiles/12/935/1686.png")
        again = client.get("/api/tiles/12/935/1686.png")
        cached = client.app.state.svc.cache.stats("osm_tiles").entries
    assert first.status_code == 200, first.text
    assert first.content.startswith(b"\x89PNG") and again.content == first.content
    assert cached == 1


@pytest.mark.anyio
async def test_election_precincts_live(tmp_path, precinct_map_dir):
    """The Texas Legislative Council's portal still lists its precinct maps, and the newest one (a
    single download, about 45 MB) reads as Pallot expects: the recorded addresses land in their
    precincts, every precinct's code fits the outlines API, and a second lookup asks nothing."""
    async with httpx.AsyncClient(headers={"User-Agent": load_config().user_agent}, follow_redirects=True,
                                 timeout=60) as client:
        cache = HttpCache(tmp_path / "cache.sqlite3", client)
        precincts = ElectionPrecincts(cache, Ttls(), precinct_map_dir, first_wait=600)
        try:
            found = {name: (await precincts.at(county, *census_points(name))).found
                     for name, county in (("capitol", 453), ("ut", 453), ("harris", 201))}
            stats = track_calls()
            again = await precincts.at(453, *census_points("capitol"))
            stored = precincts.stored()
            codes = [row[1] for row in read_dbf(stored.file(precincts.folder, "dbf")) if row]
            outline = await precincts.outline(453, found["capitol"].code)
        finally:
            await precincts.aclose()
            cache.close()
    assert {name: f.name for name, f in found.items()} == {"capitol": "300", "ut": "312", "harris": "890"}
    assert again.found == found["capitol"]
    assert stats.external_calls == 0 and stored.resource.label.endswith("Voting Precincts")
    assert len(codes) > 9000 and all(1 <= len(code) <= 16 for code in codes)  # the outlines API's limit
    lat, lon = census_points("capitol")[0]
    assert sum(_inside(lon, lat, ring) for ring in outline) % 2


@pytest.mark.anyio
async def test_california_list_live(tmp_path):
    """California's certified list (one 14 MB PDF) still reads whole: every U.S. House race, the
    Legislature's and the courts' retention, kept as its candidates alone; asked again, from the cache."""
    async with httpx.AsyncClient(headers={"User-Agent": load_config().user_agent}, follow_redirects=True,
                                 timeout=120) as client:
        cache = HttpCache(tmp_path / "cache.sqlite3", client, min_interval=dict(MIN_INTERVAL))
        lists = CaList(cache, Ttls())
        day = fec.general_day(dt.date.today())
        try:
            found = await lists.filings(day)
            stats = track_calls()
            again = await lists.filings(day)
        finally:
            cache.close()
    assert found and again == found and stats.external_calls == 0
    reaches = {reach: len({f.office_id for f in found if f.reach == reach}) for reach in ("cd", "sd", "hd", "counties")}
    assert reaches["cd"] == 52 and reaches["sd"] >= 19 and reaches["hd"] == 80 and reaches["counties"] >= 30
    assert {county for f in found for county in f.counties} == {c.name.upper() for c in counties.counties("CA")}
    assert not list(tmp_path.glob(".*.part"))


@pytest.mark.anyio
async def test_colorado_list_live(tmp_path):
    """Colorado's spreadsheet is still where the year's URL says and reads whole: every House
    district and the Governors' tickets, kept as its candidates alone; asked again, from the cache."""
    async with httpx.AsyncClient(headers={"User-Agent": load_config().user_agent}, follow_redirects=True,
                                 timeout=120) as client:
        cache = HttpCache(tmp_path / "cache.sqlite3", client, min_interval=dict(MIN_INTERVAL))
        lists = CoList(cache, Ttls())
        day = fec.general_day(dt.date.today())
        try:
            found = await lists.filings(day)
            stats = track_calls()
            again = await lists.filings(day)
        finally:
            cache.close()
    assert found and again == found and stats.external_calls == 0
    assert {f.district for f in found if f.family == "US HOUSE"} == {str(n) for n in range(1, 9)}
    assert any(f.family == "GOVERNOR" and " and " in f.name for f in found)
    assert not list(tmp_path.glob(".*.part"))

@pytest.mark.anyio
async def test_new_jersey_lists_live(tmp_path):
    """New Jersey's page still links its official U.S. Senate and House lists, and they read whole:
    every House district, kept as their candidates and the page's links alone; asked again, from the cache."""
    async with httpx.AsyncClient(headers={"User-Agent": load_config().user_agent}, follow_redirects=True,
                                 timeout=120) as client:
        cache = HttpCache(tmp_path / "cache.sqlite3", client, min_interval=dict(MIN_INTERVAL))
        lists = NjList(cache, Ttls())
        day = fec.general_day(dt.date.today())
        try:
            found = await lists.filings(day)
            stats = track_calls()
            again = await lists.filings(day)
        finally:
            cache.close()
    assert found and again == found and stats.external_calls == 0
    assert {f.district for f in found if f.reach == "cd"} == {str(n) for n in range(1, 13)}
    assert not list(tmp_path.glob(".*.part"))


@pytest.mark.anyio
async def test_alaska_list_live(tmp_path):
    """Alaska's server still needs the intermediate Pallot ships, and its list reads whole through
    it: the at-large House race and every State House district, kept as its candidates and its
    pages' links alone; asked again, from the cache."""
    async with httpx.AsyncClient(headers={"User-Agent": load_config().user_agent}, follow_redirects=True,
                                 timeout=120) as client:
        cache = HttpCache(tmp_path / "cache.sqlite3", client, min_interval=dict(MIN_INTERVAL))
        lists = AkList(cache, Ttls())
        day = fec.general_day(dt.date.today())
        try:
            found = await lists.filings(day)
            stats = track_calls()
            again = await lists.filings(day)
        finally:
            await cache.aclose()
    assert found and again == found and stats.external_calls == 0
    assert {f.district for f in found if f.reach == "cd"} == {"0"}
    assert {f.district for f in found if f.reach == "hd"} == {str(n) for n in range(1, 41)}
    assert {f.reach for f in found if f.group == "judicial"} <= {"state", "counties"}
    assert not list(tmp_path.glob(".*.part"))


@pytest.mark.anyio
async def test_georgia_nominees_live(tmp_path):
    """Georgia's results site still answers scripts and reads as Pallot expects: a nominee of each
    party for U.S. Senate, every U.S. House district with one, from the results site alone (never
    the qualifying site); asked again, from the cache."""
    async with httpx.AsyncClient(headers={"User-Agent": load_config().user_agent}, follow_redirects=True,
                                 timeout=120) as client:
        cache = HttpCache(tmp_path / "cache.sqlite3", client, min_interval=dict(MIN_INTERVAL))
        lists = GaList(cache, Ttls())
        day = fec.general_day(dt.date.today())
        try:
            found = await lists.nominees(day)
            stats = track_calls()
            again = await lists.nominees(day)
        finally:
            cache.close()
    assert found and again == found and stats.external_calls == 0
    assert {f.party for f in found if f.office_id == "US SENATE"} == {"R", "D"}
    assert {f.district for f in found if f.reach == "cd"} == {str(n) for n in range(1, 15)}
    assert len({f.office_id for f in found if f.reach == "hd"}) > 150


@pytest.mark.anyio
async def test_county_precincts_live(tmp_path, precinct_map_dir):
    """Each county's records are still found by name and read as Pallot expects, against the
    precinct map: a list of exactly the map's precincts, or maps that settle most of a sample of
    them, 20 spread through the county; asked again, from the cache."""
    async with httpx.AsyncClient(headers={"User-Agent": load_config().user_agent}, follow_redirects=True,
                                 timeout=60) as client:
        cache = HttpCache(tmp_path / "cache.sqlite3", client, min_interval=dict(MIN_INTERVAL))
        precincts = ElectionPrecincts(cache, Ttls(), precinct_map_dir, first_wait=600)
        counties = CountyPrecincts(cache, Ttls(), precincts)
        try:
            await precincts.at(453, *census_points("capitol"))  # the map, unless the test above kept it
            settled, samples = {}, {}
            for fips, county in COUNTIES.items():
                codes = sorted(await precincts.codes(fips))
                samples[fips] = codes[::max(1, len(codes) // 20)][:20]
                kinds = 1 if county.table and not county.table.jp else 2  # Fort Bend's list has no JP precincts
                found = [await counties.at(fips, (code,)) for code in samples[fips]]
                settled[county.name] = (sum(len(f.numbers) == kinds for f in found), county.method)
            stats = track_calls()
            for fips, sample in samples.items():
                await counties.at(fips, (sample[0],))
        finally:
            await precincts.aclose()
            cache.close()
    assert all(n == 20 if method == "table" else n >= 15 for n, method in settled.values()), settled  # maps: most
    assert stats.external_calls == 0


@pytest.mark.anyio
async def test_endorsement_feeds_live(tmp_path):
    """Each organization's feed still answers in the shape its adapter reads, every candidate it
    gives passes as a file's would, and a second fetch comes from the cache."""
    async with httpx.AsyncClient(headers={"User-Agent": load_config().user_agent}, follow_redirects=True,
                                 timeout=60) as client:
        cache = HttpCache(tmp_path / "cache.sqlite3", client, min_interval=dict(MIN_INTERVAL))
        try:
            for feed in make_feeds(cache, Ttls()):
                found = await feed.fetch()
                assert found.entries and len(found.entries) == len(feed.feed.read(cache.peek(feed.spec).value)), feed.source
                stats = track_calls()
                await feed.fetch()
                assert stats.external_calls == 0
        finally:
            cache.close()
