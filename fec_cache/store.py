"""On-disk layout: current.json ({"snapshot", "answers": [{"request", "value"}]}) and meta.json."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PACKAGE_DATA_DIR = Path(__file__).resolve().parent / "data"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Snapshot:
    """The bundled answers, and when they were last checked against the FEC (epoch seconds)."""

    day: str | None  # the day the answers last changed, "2026-10-08"
    checked_at: float | None
    answers: list[dict[str, Any]]  # {"request": RequestSpec.dumps() as an object, "value": the FEC's answer}


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, obj: Any) -> None:
    """Atomic write: temp file in the same directory, then os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def answers_hash(answers: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(answers, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load(data_dir: Path = PACKAGE_DATA_DIR) -> Snapshot:
    """The snapshot in ``data_dir``; no answers when there's none."""
    current = read_json(data_dir / "current.json", default={}) or {}
    meta = read_json(data_dir / "meta.json", default={}) or {}
    checked = meta.get("last_checked")
    return Snapshot(
        day=current.get("snapshot"),
        checked_at=datetime.fromisoformat(checked).timestamp() if checked else None,
        answers=list(current.get("answers") or []),
    )
