"""When to vote in a line, for a phone (key-dates.js). Run in Node, which loads the module as the
browser does."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from pallot.api import STATIC_DIR

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")

MODULE = (STATIC_DIR / "js" / "key-dates.js").as_uri()


def _summary(dates) -> str:
    source = (f'const m = await import("{MODULE}");\n'
              f"console.log(JSON.stringify(m.keyDatesSummary({{ key_dates: {json.dumps(dates)} }})));")
    env = {**os.environ, "TZ": "America/Chicago", "LANG": "en_US.UTF-8"}
    done = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, check=True, env=env)
    return json.loads(done.stdout)


def test_early_voting_and_election_day_in_a_line():
    dates = {"early_voting_start": "2099-10-19", "early_voting_end": "2099-10-30", "election_day": "2099-11-03"}
    assert _summary(dates) == "Early voting Oct 19–30 · Election Day Nov 3"


def test_early_voting_across_two_months():
    dates = {"early_voting_start": "2099-10-30", "early_voting_end": "2099-11-02", "election_day": "2099-11-05"}
    assert _summary(dates) == "Early voting Oct 30 – Nov 2 · Election Day Nov 5"


def test_early_voting_goes_once_its_over():
    dates = {"early_voting_start": "2000-10-19", "early_voting_end": "2000-10-30", "election_day": "2099-11-03"}
    assert _summary(dates) == "Election Day Nov 3"


def test_early_voting_through_election_day_says_from_and_stays_until_then():
    dates = {"early_voting_start": "2000-10-19", "early_voting_end": None, "election_day": "2099-11-03"}
    assert _summary(dates) == "Early voting from Oct 19 · Election Day Nov 3"


def test_no_dates():
    assert _summary(None) == "Registration and where to vote"
