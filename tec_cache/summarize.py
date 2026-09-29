"""Turn the stage into a snapshot: per candidate or officeholder, the totals from their
reports in the window, and breakdowns of those reports' itemized contributions.

A filer's totals are sums over their candidate/officeholder reports whose period ends in
the window (so the first may start a few months earlier). Cash on hand and outstanding
loans come from the latest of them. Daily pre-election and special-session reports aren't
in the files we read (see parse), so nothing is counted twice.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict
from typing import Any

from .models import REPORT_FORMS, REPORT_NAMES, SIZE_BUCKETS, TOP_DONORS, TOP_SPENDERS, tec_date


def _money(value: float | None) -> float:
    return round(value or 0.0, 2)


def _drop_empty(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if value not in (None, "", {}, [])}


def _office(code: str, district: str, place: str, county: str, descr: str = "") -> dict[str, str]:
    return _drop_empty({"office": code, "district": district, "place": place, "county": county, "descr": descr})


def _report_name(types: str) -> tuple[str, str]:
    """A report can cover several report types ("SEMIJUL,E30DAYBEF"): the first we can name."""
    codes = [code for code in types.split(",") if code]
    code = next((c for c in codes if c in REPORT_NAMES), codes[0] if codes else "")
    return code, REPORT_NAMES.get(code, "report")


def summarize(db: sqlite3.Connection, window: dt.date) -> dict[str, Any]:
    """{"window", "filers", "outside"}; the caller adds the snapshot date and zip details."""
    forms = sorted(REPORT_FORMS)
    db.executescript("DROP TABLE IF EXISTS included; DROP TABLE IF EXISTS kept;")
    db.execute(
        f"CREATE TEMP TABLE included AS SELECT * FROM reports WHERE form IN ({','.join('?' * len(forms))})"
        " AND period_end >= ?",
        (*forms, window.strftime("%Y%m%d")),
    )
    db.execute("CREATE INDEX included_id ON included(id)")
    db.execute("CREATE TEMP TABLE kept AS SELECT c.* FROM contribs c JOIN included r ON r.id = c.report")

    filers: dict[str, dict[str, Any]] = {}
    for row in db.execute(
        "SELECT f.id, f.type, f.first, f.last, f.short, f.suffix, f.name,"
        " f.seek_office, f.seek_district, f.seek_place, f.seek_county, f.seek_descr,"
        " f.hold_office, f.hold_district, f.hold_place, f.hold_county, f.hold_descr,"
        " COUNT(*), SUM(r.raised), SUM(r.unitemized), SUM(r.spent)"
        " FROM included r JOIN filers f ON f.id = r.filer GROUP BY f.id"
    ):
        (ident, kind, first, last, short, suffix, full, *offices), (reports, raised, unitemized, spent) = row[:17], row[17:]
        display = " ".join(part for part in (first, last, suffix) if part) or full
        filers[ident] = _drop_empty({
            "id": ident,
            "type": kind,
            "name": display,
            "first": first,
            "last": last,
            "short": short if short and short.upper() != (first or "").upper() else "",
            "seek": _office(*offices[0:5]),
            "hold": _office(*offices[5:10]),
            "totals": {"raised": _money(raised), "unitemized": _money(unitemized), "spent": _money(spent), "reports": reports},
        })

    for ident, types, period_end, received, cash, loans in db.execute(
        "SELECT filer, type, period_end, received, cash, loans FROM ("
        " SELECT *, ROW_NUMBER() OVER (PARTITION BY filer ORDER BY period_end DESC, received DESC, id DESC) AS n"
        " FROM included) WHERE n = 1"
    ):
        if ident in filers:
            code, name = _report_name(types or "")
            filers[ident]["totals"].update(
                cash=_money(cash),
                loans=_money(loans),
                as_of=tec_date(period_end),
                latest=_drop_empty({"type": code, "name": name, "period_end": tec_date(period_end),
                                    "filed": tec_date(received)}),
            )

    for ident, kind, total, count in db.execute("SELECT filer, kind, SUM(amount), COUNT(*) FROM kept GROUP BY filer, kind"):
        if ident in filers:
            filers[ident].setdefault("by_kind", {})[kind] = {"amount": _money(total), "count": count}

    for ident, where, total in db.execute(
        "SELECT filer, CASE WHEN state = 'TX' THEN 'TX' WHEN state = '' THEN 'unknown' ELSE 'other' END, SUM(amount)"
        " FROM kept GROUP BY 1, 2"
    ):
        if ident in filers:
            filers[ident].setdefault("by_state", {})[where] = _money(total)

    bucket = "CASE " + " ".join(f"WHEN amount >= {floor} THEN {i}" for i, (floor, _) in reversed(list(enumerate(SIZE_BUCKETS)))) + " END"
    for ident, index, total, count in db.execute(f"SELECT filer, {bucket}, SUM(amount), COUNT(*) FROM kept GROUP BY 1, 2"):
        if ident in filers and index is not None:
            sizes = filers[ident].setdefault("sizes", [{"amount": 0.0, "count": 0} for _ in SIZE_BUCKETS])
            sizes[index] = {"amount": _money(total), "count": count}

    # Largest donors: grouped by name and state; shown as written in their latest donation.
    for ident, total, count, kind, name, city, state, employer, occupation in db.execute(
        "WITH donors AS ("
        "  SELECT filer, who, state, SUM(amount) AS total, COUNT(*) AS n, MAX(dt || printf('%012d', rowid)) AS latest"
        "  FROM kept GROUP BY filer, who, state),"
        " ranked AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY filer ORDER BY total DESC, who) AS rank FROM donors)"
        " SELECT r.filer, r.total, r.n, k.kind, k.name, k.city, k.state, k.employer, k.occupation"
        " FROM ranked r JOIN kept k ON k.rowid = CAST(substr(r.latest, 9) AS INTEGER)"
        f" WHERE r.rank <= {TOP_DONORS} ORDER BY r.filer, r.rank"
    ):
        if ident in filers:
            filers[ident].setdefault("top_donors", []).append(_drop_empty({
                "name": name, "kind": kind, "city": city, "state": state, "employer": employer,
                "occupation": occupation, "amount": _money(total), "count": count,
            }))

    outside: dict[tuple, dict[str, Any]] = {}
    spenders: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for (first, last, org, seek_office, seek_district, seek_place, seek_county, hold_office, hold_district,
         hold_place, spender, total, count) in db.execute(
        "SELECT first, last, org, seek_office, seek_district, seek_place, seek_county, hold_office, hold_district,"
        " hold_place, spender, SUM(amount), COUNT(*) FROM dce GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11"
        " ORDER BY 1, 2, 3, 4, 5, 6, 7, SUM(amount) DESC"
    ):
        key = (first.upper(), last.upper(), org.upper(), seek_office, seek_district, seek_place, seek_county)
        entry = outside.setdefault(key, _drop_empty({
            "name": " ".join(part for part in (first, last) if part) or org,
            "first": first, "last": last,
            "seek": _office(seek_office, seek_district, seek_place, seek_county),
            "hold": _office(hold_office, hold_district, hold_place, ""),
        }))
        entry["total"] = _money(entry.get("total", 0) + (total or 0))
        spenders[key].append({"name": spender, "amount": _money(total), "count": count})
    for key, entry in outside.items():
        merged: dict[str, dict[str, Any]] = {}
        for spender in spenders[key]:  # one spender can appear under two hold-office spellings
            seen = merged.setdefault(spender["name"], {"name": spender["name"], "amount": 0.0, "count": 0})
            seen["amount"] = _money(seen["amount"] + spender["amount"])
            seen["count"] += spender["count"]
        entry["spenders"] = sorted(merged.values(), key=lambda s: -s["amount"])[:TOP_SPENDERS]

    return {
        "window": {"start": window.isoformat()},
        "filers": sorted(filers.values(), key=lambda f: f["id"]),
        "outside": sorted(outside.values(), key=lambda o: (o.get("last", ""), o.get("first", ""), o["name"], str(o.get("seek")))),
    }
