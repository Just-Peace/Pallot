"""The Issues tab's question (issue-prompt.js): the seat, each candidate's party, a table when it
compares, and keywords for a search engine. Run in Node, which loads the module as the browser does."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from pallot.api import STATIC_DIR

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")

MODULE = (STATIC_DIR / "js" / "issue-prompt.js").as_uri()
RACE = {"candidates": [
    {"name": "Greg Abbott", "party": "R", "incumbent": True},
    {"name": "Jane Doe", "party": "D"},
    {"name": "Sam Roe", "party": "L"},
]}
WHERE = {"office": "Governor", "place": ["Texas"], "year": "2026"}
TAXES = {"label": "Taxes", "terms": "taxes"}
GUNS = {"label": "Gun laws", "terms": "gun rights gun control"}


def _prompt(race, candidates, topics, ai=True):
    args = json.dumps([race, WHERE, candidates, topics, ai])
    source = f'const m = await import("{MODULE}");\nconsole.log(JSON.stringify(m.issuePrompt(...{args})));'
    done = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_one_candidate_is_named_with_their_party_and_seat_and_the_issues_numbered():
    lines = _prompt(RACE, RACE["candidates"][:1], [TAXES, GUNS]).split("\n")
    assert lines[:4] == ["Where does Greg Abbott, the Republican candidate (incumbent), running for Governor in Texas "
                         "in the 2026 election, stand on these issues?", "", "1. Taxes", "2. Gun laws"]
    text = "\n".join(lines)
    assert "Cite sources" in text and "more than one view" in text and "neutral" in text
    assert "table" not in text


def test_several_candidates_get_a_table():
    lines = _prompt(RACE, RACE["candidates"], [TAXES, GUNS]).split("\n")
    assert lines[0] == "Compare where these candidates for Governor in Texas in the 2026 election stand on these issues."
    assert lines[2:6] == ["Candidates:", "- Greg Abbott, the Republican candidate (incumbent)", "- Jane Doe, the Democratic candidate",
                          "- Sam Roe, the Libertarian candidate"]
    assert lines[7:10] == ["Issues:", "1. Taxes", "2. Gun laws"]
    assert "one row per issue and one column per candidate" in lines[-1]


def test_a_primary_says_a_party_candidate_and_no_issue_means_the_main_ones():
    primary = {"candidates": [{"name": "A One", "party": "R"}, {"name": "B Two", "party": "R"}]}
    text = _prompt(primary, primary["candidates"], [])
    assert "- A One, a Republican candidate" in text
    assert "stand on the main issues in this race" in text


def test_a_search_engine_gets_keywords_for_the_first_candidate():
    text = _prompt(RACE, RACE["candidates"], [GUNS], ai=False)
    assert text == "Greg Abbott Governor Texas 2026 position on gun rights gun control"
