"""Share picks (share.js): a picks file built from the ballot shown, read back with anything it
shouldn't hold dropped, carried in a link, and matched to another ballot by key, then by name.
Run in Node, which loads the module as the browser does, with a stand-in for localStorage."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from pallot.api import STATIC_DIR

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")

MODULE = (STATIC_DIR / "js" / "share.js").as_uri()
PICKS = (STATIC_DIR / "js" / "picks.js").as_uri()
SETUP = f"""
const store = new Map();
globalThis.localStorage = {{
  getItem: (key) => (store.has(key) ? store.get(key) : null),
  setItem: (key, value) => store.set(key, String(value)),
  removeItem: (key) => store.delete(key),
}};
const m = await import("{MODULE}");
const {{ Picks }} = await import("{PICKS}");
const ballot = {{
  election_date: "2026-11-03",
  races: [
    {{ key: "sos:1:sen", name: "U.S. Senator", seats: 1, candidates: [
      {{ key: "sos:1:a", name: "Ann Lee" }}, {{ key: "sos:1:b", name: "Bob Ray" }},
    ] }},
    {{ key: "sos:1:board", name: "School Board", seats: 2, candidates: [
      {{ key: "sos:1:c", name: "Cy Moe" }}, {{ key: "sos:1:d", name: "Di Fox" }}, {{ key: "sos:1:e", name: "Ed Poe" }},
    ] }},
    {{ key: "sos:1:judge", name: "Keep Judge Roe?", seats: 1, retention: true, candidates: [{{ key: "sos:1:r", name: "Jo Roe" }}] }},
  ],
  maybe: [{{ id: "jp", title: "JP", races: [
    {{ key: "sos:1:jp", name: "Justice of the Peace", seats: 1, candidates: [{{ key: "sos:1:j", name: "Al Day" }}] }},
  ] }}],
}};
"""


def _run(script: str):
    source = f"{SETUP}\nconsole.log(JSON.stringify(await (async () => {{ {script} }})()));"
    done = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_a_picks_file_names_each_pick_and_keeps_notes_and_the_address_only_when_asked():
    assert _run("""
const picks = new Picks("2026-11-03");
picks.set("sos:1:sen", ["sos:1:a"]);
picks.set("sos:1:judge", ["no"]);
picks.set("sos:1:jp", ["write-in"]);
picks.setWriteIn("sos:1:jp", "Mo Bay");
picks.setNote("sos:1:b", "Spoke at the forum");
const request = { address: "1 Main St", election_date: "2026-11-03", party: "D" };
const full = m.buildSlate(ballot, picks, { request, title: "Nov 3", address: true });
const bare = m.buildSlate(ballot, picks, { request, notes: false });
return { races: full.races, notes: full.notes, ballot: full.ballot, election: bare.election, bare: [bare.notes, "ballot" in bare],
  counts: m.slateCounts(full) };
""") == {
        "races": [
            {"key": "sos:1:sen", "name": "U.S. Senator", "picks": [{"key": "sos:1:a", "name": "Ann Lee"}]},
            {"key": "sos:1:judge", "name": "Keep Judge Roe?", "picks": [{"key": "no", "name": "No"}]},
            {"key": "sos:1:jp", "name": "Justice of the Peace", "picks": [{"key": "write-in", "name": "Mo Bay"}], "write_in": "Mo Bay"},
        ],
        "notes": [{"key": "sos:1:b", "name": "Bob Ray", "race": "sos:1:sen", "text": "Spoke at the forum"}],
        "ballot": {"address": "1 Main St"},
        "election": {"date": "2026-11-03", "title": "", "party": "D"},
        "bare": [[], False],
        "counts": {"races": 3, "notes": 1},
    }


def test_reading_a_file_refuses_what_isnt_one_and_drops_what_it_shouldnt_hold():
    assert _run("""
const errors = [];
for (const text of ["not json", JSON.stringify([1]), JSON.stringify({ kind: "pallot-picks", version: 9 })]) {
  try { m.readSlate(text); } catch (error) { errors.push(error.message); }
}
const read = m.readSlate({
  kind: "pallot-picks", version: 1, extra: "x",
  election: { date: "soon", title: "Nov 3" },
  ballot: { address: "1 Main St", districts: { cd: 10, sd: "x" }, script: "<b>" },
  races: [{ key: "r", name: "Race", picks: [{ key: "a", name: "A" }, "junk"] }, { key: "empty", picks: [] }, 5],
  notes: [{ key: "a", name: "A", race: "r", text: "  " }, { key: "a", name: "A", race: "r", text: "Good" }],
});
return { errors, read };
""") == {
        "errors": ["This isn't a Pallot picks file.", "This isn't a Pallot picks file.", "This picks file was made by a newer Pallot."],
        "read": {
            "kind": "pallot-picks", "version": 1,
            "election": {"date": None, "title": "Nov 3"},
            "ballot": {"address": "1 Main St", "districts": {"cd": 10}},
            "races": [{"key": "r", "name": "Race", "picks": [{"key": "a", "name": "A"}]}],
            "notes": [{"key": "a", "name": "A", "race": "r", "text": "Good"}],
        },
    }


def test_a_link_carries_the_file_after_its_hash_and_a_broken_one_says_so():
    assert _run("""
const picks = new Picks("2026-11-03");
picks.set("sos:1:sen", ["sos:1:b"]);
picks.setNote("sos:1:b", "Ünïcode ✓ note");
const slate = m.buildSlate(ballot, picks, { title: "Nov 3" });
const link = new URL(await m.slateLink(slate, "http://127.0.0.1:8000/"));
const value = new URLSearchParams(link.hash.slice(1)).get(m.LINK_KEY);
const back = await m.slateFromLink(value);
let broken = null;
try { await m.slateFromLink("zAAAA"); } catch (error) { broken = error.message; }
return { path: link.pathname, search: link.search, packed: value[0], same: JSON.stringify(back) === JSON.stringify(slate), broken };
""") == {
        "path": "/", "search": "", "packed": "z", "same": True,
        "broken": "This link's picks couldn't be read. Ask for the link again.",
    }


def test_opening_picks_matches_races_and_candidates_by_key_then_by_a_name_only_one_fits():
    assert _run("""
const picks = new Picks("2026-11-03");
picks.set("sos:1:board", ["sos:1:e"]);
const slate = m.readSlate({
  kind: "pallot-picks", version: 1, election: { date: "2026-11-03" },
  races: [
    { key: "sos:9:sen", name: "U.S.  senator", picks: [{ key: "sos:9:a", name: "ann lee" }] },
    { key: "sos:1:board", name: "School Board", picks: [{ key: "sos:1:c" }, { key: "sos:1:d" }, { key: "sos:1:e" }] },
    { key: "sos:1:judge", name: "Keep Judge Roe?", picks: [{ key: "yes", name: "Yes" }] },
    { key: "sos:9:mayor", name: "Mayor", picks: [{ key: "x", name: "Xi Ng" }] },
    { key: "sos:1:jp", name: "Justice of the Peace", picks: [{ key: "sos:9:z", name: "Nobody" }] },
  ],
  notes: [{ key: "sos:9:a", name: "Ann Lee", race: "sos:9:sen", text: "Good record" }],
});
const plan = m.planImport(slate, ballot, picks);
return { ...plan, changes: plan.changes };
""") == {
        "changes": {
            "races": {"sos:1:sen": ["sos:1:a"], "sos:1:board": ["sos:1:c", "sos:1:d"], "sos:1:judge": ["yes"]},
            "writeIns": {},
            "notes": {"sos:1:a": "Good record"},
        },
        "picks": 3, "replaced": 1, "notes": 1, "missing": ["Mayor", "Justice of the Peace"], "changed": True,
    }


def test_a_name_two_candidates_share_is_left_out_rather_than_guessed():
    assert _run("""
const twins = { ...ballot, races: [{ key: "r", name: "Race", seats: 1, candidates: [{ key: "a", name: "Pat Kim" }, { key: "b", name: "Pat Kim" }] }], maybe: [] };
const slate = m.readSlate({ kind: "pallot-picks", version: 1, races: [{ key: "r", name: "Race", picks: [{ key: "old", name: "Pat Kim" }] }] });
const plan = m.planImport(slate, twins, new Picks("2026-11-03"));
return [plan.missing, plan.changed];
""") == [["Race"], False]


def test_opening_your_own_picks_again_changes_nothing_and_a_new_note_joins_yours():
    assert _run("""
const picks = new Picks("2026-11-03");
picks.set("sos:1:sen", ["sos:1:a"]);
picks.setNote("sos:1:a", "Mine");
const own = m.readSlate(m.buildSlate(ballot, picks));
const again = m.planImport(own, ballot, picks);
own.notes = [{ key: "sos:1:a", name: "Ann Lee", race: "sos:1:sen", text: "Theirs" }];
return [again.changed, m.planImport(own, ballot, picks).changes.notes];
""") == [False, {"sos:1:a": "Mine\n\nTheirs"}]


def test_merging_picks_makes_them_the_voters_own_and_restore_puts_back_what_was_there():
    assert _run("""
const picks = new Picks("2026-11-03");
picks.setMany({ "sos:1:sen": ["sos:1:b"] }, { "sos:1:sen": ["sos:1:b"] });
picks.setNote("sos:1:b", "Mine");
const before = picks.merge({ races: { "sos:1:sen": ["sos:1:a"] }, writeIns: { "sos:1:jp": "Mo Bay" }, notes: { "sos:1:a": "Theirs" } });
const stored = new Picks("2026-11-03");
const merged = { sen: stored.picked("sos:1:sen"), auto: stored.auto("sos:1:sen"), writeIn: stored.writeIn("sos:1:jp"),
  notes: [stored.note("sos:1:a"), stored.note("sos:1:b")] };
picks.restore(before);
const undone = new Picks("2026-11-03");
return { merged, undone: [undone.picked("sos:1:sen"), undone.auto("sos:1:sen"), undone.writeIn("sos:1:jp"), undone.note("sos:1:a")] };
""") == {
        "merged": {"sen": ["sos:1:a"], "auto": [], "writeIn": "Mo Bay", "notes": ["Theirs", "Mine"]},
        "undone": [["sos:1:b"], ["sos:1:b"], "", ""],
    }
