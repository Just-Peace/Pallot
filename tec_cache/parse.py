"""Stream TEC's CSV members into a temporary SQLite database ("the stage"), keeping only
what a snapshot needs: candidate and officeholder filers, their reports and itemized
contributions from the window on, and direct campaign expenditures naming candidates.
The stage goes on disk so memory stays flat while a couple of GB of CSV go through.

The layouts are in CFS-ReadMe.txt inside the zip. Columns are found by name, and a member
missing one we use aborts the refresh (ValidationError) before anything is written. TEC
keeps daily pre-election and special-session reports (whose contributions are reported
again on the next regular report) in cover_t/cover_ss and cont_t/cont_ss, which we never
read, so nothing is counted twice.
"""

from __future__ import annotations

import csv
import datetime as dt
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator

from .errors import ValidationError
from .models import CANDIDATE_FILERS, DAILY_FORMS

REQUIRED: dict[str, tuple[str, ...]] = {
    "filers": (
        "filerIdent", "filerTypeCd", "filerName", "filerNameFirst", "filerNameLast", "filerNameShort",
        "filerNameSuffixCd", "filerFilerpersStatusCd", "filerEffStartDt", "filerEffStopDt",
        "ctaSeekOfficeCd", "ctaSeekOfficeDistrict", "ctaSeekOfficePlace", "ctaSeekOfficeDescr", "ctaSeekOfficeCountyDescr",
        "filerHoldOfficeCd", "filerHoldOfficeDistrict", "filerHoldOfficePlace", "filerHoldOfficeDescr",
        "filerHoldOfficeCountyDescr",
    ),
    "cover": (  # plus reportTypeCd1..10: the report types a report covers (see _report_types)
        "reportInfoIdent", "infoOnlyFlag", "filerIdent", "filerTypeCd", "formTypeCd", "receivedDt",
        "periodStartDt", "periodEndDt", "totalContribAmount", "unitemizedContribAmount", "totalExpendAmount",
        "contribsMaintainedAmount", "loanBalanceAmount",
    ),
    "contribs": (
        "reportInfoIdent", "infoOnlyFlag", "filerIdent", "filerTypeCd", "receivedDt", "contributionDt",
        "contributionAmount", "itemizeFlag", "contributorPersentTypeCd", "contributorNameOrganization", "contributorNameLast",
        "contributorNameFirst", "contributorNameSuffixCd", "contributorStreetCity", "contributorStreetStateCd",
        "contributorEmployer", "contributorOccupation",
    ),
    "cand": (
        "reportInfoIdent", "infoOnlyFlag", "formTypeCd", "filerIdent", "filerName", "expendDt", "expendAmount",
        "candidateNameOrganization", "candidateNameLast", "candidateNameFirst",
        "candidateSeekOfficeCd", "candidateSeekOfficeDistrict", "candidateSeekOfficePlace", "candidateSeekOfficeCountyDescr",
        "candidateHoldOfficeCd", "candidateHoldOfficeDistrict", "candidateHoldOfficePlace",
    ),
}

_SCHEMA = """
PRAGMA journal_mode = OFF;
PRAGMA synchronous = OFF;
CREATE TABLE filers (
    id TEXT PRIMARY KEY, type TEXT, name TEXT, first TEXT, last TEXT, short TEXT, suffix TEXT, status TEXT,
    seek_office TEXT, seek_district TEXT, seek_place TEXT, seek_descr TEXT, seek_county TEXT,
    hold_office TEXT, hold_district TEXT, hold_place TEXT, hold_descr TEXT, hold_county TEXT
);
CREATE TABLE reports (
    id TEXT PRIMARY KEY, filer TEXT, form TEXT, type TEXT, received TEXT, period_start TEXT, period_end TEXT,
    raised REAL, unitemized REAL, spent REAL, cash REAL, loans REAL
);
CREATE TABLE contribs (
    report TEXT, filer TEXT, dt TEXT, amount REAL, kind TEXT, who TEXT, name TEXT, city TEXT, state TEXT,
    employer TEXT, occupation TEXT
);
CREATE TABLE dce (
    spender TEXT, dt TEXT, amount REAL, first TEXT, last TEXT, org TEXT,
    seek_office TEXT, seek_district TEXT, seek_place TEXT, seek_county TEXT,
    hold_office TEXT, hold_district TEXT, hold_place TEXT
);
"""

_BATCH = 5_000


def member_kind(name: str) -> str | None:
    """Which layout a member has: "filers", "cover", "contribs" (contribs_NN.csv) or "cand"."""
    if re.fullmatch(r"contribs_\d+\.csv", name):
        return "contribs"
    return {"filers.csv": "filers", "cover.csv": "cover", "cand.csv": "cand"}.get(name)


def contrib_number(name: str) -> int | None:
    found = re.fullmatch(r"contribs_(\d+)\.csv", name)
    return int(found.group(1)) if found else None


def _text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def lines(chunks: Iterable[bytes]) -> Iterator[str]:
    """Text lines (with their newline, as csv wants them) from a member's bytes."""
    pending = b""
    for chunk in chunks:
        pending += chunk
        *complete, pending = pending.split(b"\n")
        for line in complete:
            yield _text(line) + "\n"
    if pending:
        yield _text(pending)


def _amount(text: str) -> float | None:
    try:
        return float(text) if text else None
    except ValueError:
        return None


def _clean(text: str) -> str:
    return " ".join(text.split())


def _report_types(header: list[str]) -> list[int]:
    """Where a cover sheet's report types are: an array of up to ten columns (reportTypeCd1…)."""
    return [i for i, column in enumerate(header) if re.fullmatch(r"reportTypeCd\d*", column)]


@dataclass
class MemberStats:
    rows: int = 0
    kept: int = 0
    first: str = ""  # earliest and latest date the member's reports were received (yyyymmdd)
    last: str = ""


class Stage:
    def __init__(self, path: Path, window: dt.date):
        self.path = path
        self.start = window.strftime("%Y%m%d")
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.executescript(_SCHEMA)
        self._types: list[int] = []  # the current cover.csv's report-type columns

    def close(self) -> None:
        self.db.close()

    def load(self, name: str, chunks: Iterable[bytes]) -> MemberStats:
        kind = member_kind(name)
        if kind is None:
            raise ValueError(f"no layout for {name}")
        reader = csv.reader(lines(chunks))
        header = [column.strip() for column in next(reader, [])]
        missing = [column for column in REQUIRED[kind] if column not in header]
        if kind == "cover" and not _report_types(header):
            missing.append("reportTypeCd1")
        if missing:
            raise ValidationError([f"{name}: missing column{'s' if len(missing) > 1 else ''} {', '.join(missing)}"])
        at = {column: header.index(column) for column in REQUIRED[kind]}
        self._types = _report_types(header)
        stats = MemberStats()
        table, row_of = {
            "filers": ("filers", self._filer),
            "cover": ("reports", self._report),
            "contribs": ("contribs", self._contribution),
            "cand": ("dce", self._expenditure),
        }[kind]
        width = len(header)
        received_at = at.get("receivedDt")
        batch: list[tuple] = []
        current: dict[str, tuple[tuple, tuple]] = {}  # filers: id -> (preference, row)
        self.db.execute("BEGIN")
        for fields in reader:
            if len(fields) < width:
                fields += [""] * (width - len(fields))
            stats.rows += 1
            if kind == "contribs":
                received = fields[received_at]
                if len(received) == 8:
                    stats.first = min(stats.first or received, received)
                    stats.last = max(stats.last, received)
            row = row_of(fields, at)
            if row is None:
                continue
            stats.kept += 1
            if kind == "filers":
                # One filer can have several rows (Greg Abbott: governor now, and once a Supreme Court
                # justice). Keep the one still in effect: no stop date, latest start, a current status.
                preference = (fields[at["filerEffStopDt"]] == "", fields[at["filerEffStartDt"]], row[7].startswith("CURRENT"))
                if row[0] not in current or preference > current[row[0]][0]:
                    current[row[0]] = (preference, row)
                continue
            batch.append(row)
            if len(batch) >= _BATCH:
                self._insert(table, batch)
        if kind == "filers":
            batch = [row for _, row in current.values()]
        self._insert(table, batch)
        self.db.execute("COMMIT")
        return stats

    def _insert(self, table: str, batch: list[tuple]) -> None:
        if batch:
            marks = ", ".join("?" * len(batch[0]))
            verb = "INSERT OR REPLACE" if table in ("filers", "reports") else "INSERT"
            self.db.executemany(f"{verb} INTO {table} VALUES ({marks})", batch)
            batch.clear()

    # -- one row of each layout (None: not needed) --------------------------------------

    def _filer(self, f: list[str], at: dict[str, int]) -> tuple | None:
        get: Callable[[str], str] = lambda column: _clean(f[at[column]])
        if get("filerTypeCd") not in CANDIDATE_FILERS:
            return None
        return (
            get("filerIdent"), get("filerTypeCd"), get("filerName"), get("filerNameFirst"), get("filerNameLast"),
            get("filerNameShort"), get("filerNameSuffixCd"), get("filerFilerpersStatusCd"),
            get("ctaSeekOfficeCd"), get("ctaSeekOfficeDistrict"), get("ctaSeekOfficePlace"), get("ctaSeekOfficeDescr"),
            get("ctaSeekOfficeCountyDescr"),
            get("filerHoldOfficeCd"), get("filerHoldOfficeDistrict"), get("filerHoldOfficePlace"),
            get("filerHoldOfficeDescr"), get("filerHoldOfficeCountyDescr"),
        )

    def _report(self, f: list[str], at: dict[str, int]) -> tuple | None:
        get: Callable[[str], str] = lambda column: f[at[column]].strip()
        if get("filerTypeCd") not in CANDIDATE_FILERS or get("infoOnlyFlag") == "Y" or get("periodEndDt") < self.start:
            return None
        types = ",".join(t for t in (f[i].strip() for i in self._types) if t)
        return (
            get("reportInfoIdent"), get("filerIdent"), get("formTypeCd"), types, get("receivedDt"),
            get("periodStartDt"), get("periodEndDt"),
            _amount(get("totalContribAmount")), _amount(get("unitemizedContribAmount")), _amount(get("totalExpendAmount")),
            _amount(get("contribsMaintainedAmount")), _amount(get("loanBalanceAmount")),
        )

    def _contribution(self, f: list[str], at: dict[str, int]) -> tuple | None:
        # Most rows are PACs' (ActBlue Texas alone has millions): reject them before any cleanup.
        if (
            f[at["filerTypeCd"]] not in CANDIDATE_FILERS
            or f[at["infoOnlyFlag"]] == "Y"
            or f[at["receivedDt"]] < self.start
            or f[at["itemizeFlag"]] == "N"  # unitemized: counted in the cover sheet's unitemized total
        ):
            return None
        get: Callable[[str], str] = lambda column: _clean(f[at[column]])
        amount = _amount(get("contributionAmount"))
        if amount is None:
            return None
        entity = get("contributorPersentTypeCd") == "ENTITY"
        first, last, org = get("contributorNameFirst"), get("contributorNameLast"), get("contributorNameOrganization")
        suffix = get("contributorNameSuffixCd")
        name = org if entity else " ".join(part for part in (first, last, suffix) if part)
        who = org.upper() if entity else f"{last.upper()}, {first.upper()}"
        date = get("contributionDt")
        return (
            get("reportInfoIdent"), get("filerIdent"), date if len(date) == 8 else "00000000", amount,
            "ENTITY" if entity else "INDIVIDUAL", who, name or org or last, get("contributorStreetCity"),
            get("contributorStreetStateCd").upper(), get("contributorEmployer"), get("contributorOccupation"),
        )

    def _expenditure(self, f: list[str], at: dict[str, int]) -> tuple | None:
        get: Callable[[str], str] = lambda column: _clean(f[at[column]])
        if get("infoOnlyFlag") == "Y" or get("formTypeCd") in DAILY_FORMS or get("expendDt") < self.start:
            return None
        amount = _amount(get("expendAmount"))
        if not amount:
            return None
        return (
            get("filerName"), get("expendDt"), amount, get("candidateNameFirst"), get("candidateNameLast"),
            get("candidateNameOrganization"),
            get("candidateSeekOfficeCd"), get("candidateSeekOfficeDistrict"), get("candidateSeekOfficePlace"),
            get("candidateSeekOfficeCountyDescr"),
            get("candidateHoldOfficeCd"), get("candidateHoldOfficeDistrict"), get("candidateHoldOfficePlace"),
        )

    def counts(self) -> dict[str, int]:
        return {
            table: self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("filers", "reports", "contribs", "dce")
        }
