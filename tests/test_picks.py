"""The picks kept in the voter's browser (picks.js): past elections' picks forgotten when a ballot
loads, folded races kept apart from the picks, and a stored bucket of the wrong shape. Run in Node,
which loads the module as the browser does, with a stand-in for localStorage. Two Picks for one
election stand for two tabs, which share it."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from pallot.api import STATIC_DIR

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")

PICKS = (STATIC_DIR / "js" / "picks.js").as_uri()
STORAGE = """
const store = new Map();
globalThis.localStorage = {
  getItem: (key) => (store.has(key) ? store.get(key) : null),
  setItem: (key, value) => store.set(key, String(value)),
  removeItem: (key) => store.delete(key),
  key: (i) => [...store.keys()][i],
  get length() { return store.size; },
};
const read = (key) => JSON.parse(store.get(key) ?? "null");
const write = (key, value) => store.set(key, JSON.stringify(value));
const DAY = 24 * 60 * 60 * 1000;
const daysAgo = (n) => new Date(Date.now() - n * DAY).toISOString().slice(0, 10);
"""


def _run(script: str, before: str = ""):
    source = (f'{STORAGE}\n{before}\nconst picks = await import("{PICKS}");\n'
              f"console.log(JSON.stringify(await (async () => {{ {script} }})()));")
    done = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_a_ballot_forgets_elections_more_than_90_days_past():
    assert _run("""
const bucket = { races: { r1: ["c1"] }, notes: { c1: "a note" } };
write("pallot.picks.v1", { [daysAgo(120)]: bucket, [daysAgo(30)]: bucket, [daysAgo(-20)]: bucket });
write("pallot.collapsed.v1", { [daysAgo(120)]: { r1: true }, [daysAgo(30)]: { r1: true } });
new picks.Picks(daysAgo(-20));
return [Object.keys(read("pallot.picks.v1")).sort(), Object.keys(read("pallot.collapsed.v1"))];
""") == [sorted([_days_ago(30), _days_ago(-20)]), [_days_ago(30)]]


def test_the_election_shown_is_kept_however_old():
    assert _run("""
write("pallot.picks.v1", { [daysAgo(400)]: { races: { r1: ["c1"] }, notes: {} } });
const p = new picks.Picks(daysAgo(400));
return [p.picked("r1"), Object.keys(read("pallot.picks.v1")).length];
""") == [["c1"], 1]


def test_an_undated_bucket_is_stamped_and_forgotten_90_days_after_its_last_save():
    assert _run("""
write("pallot.picks.v1", { undated: { races: { r1: ["c1"] }, notes: {} } });
new picks.Picks("2026-11-03");
const stamped = typeof read("pallot.picks.v1").undated.saved_at === "number";
write("pallot.picks.v1", { undated: { races: {}, notes: {}, saved_at: Date.now() - 91 * DAY } });
write("pallot.collapsed.v1", { undated: { r1: true } });
new picks.Picks("2026-11-03");
const gone = !("undated" in read("pallot.picks.v1")) && !("undated" in read("pallot.collapsed.v1"));
const p = new picks.Picks(null);
p.set("r1", ["c1"]);
return [stamped, gone, Date.now() - read("pallot.picks.v1").undated.saved_at < DAY];
""") == [True, True, True]


def test_folded_races_move_out_of_the_picks_once():
    assert _run("""
write("pallot.picks.v1", { "2099-11-03": { races: { r1: ["c1"] }, notes: {}, collapsed: { r1: true, r2: true } } });
const p = new picks.Picks("2099-11-03");
const after = read("pallot.picks.v1")["2099-11-03"];
return [p.isCollapsed("r1"), p.isCollapsed("r2"), p.isCollapsed("r3"), "collapsed" in after, after.races, read("pallot.collapsed.v1")];
""") == [True, True, False, False, {"r1": ["c1"]}, {"2099-11-03": {"r1": True, "r2": True}}]


def test_folding_a_race_leaves_the_picks_untouched_in_either_tab():
    assert _run("""
const one = new picks.Picks("2099-11-03");
const two = new picks.Picks("2099-11-03");
one.set("r1", ["c1"]);
const picksBefore = store.get("pallot.picks.v1");
one.setCollapsed("r1", true);
two.setCollapsed(["r2", "r3"], true);
two.setCollapsed("r3", false);
const untouched = store.get("pallot.picks.v1") === picksBefore;
two.reload();
two.set("r2", ["c2"]);
one.reload(); // the storage event the pick fires in the other tab
const cleared = one.clear();
two.reload();
return [untouched, read("pallot.collapsed.v1"), cleared.races, two.picked("r1"), two.isCollapsed("r1"), new picks.Picks("2099-11-03").isCollapsed("r1")];
""") == [True, {"2099-11-03": {"r1": True, "r2": True}}, {"r1": ["c1"], "r2": ["c2"]}, [], False, True]


def test_a_bucket_of_the_wrong_shape_reads_as_empty_and_is_dropped():
    assert _run("""
write("pallot.picks.v1", { "2099-11-03": { writeIns: { r1: "Ann" } }, "2099-12-01": "junk", "2099-12-02": [1], "2099-12-03": { races: "x" } });
const p = new picks.Picks("2099-11-03");
const q = new picks.Picks("2099-12-03");
return [p.picked("r1"), p.note("c1"), p.isEmpty(), p.writeIn("r1"), q.isEmpty(), Object.keys(read("pallot.picks.v1")).sort()];
""") == [[], "", False, "Ann", True, ["2099-11-03", "2099-12-03"]]


def test_clear_my_picks_removes_the_folded_races_and_undo_puts_them_back():
    assert _run("""
const p = new picks.Picks("2099-11-03");
p.set("r1", ["c1"]);
p.setCollapsed("r1", true);
const removed = picks.clearPicksAndNotes();
const gone = [store.has("pallot.picks.v1"), store.has("pallot.collapsed.v1")];
picks.restoreBrowserData(removed);
return [gone, new picks.Picks("2099-11-03").isCollapsed("r1")];
""") == [[False, False], True]


def _days_ago(n: int) -> str:
    return _run(f"return daysAgo({n});")
