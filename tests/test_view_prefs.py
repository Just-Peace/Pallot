"""The view settings and picks kept in the voter's browser (view.js, picks.js): whether "What matters
to you?" still has to be asked. Run in Node, which loads the modules as the browser does, with a
stand-in for localStorage."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from pallot.api import STATIC_DIR

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")

PICKS = (STATIC_DIR / "js" / "picks.js").as_uri()
VIEW = (STATIC_DIR / "js" / "view.js").as_uri()
STORAGE = """
const store = new Map();
globalThis.localStorage = {
  getItem: (key) => (store.has(key) ? store.get(key) : null),
  setItem: (key, value) => store.set(key, String(value)),
  removeItem: (key) => store.delete(key),
};
"""


def _run(script: str):
    source = (f'{STORAGE}\nconst picks = await import("{PICKS}");\nconst view = await import("{VIEW}");\n'
              f"console.log(JSON.stringify(await (async () => {{ {script} }})()));")
    done = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_a_voter_with_a_pick_in_any_election_has_answered():
    assert _run("""
const before = picks.hasAnyPicks();
const p = new picks.Picks("2026-11-03");
p.setNote("c1", "maybe");
const noteOnly = picks.hasAnyPicks();
p.set("r1", ["c1"]);
return [before, noteOnly, picks.hasAnyPicks()];
""") == [False, False, True]


def test_the_question_counts_as_asked_once_dismissed():
    assert _run("""
const before = view.focusAsked();
view.dismissFocusAsk();
return [before, view.focusAsked()];
""") == [False, True]
