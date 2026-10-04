"""On-disk layout: history/YYYY-MM-DD.json, current.json, meta.json."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

DATA_DIR_ENV = "VOTEFORPEACE_CACHE_DIR"
PACKAGE_DATA_DIR = Path(__file__).resolve().parent / "data"
SCHEMA_VERSION = 1


def resolve_data_dir(data_dir: str | Path | None = None) -> Path:
    if data_dir is not None:
        return Path(data_dir)
    env = os.environ.get(DATA_DIR_ENV)
    return Path(env) if env else PACKAGE_DATA_DIR


class Paths:
    def __init__(self, root: Path):
        self.root = root
        self.current = root / "current.json"
        self.meta = root / "meta.json"
        self.history_dir = root / "history"

    def snapshot(self, day: date) -> Path:
        return self.history_dir / f"{day.isoformat()}.json"

    def latest_snapshot(self) -> Path | None:
        if not self.history_dir.is_dir():
            return None
        files = sorted(p for p in self.history_dir.glob("*.json") if _is_day_stem(p.stem))
        return files[-1] if files else None


def _is_day_stem(stem: str) -> bool:
    try:
        date.fromisoformat(stem)
    except ValueError:
        return False
    return True


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_json(path: Path, obj: Any) -> None:
    """Atomic write: temp file in the same directory, then os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(dump_json(obj))
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load_meta(paths: Paths) -> dict[str, Any]:
    meta = read_json(paths.meta, default={}) or {}
    meta.setdefault("schema_version", SCHEMA_VERSION)
    meta.setdefault("last_refresh", None)
    meta.setdefault("last_checked", None)
    meta.setdefault("latest_snapshot", None)
    meta.setdefault("rows_hash", None)
    return meta


def build_current(rows: list[dict[str, Any]], snapshot_name: str) -> dict[str, Any]:
    """The latest snapshot's rows, unmodified, under the day they were fetched."""
    return {"snapshot": snapshot_name, "candidates": rows}
