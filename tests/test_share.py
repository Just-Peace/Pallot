"""A Pallot file (share.js, session.js): picks built from the ballot shown, or a whole session, read
back with anything it shouldn't hold dropped, carried in a link, matched to another ballot by key,
then by name, and a session put back by replacing or merging. Run in Node, which loads the modules
as the browser does, with a stand-in for localStorage."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from pallot.api import STATIC_DIR

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")

MODULE = (STATIC_DIR / "js" / "share.js").as_uri()
PICKS = (STATIC_DIR / "js" / "picks.js").as_uri()
SESSION = (STATIC_DIR / "js" / "session.js").as_uri()
SETUP = f"""
const store = {{}};
Object.defineProperties(store, {{
  getItem: {{ value: (key) => (key in store ? store[key] : null) }},
  setItem: {{ value: (key, value) => {{ store[key] = String(value); }} }},
  removeItem: {{ value: (key) => {{ delete store[key]; }} }},
}});
globalThis.localStorage = store;
const m = await import("{MODULE}");
const s = await import("{SESSION}");
const {{ Picks }} = await import("{PICKS}");
const ballot = {{
  election_date: "2026-11-03",
  elections: [{{ name: "2026 November General Election", type: "general" }}],
  location: {{ state: "TX", county: "Travis" }},
  districts: {{ cd: 10, sd: 14, hd: 49, election_precinct: {{ name: "300" }} }},
  races: [
    {{ key: "sos:1:sen", name: "U.S. Senator", seats: 1, seat: "TX-SEN", candidates: [
      {{ key: "sos:1:a", name: "Ann Lee", party: "D" }}, {{ key: "sos:1:b", name: "Bob Ray", party: "R" }},
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
const header = (bytes) => [String.fromCharCode(...bytes.slice(0, 6)), bytes[6], bytes[7]];
const linkBytes = (value) => Uint8Array.from(atob(value.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
"""


def _run(script: str):
    source = f"{SETUP}\nconsole.log(JSON.stringify(await (async () => {{ {script} }})()));"
    done = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_a_link_names_each_pick_with_its_party_and_the_districts_never_the_address_and_notes_and_avoid_only_when_asked():
    assert _run("""
const picks = new Picks("2026-11-03");
picks.set("sos:1:sen", ["sos:1:a"]);
picks.set("sos:1:judge", ["no"]);
picks.set("sos:1:jp", ["write-in"]);
picks.setWriteIn("sos:1:jp", "Mo Bay");
picks.setNote("sos:1:b", "Spoke at the forum");
const request = { address: "1 Main St", election_date: "2026-11-03", party: "D" };
const districts = m.districtsRecord(ballot, "U.S. House 10 · Pct 300");
const avoid = [{ text: "Cy Moe", plain: true }, { text: "^Ed", plain: false }];
const full = m.buildSlate(ballot, picks, { request, title: "Nov 3", notes: true, avoid, districts });
const bare = m.buildSlate(ballot, picks, { request, districts });
const avoidOnly = m.buildSlate(ballot, picks, { withPicks: false, avoid });
return { races: full.races, notes: full.notes, districts: full.districts, avoid: full.avoid, election: bare.election,
  bare: [bare.notes, "ballot" in bare, "avoid" in bare], avoidOnly: [avoidOnly.races, avoidOnly.avoid.length],
  counts: m.slateCounts(full) };
""") == {
        "races": [
            {"key": "sos:1:sen", "name": "U.S. Senator", "picks": [{"key": "sos:1:a", "name": "Ann Lee", "party": "D"}]},
            {"key": "sos:1:judge", "name": "Keep Judge Roe?", "picks": [{"key": "no", "name": "No"}]},
            {"key": "sos:1:jp", "name": "Justice of the Peace", "picks": [{"key": "write-in", "name": "Mo Bay"}], "write_in": "Mo Bay"},
        ],
        "notes": [{"key": "sos:1:b", "name": "Bob Ray", "race": "sos:1:sen", "party": "R", "text": "Spoke at the forum"}],
        "districts": {"state": "TX", "county": "Travis", "cd": 10, "sd": 14, "hd": 49, "precinct": "300", "line": "U.S. House 10 · Pct 300"},
        "avoid": [{"text": "Cy Moe", "plain": True}, {"text": "^Ed", "plain": False}],
        "election": {"date": "2026-11-03", "title": "", "party": "D", "cycle": {
            "date": "2026-11-03", "state": "TX", "elections": [{"name": "2026 November General Election", "type": "general"}],
        }},
        "bare": [[], False, False],
        "avoidOnly": [[], 2],
        "counts": {"races": 3, "notes": 1, "avoid": 2},
    }


def test_reading_a_file_refuses_what_isnt_one_and_drops_what_it_shouldnt_hold():
    assert _run("""
const errors = [];
for (const text of ["not json", JSON.stringify([1]), JSON.stringify({ kind: "pallot", version: 9 })]) {
  try { m.readSlate(text); } catch (error) { errors.push(error.message); }
}
const read = m.readSlate({
  kind: "pallot", version: 1, extra: "x",
  election: { date: "soon", title: "Nov 3", cycle: { date: "2026-11-03", state: "Texas", elections: [{ name: "General", type: "general", x: 1 }, 5] } },
  ballot: { address: "1 Main St", districts: { cd: 10, sd: "x" }, script: "<b>" },
  districts: { cd: 10, hd: "<b>", evil: 1, line: "U.S. House 10" },
  races: [{ key: "r", name: "Race", picks: [{ key: "a", name: "A", party: "D" }, "junk"] }, { key: "empty", picks: [] }, 5],
  notes: [{ key: "a", name: "A", race: "r", text: "  " }, { key: "a", name: "A", race: "r", text: "Good" }],
  avoid: [{ text: " Bo Li ", plain: true }, { text: "bo li" }, { text: "^Ed" }, { text: "(a+)+$" }, { text: "(x)\\\\1" }, { text: "" }, "junk"],
  session:{ store: { "pallot.ui.v1": "{}", "pallot.settingsChanged.v1": "1", "other.key": "{}", "pallot.bad.v1": "{oops" }, race: "r" },
});
return { errors, read };
""") == {
        "errors": ["This isn't a Pallot file.", "This isn't a Pallot file.", "This file was made by a newer Pallot."],
        "read": {
            "kind": "pallot", "version": 1,
            "election": {"date": None, "title": "Nov 3", "cycle": {"date": "2026-11-03", "elections": [{"name": "General", "type": "general"}]}},
            "ballot": {"address": "1 Main St", "districts": {"cd": 10}},
            "districts": {"cd": 10, "hd": "<b>", "line": "U.S. House 10"},
            "races": [{"key": "r", "name": "Race", "picks": [{"key": "a", "name": "A", "party": "D"}]}],
            "notes": [{"key": "a", "name": "A", "race": "r", "text": "Good"}],
            "avoid": [{"text": "Bo Li", "plain": True}, {"text": "^Ed", "plain": False}, {"text": "(a+)+$", "plain": True},
                      {"text": "(x)\\1", "plain": True}],
            "session": {"store": {"pallot.ui.v1": "{}"}, "race": "r"},
        },
    }


def test_a_link_carries_the_files_bytes_after_its_hash_and_a_broken_one_says_so():
    assert _run("""
const picks = new Picks("2026-11-03");
picks.set("sos:1:sen", ["sos:1:b"]);
picks.setNote("sos:1:b", "Ünïcode ✓ note");
const slate = m.buildSlate(ballot, picks, { title: "Nov 3" });
const link = new URL(await m.slateLink(slate, "http://127.0.0.1:8000/"));
const value = new URLSearchParams(link.hash.slice(1)).get(m.LINK_KEY);
const back = await m.slateFromLink(value);
const broken = [];
for (const bad of ["zAAAA", "AAAAAAAAAAAA"]) {
  try { await m.slateFromLink(bad); } catch (error) { broken.push(error.message); }
}
return { path: link.pathname, search: link.search, header: header(linkBytes(value)), same: JSON.stringify(back) === JSON.stringify(slate), broken };
""") == {
        "path": "/", "search": "", "header": ["PALLOT", 1, 0], "same": True,
        "broken": ["This link's picks couldn't be read. Ask for the link again."] * 2,
    }


def test_a_file_is_binary_locked_with_the_built_in_key_and_opens_without_asking():
    assert _run("""
const picks = new Picks("2026-11-03");
picks.set("sos:1:sen", ["sos:1:a"]);
picks.setNote("sos:1:a", "Secret note");
const slate = m.buildSlate(ballot, picks, { title: "Nov 3" });
const bytes = await m.pallotFile(slate);
const back = await m.readPallotFile(bytes, async () => { throw new Error("asked for a phrase"); });
const errors = [];
for (const bad of [new TextEncoder().encode(JSON.stringify(slate)), Uint8Array.from([...bytes.slice(0, 8), 1, 2, 3]), Uint8Array.from([...bytes.slice(0, 6), 9, 1])]) {
  try { await m.readPallotFile(bad, null); } catch (error) { errors.push(error.message); }
}
return { header: header(bytes), hidden: !/Ann Lee|Secret note|Senator/.test(String.fromCharCode(...bytes)), same: JSON.stringify(back) === JSON.stringify(slate), errors };
""") == {
        "header": ["PALLOT", 1, 1], "hidden": True, "same": True,
        "errors": ["This isn't a Pallot file.", "This Pallot file couldn't be read.", "This file was made by a newer Pallot."],
    }


def test_a_phrase_locks_a_link_or_file_until_the_right_phrase_is_given_and_cancel_gives_up():
    assert _run("""
const picks = new Picks("2026-11-03");
picks.set("sos:1:sen", ["sos:1:a"]);
const slate = m.buildSlate(ballot, picks);
const link = new URL(await m.slateLink(slate, "http://127.0.0.1:8000/", "Right-Phrase-7"));
const value = new URLSearchParams(link.hash.slice(1)).get(m.LINK_KEY);
const tries = [];
const back = await m.slateFromLink(value, async (open) => {
  tries.push(await open("Wrong-Phrase-7"));
  return open("Right-Phrase-7");
});
const cancelled = await m.slateFromLink(value, async () => null);
const file = await m.pallotFile(slate, "Right-Phrase-7");
const fromFile = await m.readPallotFile(file, (open) => open("Right-Phrase-7"));
return {
  how: linkBytes(value)[7], wrong: tries, picks: back.races[0].picks, cancelled,
  fileHow: file[7], filePicks: fromFile.races[0].picks,
};
""") == {
        "how": 2, "wrong": [None], "picks": [{"key": "sos:1:a", "name": "Ann Lee", "party": "D"}], "cancelled": None,
        "fileHow": 2, "filePicks": [{"key": "sos:1:a", "name": "Ann Lee", "party": "D"}],
    }


def test_a_phrase_needs_ten_characters_a_capital_a_small_letter_and_a_number():
    assert _run("""
const met = (phrase) => Object.fromEntries(m.phraseRules(phrase).map((rule) => [rule.id, rule.met]));
return {
  missing: m.phraseRules("Abc").filter((rule) => !rule.met).map((rule) => rule.short),
  some: met("Élan vital 9!"),
  ready: ["Abcdefghi1", "Abcdefgh1", "abcdefghi1", "ABCDEFGHI1", "Abcdefghij"].map(m.phraseReady),
};
""") == {
        "missing": ["7 more characters", "0–9"],
        "some": {"length": True, "upper": True, "lower": True, "number": True},
        "ready": [True, False, False, False, False],
    }


def test_opening_picks_matches_races_and_candidates_by_key_then_by_a_name_only_one_fits():
    assert _run("""
const picks = new Picks("2026-11-03");
picks.set("sos:1:board", ["sos:1:e"]);
const slate = m.readSlate({
  kind: "pallot", version: 1, election: { date: "2026-11-03" },
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
const slate = m.readSlate({ kind: "pallot", version: 1, races: [{ key: "r", name: "Race", picks: [{ key: "old", name: "Pat Kim" }] }] });
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


def test_kept_picks_carry_the_cycle_and_the_names_behind_them_once_a_ballot_is_described():
    assert _run("""
const picks = new Picks("2026-11-03");
picks.describe(ballot);
picks.set("sos:1:sen", ["sos:1:a"]);
picks.setNote("sos:1:j", "Fair judge");
const kept = JSON.parse(store["pallot.picks.v1"])["2026-11-03"];
return { names: kept.names, cycle: kept.cycle };
""") == {
        "names": {
            "races": {"sos:1:sen": {"name": "U.S. Senator", "seat": "TX-SEN"}, "sos:1:jp": {"name": "Justice of the Peace"}},
            "people": {"sos:1:a": {"name": "Ann Lee", "party": "D", "race": "sos:1:sen"}, "sos:1:j": {"name": "Al Day", "race": "sos:1:jp"}},
        },
        "cycle": {"date": "2026-11-03", "state": "TX", "elections": [{"name": "2026 November General Election", "type": "general"}]},
    }


def test_the_same_address_or_districts_count_as_the_same_ballot():
    assert _run("""
const here = m.districtsRecord(ballot, "a");
const moved = m.districtsRecord({ ...ballot, districts: { ...ballot.districts, hd: 50 } }, "a");
return [
  m.samePlace({ address: "1 Main St." }, { address: "1  main st" }),
  m.samePlace({ address: "1 Main St" }, { address: "2 Main St" }),
  m.samePlace({ county: "Travis County", precinct: "0300" }, { county: "travis", precinct: "300" }),
  m.sameDistricts(here, m.districtsRecord(ballot, "b")),
  m.sameDistricts(here, moved),
  m.sameDistricts(here, null),
];
""") == [True, False, True, True, False, False]


def test_a_session_replaces_or_merges_keeps_your_address_in_the_same_districts_and_undoes():
    assert _run("""
const put = (values) => { for (const key of Object.keys(store)) delete store[key]; for (const [k, v] of Object.entries(values)) store[k] = JSON.stringify(v); };
const districts = m.districtsRecord(ballot, "x");
const mine = {
  "pallot.ui.v1": { theme: "dark", focuses: ["money"] },
  "pallot.banList.v1": [{ text: "Bob Ray", plain: true }],
  "pallot.lastLookup.v1": { address: "1 Main St", election_date: "2026-03-03" },
  "pallot.lastDistricts.v1": districts,
  "pallot.settingsChanged.v1": 5,
};
const theirs = {
  "pallot.ui.v1": JSON.stringify({ theme: "light", focuses: ["polls"], issues: ["Taxes"] }),
  "pallot.banList.v1": JSON.stringify([{ text: "Cy Moe", plain: true }]),
  "pallot.lastLookup.v1": JSON.stringify({ address: "9 Elm St", election_date: "2026-11-03" }),
  "pallot.lastDistricts.v1": JSON.stringify(districts),
};
const session = m.readSlate(JSON.stringify(m.buildSession(theirs, { race: "sos:1:sen" })));
const read = (key) => JSON.parse(store[key]);
const out = {};
for (const how of ["replace", "theirs", "mine"]) {
  put(mine);
  const before = s.restoreSession(session.session.store, how);
  out[how] = { ui: read("pallot.ui.v1"), ban: read("pallot.banList.v1").map((e) => e.text), lookup: read("pallot.lastLookup.v1") };
  s.undoRestore(before);
  out[how].undone = read("pallot.ui.v1").theme;
}
put({ "pallot.lastLookup.v1": { address: "1 Main St" } });
s.restoreSession(session.session.store, "replace");
out.elsewhere = read("pallot.lastLookup.v1").address;
return { out, race: session.session.race, place: session.ballot, stamp: s.sessionStore()["pallot.settingsChanged.v1"] ?? null };
""") == {
        "out": {
            "replace": {"ui": {"theme": "light", "focuses": ["polls"], "issues": ["Taxes"]}, "ban": ["Cy Moe"],
                        "lookup": {"address": "1 Main St", "election_date": "2026-11-03"}, "undone": "dark"},
            "theirs": {"ui": {"theme": "light", "focuses": ["polls"], "issues": ["Taxes"]}, "ban": ["Bob Ray", "Cy Moe"],
                       "lookup": {"address": "1 Main St", "election_date": "2026-11-03"}, "undone": "dark"},
            "mine": {"ui": {"theme": "dark", "focuses": ["money"], "issues": ["Taxes"]}, "ban": ["Bob Ray", "Cy Moe"],
                     "lookup": {"address": "1 Main St", "election_date": "2026-03-03"}, "undone": "dark"},
            "elsewhere": "9 Elm St",
        },
        "race": "sos:1:sen",
        "place": {"address": "9 Elm St"},
        "stamp": None,
    }
