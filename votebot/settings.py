"""Source on/off switches from the Settings page, kept in data/settings.json."""

from __future__ import annotations

import json
from pathlib import Path

from .fsutil import write_text_atomic

DEFAULT_SOURCES: dict[str, bool] = {
    "tigerweb": True, "osm_tiles": True, "suggestions": True, "sos": True, "key_dates": True, "ballotpedia": True,
    "trackaipac": True, "fec": True, "tec": True, "polls": True, "election_precincts": True, "county_precincts": True,
}


class Settings:
    def __init__(self, path: Path):
        self.path = path
        self._sources = dict(DEFAULT_SOURCES)
        try:
            saved = json.loads(path.read_text(encoding="utf-8")).get("sources", {})
        except (FileNotFoundError, ValueError, AttributeError):
            saved = {}
        self._sources.update({k: bool(v) for k, v in saved.items() if k in DEFAULT_SOURCES})

    def enabled(self, source_id: str) -> bool:
        return self._sources.get(source_id, True)

    def set_enabled(self, source_id: str, enabled: bool) -> None:
        if source_id not in DEFAULT_SOURCES:
            raise KeyError(source_id)
        self._sources[source_id] = enabled
        write_text_atomic(self.path, json.dumps({"sources": self._sources}, indent=2) + "\n")
