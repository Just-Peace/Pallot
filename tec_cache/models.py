"""What a snapshot covers (which filers, reports and dates), and the refresh result."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

ZIP_URL = "https://prd.tecprd.ethicsefile.com/public/cf/public/TEC_CF_CSV.zip"
SEARCH_URL = "https://www.ethics.state.tx.us/search/cf/"

# Candidates and officeholders, judicial ones included. PACs and parties are left out.
CANDIDATE_FILERS = frozenset({"COH", "JCOH"})
# Their campaign finance reports (and final reports). Unexpended-contribution (COHUC),
# party-chair and Speaker's-race reports aren't fundraising for the office, so they don't
# count. Daily pre-election and special-session reports, whose contributions are reported
# again on the next regular report, sit in files we never read (cover_t/cover_ss).
REPORT_FORMS = frozenset({"COH", "JCOH", "COHFR"})

# What to call a report, by the report types it covers (reportTypeCd1..10).
REPORT_NAMES = {
    "SEMIJAN": "January semiannual report",
    "SEMIJUL": "July semiannual report",
    **{f"CF{m.upper()}": f"{m} monthly report" for m in
       ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")},
    "E50DAYBEF": "50-day pre-election report",
    "E30DAYBEF": "30-day pre-election report",
    "E08DAYBEF": "8-day pre-election report",
    "RUNOFF": "runoff report",
    "A10DAYAFT": "report after appointing a treasurer",
    "A15DAYAFT": "report after appointing a treasurer",
    "500EXCEED": "report on exceeding the modified-reporting limit",
    "FINAL": "final report",
}

# Direct campaign expenditures reported on daily pre-election reports show up again later.
DAILY_FORMS = frozenset({"DIRE", "DAILYCPAC", "DAILYEPAC", "DAILYCCOH"})

# Itemized donations by size. Texas has no contribution limits for most state offices.
SIZE_BUCKETS: tuple[tuple[float, str], ...] = (
    (0, "Under $500"),
    (500, "$500 to $4,999"),
    (5_000, "$5,000 to $24,999"),
    (25_000, "$25,000 to $99,999"),
    (100_000, "$100,000 and over"),
)

TOP_DONORS = 10
TOP_SPENDERS = 10
NEWEST_CONTRIB_FILES = 30  # a first build reads this many of the newest contribs_NN.csv files


def general_election(year: int) -> dt.date:
    """Texas's November general election: the Tuesday after the first Monday."""
    first = dt.date(year, 11, 1)
    monday = first + dt.timedelta(days=-first.weekday() % 7)
    return monday + dt.timedelta(days=1)


def window_start(today: dt.date) -> dt.date:
    """The day after the last even-year general election before today. A snapshot counts
    the reports for periods ending from then on: the money raised for the next election."""
    year = today.year - today.year % 2
    election = general_election(year)
    if election >= today:
        election = general_election(year - 2)
    return election + dt.timedelta(days=1)


def tec_date(text: str | None) -> str | None:
    """TEC's "20260630" -> "2026-06-30"."""
    text = (text or "").strip()
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if len(text) == 8 and text.isdigit() else None


@dataclass(frozen=True)
class RefreshResult:
    """Outcome of refresh(). status is "updated", "no_changes" or "would_update" (dry run)."""

    status: str
    checked_at: dt.datetime
    source: str
    snapshot: str | None = None
    window_start: dt.date | None = None
    filers: int = 0
    requests: int = 0
    downloaded: int = 0  # bytes
    warnings: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return self.status != "no_changes"

    def summary(self) -> str:
        if self.requests:
            fetched = f"{self.requests} request{'s' if self.requests != 1 else ''}, {self.downloaded / 1_048_576:.0f} MB"
        else:
            fetched = f"read {self.source}"
        if self.status == "no_changes":
            head = f"no changes: snapshot {self.snapshot} is up to date ({fetched})"
        else:
            verb = "updated" if self.status == "updated" else "would update"
            since = f" since {self.window_start:%b} {self.window_start.day}, {self.window_start.year}" if self.window_start else ""
            head = f"{verb} snapshot {self.snapshot}: {self.filers:,} candidates and officeholders with reports{since} ({fetched})"
        return "\n".join([head, *(f"note: {w}" for w in self.warnings)])
