"""Which sources a request uses. Pallot's defaults are declared in sources.toml beside this
module; an optional sources.toml in the data folder changes them for everyone using this
Pallot. The voter's own choices are kept in their browser (localStorage) and sent with each
request in the ``X-Pallot-Sources`` header, so one voter's switches never change another's
ballot."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

HEADER = "X-Pallot-Sources"
DEFAULTS_FILE = Path(__file__).with_name("sources.toml")


class BadSourcesFile(ValueError):
    """A sources.toml that can't be used; its message names the file and what's wrong."""


def read_sources_file(path: Path, known: Iterable[str] | None = None) -> dict[str, bool]:
    """The ``[sources]`` table of a sources.toml, ids to true or false; {} when there's no file.
    With ``known``, an id that isn't one of them is refused, so a typo doesn't go unnoticed."""
    try:
        data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise BadSourcesFile(f"{path}: {exc}") from exc
    table = data.get("sources", {})
    if not isinstance(table, dict) or set(data) - {"sources"}:
        raise BadSourcesFile(f"{path}: put the switches under [sources], as id = true or false")
    if wrong := sorted(k for k, v in table.items() if not isinstance(v, bool)):
        raise BadSourcesFile(f"{path}: {', '.join(wrong)} must be true or false")
    if known is not None and (unknown := sorted(set(table) - set(known))):
        raise BadSourcesFile(f"{path}: no such source {', '.join(unknown)} (the ids are: {', '.join(sorted(known))})")
    return dict(table)


DEFAULT_SOURCES: dict[str, bool] = read_sources_file(DEFAULTS_FILE)


def defaults(extra: Iterable[str] = (), overrides: Path | None = None) -> dict[str, bool]:
    """DEFAULT_SOURCES, with ``extra`` (the endorsement lists' and feeds' ids) on unless the file
    turns one off, and the data folder's ``overrides`` file on top."""
    found = {**dict.fromkeys(extra, True), **DEFAULT_SOURCES}
    if overrides is not None:
        found.update(read_sources_file(overrides, found))
    return found


class Sources:
    """The sources on for one request: ``defaults`` (defaults()), with the voter's ``chosen``
    switches on top; ids that aren't sources are ignored."""

    def __init__(self, defaults: Mapping[str, bool], chosen: Mapping[str, bool] | None = None):
        self._defaults = dict(defaults)
        self._sources = {**self._defaults, **{k: v for k, v in (chosen or {}).items() if k in self._defaults}}

    def enabled(self, source_id: str) -> bool:
        return self._sources.get(source_id, True)

    def chosen(self, header: str | None) -> Sources:
        """These defaults with the voter's choices from the header: a JSON object of ids to true or
        false. One that can't be read leaves the defaults, as does any entry that isn't a boolean."""
        try:
            raw = json.loads(header) if header else {}
        except ValueError:
            raw = {}
        choices = {k: v for k, v in raw.items() if isinstance(v, bool)} if isinstance(raw, dict) else {}
        return Sources(self._defaults, choices)
