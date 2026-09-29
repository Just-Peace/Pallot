"""A data set that ships inside a package in this repo (trackaipac_cache, tec_cache) and is
copied into VoteBot's data folder on first use. Lookups read the copy, reloading it when
its file changes; only Refresh in Settings fetches anything, and Reset goes back to the
bundled one.
"""

from __future__ import annotations

import contextlib
import json
import shutil
from importlib import resources
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, ContextManager

from ..matching import NameIndex


def summary_of(result: Any) -> str:
    """What a package's refresh() reported, as one message for Settings."""
    return result.summary() if hasattr(result, "summary") else str(result)


class BundledSnapshot:
    """``current.json`` and ``meta.json`` in ``data_dir``, seeded from ``package``/data (or
    ``bundled_dir``, in tests). Subclasses say how to throw away refreshed data (_discard)
    and how to refresh (_refresh)."""

    EMPTY: dict[str, Any] = {"snapshot": None}  # what document() returns before there's any data

    def __init__(
        self,
        data_dir: Path,
        package: ModuleType,
        *,
        refresh_fn: Callable[..., Any] | None = None,
        bundled_dir: Path | None = None,
    ):
        self.data_dir = data_dir
        self._package = package
        self._refresh_fn = refresh_fn
        self._bundled_dir = bundled_dir
        self._doc: tuple[tuple[int, int], dict[str, Any]] | None = None
        self._indexes: dict[str, NameIndex] = {}
        self.last_error: str | None = None  # why the last refresh failed, for Settings

    @property
    def current_path(self) -> Path:
        return self.data_dir / "current.json"

    @property
    def meta_path(self) -> Path:
        return self.data_dir / "meta.json"

    def _bundled(self) -> ContextManager[Path]:
        if self._bundled_dir is not None:
            return contextlib.nullcontext(self._bundled_dir)
        return resources.as_file(resources.files(self._package) / "data")

    def ensure_seeded(self) -> bool:
        """Copy in the package's bundled snapshot if we have no data yet; True if copied."""
        if self.current_path.exists():
            return False
        with self._bundled() as source:
            if not (source / "current.json").exists():
                return False
            shutil.copytree(source, self.data_dir, dirs_exist_ok=True)
        return True

    def reset(self) -> None:
        """Throw away refreshed data and go back to the bundled snapshot."""
        self._discard()
        self._doc = None
        self._indexes = {}
        self.last_error = None
        self.ensure_seeded()

    def _discard(self) -> None:
        raise NotImplementedError

    async def refresh(self) -> str:
        """Rebuild the snapshot (the package writes only after it validated what it fetched);
        returns the package's summary."""
        self.ensure_seeded()
        try:
            summary = await self._refresh()
        except Exception as exc:
            self.last_error = str(exc)
            raise
        self.last_error = None
        return summary

    async def _refresh(self) -> str:
        raise NotImplementedError

    def _signature(self) -> tuple[int, int] | None:
        try:
            stat = self.current_path.stat()
        except FileNotFoundError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def document(self) -> dict[str, Any]:
        """The parsed current.json, re-read only when the file changed."""
        signature = self._signature()
        if signature is None:
            return dict(self.EMPTY)
        if self._doc is None or self._doc[0] != signature:
            self._doc = (signature, json.loads(self.current_path.read_text(encoding="utf-8")))
            self._indexes = {}
        return self._doc[1]

    def meta(self) -> dict[str, Any]:
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}

    def _index(self, key: str, build: Callable[[dict[str, Any]], NameIndex]) -> NameIndex:
        """A name index over the document, built once per version of the file."""
        document = self.document()  # (re)loads, clearing the indexes when the file changed
        if key not in self._indexes:
            self._indexes[key] = build(document)
        return self._indexes[key]
