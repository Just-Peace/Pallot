"""What the ballot page and the print sheet share (ballot-shared.js): the short election line a phone
shows under "Your ballot". Run in Node, which loads the module as the browser does."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from pallot.api import STATIC_DIR

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")

MODULE = (STATIC_DIR / "js" / "ballot-shared.js").as_uri()


def _short(ballot: dict) -> str:
    source = f'const m = await import("{MODULE}");\nconsole.log(JSON.stringify(m.shortElectionLine({json.dumps(ballot)})));'
    done = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_the_short_line_drops_the_year_and_month_the_date_gives():
    ballot = {"election_date": "2026-11-03", "elections": [{"name": "2026 November General Election"}]}
    assert _short(ballot) == "Nov 3 · General Election"


def test_the_short_line_joins_elections_held_together():
    ballot = {"election_date": "2026-03-03", "elections": [{"name": "2026 Republican Primary"}, {"name": "2026 Democratic Primary"}]}
    assert _short(ballot) == "Mar 3 · Republican Primary + Democratic Primary"


def test_a_name_with_nothing_but_a_date_is_kept_whole():
    assert _short({"election_date": None, "elections": [{"name": "November 2026"}]}) == "November 2026"
