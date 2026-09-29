"""A small, made-up TEC export (with TEC's real column names) zipped in memory, and a fake
download server that honours Range and If-Range the way TEC's CloudFront does."""

from __future__ import annotations

import csv
import datetime as dt
import io
import zipfile
from typing import Any

import httpx
import pytest
import respx

from tec_cache.parse import REQUIRED

URL = "https://tec.example/TEC_CF_CSV.zip"
NOW = dt.datetime(2026, 9, 27, 12, tzinfo=dt.timezone.utc)  # the window starts Nov 6, 2024
NO_MINIMUMS: dict[str, int] = {}


EXTRA_COLUMNS = {"cover": ("reportTypeCd1", "reportTypeCd2")}  # an array of up to ten in TEC's files


def csv_text(kind: str, rows: list[dict[str, Any]]) -> str:
    columns = ["recordType", *REQUIRED[kind], *EXTRA_COLUMNS.get(kind, ()), "somethingElse"]  # TEC's have more
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(column, "") for column in columns])
    return out.getvalue()


def filer(ident: str, first: str, last: str, office: str = "STATEREP", district: str = "49", kind: str = "COH", **extra: Any):
    return {"filerIdent": ident, "filerTypeCd": kind, "filerName": f"{last}, {first}", "filerNameFirst": first,
            "filerNameLast": last, "ctaSeekOfficeCd": office, "ctaSeekOfficeDistrict": district,
            "filerFilerpersStatusCd": "CURRENT_OFFICEHOLDER", "filerEffStartDt": "20240101", **extra}


def report(ident: str, filer_id: str, kind: str, start: str, end: str, raised: float, unitemized: float, spent: float,
           cash: float, loans: float = 0, form: str = "COH", superseded: bool = False, filer_type: str = "COH"):
    return {"reportInfoIdent": ident, "filerIdent": filer_id, "filerTypeCd": filer_type, "formTypeCd": form,
            "reportTypeCd1": kind, "periodStartDt": start, "periodEndDt": end, "receivedDt": end,
            "infoOnlyFlag": "Y" if superseded else "N", "totalContribAmount": raised,
            "unitemizedContribAmount": unitemized, "totalExpendAmount": spent, "contribsMaintainedAmount": cash,
            "loanBalanceAmount": loans}


def gift(report_id: str, filer_id: str, amount: float, received: str, *, first: str = "", last: str = "", org: str = "",
         state: str = "TX", city: str = "AUSTIN", employer: str = "", occupation: str = "", superseded: bool = False,
         filer_type: str = "COH", unitemized: bool = False):
    return {"reportInfoIdent": report_id, "filerIdent": filer_id, "filerTypeCd": filer_type, "receivedDt": received,
            "contributionDt": received, "contributionAmount": amount, "infoOnlyFlag": "Y" if superseded else "N",
            "itemizeFlag": "N" if unitemized else "Y",
            "contributorPersentTypeCd": "ENTITY" if org else "INDIVIDUAL", "contributorNameOrganization": org,
            "contributorNameFirst": first, "contributorNameLast": last, "contributorStreetCity": city,
            "contributorStreetStateCd": state, "contributorEmployer": employer, "contributorOccupation": occupation}


def spending(spender: str, amount: float, day: str, *, first: str, last: str, office: str = "STATEREP", district: str = "49",
             form: str = "GPAC"):
    return {"filerIdent": "99", "filerName": spender, "formTypeCd": form, "reportInfoIdent": "900", "infoOnlyFlag": "N",
            "expendDt": day, "expendAmount": amount, "candidateNameFirst": first, "candidateNameLast": last,
            "candidateSeekOfficeCd": office, "candidateSeekOfficeDistrict": district}


def export(**overrides: str) -> dict[str, str]:
    """The members of a small TEC export. Jane Doe and Juan Perez run for State Rep 49."""
    members = {
        "filers.csv": csv_text("filers", [
            filer("00000001", "Jane", "Doe", filerNameShort="Janie"),
            # the same filer's old judicial record: not the one to keep
            filer("00000001", "Jane", "Doe", office="JUSTICE_SC", district="", kind="JCOH",
                  filerFilerpersStatusCd="NOT_OFFICEHOLDER", filerEffStartDt="20100101", filerEffStopDt="20141231"),
            filer("00000002", "Juan", "Perez"),
            filer("00000003", "Ann", "Judge", office="JUDGEDIST", district="147", kind="JCOH"),
            filer("00000009", "Big", "Pac", kind="GPAC"),
        ]),
        "cover.csv": csv_text("cover", [
            report("1", "00000001", "SEMIJAN", "20240701", "20241231", 1000, 100, 200, 5000),
            report("2", "00000001", "SEMIJUL", "20250101", "20250630", 3000, 300, 500, 7000, loans=1000),
            report("3", "00000001", "SEMIJUL", "20250101", "20250630", 9999, 0, 0, 0, superseded=True),  # corrected later
            report("4", "00000001", "DAILYCCOH", "20251020", "20251021", 800, 0, 0, 0, form="DAILYCCOH"),  # repeats later
            report("5", "00000001", "SEMIJUL", "20240101", "20240630", 50000, 0, 0, 0),  # before the window
            report("6", "00000002", "E30DAYBEF", "20250701", "20260924", 250, 50, 10, 240),
            report("7", "00000003", "SEMIJUL", "20250101", "20250630", 600, 0, 0, 600, form="JCOH", filer_type="JCOH"),
            report("8", "00000009", "SEMIJUL", "20250101", "20250630", 1_000_000, 0, 0, 0, form="GPAC", filer_type="GPAC"),
        ]),
        "contribs_01.csv": csv_text("contribs", [
            gift("5", "00000001", 50000, "20240715", first="Old", last="Money"),  # before the window
        ]),
        "contribs_02.csv": csv_text("contribs", [
            gift("1", "00000001", 400, "20250115", first="Pat", last="Smith", employer="ACME", occupation="CEO"),
            gift("1", "00000001", 500, "20250115", org="Teachers PAC"),
            gift("3", "00000001", 9999, "20250715", first="Wrong", last="Copy", superseded=True),
            gift("8", "00000009", 1_000_000, "20250715", first="Pac", last="Donor", filer_type="GPAC"),
        ]),
        "contribs_03.csv": csv_text("contribs", [
            gift("2", "00000001", 2000, "20250715", first="Pat", last="Smith", employer="ACME", occupation="CEO"),
            gift("2", "00000001", 700, "20250715", first="Lee", last="Far", state="CA", city="Oakland"),
            gift("2", "00000001", 50, "20250715", first="Small", last="Giver", unitemized=True),  # in the unitemized total
            gift("4", "00000001", 800, "20251021", first="Daily", last="Report"),
            gift("6", "00000002", 200, "20260924", first="Sam", last="Small"),
            gift("7", "00000003", 600, "20250715", first="Law", last="Yer"),
        ]),
        "cand.csv": csv_text("cand", [
            spending("Texans for Jane", 1500, "20251001", first="Jane", last="Doe"),
            spending("Texans for Jane", 500, "20251015", first="Jane", last="Doe"),
            spending("Other Group", 300, "20251020", first="Jane", last="Doe"),
            spending("Daily Group", 900, "20251030", first="Jane", last="Doe", form="DIRE"),
            spending("Too Early", 700, "20240101", first="Jane", last="Doe"),
        ]),
        "CFS-ReadMe.txt": "record layouts\n",
    }
    members.update(overrides)
    return members


def zip_bytes(members: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return buffer.getvalue()


class Server:
    """TEC's CloudFront, as far as tec_cache can tell: byte ranges, ETags, If-Range, and a
    status to answer with instead (403 when it blocks us)."""

    def __init__(self, data: bytes, etag: str = '"v1"'):
        self.data, self.etag = data, etag
        self.status: int | None = None
        self.ranges: list[str | None] = []

    def replace(self, data: bytes, etag: str) -> None:
        self.data, self.etag = data, etag

    def __call__(self, request: httpx.Request) -> httpx.Response:
        wanted = request.headers.get("range")
        self.ranges.append(wanted)
        if self.status:
            return httpx.Response(self.status, text="Request blocked.")
        headers = {"etag": self.etag, "last-modified": "Sun, 27 Sep 2026 10:35:03 GMT"}
        if_range = request.headers.get("if-range")
        if wanted is None or (if_range and if_range != self.etag):
            return httpx.Response(200, content=self.data, headers=headers)
        spec, size = wanted.removeprefix("bytes="), len(self.data)
        if spec.startswith("-"):
            start, end = max(0, size - int(spec[1:])), size - 1
        else:
            first, last = spec.split("-")
            start, end = int(first), min(int(last), size - 1)
        headers["content-range"] = f"bytes {start}-{end}/{size}"
        return httpx.Response(206, content=self.data[start : end + 1], headers=headers)


@pytest.fixture
def server():
    fake = Server(zip_bytes(export()))
    with respx.mock(assert_all_called=False) as router:
        router.get(URL).mock(side_effect=fake)
        yield fake
