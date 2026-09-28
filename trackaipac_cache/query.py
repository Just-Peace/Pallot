"""Read-side API. Reads current.json, except history() (registry.json + history/*.json)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

from .errors import AmbiguousNameError
from .models import CATEGORIES, STATES, Candidate, Snapshot
from .parser import normalize_name
from .store import Paths, read_json, resolve_data_dir

T = TypeVar("T")

_STATE_BY_NAME = {name.lower(): code for code, name in STATES.items()}
_PARTIES = {
    "d": "D", "dem": "D", "democrat": "D", "democratic": "D",
    "r": "R", "rep": "R", "gop": "R", "republican": "R",
    "i": "I", "ind": "I", "independent": "I",
}
_CHAMBERS = {"house": "house", "senate": "senate"}

_file_cache: dict[tuple[Path, str], tuple[tuple[int, int, int], Any]] = {}


def _load(path: Path, transform: Callable[[Any], T], default: T) -> T:
    """Load and transform a JSON file, cached until the file changes.

    st_ino is part of the key because store.write_json replaces files atomically (new
    file id), and mtime alone is too coarse on some filesystems to spot a same-size rewrite.
    """
    try:
        stat = path.stat()
    except FileNotFoundError:
        return default
    signature = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
    key = (path.resolve(), getattr(transform, "__name__", repr(transform)))
    hit = _file_cache.get(key)
    if hit and hit[0] == signature:
        return hit[1]
    value = transform(read_json(path))
    _file_cache[key] = (signature, value)
    return value


def _to_candidates(doc: Any) -> tuple[Candidate, ...]:
    return tuple(Candidate.from_dict(c) for c in (doc or {}).get("candidates", []))


def _identity(doc: Any) -> dict[str, dict[str, Any]]:
    return doc or {}


def _rows(doc: Any) -> list[dict[str, Any]]:
    return doc or []


def _paths(data_dir: str | Path | None) -> Paths:
    return Paths(resolve_data_dir(data_dir))


def _candidates(data_dir: str | Path | None) -> tuple[Candidate, ...]:
    return _load(_paths(data_dir).current, _to_candidates, ())


def normalize_state(value: str) -> str:
    """"TX", "tx" or "Texas" -> "TX"."""
    v = value.strip()
    if v.upper() in STATES:
        return v.upper()
    code = _STATE_BY_NAME.get(v.lower())
    if code is None:
        raise ValueError(f"unknown state: {value!r}")
    return code


def normalize_party(value: str) -> str:
    """"D"/"Democrat"/"Democratic" -> "D", likewise R and I."""
    party = _PARTIES.get(value.strip().lower())
    if party is None:
        raise ValueError(f"unknown party: {value!r}")
    return party


def _filter(
    candidates: tuple[Candidate, ...],
    category: str,
    state: str | None = None,
    party: str | None = None,
    chamber: str | None = None,
) -> list[Candidate]:
    state_code = normalize_state(state) if state else None
    party_code = normalize_party(party) if party else None
    chamber_name = _CHAMBERS.get(chamber.strip().lower()) if chamber else None
    if chamber and chamber_name is None:
        raise ValueError(f"unknown chamber: {chamber!r} (use 'house' or 'senate')")
    return [
        c
        for c in candidates
        if category in c.categories
        and (state_code is None or c.state == state_code)
        and (party_code is None or c.party == party_code)
        and (chamber_name is None or c.chamber == chamber_name)
    ]


def get_candidate(name_or_id: str, *, data_dir: str | Path | None = None) -> Candidate | None:
    """Look up by candidate_id or by name (accent/case/punctuation-insensitive).

    Raises AmbiguousNameError when a name matches more than one person.
    """
    candidates = _candidates(data_dir)
    key = name_or_id.strip()
    for c in candidates:
        if c.candidate_id == key.lower():
            return c
    wanted = normalize_name(key)
    matches = [c for c in candidates if normalize_name(c.name) == wanted]
    if len(matches) > 1:
        raise AmbiguousNameError(key, [c.candidate_id for c in matches])
    return matches[0] if matches else None


def list_watchlist(
    state: str | None = None, party: str | None = None, *, data_dir: str | Path | None = None
) -> list[Candidate]:
    return _filter(_candidates(data_dir), "watchlist", state=state, party=party)


def list_endorsed(
    state: str | None = None, incumbents_only: bool | None = None, *, data_dir: str | Path | None = None
) -> list[Candidate]:
    """incumbents_only: None -> everyone, True -> people listed as sitting members
    ("U.S. Representative"/"U.S. Senator"), False -> people listed as challengers
    ("Candidate for …"). Someone listed both ways on the page appears in both."""
    endorsed = _filter(_candidates(data_dir), "endorsed", state=state)
    if incumbents_only is None:
        return endorsed
    return [c for c in endorsed if any(item.incumbent is incumbents_only for item in c.listings_in("endorsed"))]


def list_congress(
    state: str | None = None,
    party: str | None = None,
    chamber: str | None = None,
    *,
    data_dir: str | Path | None = None,
) -> list[Candidate]:
    return _filter(_candidates(data_dir), "congress", state=state, party=party, chamber=chamber)


def search(query: str, *, data_dir: str | Path | None = None) -> list[Candidate]:
    """Substring search over name, id, seat, state name and PACs; name matches rank first."""
    wanted = normalize_name(query)
    if not wanted:
        return []
    ranked: list[tuple[int, str, str, Candidate]] = []
    for c in _candidates(data_dir):
        name = normalize_name(c.name)
        if name.startswith(wanted):
            rank = 0
        elif wanted in name:
            rank = 1
        else:
            pacs = [pac for item in c.listings for pac in item.pacs]
            seats = [item.seat or "" for item in c.listings]
            fields = (c.candidate_id, c.seat or "", STATES.get(c.state or "", ""), *seats, *pacs)
            if not any(wanted in normalize_name(f) for f in fields):
                continue
            rank = 2
        ranked.append((rank, c.name.lower(), c.candidate_id, c))
    ranked.sort(key=lambda item: item[:3])
    return [item[3] for item in ranked]


def history(name_or_id: str, *, data_dir: str | Path | None = None) -> list[Snapshot]:
    """Every snapshot row for one person across history/*.json, oldest first (within a
    day: by category, then page order).

    Resolves through registry.json, so people no longer listed are still found.
    """
    paths = _paths(data_dir)
    candidate_id = _resolve_id(name_or_id, paths)
    if candidate_id is None:
        return []
    snapshots: list[Snapshot] = []
    for path in paths.history_files():
        day = date.fromisoformat(path.stem)
        rows = [r for r in _load(path, _rows, []) if r.get("candidate_id") == candidate_id]
        rows.sort(key=lambda r: CATEGORIES.index(r["category"]) if r.get("category") in CATEGORIES else len(CATEGORIES))
        snapshots += [Snapshot.from_history(day, r) for r in rows]
    return snapshots


def last_refreshed(*, data_dir: str | Path | None = None) -> datetime | None:
    """When data was last written (not merely checked); None if the cache was never filled."""
    meta = read_json(_paths(data_dir).meta, default={}) or {}
    stamp = meta.get("last_refresh")
    return datetime.fromisoformat(stamp) if stamp else None


def _resolve_id(name_or_id: str, paths: Paths) -> str | None:
    registry = _load(paths.registry, _identity, {})
    key = name_or_id.strip()
    if key.lower() in registry:
        return key.lower()
    wanted = normalize_name(key)
    matches = sorted(cid for cid, ident in registry.items() if normalize_name(ident.get("name", "")) == wanted)
    if len(matches) > 1:
        raise AmbiguousNameError(key, matches)
    return matches[0] if matches else None
