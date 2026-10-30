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
    """Write ``state``'s bundle from the file at ``path`` (or the folder, for a list saved as several
    files: ManualList.folders); BundleError, writing nothing, when it can't be read or isn't the list."""
    cls = MANUAL.get(state.upper())
    if cls is None:
        raise BundleError(f"{state} has no list imported by hand; the states that do: {', '.join(MANUAL)}")
    folder = Path(path).is_dir()
    if folder != cls.folders:
        raise BundleError(f"{path} isn't {'a folder' if cls.folders else 'a file'}: the {cls.label}'s list is imported "
                          f"from {'the folder of its files' if cls.folders else 'its saved file'} ({cls.folder}/README.md)")
    try:
        raw = ({file.name: file.read_bytes() for file in sorted(Path(path).iterdir()) if file.is_file()} if folder
               else Path(path).read_bytes())
    except OSError as exc:
        raise BundleError(f"couldn't read {path}: {exc.strerror or exc}") from exc
    text = "" if isinstance(raw, dict) else raw.decode("utf-8", errors="replace")
    if not isinstance(raw, dict) and not raw.startswith(b"%PDF") and any(mark in text for mark in cls.challenge):
        raise BundleError(f"{path} is the site's bot check, not the list: open the page, wait for the candidates to "
                          f"show, and save it again ({cls.folder}/README.md)")
    try:
        filings = cls.parse(raw if cls.binary or isinstance(raw, dict) else text)
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
    return Outcome(cls.source, store.record(root, cls.source, answers, counts, stamp), len(answers), counts)
