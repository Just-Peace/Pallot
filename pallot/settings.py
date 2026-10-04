"""Source on/off switches from the Settings page, kept in data/settings.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .fsutil import write_text_atomic

DEFAULT_SOURCES: dict[str, bool] = {
    "tigerweb": True, "osm_tiles": True, "suggestions": True, "sos": True, "key_dates": True, "ballotpedia": True,
    "trackaipac": True, "voteforpeace": True, "fec": True, "tec": True, "polls": True, "election_precincts": True, "county_precincts": True,
}


class Settings:
    """``extra``: the ids of sources found at startup (the endorsement lists), on by default."""

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
        if source_id not in self._sources:
            raise KeyError(source_id)
        self._sources[source_id] = enabled
        write_text_atomic(self.path, json.dumps({"sources": self._sources}, indent=2) + "\n")
