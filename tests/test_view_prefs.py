"""The view settings kept in the voter's browser (view.js, issues.js): the view's mode, and the issues
that matter most to the voter. Run in Node, which loads the modules as the browser does, with a
stand-in for localStorage."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from pallot.api import STATIC_DIR

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")

VIEW = (STATIC_DIR / "js" / "view.js").as_uri()
ISSUES = (STATIC_DIR / "js" / "issues.js").as_uri()
STORAGE = """
const store = new Map();
globalThis.localStorage = {
  getItem: (key) => (store.has(key) ? store.get(key) : null),
  setItem: (key, value) => store.set(key, String(value)),
  removeItem: (key) => store.delete(key),
};
globalThis.document = { dispatchEvent() {} };
"""


def _run(script: str):
    source = (f'{STORAGE}\nconst view = await import("{VIEW}");\nconst issues = await import("{ISSUES}");\n'
              f"console.log(JSON.stringify(await (async () => {{ {script} }})()));")
    done = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_opening_the_map_keeps_the_mode_and_another_switch_makes_it_custom():
    assert _run("""
const modes = [view.viewMode()];
view.setViewPref("showMap", true);
modes.push(view.viewMode());
view.setViewMode("detailed");
view.setViewPref("showMap", false);
modes.push(view.viewMode(), view.viewPref("showMap"));
view.setViewPref("showPolls", false);
modes.push(view.viewMode());
return modes;
""") ==["simple", "simple", "detailed", False, "custom"]


def test_saved_issues_keep_the_list_order_and_drop_one_no_longer_offered():
    assert _run("""
const before = issues.savedIssues();
issues.setSavedIssue("Taxes", true);
issues.setSavedIssue("Abortion", true);
issues.setSavedIssue("Energy", true);
issues.setSavedIssue("Taxes", true);
const chosen = issues.savedIssues();
issues.setSavedIssue("Energy", false);
const stored = JSON.parse(store.get("pallot.ui.v1"));
localStorage.setItem("pallot.ui.v1", JSON.stringify({ ...stored, issues: [...stored.issues, "Not an issue"] }));
return [before, chosen, issues.savedIssues()];
""") == [[], ["Energy", "Taxes", "Abortion"], ["Taxes", "Abortion"]]
