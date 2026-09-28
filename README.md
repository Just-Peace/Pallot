# VoteBot

A voter's personal ballot, currently for Texas addresses. Enter a home address and VoteBot shows every race on that voter's ballot, with candidates in ballot order. Each candidate carries information from several sources. You can pick candidates, write notes, and print your picks to take to the polls.

It runs locally as one Python process (FastAPI) serving a plain HTML/JS page. There's no build step and no database server.

## Run it

Needs [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`).

```bash
uv sync          # creates .venv with VoteBot, its dependencies and the dev tools, pinned by uv.lock
uv run votebot   # serves http://127.0.0.1:8000 (options: --port 8000, --reload)
```

Keep the default `127.0.0.1` binding, because the Settings actions have no login.

Tests:

```bash
uv run pytest                              # offline: recorded responses in tests/fixtures, plus trackaipac_cache's own tests
uv run pytest -m live                      # one smoke test against the real services
uv run python scripts/record_fixtures.py   # re-record tests/fixtures from the live APIs
```

## Using it

- **Left pane:**
  - the address lookup
  - your ballot summary: districts, a progress bar, Print and Clear buttons, and where the data came from
  - a list of sections showing how many races in each you've picked
  - **Settings**
- **Main area:** the races.
  - Click a race's heading to collapse it. A collapsed race shows your pick ("James Talarico selected") or "Not picked yet".
  - **Collapse all** gives a one-screen overview of your picks.
  - Collapsed races stay collapsed when you come back.
- **Each candidate has:**
  - a pick button
  - a note
  - **Details**, with one tab per source
  - a **Google ↗** link that searches for their name, office and place

Picks, notes and collapsed races are kept in the browser's `localStorage`, never on the server.

## Where the data comes from

| Source | Used for | Notes |
|---|---|---|
| US Census geocoder | address → county, U.S. House, State Senate and State House districts | already on the 2026 maps (120th Congress, 2026 legislative districts) |
| OpenStreetMap Nominatim | fallback when the Census can't match an address | results flagged as approximate unless they hit a building |
| Texas Legislative Council map (PLANE2106) | State Board of Education district | downloaded once, point-in-polygon in pure Python |
| Texas Secretary of State | official ballot order per county, candidate filings | the public API behind goelect.txelections.civixapps.com |
| Ballotpedia | city council, school board and special-district races; JP/constable/commissioner precinct; candidate profiles | **unofficial** endpoint that needs Ballotpedia's own origin header. Its terms forbid commercial scraping, so keep it personal or turn it off in Settings |
| TrackAIPAC | pro-Israel lobby money and endorsements for congressional candidates | from `trackaipac_cache/` (see below) |

The Texas SOS data covers every race touching a county. VoteBot keeps only the voter's congressional, legislative and SBOE districts; judicial and DA districts are whole counties. Commissioner, JP and constable races depend on the voter's precinct. That comes from Ballotpedia or from numbers the voter types in; otherwise those races are listed under "Depends on your precinct". Ballotpedia lists MUDs and water districts for a whole county, so those appear under "Special districts" as "may be on your ballot".

State-specific text (the official elections site, the print sheet's voting rules) comes from `STATES` in `votebot/static/js/labels.js`, keyed by the address's state, so adding a state doesn't mean rewriting pages.

Candidates are matched across sources by name, with seat and party as corroboration. Every match is labelled **exact** or **likely**, and ambiguous ones are left unmatched. TrackAIPAC lists members of Congress by their current seat, so a 2026 seat change after the 2025 redistricting shows up as "likely" unless TrackAIPAC's entry mentions the new seat.

## Caching

Every outbound call goes through `votebot/http_cache.py`, a SQLite cache in `data/cache.sqlite3`. Looking up the same address again makes **zero** external calls, even after a restart. Each ballot response reports `meta.external_calls`, and the status line under the lookup shows it.

- Lifetimes:
  - reference data: 30 days
  - elections, ballot order and statewide candidate lists: 24 hours (a year for past elections)
  - empty ballot orders: 6 hours
  - geocodes: 30 days
  - Ballotpedia: 24 hours
  - Override any of these with `VOTEBOT_TTL_<NAME>` in seconds; see `votebot/config.py`.
- Candidate details come from one statewide list per election (~2.6 MB, one request per day), not one request per candidate.
- Concurrent identical requests share one fetch. If a refresh fails, the old copy is shown with a "data as of" note.
- If Ballotpedia refuses a request, VoteBot stops asking it for an hour.

**Settings**, at the bottom of the left pane:
- turns Texas SOS, Ballotpedia and TrackAIPAC on or off;
- shows what each source has cached, with a refresh or clear button per source, plus "clear everything";
- has a button to delete your picks and notes from the browser.

Turning a source on or off re-runs the lookup straight away. With Texas SOS off, the ballot comes entirely from Ballotpedia.

## trackaipac_cache

`trackaipac_cache/` is a copy of the TrackAIPAC library from `git@github.com:Fahd-Siddiqui/TrackAipacCache.git` (develop, commit `423443a`), with its tests in `tests/trackaipac/`. VoteBot copies its bundled snapshot into `data/trackaipac/` on first run, so it works without calling trackaipac.com.

- **Refresh** (TrackAIPAC's row in Settings) runs the package's `refresh()`, which validates the pages and writes only if the site changed.
- **Reset** goes back to the copy in the repo.
- To update the bundled copy itself, run `uv run trackaipac-cache refresh` and see `trackaipac_cache/README.md`.

## Configuration

Set these as environment variables, for example `VOTEBOT_DATA_DIR=/var/lib/votebot uv run votebot`.

| Variable | Default |
|---|---|
| `VOTEBOT_DATA_DIR` | `data/` in the project (cache, settings, SBOE map, TrackAIPAC data; git-ignored) |
| `VOTEBOT_USER_AGENT` | `VoteBot/0.1 (personal ballot helper)` (Nominatim requires an identifying one) |
| `VOTEBOT_HTTP_TIMEOUT` | `30` seconds |
| `VOTEBOT_TTL_*` | cache lifetimes, see above |

## Layout

```
votebot/
  api.py            routes + static files          ballot.py   assembles the ballot
  http_cache.py     persistent request cache       enrich.py   adds each source's cards to candidates
  offices.py        SOS office names -> districts  matching.py cross-source name matching
  admin.py          Settings actions               settings.py source on/off switches (data/settings.json)
  sources/          census, nominatim, sboe, sos, ballotpedia, trackaipac
  static/           index.html, css/app.css, js/ (ballot.js, settings-pane.js, source-cards.js, print.js, …)
trackaipac_cache/   TrackAIPAC library (copied in)
scripts/            record_fixtures.py, capture_trackaipac_fixtures.py
tests/              VoteBot tests + tests/trackaipac/
```

## Adding a source

Each source contributes `SourceCard`s (badges, facts, quotes, links, match confidence). The page renders them generically, as badges on the candidate row and a tab in Details. So a new source only needs:

1. A module in `votebot/sources/` that fetches through `HttpCache` and builds cards.
2. A line in `enrich.py`.
3. An entry in `admin.py` so it appears in Settings.

## Not built yet

The research phase:
- PACs beyond TrackAIPAC (FEC for federal candidates, Texas Ethics Commission for state and county candidates)
- each candidate's top three views (LLM plus web search)
- chances of winning (race ratings, district partisan lean)
