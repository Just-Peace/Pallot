"""On-disk layout: current.json (the snapshot) and meta.json (how and when it was made)."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

DATA_DIR_ENV = "TEC_CACHE_DIR"
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


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


def _write_text(path: Path, text: str) -> None:
    """Atomically, with LF line endings on every platform."""
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


def write_json(path: Path, data: Any) -> None:
    _write_text(path, json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def _line(item: Any) -> str:
    return json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot_text(snapshot: dict[str, Any]) -> str:
    """JSON with one filer (and one outside-spending entry) per line, so the diff of a
    refresh shows just the candidates whose numbers changed."""
    lists = ("filers", "outside")
    parts = ["{"]
    parts += [f"{json.dumps(key)}: {_line(snapshot[key])}," for key in sorted(snapshot) if key not in lists]
    for key in lists:
        items = snapshot.get(key) or []
        parts.append(f'"{key}": [')
        if items:
            parts.append(",\n".join(_line(item) for item in items))
        parts.append("]," if key != lists[-1] else "]")
    parts.append("}")
    return "\n".join(parts) + "\n"


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    _write_text(path, snapshot_text(snapshot))


def content_hash(snapshot: dict[str, Any]) -> str:
    """What the snapshot says, leaving out when it was made and which zip it came from."""
    content = {key: snapshot.get(key) for key in ("window", "filers", "outside")}
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
