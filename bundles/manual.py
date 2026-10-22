"""import_list(): a state's list saved by hand (its site blocks scripts) -> its manual bundle.

The file is read with the state's adapter and refused unless it holds the next general
election's candidates. What's bundled is their parsed filings, under the key a lookup reads
(ManualList.spec), never the file, which can carry addresses, phones and emails.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Callable

from pallot.sources.fec import general_day
from pallot.states import ManualList, filings_json
from pallot.states.adapters import ADAPTERS

from . import store
from .entry import BundleError
from .refresh import Outcome, json_request

MANUAL = {state: cls for state, cls in ADAPTERS.items() if issubclass(cls, ManualList)}  # "AZ" -> AzList


def import_list(state: str, path: str | Path, *, data_dir: str | Path | None = None,
                today: Callable[[], dt.date] = dt.date.today, now: dt.datetime | None = None) -> Outcome:
    """Write ``state``'s bundle from the file at ``path``; BundleError, writing nothing, when the
    file can't be read or isn't the list."""
    cls = MANUAL.get(state.upper())
    if cls is None:
        raise BundleError(f"{state} has no list imported by hand; the states that do: {', '.join(MANUAL)}")
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise BundleError(f"couldn't read {path}: {exc.strerror or exc}") from exc
    text = raw.decode("utf-8", errors="replace")
    if not raw.startswith(b"%PDF") and any(mark in text for mark in cls.challenge):
        raise BundleError(f"{path} is the site's bot check, not the list: open the page, wait for the candidates to "
                          f"show, and save it again ({cls.folder}/README.md)")
    try:
        filings = cls.parse(raw if cls.binary else text)
    except ValueError as exc:
        raise BundleError(f"{path} isn't a list the {cls.label}'s reader understands: {exc}") from exc
    day = general_day(today())
    found = [f for f in filings if f.day == day.isoformat()]
    if not found:
        days = ", ".join(sorted({f.day for f in filings}))
        raise BundleError(f"{path} has no candidates for the general election on {day.isoformat()} (only {days})")
    answers = [{"request": json_request(cls.spec(day)), "value": filings_json(found)}]
    counts = {"races": len({f.office_id for f in found}), "candidates": len(found)}
    root = Path(data_dir) if data_dir else store.PACKAGE_DATA_DIR
    stamp = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc).isoformat(timespec="seconds")
    digest = store.answers_hash(answers)
    meta = store.read_meta(root).get(cls.source, {})
    unchanged = meta.get("answers_hash") == digest and (root / f"{cls.source}.json").exists()
    if not unchanged:
        store.write_answers(root / f"{cls.source}.json", answers)
    store.write_meta(root, cls.source, {
        "last_refresh": meta.get("last_refresh", stamp) if unchanged else stamp, "last_checked": stamp,
        "answers_hash": digest, "answers": len(answers), **counts})
    return Outcome(cls.source, "no_changes" if unchanged else "updated", len(answers), counts)
