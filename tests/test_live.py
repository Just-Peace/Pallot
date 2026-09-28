"""Smoke test against the real services: python -m pytest -m live"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from votebot.api import create_app
from votebot.config import Config

pytestmark = pytest.mark.live


def test_capitol_ballot_live(tmp_path):
    with TestClient(create_app(Config(data_dir=tmp_path / "data"))) as client:
        response = client.post("/api/ballot", json={"address": "1100 Congress Ave, Austin, TX 78701"})
        assert response.status_code == 200, response.text
        ballot = response.json()
        again = client.post("/api/ballot", json={"address": "1100 Congress Ave, Austin, TX 78701"}).json()

    d = ballot["districts"]
    assert (d["cd"], d["hd"], d["sboe"]) == (10, 49, 5)
    names = [r["name"] for r in ballot["races"]]
    assert "U.S. Senator" in names and "U.S. Representative District 10" in names
    assert again["meta"]["external_calls"] == 0
