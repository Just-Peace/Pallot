"""Smoke test against the real services: python -m pytest -m live"""

from __future__ import annotations

import csv
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from tec_cache.models import ZIP_URL
from tec_cache.parse import REQUIRED, lines
from tec_cache.remote_zip import RemoteZip
from votebot.api import MIN_INTERVAL, create_app
from votebot.config import DEMO_KEY, Config, Ttls, load_config
from votebot.http_cache import HttpCache, track_calls
from votebot.sources import fec, key_dates, polls
from votebot.sources.county_precincts import COUNTIES, CountyPrecincts
from votebot.sources.election_precincts import ElectionPrecincts, read_dbf
from votebot.sources.sboe import _inside

from .conftest import census_points

pytestmark = [pytest.mark.live, pytest.mark.xdist_group("live")]  # one worker, so one call at a time
FEC_KEY = load_config().fec_api_key  # from the environment or .env


@pytest.fixture(scope="module")
def precinct_map_dir(tmp_path_factory) -> Path:
    """One folder for the Texas Legislative Council's precinct map, so these tests download it once."""
    return tmp_path_factory.mktemp("election_precincts")


def test_capitol_ballot_live(tmp_path):
    with TestClient(create_app(Config(data_dir=tmp_path / "data", fec_api_key=FEC_KEY, allowed_hosts=("testserver",)))) as client:
        client.put("/api/sources/election_precincts", json={"enabled": False})  # its own test downloads the map, once
        response = client.post("/api/ballot", json={"address": "1100 Congress Ave, Austin, TX 78701"})
        assert response.status_code == 200, response.text
        ballot = response.json()
        again = client.post("/api/ballot", json={"address": "1100 Congress Ave, Austin, TX 78701"}).json()

    d = ballot["districts"]
    assert (d["cd"], d["hd"], d["sboe"]) == (10, 49, 5)
    names = [r["name"] for r in ballot["races"]]
    assert "U.S. Senator" in names and "U.S. Representative District 10" in names
    assert again["meta"]["external_calls"] == 0


@pytest.mark.skipif(FEC_KEY == DEMO_KEY, reason="needs VOTEBOT_FEC_API_KEY (DEMO_KEY runs out fast)")
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


def test_photon_suggestions_live(tmp_path):
    with TestClient(create_app(Config(data_dir=tmp_path / "data", allowed_hosts=("testserver",)))) as client:
        found = client.get("/api/suggest", params={"q": "1001 preston st houston"}).json()
    assert found["enabled"] and any("Preston" in s["label"] and "Houston" in s["label"] for s in found["suggestions"])


def test_polls_live():
    """FiftyPlusOne still answers a browser's User-Agent, in the shape polls.py reads."""
    response = httpx.get(polls.API, headers=polls.HEADERS, timeout=60, params={
        "offset": "0", "limit": str(polls.PAGE), "filterValue": polls.SENATE, "sortBy": "created_at", "dir": "DESC"})
    response.raise_for_status()
    texas = [row for row in response.json()["data"] if row.get("state") == polls.STATE]
    assert texas and texas[0]["pollster_id"] and texas[0]["end_date"]
    answers = [a for row in texas for q in row["questions"] for a in q["answers"]]
    assert any(a["candidate"]["name"] and isinstance(a["pct"], (int, float)) for a in answers)


def test_key_dates_live():
    """The Texas SOS's Important Election Dates page still parses into elections with deadlines."""
    response = httpx.get(key_dates.URL, timeout=60, follow_redirects=True)
    response.raise_for_status()
    found = key_dates.parse(response.text)
    assert found and all(d.register_by and d.register_by < d.day for d in found)
    assert any(d.early_start and d.early_end and d.mail_apply_by for d in found)


def test_district_outlines_live(tmp_path):
    """TIGERweb still names its layers as the geocoder does, and the Capitol's districts come back
    as rings around it; asked again, from the cache."""
    with TestClient(create_app(Config(data_dir=tmp_path / "data", allowed_hosts=("testserver",)))) as client:
        params = {"cd": 10, "sd": 14, "hd": 49, "sboe": 5}
        got = client.get("/api/district-outlines", params=params).json()
        again = client.get("/api/district-outlines", params=params).json()
    assert [o["kind"] for o in got["outlines"]] == ["cd", "sd", "hd", "sboe"] and got["notes"] == []
    lat, lon = 30.27644, -97.73975  # the Capitol, as the Census places it
    assert all(sum(_inside(lon, lat, ring) for ring in o["rings"]) % 2 for o in got["outlines"])
    assert again["meta"]["external_calls"] == 0


def test_street_map_tile_live(tmp_path):
    """One OpenStreetMap tile over Austin, through VoteBot, which OpenStreetMap still serves to
    VoteBot's User-Agent; asked again, from the cache."""
    with TestClient(create_app(Config(data_dir=tmp_path / "data", allowed_hosts=("testserver",)))) as client:
        first = client.get("/api/tiles/12/935/1686.png")
        again = client.get("/api/tiles/12/935/1686.png")
        cached = client.get("/api/sources").json()["sources"]
    assert first.status_code == 200, first.text
    assert first.content.startswith(b"\x89PNG") and again.content == first.content
    assert next(s for s in cached if s["id"] == "osm_tiles")["cache"]["entries"] == 1


@pytest.mark.anyio
async def test_election_precincts_live(tmp_path, precinct_map_dir):
    """The Texas Legislative Council's portal still lists its precinct maps, and the newest one (a
    single download, about 45 MB) reads as VoteBot expects: the recorded addresses land in their
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
async def test_county_precincts_live(tmp_path, precinct_map_dir):
    """Each county's records are still found by name and read as VoteBot expects, against the
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
