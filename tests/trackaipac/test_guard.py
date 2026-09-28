from __future__ import annotations

import re
from dataclasses import replace

import pytest

from trackaipac_cache.errors import ValidationError
from trackaipac_cache.guard import changed_sources, hash_rows, validate
from trackaipac_cache.parser import ParseResult, parse_source
from trackaipac_cache.store import snapshot_rows

from .conftest import keep_items


def test_fixtures_pass_and_report_rows_without_seat(parsed):
    assert validate(parsed) == [
        "congress: 'Chuck Fleischmann' is listed without a seat line; stored as shown (state TN from section 'Tennessee')"
    ]


def test_record_floor(parsed, pages):
    results = {**parsed, "candidates": parse_source("candidates", keep_items(pages["candidates"], 5))}
    with pytest.raises(ValidationError) as exc:
        validate(results)
    assert exc.value.problems == ["candidates: parsed 5 records, expected at least 20"]


def test_empty_page_fails(parsed):
    with pytest.raises(ValidationError, match="endorsements: parsed 0 records"):
        validate({**parsed, "endorsements": parse_source("endorsements", "<html>Service unavailable</html>")})


def test_list_item_without_name_aborts(parsed, pages):
    html, n = re.subn(r"<h2(\s[^>]*>Mary Peltola)</h2>", r"<p\1</p>", pages["candidates"])
    assert n == 1
    with pytest.raises(ValidationError, match="candidates: 1 list items have no name heading"):
        validate({**parsed, "candidates": parse_source("candidates", html)})


def test_coverage_catches_renamed_label(parsed, pages):
    relabelled = pages["congress"].replace("Lobby Total", "Money Sum")
    with pytest.raises(ValidationError, match=r"congress: only 0/535 records have israel_lobby_total"):
        validate({**parsed, "congress": parse_source("congress", relabelled)})


def test_coverage_catches_unparseable_seats(parsed):
    base = parsed["endorsements"]
    broken = ParseResult(
        source="endorsements",
        records=[replace(r, chamber=None) for r in base.records],
        total_items=base.total_items,
    )
    with pytest.raises(ValidationError, match=r"endorsements: only 0/56 records have seat"):
        validate({**parsed, "endorsements": broken})


def test_all_problems_reported_together(parsed, pages):
    results = {
        **parsed,
        "candidates": parse_source("candidates", keep_items(pages["candidates"], 5)),
        "endorsements": parse_source("endorsements", ""),
    }
    with pytest.raises(ValidationError) as exc:
        validate(results)
    assert [p.split(":")[0] for p in exc.value.problems] == ["candidates", "endorsements"]


def test_hash_covers_exact_rows_and_order(parsed):
    rows = snapshot_rows(parsed["candidates"].records)
    assert hash_rows(rows) == hash_rows([dict(r) for r in rows])
    assert hash_rows(list(reversed(rows))) != hash_rows(rows)
    bumped = [{**rows[0], "israel_lobby_total": rows[0]["israel_lobby_total"] + 1}, *rows[1:]]
    assert hash_rows(bumped) != hash_rows(rows)
    spaced = [{**rows[0], "lines": [line + " " for line in rows[0]["lines"]]}, *rows[1:]]
    assert hash_rows(spaced) != hash_rows(rows)


def test_changed_sources():
    meta = {"source_hashes": {"a": "1", "b": "2"}}
    assert changed_sources({"a": "1", "b": "2"}, meta, snapshot_present=True) == []
    assert changed_sources({"a": "1", "b": "X"}, meta, snapshot_present=True) == ["b"]
    assert changed_sources({"a": "1", "b": "2", "c": "3"}, meta, snapshot_present=True) == ["c"]
    assert changed_sources({"a": "1", "b": "2"}, meta, snapshot_present=False) == ["a", "b"]
