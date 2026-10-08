"""The ban list (ban-list.js), kept in the voter's browser: what its entries match, and banning and
unbanning a candidate from Details. Run in Node, which loads the module as the browser does, with
a stand-in for localStorage."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from pallot.api import STATIC_DIR

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")

MODULE = (STATIC_DIR / "js" / "ban-list.js").as_uri()
STORAGE = """
const store = new Map();
globalThis.localStorage = {
  getItem: (key) => (store.has(key) ? store.get(key) : null),
  setItem: (key, value) => store.set(key, String(value)),
  removeItem: (key) => store.delete(key),
};
"""


def _run(script: str):
    source = f'{STORAGE}\nconst m = await import("{MODULE}");\nconsole.log(JSON.stringify(await (async () => {{ {script} }})()));'
    done = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_a_pattern_matches_any_part_of_a_name_ignoring_case():
    entries = [{"text": "smith"}, {"text": "^john"}, {"text": "Doe"}, {"text": "Jo(e|hn) Q"}]
    assert _run(f'return m.banMatches("John Q. Smith", {json.dumps(entries)}).map((e) => e.text);') == [
        "smith", "^john", "Jo(e|hn) Q",
    ]


def test_an_invalid_pattern_matches_as_plain_text():
    entries = [{"text": "Smith ("}, {"text": "[x"}]
    assert _run(f'return [m.isPattern("Smith ("), m.banMatches("Ann Smith (Jr)", {json.dumps(entries)}).map((e) => e.text)];') == [
        False, ["Smith ("],
    ]


def test_a_plain_entry_matches_its_own_name_with_regex_characters():
    entries = [{"text": "John Smith (Jr.)", "plain": True}, {"text": "John Smith (Jr.)"}]
    assert _run(f'return m.banMatches("John Smith (Jr.)", {json.dumps(entries)}).map((e) => e.plain || false);') == [True]


def test_banning_from_details_adds_the_name_once_as_plain_text():
    assert _run("""
m.banName("Ann Smith");
m.banName("ann smith");
return m.banList();
""") == [{"text": "Ann Smith", "plain": True}]


def test_unbanning_takes_off_every_matching_entry_and_undo_puts_them_back():
    assert _run("""
m.setBanList([{ text: "Ann Smith", plain: true }, { text: "smith" }, { text: "Jones" }]);
const removed = m.unbanName("Ann Smith");
const after = m.banList().map((e) => e.text);
m.restoreBans(removed);
return { removed: removed.map((e) => e.text), after, restored: m.banList().map((e) => e.text) };
""") == {"removed": ["Ann Smith", "smith"], "after": ["Jones"], "restored": ["Jones", "Ann Smith", "smith"]}


def test_a_stored_list_that_isnt_one_reads_as_empty():
    assert _run("""
localStorage.setItem("pallot.banList.v1", JSON.stringify({ text: "x" }));
const odd = m.banList();
localStorage.setItem("pallot.banList.v1", JSON.stringify([{ text: " " }, "Smith", { text: "Doe" }]));
return [odd, m.banList()];
""") == [[], [{"text": "Doe"}]]


RULES = (STATIC_DIR / "js" / "pick-rules.js").as_uri()


def test_pick_by_rule_takes_back_and_skips_anyone_on_the_ban_list():
    assert _run(f"""
const r = await import("{RULES}");
m.setBanList([{{ text: "smith" }}]);
const race = {{ key: "r1", seats: 1, candidates: [
  {{ key: "a", name: "Ann Smith", party: "D", cards: [] }},
  {{ key: "b", name: "Bob Jones", party: "D", cards: [] }},
] }};
const picks = {{ picked: () => ["a"] }};
const rule = {{ ...structuredClone(r.DEFAULT_RULE), parties: ["D"], keepMine: false }};
const on = r.plan([race], rule, picks).rows[0];
const off = r.plan([race], {{ ...rule, banned: false }}, picks).rows[0];
const has = r.available([race]);
return {{
  default: r.DEFAULT_RULE.banned, has: has.banned,
  after: on.after, takenBack: on.takenBack, offOutcome: off.outcome,
  words: r.describeRule(rule, r.ballotParties([race]), has).skip,
}};
""") == {
        "default": True, "has": True,
        "after": ["b"], "takenBack": [{"key": "a", "reasons": ["on your ban list"]}], "offOutcome": "many",
        "words": "Don't pick anyone on your ban list, and take back their picks.",
    }
