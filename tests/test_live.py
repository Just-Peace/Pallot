"""Smoke test against the real services: python -m pytest -m live"""

from __future__ import annotations

import csv

import httpx
import pytest
from fastapi.testclient import TestClient

from tec_cache.models import ZIP_URL
from tec_cache.parse import REQUIRED, lines
from tec_cache.remote_zip import RemoteZip
from votebot.api import create_app
from votebot.config import DEMO_KEY, Config, load_config
from votebot.sources import fec, key_dates, polls
from votebot.sources.sboe import _inside

pytestmark = [pytest.mark.live, pytest.mark.xdist_group("live")]  # one worker, so one call at a time
FEC_KEY = load_config().fec_api_key  # from the environment or .env


def test_capitol_ballot_live(tmp_path):
    with TestClient(create_app(Config(data_dir=tmp_path / "data", fec_api_key=FEC_KEY, allowed_hosts=("testserver",)))) as client:
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
