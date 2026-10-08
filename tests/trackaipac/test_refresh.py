from __future__ import annotations

import json
from datetime import datetime

import pytest

from trackaipac_cache.errors import FetchError, ValidationError
from trackaipac_cache.refresh import refresh, row_keys

from .conftest import at, drop_item, edit_item, keep_items, move_item_to_end, tree_bytes

PELTOLA_TOTAL = "Israel Lobby Total: $96,546"
ROW_FIELDS = {
    "candidate_id", "source", "category", "section", "name", "title", "seat_text", "seat", "state",
    "district", "chamber", "party", "incumbent", "israel_lobby_total", "donations", "ie", "pacs",
    "election_date", "campaign_url", "donate_url", "notes", "lines",
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_first_run_writes_everything(run, data_dir, parsed):
    result = run()
    assert result.status == "updated"
    assert result.changed_sources == ("candidates", "endorsements", "congress")
    assert result.record_counts == {"candidates": 54, "endorsements": 56, "congress": 535}
    assert len(result.added) == 645 and result.removed == () and result.modified == {}
    assert result.snapshot == "2026-09-01"
    assert sorted(tree_bytes(data_dir)) == ["current.json", "meta.json", "registry.json"]

    rows = [r.snapshot_row() for source in ("candidates", "endorsements", "congress") for r in parsed[source].records]
    assert set(rows[0]) == ROW_FIELDS

    registry = load(data_dir / "registry.json")
    assert registry["ak-mary-peltola"] == {"name": "Mary Peltola", "state": "AK", "district": None, "party": "D", "chamber": "senate"}
    assert registry["md-chris-van-hollen"]["party"] == "D"  # shown on /congress, not on /endorsements
    assert registry["tn-chuck-fleischmann"] == {"name": "Chuck Fleischmann", "state": "TN", "district": None, "party": None, "chamber": None}

    current = load(data_dir / "current.json")
    assert current["snapshot"] == "2026-09-01"
    assert len(current["candidates"]) == 624
    assert sum(len(c["listings"]) for c in current["candidates"]) == 645
    mejia = next(c for c in current["candidates"] if c["candidate_id"] == "nj-analilia-mejia")
    assert [(r["category"], r["section"]) for r in mejia["listings"]] == [
        ("endorsed", "Candidates Endorsed By Citizens Against AIPAC COrruption"),
        ("endorsed", "Our Endorsed Incumbents"),
        ("congress", "New Jersey"),
    ]
    assert all(r in rows for r in mejia["listings"])

    meta = load(data_dir / "meta.json")
    assert meta["last_refresh"] == meta["last_checked"] == "2026-09-01T12:00:00+00:00"
    assert "latest_snapshot" not in meta
    assert meta["schema_version"] == 2
    assert set(meta["source_hashes"]) == {"candidates", "endorsements", "congress"}


def test_json_is_diff_friendly(run, data_dir):
    run()
    text = (data_dir / "registry.json").read_text(encoding="utf-8")
    assert text.startswith('{\n  "ak-')
    assert text.endswith("}\n")
    assert "Angélica Dueñas" in text  # not \u-escaped
    assert not list(data_dir.rglob("*.tmp"))


def test_unchanged_only_touches_last_checked(run, data_dir):
    run(day=1)
    before = tree_bytes(data_dir)
    result = run(day=2)
    assert result.status == "no_changes" and str(result).startswith("no changes")
    after = tree_bytes(data_dir)
    assert sorted(after) == sorted(before)
    assert {k for k in after if after[k] != before[k]} == {"meta.json"}
    meta = load(data_dir / "meta.json")
    assert meta["last_checked"] == "2026-09-02T12:00:00+00:00"
    assert meta["last_refresh"] == "2026-09-01T12:00:00+00:00"


def test_page_noise_outside_lists_is_not_a_change(run, pages):
    run(day=1)
    noisy = pages["candidates"].replace(
        "<body", '<nav><a href="/new">New menu item</a></nav><script>var build = 42;</script><body', 1
    ).replace("Pro-Israel candidates", "Pro-Israel Candidates for 2026")
    assert noisy != pages["candidates"]
    assert run({"candidates": noisy}, day=2).status == "no_changes"


def test_changed_value_rewrites_current(run, pages, data_dir):
    run(day=1)
    changed = pages["candidates"].replace(PELTOLA_TOTAL, "Israel Lobby Total: $99,999", 1)

    result = run({"candidates": changed}, day=2)
    assert result.status == "updated"
    assert result.changed_sources == ("candidates",)
    assert result.modified == {"watchlist/ak-mary-peltola": ("israel_lobby_total", "lines")}
    assert result.added == () and result.removed == ()
    assert result.snapshot == "2026-09-02"

    current = load(data_dir / "current.json")
    peltola = next(c for c in current["candidates"] if c["candidate_id"] == "ak-mary-peltola")
    assert peltola["listings"][0]["israel_lobby_total"] == 99999
    assert "Israel Lobby Total: $99,999" in peltola["listings"][0]["lines"]
    assert current["snapshot"] == "2026-09-02"


def test_any_text_change_is_captured(run, pages):
    run(day=1)
    changed = edit_item(pages["congress"], "Ro Khanna", "This representative rejects AIPAC", "This representative firmly rejects AIPAC")
    result = run({"congress": changed}, day=2)
    assert result.modified == {"congress/ca-ro-khanna": ("lines", "notes")}


def test_second_listing_of_same_person_is_tracked_separately(run, pages):
    run(day=1)
    changed = edit_item(pages["endorsements"], "Analilia Mejia", "General Election", "Special Election", occurrence=2)
    result = run({"endorsements": changed}, day=2)
    assert result.modified == {"endorsed/nj-analilia-mejia#2": ("lines", "notes")}


def test_page_order_is_a_change(run, pages):
    run(day=1)
    result = run({"candidates": move_item_to_end(pages["candidates"], "Mary Peltola")}, day=2)
    assert result.status == "updated" and result.changed_sources == ("candidates",)
    assert result.added == result.removed == () and result.modified == {}


def test_same_day_change_overwrites_current(run, pages, data_dir):
    run(day=1)
    run({"candidates": pages["candidates"].replace(PELTOLA_TOTAL, "Israel Lobby Total: $1", 1)}, day=2)
    result = run({"candidates": pages["candidates"].replace(PELTOLA_TOTAL, "Israel Lobby Total: $2", 1)}, day=2)
    assert result.status == "updated"
    assert result.modified == {"watchlist/ak-mary-peltola": ("israel_lobby_total", "lines")}
    assert sorted(tree_bytes(data_dir)) == ["current.json", "meta.json", "registry.json"]
    peltola = next(c for c in load(data_dir / "current.json")["candidates"] if c["candidate_id"] == "ak-mary-peltola")
    assert peltola["listings"][0]["israel_lobby_total"] == 2


def test_removed_candidate_stays_in_registry(run, pages, data_dir):
    run(day=1)
    result = run({"candidates": drop_item(pages["candidates"], "Mary Peltola")}, day=2)
    assert result.removed == ("watchlist/ak-mary-peltola",)
    assert "ak-mary-peltola" in load(data_dir / "registry.json")
    assert all(c["candidate_id"] != "ak-mary-peltola" for c in load(data_dir / "current.json")["candidates"])


def test_dry_run_writes_nothing(run, pages, data_dir):
    run(day=1)
    before = tree_bytes(data_dir)
    changed = pages["candidates"].replace(PELTOLA_TOTAL, "Israel Lobby Total: $99,999", 1)
    result = run({"candidates": changed}, day=2, dry_run=True)
    assert result.status == "would_update"
    assert result.modified == {"watchlist/ak-mary-peltola": ("israel_lobby_total", "lines")}
    assert result.snapshot == "2026-09-02"
    assert "would update" in result.summary()
    assert tree_bytes(data_dir) == before

    assert run(day=3, dry_run=True).status == "no_changes"
    assert tree_bytes(data_dir) == before  # not even last_checked


def test_dry_run_on_empty_cache(run, data_dir):
    result = run(dry_run=True)
    assert result.status == "would_update" and len(result.added) == 645
    assert not data_dir.exists()


def test_force_writes_even_without_changes(run, data_dir):
    run(day=1)
    candidates = load(data_dir / "current.json")["candidates"]
    result = run(day=2, force=True)
    assert result.status == "updated"
    assert result.changed_sources == ()
    assert result.modified == {} and result.added == ()
    assert load(data_dir / "current.json")["candidates"] == candidates
    assert load(data_dir / "meta.json")["last_refresh"] == "2026-09-02T12:00:00+00:00"


def test_validation_failure_leaves_cache_untouched(run, pages, data_dir):
    run(day=1)
    before = tree_bytes(data_dir)
    with pytest.raises(ValidationError):
        run({"congress": keep_items(pages["congress"], 10)}, day=2)
    assert tree_bytes(data_dir) == before


def test_validation_failure_on_empty_cache_creates_nothing(run, data_dir):
    with pytest.raises(ValidationError):
        run({"endorsements": "<html></html>"})
    assert not data_dir.exists()


def test_missing_source_is_a_fetch_error(pages, data_dir):
    partial = {k: v for k, v in pages.items() if k != "congress"}
    with pytest.raises(FetchError, match="congress"):
        refresh(data_dir=data_dir, fetcher=lambda: partial, now=at(1))
    assert not data_dir.exists()


def test_missing_current_forces_rewrite(run, data_dir):
    run(day=1)
    (data_dir / "current.json").unlink()
    result = run(day=2)
    assert result.status == "updated"
    assert load(data_dir / "current.json")["snapshot"] == "2026-09-02"


def test_naive_now_is_treated_as_utc(pages, data_dir):
    result = refresh(data_dir=data_dir, fetcher=lambda: pages, now=datetime(2026, 9, 5, 23, 30))
    assert result.snapshot == "2026-09-05"
    assert load(data_dir / "meta.json")["last_refresh"] == "2026-09-05T23:30:00+00:00"


def test_row_keys_number_repeat_listings():
    rows = [
        {"category": "endorsed", "candidate_id": "a"},
        {"category": "endorsed", "candidate_id": "b"},
        {"category": "endorsed", "candidate_id": "a"},
        {"category": "congress", "candidate_id": "a"},
    ]
    assert row_keys(rows) == ["endorsed/a", "endorsed/b", "endorsed/a#2", "congress/a"]
