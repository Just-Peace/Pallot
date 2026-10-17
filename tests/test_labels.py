"""Districts in words, and how much of a state's ballot Pallot has (labels.js). Run in Node, which
loads the module as the browser does."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from pallot.api import STATIC_DIR

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")

MODULE = (STATIC_DIR / "js" / "labels.js").as_uri()


def _run(expression: str):
    source = f'const m = await import("{MODULE}");\nconsole.log(JSON.stringify({expression}));'
    done = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_an_at_large_seat_is_said_and_not_dropped():
    assert _run('m.districtLine({ cd: 0 }, { state: "WY" })') == "U.S. House At large"
    assert _run('m.districtLine({ cd: 0 }, { state: "DC" })') == "U.S. House Delegate (at large)"
    assert _run('m.districtLine({ cd: 10, sd: 14, jp: 5 }, { state: "TX" })') == "U.S. House 10 · State Senate 14 · JP 5"
    assert _run("m.houseText(null, \"GA\")") is None


def test_a_ballot_from_before_coverage_is_texas_s():
    assert _run("m.coverageOf({}).districts") == ["cd", "sd", "hd", "sboe"]
    assert _run('m.coverageOf({ coverage: { ballot: "fec", districts: ["cd"] } }).ballot') == "fec"
