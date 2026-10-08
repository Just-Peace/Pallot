from __future__ import annotations

import json

import pytest

from voteforpeace_cache.errors import ValidationError
from voteforpeace_cache.parser import parse_page
from voteforpeace_cache.refresh import refresh

from .conftest import at, edit


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def files(root):
    return sorted(str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*") if p.is_file())


def test_first_run_writes_everything(page, tmp_path):
    result = refresh(data_dir=tmp_path, fetcher=lambda: page, now=at(4))
    assert result.status == "updated" and result.record_count == 197
    assert len(result.added) == 197 and result.removed == () and result.modified == {}
    assert files(tmp_path) == ["current.json", "meta.json"]
    rows = [r.snapshot_row() for r in parse_page(page).records]
    assert load(tmp_path / "current.json") == {"snapshot": "2026-10-04", "candidates": rows}
    meta = load(tmp_path / "meta.json")
    assert "latest_snapshot" not in meta
    assert (meta["last_refresh"], meta["last_checked"]) == ("2026-10-04T12:00:00+00:00", "2026-10-04T12:00:00+00:00")


def test_an_unchanged_site_only_updates_last_checked(page, tmp_path):
    refresh(data_dir=tmp_path, fetcher=lambda: page, now=at(4))
    result = refresh(data_dir=tmp_path, fetcher=lambda: page, now=at(5))
    assert result.status == "no_changes" and "no changes" in result.summary()
    meta = load(tmp_path / "meta.json")
    assert (meta["last_refresh"], meta["last_checked"]) == ("2026-10-04T12:00:00+00:00", "2026-10-05T12:00:00+00:00")
    assert files(tmp_path) == ["current.json", "meta.json"]


def test_a_change_rewrites_current(page, tmp_path):
    refresh(data_dir=tmp_path, fetcher=lambda: page, now=at(4))
    changed = edit(page, '"our_rating":"vote","public_notes":"Candidate\'s foreign', '"our_rating":"reject","public_notes":"Candidate\'s foreign')
    result = refresh(data_dir=tmp_path, fetcher=lambda: changed, now=at(6))
    assert result.status == "updated" and result.modified == {"TX/james-talarico": ("rating",)}
    assert result.added == () and result.removed == ()
    assert load(tmp_path / "current.json")["snapshot"] == "2026-10-06"
    talarico = next(p for p in load(tmp_path / "current.json")["candidates"] if p["slug"] == "james-talarico")
    assert talarico["rating"] == "reject"
    assert files(tmp_path) == ["current.json", "meta.json"]


def test_dry_run_and_force(page, tmp_path):
    assert refresh(data_dir=tmp_path, fetcher=lambda: page, now=at(4), dry_run=True).status == "would_update"
    assert files(tmp_path) == []
    refresh(data_dir=tmp_path, fetcher=lambda: page, now=at(4))
    assert refresh(data_dir=tmp_path, fetcher=lambda: page, now=at(7), force=True).status == "updated"
    assert load(tmp_path / "current.json")["snapshot"] == "2026-10-07"


def test_a_broken_page_writes_nothing(page, tmp_path):
    refresh(data_dir=tmp_path, fetcher=lambda: page, now=at(4))
    before = {name: (tmp_path / name).read_bytes() for name in files(tmp_path)}
    unrated = page.replace('\\"our_rating\\":\\"vote\\"', '\\"our_rating\\":\\"endorse\\"')
    with pytest.raises(ValidationError, match="unknown ratings: endorse"):
        refresh(data_dir=tmp_path, fetcher=lambda: unrated, now=at(5))
    assert {name: (tmp_path / name).read_bytes() for name in files(tmp_path)} == before
