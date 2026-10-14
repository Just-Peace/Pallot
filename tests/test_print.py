"""The print sheet (print.js): which races it prints and the notes it puts beside them. Run in Node,
which loads the module as the browser does."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from pallot.api import STATIC_DIR

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")

MODULE = (STATIC_DIR / "js" / "print.js").as_uri()
SETUP = """
const ballot = { maybe: [], measures: [], races: [
  { key: "r1", name: "U.S. Senate", group: "federal", seats: 1, candidates: [
    { key: "a", name: "Ann Lee", party: "D", cards: [] },
    { key: "b", name: "Bob Ray", party: "R", cards: [] },
  ] },
  { key: "r2", name: "Governor", group: "state", seats: 1, candidates: [{ key: "c", name: "Cy Moe", party: "D", cards: [] }] },
  { key: "r3", name: "Comptroller", group: "state", seats: 1, candidates: [{ key: "d", name: "Di Fox", party: "R", cards: [] }] },
] };
const stored = { races: { r1: ["a"] }, notes: { a: "solid record", b: " check her stance on housing ", c: "ask about roads", d: "  " } };
const picks = {
  picked: (key) => stored.races[key] || [],
  has: (key) => (stored.races[key] || []).length > 0,
  note: (key) => stored.notes[key] || "",
};
const titles = (sections) => sections.flatMap((s) => s.races.map((r) => r.name));
"""


def _run(script: str):
    source = f'const m = await import("{MODULE}");\n{SETUP}\nconsole.log(JSON.stringify((() => {{ {script} }})()));'
    done = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_every_note_in_a_race_is_printed_with_its_candidates_name_picked_or_not():
    assert _run("return m.raceNotes(ballot.races[0], picks);") == [
        "Ann Lee: solid record", "Bob Ray: check her stance on housing",
    ]


def test_a_race_with_only_notes_is_printed_when_notes_are():
    assert _run("""
return {
  picked: titles(m.printedSections(ballot, picks)),
  notes: titles(m.printedSections(ballot, picks, { includeNotes: true })),
  blank: titles(m.printedSections(ballot, picks, { includeBlank: true })),
};
""") == {
        "picked": ["U.S. Senate"],
        "notes": ["U.S. Senate", "Governor"],
        "blank": ["U.S. Senate", "Governor", "Comptroller"],
    }
