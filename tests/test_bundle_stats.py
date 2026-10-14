"""bundles.stats: the snapshots' counts as one table, their change since a git ref, and README's section."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from bundles import stats
from bundles.__main__ import main
from pallot.config import PROJECT_DIR

NOW = dt.datetime(2026, 10, 14, 15, 0, tzinfo=dt.timezone.utc)
TODAY = "2026-10-14T14:50:00+00:00"
LAST_WEEK = "2026-10-08T20:00:00+00:00"


def write(root: Path, path: str, value: object) -> None:
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(json.dumps(value), encoding="utf-8")


def snapshots(root: Path, *, cair: int = 1020, missing: int = 0, ballot_checked: str = TODAY,
              peace: tuple[str, ...] = ("federal", "state_legislature")) -> None:
    """A repo's worth of snapshot files, as the refreshes write them."""
    meta = {
        "fec": {"answers": 469, "answers_hash": "x", "candidates": 93, "races": 39,
                "last_checked": TODAY, "last_refresh": TODAY},
        "sos": {"answers": 9, "candidates": 3, "elections": 2, "last_checked": TODAY, "last_refresh": TODAY},
        "sos_ballot_order": {"answers": 254, "ballot_orders": 254, "elections": 2, "server_errors": 0,
                             "last_checked": ballot_checked, "last_refresh": ballot_checked},
        "tigerweb": {"cd": 38, "hd": 150, "missing": missing, "sd": 31,
                     "last_checked": LAST_WEEK, "last_refresh": LAST_WEEK},
        "cair": {"candidates": cair, "texas": 101, "last_checked": TODAY, "last_refresh": LAST_WEEK},
    }
    write(root, "bundles/data/meta.json", {"schema_version": 1, "sources": meta})
    rows = [{"txElectionName": "2026 NOVEMBER GENERAL ELECTION"}] * 2 + [{"txElectionName": "2026 SPECIAL ELECTION SENATE DISTRICT 22"}]
    write(root, "bundles/data/sos.json", {"answers": [
        {"request": {"method": "GET", "url": "https://sos.test/api/cbp/getElectionsByYear/"}, "value": []},
        {"request": {"method": "POST", "url": "https://sos.test/api/cbp/findQualifiedCandidates"}, "value": rows},
    ]})
    write(root, "trackaipac_cache/data/current.json", {"candidates": [
        {"chamber": "house", "state": "TX"}, {"chamber": "house", "state": "CA"}, {"chamber": "senate", "state": "TX"}]})
    write(root, "trackaipac_cache/data/meta.json", {"last_checked": TODAY, "last_refresh": TODAY})
    write(root, "voteforpeace_cache/data/current.json",
          {"candidates": [{"level": level, "state": "TX"} for level in peace]})
    write(root, "voteforpeace_cache/data/meta.json", {"last_checked": TODAY, "last_refresh": TODAY})
    write(root, "tec_cache/data/meta.json", {"counts": {"snapshot_filers": 2153, "contribs": 802975, "reports": 8281},
                                             "last_checked": TODAY, "last_refresh": "2026-10-10T15:49:33+00:00"})


def line(lines: list[str], title: str) -> str:
    return next(row for row in lines if row.startswith(f"| {title} |"))


def test_every_source_gets_a_row_with_its_candidates_broken_down(tmp_path):
    snapshots(tmp_path)
    lines = stats.table(stats.rows(stats.disk(tmp_path)), [], NOW)
    assert lines[0] == "| Source | Candidates | Also | Data changed | Checked |"
    assert line(lines, "FEC") == "| FEC | **93** | 39 races | 2026-10-14 | 2026-10-14 |"
    assert ("**3** · 2026 November General Election: 2 · 2026 Special Election Senate District 22: 1"
            in line(lines, "Texas SOS candidate lists"))
    assert "| — | 38 U.S. House · 31 State Senate · 150 State House |" in line(lines, "TIGERweb district outlines")
    assert "| **1,020** · Texas: 101 | — | 2026-10-08 | 2026-10-14 |" in line(lines, "CAIR Action")
    assert "**3** · Texas: 2 · House: 2 · Senate: 1" in line(lines, "TrackAIPAC")
    assert "**2** · Texas: 2 · Federal: 1 · State legislature: 1" in line(lines, "Vote for Peace")
    assert "| **2,153** | 802,975 contributions · 8,281 reports | 2026-10-10 |" in line(lines, "Texas Ethics Commission")
    assert "never" in line(lines, "Wikidata")


def test_a_missing_count_shows_only_when_something_is_missing(tmp_path):
    snapshots(tmp_path)
    assert "missing" not in line(stats.table(stats.rows(stats.disk(tmp_path)), [], NOW), "TIGERweb district outlines")
    snapshots(tmp_path, missing=2)
    assert "150 State House · 2 missing" in line(stats.table(stats.rows(stats.disk(tmp_path)), [], NOW),
                                                "TIGERweb district outlines")


def test_a_source_not_checked_within_its_cadence_is_marked_overdue(tmp_path):
    snapshots(tmp_path, ballot_checked="2026-10-11T15:37:29+00:00")
    lines = stats.table(stats.rows(stats.disk(tmp_path)), [], NOW)
    assert line(lines, "Texas SOS ballot orders").endswith("| 2026-10-11 | 2026-10-11 ⚠ overdue (daily) |")
    assert "overdue" not in line(lines, "TIGERweb district outlines")  # weekly, checked 6 days ago
    assert "overdue" not in line(lines, "FEC")


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True,
                   capture_output=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_since_shows_each_figure_s_change_since_the_ref(tmp_path):
    snapshots(tmp_path)
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "snapshots")
    snapshots(tmp_path, cair=1030, peace=("federal",))
    lines = stats.stats(tmp_path, since="HEAD", now=NOW)
    assert "| **1,030** (+10) · Texas: 101 |" in line(lines, "CAIR Action")
    assert "**1** (-1) · Texas: 1 (-1) · Federal: 1 |" in line(lines, "Vote for Peace")
    assert "| **93** | 39 races |" in line(lines, "FEC")
    assert "(+" not in line(stats.stats(tmp_path, since="no-such-ref", now=NOW), "CAIR Action")


def test_readme_section_is_replaced_keeping_crlf(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_bytes(b"# Title\r\n\r\n<!-- source-stats:start -->\r\nold\r\n<!-- source-stats:end -->\r\n\r\n## Next\r\n")
    stats.write_readme(readme, ["| a |", "|---|"])
    assert readme.read_bytes() == (b"# Title\r\n\r\n<!-- source-stats:start -->\r\n| a |\r\n|---|\r\n"
                                   b"<!-- source-stats:end -->\r\n\r\n## Next\r\n")
    readme.write_text("# No section\n", encoding="utf-8")
    with pytest.raises(ValueError):
        stats.write_readme(readme, ["| a |"])


def test_the_command_prints_the_repo_s_table_and_readme_has_its_section(capsys):
    assert main(["stats"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("| Source | Candidates |") and "| FEC |" in out and "| Vote for Peace |" in out
    text = (PROJECT_DIR / "README.md").read_text(encoding="utf-8")
    assert all(marker in text for marker in stats.MARKERS)
