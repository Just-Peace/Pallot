"""On-disk layout: data/<source>.json ({"answers": [{"request", "value"}]}, one answer per line) and
data/meta.json ({"schema_version", "sources": {<source>: {"last_refresh", "last_checked", "answers_hash", counts}}})."""

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
class Loaded:
    """One source's bundled answers, and when they were last checked (epoch seconds)."""

    source: str
    checked_at: float | None
    answers: list[dict[str, Any]]  # {"request": RequestSpec's fields, "value": the source's answer}


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _write(path: Path, text: str) -> None:
    """Atomic write: temp file in the same directory, then os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _compact(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def write_answers(path: Path, answers: list[dict[str, Any]]) -> None:
    """Compact JSON, one answer per line, so a diff shows each changed answer."""
    lines = ",\n".join(_compact(answer) for answer in answers)
    _write(path, f'{{"answers":[\n{lines}\n]}}\n' if answers else '{"answers":[]}\n')


def read_meta(data_dir: Path) -> dict[str, dict[str, Any]]:
    """Each source's entry in meta.json."""
    return dict((read_json(data_dir / "meta.json", default={}) or {}).get("sources") or {})


def write_meta(data_dir: Path, source: str, entry: dict[str, Any]) -> None:
    """Replace ``source``'s entry, read again just before, so a refresh of another source meanwhile is kept."""
    sources = {**read_meta(data_dir), source: entry}
    _write(data_dir / "meta.json", json.dumps({"schema_version": SCHEMA_VERSION, "sources": sources},
                                              indent=1, sort_keys=True, ensure_ascii=False) + "\n")


def answers_hash(answers: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(answers, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def request_order(answer: dict[str, Any]) -> tuple[Any, ...]:
    """How answers are sorted: by URL, then parameters, method and body."""
    request = answer["request"]
    return (request["url"], sorted((request.get("params") or {}).items()), request.get("method") or "",
            json.dumps(request.get("json"), sort_keys=True))


def load(source: str, data_dir: Path = PACKAGE_DATA_DIR) -> Loaded:
    """``source``'s bundle in ``data_dir``; no answers when there's none."""
    checked = read_meta(data_dir).get(source, {}).get("last_checked")
    answers = (read_json(data_dir / f"{source}.json", default={}) or {}).get("answers") or []
    return Loaded(source, datetime.fromisoformat(checked).timestamp() if checked else None, list(answers))
