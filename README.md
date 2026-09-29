# VoteBot

A voter's personal ballot, currently for Texas addresses. Enter a home address and VoteBot shows every race on that voter's ballot, with candidates in ballot order. Each candidate carries information from several sources. You can pick candidates, write notes, and print your picks to take to the polls.

It runs locally as one Python process (FastAPI) serving a plain HTML/JS page. There's no build step and no database server.

## Run it

Needs [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`).

```bash
uv sync                 # creates .venv with VoteBot, its dependencies and the dev tools, pinned by uv.lock
cp .env.example .env    # optional: put your free FEC key in it (see Configuration)
uv run votebot          # serves http://127.0.0.1:8000 (options: --port 8000, --reload)
```

Keep the default `127.0.0.1` binding (there is a `--host` option, but don't change it), because the Settings actions have no login.

Tests:

```bash
uv run pytest                              # offline: recorded responses in tests/fixtures, plus trackaipac_cache's and tec_cache's own tests
uv run pytest -m live                      # smoke tests against the real services (the FEC one needs an FEC key)
uv run python scripts/record_fixtures.py   # re-record tests/fixtures from the live APIs (--only ballots|fec|polls|tec|trackaipac)
```

## Using it

- **Left pane**, the same on every page:
  - at the top, **Your ballot**, with your address under it. After a lookup the address is saved in the browser and shown as a card with your county and districts. **Change** opens the form again; on the other pages it takes you to the ballot with the form open.
  - while you type an address, **suggestions** from Photon appear under the box: ↑/↓ and Enter pick one, which only fills the box in. "Street only" means OpenStreetMap has the street but not that house number, so the suggestion keeps the number you typed. Turn them off in Settings to get the browser's own address autofill back.
  - on the ballot, the list of sections, with how many races in each you've picked
  - at the bottom, links to **Settings**, **FAQ**, **About** and **Privacy**
- **Top of the ballot:** a progress bar that stays in view, plus Collapse all, Expand all, Clear picks and Print my picks.
- **Races:** click a race's heading to collapse it to one line, with the race on the left and your pick ("✓ James Talarico") on the right. Collapsed races stay collapsed when you come back.
- **Picks follow the party:** a picked candidate's row takes their party's colour (Republican red, Democratic blue, Libertarian yellow, Green green, gray otherwise). Party badges are solid colour so they stand apart from the sources' badges.
- **Money:** congressional and state races show what each candidate has raised, above the candidates. The figures come from the FEC for Congress and the Texas Ethics Commission for state offices. Each candidate's tab from that source breaks it down:
  - where the money came from;
  - donation sizes;
  - where donors live;
  - the largest donors (the FEC groups them by employer);
  - outside spending.

  **Compare candidates** on a race's money box puts everyone in the race side by side: totals, then each breakdown with one bar per candidate, and the largest donors and outside spenders in columns, with names that appear in more than one candidate's list marked. The FAQ's "Campaign money" section explains how each figure is put together. Outside spending is marked with a blue "for" or an amber "against" the candidate; none of it went to the campaign.
- **Polls:** U.S. Senate, U.S. House and Governor races with public polls show one bar under the money box: each candidate's median share, in their party's colour, with the rest (undecided and others) in gray. The median is over each pollster's latest poll of the matchup actually on the ballot, likely voters where a poll asked them. Each candidate's **Polls** tab lists the polls. Most House districts have no polls, so they show no bar.
- **Write-ins:** every race ends with a write-in line. Type someone else's name and it becomes your pick; it shows on the collapsed line and the printed sheet as "Name (write-in)". In Texas a write-in only counts for someone who filed as a write-in candidate, and the page says so when you pick one.
- **Each candidate has:**
  - a pick button
  - a note
  - **Details**, with one tab per source
  - a **Web search ↗** link that searches for their name, office and place, using Google unless you pick another engine (Bing, DuckDuckGo, Brave, Yahoo, Startpage, Ecosia, Kagi or Perplexity) in Settings

Picks, notes and collapsed races are kept in the browser's `localStorage`, never on the server.

## Where the data comes from

| Source | Used for | Notes |
|---|---|---|
| US Census geocoder | address → county, U.S. House, State Senate and State House districts | already on the 2026 maps (120th Congress, 2026 legislative districts) |
| OpenStreetMap Nominatim | fallback when the Census can't match an address | results flagged as approximate unless they hit a building |
| Photon (photon.komoot.io) | address suggestions while typing | OpenStreetMap data; free for reasonable use, no key. Nominatim's policy forbids search-as-you-type. Only results on a street matching what was typed are kept; without the house in OpenStreetMap, the typed number goes on the street |
| Texas Legislative Council map (PLANE2106) | State Board of Education district | downloaded once, point-in-polygon in pure Python |
| Texas Secretary of State | official ballot order per county, candidate filings | the public API behind goelect.txelections.civixapps.com |
| Ballotpedia | city council, school board and special-district races; JP/constable/commissioner precinct; candidate profiles | **unofficial** endpoint that needs Ballotpedia's own origin header. Its terms forbid commercial scraping, so keep it personal or turn it off in Settings |
| TrackAIPAC | pro-Israel lobby money and endorsements for congressional candidates | from `trackaipac_cache/` (see below) |
| FEC (Federal Election Commission) | money raised and spent by congressional campaigns, where it came from, and outside spending for or against them | the OpenFEC API. The shared `DEMO_KEY` only allows race totals; set `VOTEBOT_FEC_API_KEY` to a free key from the [OpenFEC developers page](https://api.open.fec.gov/developers/) for the rest |
| Texas Ethics Commission | the same for state candidates and officeholders, plus their largest donors | from `tec_cache/` (see below), built from TEC's nightly CSV export |
| FiftyPlusOne (fiftyplusone.news) | public polls of U.S. Senate, U.S. House and Governor races | the site's own JSON API: nationwide lists, 500 polls to a page, filtered to Texas on the server. It answers 403 unless the request looks like a browser's |

The Texas SOS data covers every race touching a county. VoteBot keeps only the voter's congressional, legislative and SBOE districts; judicial and DA districts are whole counties. Commissioner, JP and constable races depend on the voter's precinct. That comes from Ballotpedia or from numbers the voter types in; otherwise those races are listed under "Depends on your precinct". Ballotpedia lists MUDs and water districts for a whole county, so those appear under "Special districts" as "may be on your ballot".

Campaign money covers congressional races (FEC) and state races (TEC), which includes:
- statewide offices;
- the Legislature;
- the State Board of Education;
- appellate and district courts;
- district attorneys.

County candidates (county courts at law included), precinct, city and school candidates file with their county or city, so their races show none.

What "raised" covers (the FAQ's "How are the FEC figures put together?" and "How are the Texas Ethics Commission figures put together?" go through every figure):
- **TEC totals:** the reports whose period ends after the last November general election, excluding daily pre-election and special-session reports, whose money is reported again later.
- **FEC totals:** the whole election period (two years for the House, six for the Senate).

State-specific text (the official elections site, the print sheet's voting rules) comes from `STATES` in `votebot/static/js/labels.js`, keyed by the address's state, so adding a state doesn't mean rewriting pages.

Candidates are matched across sources by name, with seat and party as corroboration. Every match is labelled **exact** or **likely**, and ambiguous ones are left unmatched. TrackAIPAC lists members of Congress by their current seat, so a 2026 seat change after the 2025 redistricting shows up as "likely" unless TrackAIPAC's entry mentions the new seat.

## Caching

Every outbound call goes through `votebot/http_cache.py`, a SQLite cache in `data/cache.sqlite3`. Looking up the same address again makes **zero** external calls, even after a restart. Each `/api/ballot` response reports `meta.external_calls`, and Settings shows the last lookup's, source by source.

- Lifetimes:
  - reference data: 30 days
  - elections, ballot order and statewide candidate lists: 24 hours (a year for past elections)
  - empty ballot orders: 6 hours
  - geocodes: 30 days (an address that wasn't found: 1 day)
  - address suggestions: 30 days
  - Ballotpedia: 24 hours
  - FEC: 7 days (a year for past elections)
  - polls: 24 hours
  - after a failed request: its old copy is served for 15 minutes before the source is asked again
  - Override any of these with `VOTEBOT_TTL_<NAME>` in seconds; see `votebot/config.py`.
- The Texas Ethics Commission data comes with VoteBot (`tec_cache/`), so lookups never contact TEC; it's only fetched again when you press Refresh.
- Candidate details come from one statewide list per election (~2.6 MB, one request per day), not one request per candidate.
- Concurrent identical requests share one fetch. If a refresh fails, the old copy is shown with a "data as of" note, and that request isn't retried for 15 minutes, so a source that's down doesn't slow every lookup.
- Only answers that succeed are cached. A source that fails before answering once has nothing to fall back on.
- If Ballotpedia, Photon or FiftyPlusOne refuses a request, VoteBot stops asking it for an hour. What it already sent still shows.
- If the FEC answers that its rate limit is reached, VoteBot stops asking it for an hour and shows what it already has meanwhile. With `DEMO_KEY`, that limit is shared by everything on your IP address, `scripts/record_fixtures.py` and the live tests included.
- Refresh in Settings doesn't ask a paused source either, and stops when a source pauses partway through.

The **Settings** page (`settings.html`, linked from the left pane):
- picks the web search engine;
- turns address suggestions, Texas SOS, Ballotpedia, TrackAIPAC, the FEC, the Texas Ethics Commission and polls on or off;
- says whether the FEC is using your key, whether a source is paused, and how old the Texas Ethics Commission snapshot is;
- shows what the server has saved for each source (responses, size, when they were fetched) and how the last lookup used it (requests made, how old the data was), plus the total on disk;
- has a refresh or clear button per source, plus "Clear all caches", which also resets TrackAIPAC and the Texas Ethics Commission to their bundled snapshots. Refreshes that send or download a lot (every saved address, every saved suggestion, TEC's 1 GB zip) ask first;
- has "Clear my picks & notes", and "Clear all browser data", which also forgets your address and search engine.

When you go back to your ballot after changing a setting, it reloads with the new one. That includes a ballot kept by the Back button or left open in another tab. With Texas SOS off, the ballot comes entirely from Ballotpedia.

## trackaipac_cache

`trackaipac_cache/` is a copy of the TrackAIPAC library from `git@github.com:Fahd-Siddiqui/TrackAipacCache.git` (develop, commit `423443a`), with its tests in `tests/trackaipac/`. VoteBot copies its bundled snapshot into `data/trackaipac/` on first run, so it works without calling trackaipac.com.

- **Refresh** (TrackAIPAC's row in Settings) runs the package's `refresh()`, which validates the pages and writes only if the site changed.
- **Reset** goes back to the copy in the repo.
- To update the bundled copy itself, run `uv run trackaipac-cache refresh` and see `trackaipac_cache/README.md`.

## tec_cache

`tec_cache/` builds the Texas Ethics Commission snapshot from TEC's nightly export, `TEC_CF_CSV.zip` (about 1 GB), and bundles it in the repo. VoteBot copies it into `data/tec/` on first run, so ballot lookups never contact TEC.
- **Refresh** (the Texas Ethics Commission row in Settings) rebuilds it in a separate process.
  - It first makes one small request to see whether TEC's zip has changed; if not, that's all.
  - If it has, it downloads the zip in one request (about 1 GB, a minute or two on a fast connection), reading just the files it needs as they arrive.
- **Reset** goes back to the bundled copy.
- **TEC's download server blocks bursts of requests.** If a refresh says it was refused, try later, or download the zip in a browser, save it as `data/tec/TEC_CF_CSV.zip`, and press Refresh again.
- To update the bundled copy itself, run `uv run tec-cache refresh` (or `--zip PATH`) and see `tec_cache/README.md`.

## Configuration

Set these as environment variables, for example `VOTEBOT_DATA_DIR=/var/lib/votebot uv run votebot`, or in a `.env` file in the project folder: `cp .env.example .env` and fill it in. VoteBot reads `.env` at startup, and git ignores it. Variables already set in the environment win over `.env`.

| Variable | Default |
|---|---|
| `VOTEBOT_DATA_DIR` | `data/` in the project (cache, settings, SBOE map, TrackAIPAC and TEC data; git-ignored) |
| `VOTEBOT_FEC_API_KEY` | `DEMO_KEY`, which only allows race totals and runs out after a few requests. Get a free key from the [OpenFEC developers page](https://api.open.fec.gov/developers/). It's only sent to the FEC, in a header, and VoteBot never writes it anywhere |
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
  sources/          census, nominatim, photon, sboe, sos, ballotpedia, trackaipac, fec, tec, polls
                    (snapshot.py: the bundled-snapshot handling TrackAIPAC and TEC share;
                    compare.py: the Compare dialog's sections, shared by the FEC and TEC)
  static/           index.html (the ballot), settings.html, faq.html, about.html, privacy.html,
                    css/app.css, js/ (ballot.js, suggest.js, compare.js, settings.js, page.js,
                    source-cards.js, print.js, …)
trackaipac_cache/   TrackAIPAC library (copied in)
tec_cache/          Texas Ethics Commission snapshot and its builder
scripts/            record_fixtures.py, capture_trackaipac_fixtures.py
tests/              VoteBot tests + tests/trackaipac/ + tests/tec/
```

## Adding a source

Each source contributes `SourceCard`s: badges, facts, quotes, money breakdowns, links and match confidence. A source can also add a card to a race, such as the money comparison. The page renders them all generically, as badges on the candidate row, a tab in Details, and a block at the top of the race. So a new source only needs:

1. A module in `votebot/sources/` that fetches through `HttpCache` and builds cards.
2. A field on `Services` in `ballot.py`, created in `api.py`'s startup.
3. A line in `enrich.py`.
4. An entry in `admin.py` so it appears in Settings, and one in `DEFAULT_SOURCES` in `settings.py` if it can be turned off.
5. A row in the tables on `static/privacy.html` (what the source is sent and kept) and `static/about.html`, and an answer in `static/faq.html` if it raises a question.

## Not built yet

The research phase:
- each candidate's top three views (LLM plus web search)
- chances of winning (race ratings, district partisan lean)
- incumbents' voting records
- campaign money for county, city and school races, which file locally (the City of Austin publishes its own data)
- lobby spending on state officeholders (TEC lobby reports), late-filing fines, and fundraising over time
