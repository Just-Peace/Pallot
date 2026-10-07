# tec_cache

A git-bundled snapshot of Texas Ethics Commission (TEC) campaign finance for state candidates and officeholders. For each one it holds:
- what they raised and spent, and their cash on hand and loans;
- where their itemized donations came from, and their largest donors;
- the outside spending that named them.

It's rebuilt from TEC's nightly CSV export, [`TEC_CF_CSV.zip`](https://prd.tecprd.ethicsefile.com/public/cf/public/TEC_CF_CSV.zip) (about 1 GB). The record layouts are in `CFS-ReadMe.txt` inside the zip.

## How Pallot uses it

Pallot copies `tec_cache/data/` into `data/tec/` on first run and reads `current.json` from there, so ballot lookups never contact TEC.
- **Refresh** (the Texas Ethics Commission row in Settings) runs `python -m tec_cache refresh --data-dir data/tec` in a separate process.
- **Reset** goes back to the files in this folder. A zip you downloaded into `data/tec/` stays.

## Refresh the bundled snapshot

```
uv run tec-cache refresh                          # writes only if the numbers changed
uv run tec-cache refresh --dry-run                # report what would change, write nothing
uv run tec-cache refresh --zip ~/Downloads/TEC_CF_CSV.zip   # use a zip downloaded in a browser
```

Without `--data-dir`, this updates `tec_cache/data/` in this repo; commit it to keep it.

A refresh makes at most two requests:
1. **The end of the file**, which holds the zip's directory. If TEC's zip hasn't changed since the last refresh, and the snapshot was built by this version's layout (`SCHEMA_VERSION` in `store.py`), this is the only request.
2. **One streaming download** of the zip, about 1 GB. As it arrives, the refresh reads only the files it needs and skips the rest:
   - `filers.csv`;
   - `cover.csv` (one row per report, with its totals);
   - `cand.csv` (direct campaign expenditures);
   - the `contribs_NN.csv` files that can hold this election cycle's reports.

It doesn't download just those files as separate byte ranges. TEC stores its files in no particular order, so that would take about twenty requests, and TEC's download server (CloudFront) blocks a burst like that.

**Even so, TEC may block the download.** A 403 "Request blocked" can last from minutes to hours. If a refresh reports `BlockedError`:
1. Wait, or download the zip in a browser.
2. Run the refresh with `--zip`. For Pallot's copy, you can instead put the file at `data/tec/TEC_CF_CSV.zip` and press Refresh.

If a file is missing a column the snapshot needs, or the counts are implausibly low, the refresh aborts without writing anything (`ValidationError`).

## What's in the snapshot (`tec_cache/data/`)

- `current.json`:
  - `window.start`: the day after the last even-year November general election (e.g. 2024-11-06). A filer's totals add up their candidate/officeholder reports whose period ends on or after it, so the first of those may start a few months earlier.
  - `filers`: one line per candidate or officeholder with reports in the window. Each has:
    - the offices they seek and hold;
    - `totals`: raised, unitemized, spent, cash on hand and loans from the latest report, the report count, and the latest report;
    - `by_kind`: itemized donations from individuals vs. entities (PACs, businesses and other groups);
    - `by_state`: Texas vs. elsewhere;
    - `sizes`: itemized donations by size (`SIZE_BUCKETS` in `models.py`: $200 and under, then up to $500, $5,000, $25,000, $100,000 and over);
    - `top_donors`: the 10 largest donors, by donor name and state, with city, employer and occupation as TEC publishes them.
  - `outside`: direct campaign expenditures naming a candidate, with the top spenders. TEC doesn't record whether they were for or against.
- `meta.json`: when the snapshot was checked and changed, which zip it came from, each contribution file's CRC and date range (so later refreshes skip files from before the window), and counts.

**Not double-counted:** TEC keeps daily pre-election and special-session reports in separate files (`cover_t`, `cover_ss`, `cont_t`, `cont_ss`), because their contributions are reported again on the next regular report. tec_cache never reads them. Superseded (corrected) reports are left out too.

**Coverage:** statewide offices, the Legislature, the State Board of Education, appellate and district courts, and district attorneys. County candidates (county courts at law included), precinct, city and school candidates file with their county or city, not TEC.

## Tests

```
uv run pytest tests/tec       # offline, against a small made-up export zipped in memory
```
