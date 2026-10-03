from __future__ import annotations

import datetime as dt
import importlib
import json

import pytest

from tec_cache import __main__ as cli
from tec_cache.errors import BlockedError, FetchError, ValidationError, ZipChangedError
from tec_cache.models import general_election, window_start
from tec_cache.refresh import refresh

from .conftest import NO_MINIMUMS, NOW, URL, csv_text, export, report, zip_bytes

refresh_module = importlib.import_module("tec_cache.refresh")  # the package's `refresh` is the function


def run(data_dir, **kwargs):
    return refresh(data_dir=data_dir, url=URL, pause=0, now=NOW, minimums=NO_MINIMUMS, **kwargs)


def snapshot(data_dir):
    return json.loads((data_dir / "current.json").read_text(encoding="utf-8"))


def by_id(document, ident):
    return next(f for f in document["filers"] if f["id"] == ident)


def test_window_follows_the_even_year_general_election():
    assert general_election(2024) == dt.date(2024, 11, 5)
    assert general_election(2026) == dt.date(2026, 11, 3)
    assert window_start(dt.date(2026, 9, 27)) == dt.date(2024, 11, 6)
    assert window_start(dt.date(2026, 11, 3)) == dt.date(2024, 11, 6)  # election day still counts toward it
    assert window_start(dt.date(2026, 11, 4)) == dt.date(2026, 11, 4)
    assert window_start(dt.date(2027, 3, 1)) == dt.date(2026, 11, 4)


def test_first_refresh_builds_the_snapshot(server, tmp_path):
    result = run(tmp_path)
    assert result.status == "updated" and result.snapshot == "2026-09-27"
    assert result.requests == 2  # the central directory, then one range for these small members
    doc = snapshot(tmp_path)
    assert doc["window"] == {"start": "2024-11-06"}
    assert [f["id"] for f in doc["filers"]] == ["00000001", "00000002", "00000003"]  # no PACs

    jane = by_id(doc, "00000001")
    assert jane["name"] == "Jane Doe" and jane["short"] == "Janie"
    assert jane["seek"] == {"office": "STATEREP", "district": "49"}
    # Only the two regular reports in the window: not the superseded one, the daily one or the old one.
    assert jane["totals"] == {
        "raised": 4000.0, "unitemized": 400.0, "spent": 700.0, "reports": 2, "cash": 7000.0, "loans": 1000.0,
        "as_of": "2025-06-30",
        "latest": {"type": "SEMIJUL", "name": "July semiannual report", "period_end": "2025-06-30", "filed": "2025-06-30"},
    }
    assert jane["by_kind"] == {"INDIVIDUAL": {"amount": 3100.0, "count": 3}, "ENTITY": {"amount": 500.0, "count": 1}}
    assert jane["by_state"] == {"TX": 2900.0, "other": 700.0}
    assert jane["by_state_count"] == {"TX": 3, "other": 1}
    assert [s["amount"] for s in jane["sizes"]] == [0.0, 400.0, 3200.0, 0.0, 0.0, 0.0]
    smith, *others = jane["top_donors"]
    assert smith == {"name": "Pat Smith", "kind": "INDIVIDUAL", "city": "AUSTIN", "state": "TX", "employer": "ACME",
                     "occupation": "CEO", "amount": 2400.0, "count": 2}
    assert [d["name"] for d in others] == ["Lee Far", "Teachers PAC"]

    [outside] = doc["outside"]
    assert outside["name"] == "Jane Doe" and outside["total"] == 2300.0  # not the daily or too-early ones
    assert outside["count"] == 3
    assert outside["spenders"] == [{"name": "Texans for Jane", "amount": 2000.0, "count": 2},
                                   {"name": "Other Group", "amount": 300.0, "count": 1}]
    assert by_id(doc, "00000003")["totals"]["raised"] == 600.0  # judicial candidates count too


def test_snapshot_file_has_one_filer_per_line(server, tmp_path):
    run(tmp_path)
    lines = (tmp_path / "current.json").read_text(encoding="utf-8").splitlines()
    filer_lines = [line for line in lines if line.startswith('{"by_kind"') or line.startswith('{"id"') or '"id":"0000000' in line]
    assert len(filer_lines) == 3
    assert json.loads((tmp_path / "current.json").read_text(encoding="utf-8"))  # still valid JSON


def test_unchanged_zip_costs_one_request(server, tmp_path):
    run(tmp_path)
    before = (tmp_path / "current.json").read_bytes()
    server.ranges.clear()
    result = run(tmp_path)
    assert result.status == "no_changes" and result.requests == 1
    assert (tmp_path / "current.json").read_bytes() == before
    assert json.loads((tmp_path / "meta.json").read_text())["last_checked"].startswith("2026-09-27")


def test_rebuilt_zip_with_the_same_numbers_keeps_the_snapshot(server, tmp_path):
    run(tmp_path)
    server.replace(zip_bytes(export(**{"CFS-ReadMe.txt": "new layouts\n"})), '"v2"')
    result = run(tmp_path)
    assert result.status == "no_changes"
    assert json.loads((tmp_path / "meta.json").read_text())["zip"]["etag"] == '"v2"'


def test_later_builds_skip_files_from_before_the_window(server, tmp_path):
    run(tmp_path)
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["members"]["contribs_01.csv"]["last"] == "20240715"
    changed = export(**{"cover.csv": csv_text("cover", [report("2", "00000001", "SEMIJUL", "20250101", "20250630",
                                                                  3000, 300, 500, 6500)])})
    server.replace(zip_bytes(changed), '"v3"')
    read = []
    original = refresh_module.Stage.load

    def spy(self, name, chunks):
        read.append(name)
        return original(self, name, chunks)

    refresh_module.Stage.load = spy
    try:
        result = run(tmp_path)
    finally:
        refresh_module.Stage.load = original
    assert "contribs_01.csv" not in read and {"contribs_02.csv", "contribs_03.csv"} <= set(read)
    assert result.status == "updated"
    assert by_id(snapshot(tmp_path), "00000001")["totals"]["cash"] == 6500.0


def test_a_zip_replaced_mid_refresh_writes_nothing(server, tmp_path):
    original = refresh_module.RemoteZip.directory

    def then_replace(self):
        directory = original(self)
        server.replace(zip_bytes(export(**{"CFS-ReadMe.txt": "v2\n"})), '"v2"')
        return directory

    refresh_module.RemoteZip.directory = then_replace
    try:
        with pytest.raises(ZipChangedError):
            run(tmp_path)
    finally:
        refresh_module.RemoteZip.directory = original
    assert not (tmp_path / "current.json").exists() and not (tmp_path / "meta.json").exists()


def test_blocked_by_tec_writes_nothing(server, tmp_path):
    server.status = 403
    with pytest.raises(BlockedError, match="--zip"):
        run(tmp_path)
    assert not tmp_path.joinpath("current.json").exists()
    assert len(server.ranges) == 1  # stops at the first refusal


def test_damaged_download_is_caught(server, tmp_path):
    data = bytearray(server.data)
    cover = data.find(b"cover.csv") + 60  # somewhere in cover.csv's compressed bytes
    data[cover] ^= 0xFF
    server.replace(bytes(data), '"v1"')
    with pytest.raises(FetchError):
        run(tmp_path)
    assert not tmp_path.joinpath("current.json").exists()


def test_a_renamed_column_aborts_before_writing(server, tmp_path):
    broken = csv_text("cover", []).replace("loanBalanceAmount", "loanBalance")
    server.replace(zip_bytes(export(**{"cover.csv": broken})), '"v2"')
    with pytest.raises(ValidationError, match="loanBalanceAmount"):
        run(tmp_path)
    assert not tmp_path.joinpath("current.json").exists()


def test_too_little_data_aborts(server, tmp_path):
    with pytest.raises(ValidationError, match="snapshot_filers"):
        refresh(data_dir=tmp_path, url=URL, pause=0, now=NOW, minimums={"snapshot_filers": 10})
    assert not tmp_path.joinpath("current.json").exists()


def test_a_downloaded_zip_needs_no_network(tmp_path):
    path = tmp_path / "TEC_CF_CSV.zip"
    path.write_bytes(zip_bytes(export()))
    result = refresh(data_dir=tmp_path / "data", zip_path=path, now=NOW, minimums=NO_MINIMUMS)
    assert result.status == "updated" and result.requests == 0
    assert by_id(snapshot(tmp_path / "data"), "00000001")["totals"]["raised"] == 4000.0


def test_dry_run_writes_nothing(server, tmp_path):
    assert run(tmp_path, dry_run=True).status == "would_update"
    assert not any(tmp_path.iterdir())


def test_cli(tmp_path, capsys, monkeypatch):
    path = tmp_path / "TEC_CF_CSV.zip"
    path.write_bytes(zip_bytes(export()))
    assert cli.main(["refresh", "--data-dir", str(tmp_path / "data"), "--zip", str(path)]) == 2  # 3 filers is too few
    assert "failed validation" in capsys.readouterr().err
    monkeypatch.setattr(refresh_module, "MIN_COUNTS", NO_MINIMUMS)
    assert cli.main(["refresh", "--data-dir", str(tmp_path / "data"), "--zip", str(path)]) == 0
    assert "updated snapshot" in capsys.readouterr().out
