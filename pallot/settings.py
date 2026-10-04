"""Source on/off switches from the Settings page, kept in data/settings.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .fsutil import write_text_atomic

DEFAULT_SOURCES: dict[str, bool] = {
    "tigerweb": True, "osm_tiles": True, "suggestions": True, "sos": True, "key_dates": True, "ballotpedia": False,
    "trackaipac": True, "voteforpeace": False, "fec": True, "tec": True, "polls": True, "election_precincts": True, "county_precincts": True,
}


class Settings:
    """``extra``: the ids of the endorsement lists and feeds, on by default."""

    def __init__(self, path: Path, extra: Iterable[str] = ()):
        self.path = path
        self._sources = {**DEFAULT_SOURCES, **dict.fromkeys(extra, True)}
        try:
            saved = json.loads(path.read_text(encoding="utf-8")).get("sources", {})
        except (FileNotFoundError, ValueError, AttributeError):
            saved = {}
        self._sources.update({k: bool(v) for k, v in saved.items() if k in self._sources})

    def enabled(self, source_id: str) -> bool:
        return self._sources.get(source_id, True)

    def set_enabled(self, source_id: str, enabled: bool) -> None:
        self.set_many({source_id: enabled})

    def set_many(self, changes: dict[str, bool]) -> None:
        """Several switches at once (a group of sources in Settings), saved in one write."""
        if unknown := changes.keys() - self._sources.keys():
            raise KeyError(", ".join(sorted(unknown)))
        self._sources.update(changes)
        write_text_atomic(self.path, json.dumps({"sources": self._sources}, indent=2) + "\n")
