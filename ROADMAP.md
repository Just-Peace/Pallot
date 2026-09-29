# Roadmap

What to fix, tidy up and build next, then what's already done. The open items come from a review of the whole codebase in September 2026. `trackaipac_cache/` and `tec_cache/` were only skimmed, since they're libraries copied into this repo. For how VoteBot works inside, see [DEVELOPMENT.md](DEVELOPMENT.md).

- [Bugs](#bugs)
- [Dead code](#dead-code)
- [Improvements](#improvements)
- [Tooling](#tooling)
- [Features](#features)
- [UI and UX](#ui-and-ux)
- [Done](#done)

## Bugs

Most severe first.

### 1. Any web page can trigger the Settings actions

The Settings actions have no login (the README says so). But the problem is bigger than someone on the network using them: any web page open in the voter's browser can use them too.

`POST /api/sources/{id}/refresh`, `POST /api/sources/{id}/clear` and `POST /api/cache/clear` take no body. So a cross-site `<form method="post">` or a `fetch(..., { mode: "no-cors" })` reaches them without a CORS preflight. A malicious page could start the Texas Ethics Commission refresh (a 1 GB download) or wipe every cache. It could also refresh Photon, which sends every saved address text to it again. The Docker default publishes VoteBot on every interface, which makes it easier to reach. DNS rebinding also gets around a plain `Origin` check, because the attacker's name resolves to VoteBot's own address.

Fix, in [votebot/api.py](votebot/api.py):
- A middleware that refuses non-GET `/api/` requests when `Sec-Fetch-Site` is `cross-site`, or when `Origin` doesn't match `Host`.
- A `Host` allowlist against DNS rebinding: `localhost`, IP literals (which covers the LAN addresses Docker users type in), plus a new `VOTEBOT_ALLOWED_HOSTS` for anyone who uses a hostname.
- Tests in [tests/test_api.py](tests/test_api.py).

### 2. An SBOE refresh failure is a bare server error

In Settings, Refresh on "Address lookup & districts" calls `sboe.download()` without catching anything ([votebot/admin.py:247](votebot/admin.py#L247)). A network error or a bad zip becomes an HTTP 500, so the page shows "Request failed (500)" and loses the "Refreshed N cached responses" message.

Fix: catch `httpx.HTTPError`, `ValueError` and `zipfile.BadZipFile`, and add "Couldn't re-download the State Board of Education map (…); kept the old one." to the message.

### 3. Overlapping ballot lookups can show a stale ballot

`lookup()` in [static/js/ballot.js:100](votebot/static/js/ballot.js#L100) doesn't cancel a lookup already in flight. The precinct form's "Update my ballot" button also stays enabled during a lookup. When two lookups overlap, the older one can finish last and replace the newer ballot.

Fix: `lookup()` aborts the previous request with an AbortController, or ignores a response that isn't from the latest request. For the AbortController, `api.post` needs the `signal` option that `api.get` already has ([static/js/api.js](votebot/static/js/api.js)).

### 4. Special elections may list other regions' races (plausible; needs a fixture)

When a county has no ballot order (as in some special elections), `_rows` ([votebot/ballot.py:343](votebot/ballot.py#L343)) falls back to the statewide candidate list. It keeps every row whose office type is `FD`, `SW` or `SR`, whatever its county. `classify` turns a state-regional (`SR`) office that matches no pattern into `whole_county`, and `placement` then includes it. So a special election for a district judge or district attorney elsewhere in Texas could show on this voter's ballot.

The existing test (`test_special_election_comes_from_the_statewide_list_when_the_county_has_no_ballot_order`) only covers a State House seat, which the district filter catches.

Next step: record a fixture with an `SR` special election and see what the ballot shows. If the bug is real, keep only the `SR` rows whose county matches, or whose district is known to include this county.

### 5. Clearing the cache during a lookup can crash the lookup

`HttpCache.get_json` reads a row's metadata (`_meta`) and then its value (`_value`, [votebot/http_cache.py:332](votebot/http_cache.py#L332)) in two separate queries. If Clear runs in Settings between the two, `_value` gets no row and raises `TypeError`, and the lookup fails with a 500.

Fix: read the metadata and the value in one query, and treat a missing row as a cache miss.

## Dead code

A sweep of every Python definition, JS export and CSS class found little:

- [static/js/dom.js](votebot/static/js/dom.js), `h()`: the `text`, `dataset` and `on…` prop branches are never used.
- [static/js/source-cards.js](votebot/static/js/source-cards.js): `breakdownBlock` and `cardPanel` are exported but only used inside that file.
- API fields the page never reads:
  - `Candidate.ballot_name` and `ballot_position`
  - `Location.school_district`, `lat`, `lon` and `geocoder`
  - `Districts.precinct_source` and `county_id`

  `precinct_source` and `school_district` are worth showing (see [UI and UX](#ui-and-ux)). The rest are cheap to keep, and some are checked in tests, so drop them only if the payload matters.
- Python: nothing unreferenced.

## Improvements

Structural changes, not micro-optimizations.

### 1. Ask the enrichment sources at the same time

`enrich.run` ([votebot/enrich.py:54](votebot/enrich.py#L54)) waits for each source before asking the next:
1. the Texas SOS statewide candidate list;
2. the FEC: one call per race, plus five per candidate with a key;
3. FiftyPlusOne's poll pages: 500 polls a page, nationwide.

None of them depends on another. Start them together with `asyncio.gather`, then add their cards in the current fixed order, because card order is the order of the tabs in Details. This speeds up a lookup whose data isn't cached yet, which is when a lookup is slow.

### 2. Keep heavy work off the event loop

Several steps block the server while they run:
- `HttpCache` parses and serializes JSON and talks to SQLite synchronously (`_value`, `_store`). Some payloads are large: the statewide candidate list is 2.6 MB and a poll page up to 800 KB.
- The Texas Ethics Commission snapshot is 2.8 MB, parsed on first use and after every refresh (`BundledSnapshot.document()`).
- SBOE point-in-polygon (`sboe.locate`) runs on the event loop.
- `Admin.overview()` walks the snapshot folders on every Settings load.

While one of these runs, every other request waits, such as address suggestions typed in another tab during a first lookup. Move the big ones to `asyncio.to_thread`. The SQLite connection already allows other threads and has a lock.

### 3. One table for the "paused" notices

`Admin._notice` ([votebot/admin.py:141](votebot/admin.py#L141)) repeats the same "Paused until … after X refused a request; what it already sent still shows" block for Ballotpedia, Photon, FiftyPlusOne and the FEC. Give each source its wording in one table (or on `SourceInfo`) and build the notice once.

### 4. Share the page chrome

The sidebar is copied into all five pages (`index`, `settings`, `faq`, `about`, `privacy`), and so is the favicon's data URI. The sidebar holds the brand, the navigation and the address card. The copies have started to drift. On the ballot page, the footer's list of sources and the welcome steps don't mention the polls. Render the shared parts from `page.js` (or a small `chrome.js`), so a new link or source is added once.

### 5. Seats for Texas Ethics Commission matches on Ballotpedia-only ballots

With Texas SOS off, races come from Ballotpedia and have no `OfficeScope`. `tec.cards` ([votebot/sources/tec.py:472](votebot/sources/tec.py#L472)) then gets no seat, and matches state candidates by name against every filer in Texas. Such a match is only ever "likely", but a seat makes it "exact" and rules out namesakes.

Fix: work the seat out from Ballotpedia's district type and name. For example, a State House District 49 race gives `STATEREP:49`.

### 6. Cache housekeeping (low priority)

Expired rows stay in `cache.sqlite3` forever, as the copy to serve when a source is down. For Photon's half-typed addresses and for addresses that weren't found, that old copy is no use. At startup:
- delete rows of those sources that expired long ago (say 30 days);
- delete expired rows from `flags`.

This keeps the file, and what it holds about typed addresses, small.

## Tooling

### 1. Faster tests

The offline suite takes about two minutes: 297 tests ran in 115 s on the development machine. Measure first with `uv run pytest --durations=20`. The likely causes:
- **Real throttling.** Each test's app uses `HttpCache`'s real `min_interval`, so its waits between calls to one source really happen. For the FEC that's 0.1 s between calls, and a ballot lookup with an FEC key makes dozens of calls. Most ballot tests start with an empty cache, so each one waits seconds.

  Fix: let `create_app` take the intervals, and have the tests' `make_app` pass none. Keep one test that checks the throttling itself.
- **A new app for every test.** Each one copies the TrackAIPAC and TEC fixture snapshots into a new data folder and parses them again. Tests that only read could share one app per module.
- **One process.** Each test has its own temporary data folder, so the tests could run in parallel with `pytest-xdist` (`-n auto`).

Aim for under 30 seconds, so running the whole suite before every commit stays cheap.

### 2. GitHub Actions

Nothing runs the tests automatically yet. Add a workflow under `.github/workflows/`:
- **The tests.** On every pull request into `develop` and every push to it, run `uv sync --locked`, then `uv run pytest`.
  - `--locked` also catches a `pyproject.toml` changed without `uv lock`.
  - Skip the run when only Markdown files changed (`paths-ignore: ["**.md"]`).
  - Make the check required before merging.
- **The Docker image.** Build it when `Dockerfile`, `compose.yaml`, `pyproject.toml` or `uv.lock` changes. A missing package-data pattern only shows up there.
- **A linter.** Run ruff for unused imports and variables, so dead code is caught without anyone looking for it (the "Leave it clean" rule in [AGENTS.md](AGENTS.md)).
- **Speed.** Use `astral-sh/setup-uv` with its cache, and `concurrency`, so that a new push cancels the run it replaces.
- **Later: the live tests,** only on demand (`workflow_dispatch`), with the FEC key as a repository secret. Never run them on every push, since they call the real services.
- **Later: fresher snapshots.** A weekly job that refreshes the bundled TrackAIPAC and TEC snapshots and opens a pull request when they changed. TEC's server blocks bursts of requests, but a refresh makes one small request and at most one download, so once a week is fine.

## Features

Up to ten, roughly in order of value to a voter. Items marked *(README)* were on the README's old "Not built yet" list.

1. **Where and when to vote.** Right on the ballot page:
   - the key dates: registration deadline, early voting, the last day to apply to vote by mail;
   - a link to check your registration;
   - the county elections office, with its sample ballot;
   - early-voting and election-day locations;
   - an `.ics` file to add the dates to a calendar.
2. **Incumbents' voting records** *(README)*. For Congress, the Congress.gov API, which takes the same api.data.gov key as the FEC. For the Texas Legislature, Open States.
3. **District lean and past results** *(README: chances of winning)*. The Texas Legislative Council publishes election results for each district plan, on the same portal as the SBOE map. Show the last results for each seat (for example "2024: R+12 in this district"), plus race ratings where they're open.
4. **Each candidate's top views** *(README)*. Opt-in, using an LLM with web search. A short summary with every claim cited, cached per candidate, and refreshed only on request.
5. **Fundraising over time** *(README)*. Money raised per report period from the FEC and per report from the TEC (which `tec_cache` already reads). Show it as a small chart, with cash on hand over time.
6. **Proposition explainers.** For Texas constitutional amendments, the Texas Legislative Council's and the House Research Organization's analyses, with the arguments for and against. For local bonds, the amount, what it pays for and the tax impact.
7. **Local campaign finance** *(README)*. County, city and school candidates file locally. Start with the City of Austin's open data, then the largest counties and cities.
8. **Lobby spending and late-filing fines** *(README)*. From the Texas Ethics Commission's lobby reports and penalty records, for state officeholders.
9. **Picks you can move and share.**
   - Export and import picks and notes as a file, to back them up or move to another device.
   - A share link that carries a slate in the URL, so nothing is stored on the server.
   - Notes carried from the primary to the general for the same candidate.
10. **Groundwork for other states.** Some of this already exists: the `STATES` table in `labels.js` and the `TEXAS_FIPS` check. Define per-state adapters for:
    - the official ballot order;
    - state campaign finance;
    - district maps the Census doesn't cover (Texas's SBOE map, for example).

    A second state can then be added without touching the Texas code.

## UI and UX

- **Phones:** below 960px, the whole left pane (address, sections, links) sits above the ballot, so the races start a screen or more down. Make it a compact top bar with the address behind a button, and keep the section chips sticky.
- **Progress includes propositions:** the bar counts races only. Show "5 of 12 races · 1 of 2 propositions", or count both in one bar.
- **Where the precincts came from:** say "Precincts from Ballotpedia · edit" when they didn't come from the voter (`precinct_source`), and show the school district on the address card (`school_district`). The server already sends both.
- **Precinct prompt at the top:** when races are waiting under "Depends on your precinct", show a line at the top of the ballot that jumps to the precinct form.
- **Getting through a long ballot:**
  - a "Next race to pick" button;
  - `j`/`k` to move between races;
  - an option to collapse a race once it's picked;
  - a filter that shows only unpicked races.
- **Details dialog:**
  - previous and next buttons, to read the candidates in a race one after another without closing the dialog;
  - on the candidate row, a "?" when a source's match is only "likely", as the tab already shows.
- **First lookup:** a lookup whose data isn't cached can take several seconds. Show a skeleton ballot and a line saying later lookups are instant.
- **Undo instead of confirm:** "Clear picks" could clear at once and offer Undo, rather than asking first.
- **Offline:** make VoteBot installable (a web app manifest and a service worker), keeping the last ballot, picks and notes for use without a connection. For example, in line at the polls.
- **Print:**
  - a compact wallet-size layout;
  - the election date and, once feature 1 exists, the polling place on the sheet.

## Done

What's been built so far, oldest first, taken from the git history. Each group is a pull request into `develop`, except the first two, which were committed directly.

### First version (Sep 27, 2026, [5e9f1b6](https://github.com/Fahd-Siddiqui/VoteBot/commit/5e9f1b6))

- [x] A ballot for any Texas address, built from:
  - the US Census geocoder, for the county and districts;
  - the Texas Legislative Council's map, for the State Board of Education district;
  - the Texas SOS ballot order, filtered down to the voter's districts.
- [x] Ballotpedia, optional, for city, school and special-district races and the voter's precincts.
- [x] Candidate details from Texas SOS, Ballotpedia and TrackAIPAC (through the copied-in `trackaipac_cache`). Candidates are matched by name, and each match is labelled exact or likely.
- [x] A SQLite cache for every outbound request, with refresh and clear per source.
- [x] The ballot page:
  - collapsible races;
  - picks and notes kept in the browser;
  - a details view per source;
  - web search links;
  - a printable sheet.
- [x] Tests against recorded responses. The project is managed with uv (`pyproject.toml`, `uv.lock`).

### UI refresh (Sep 27, [24d3555](https://github.com/Fahd-Siddiqui/VoteBot/commit/24d3555))

- [x] A calmer left pane, with the saved-address card (and Change) and the section list. The progress bar, Print and Clear picks are pinned above the ballot.
- [x] A collapsed race is one line, with the pick on the right.
- [x] A pick takes its party's colour, and party badges are solid fills.
- [x] Source badges link to the source: the Ballotpedia profile, and the TrackAIPAC list with the Israel-lobby total.
- [x] A write-in line on every race. It's saved, shown when the race is collapsed, and printed.
- [x] A web search link per candidate, with nine search engines to choose from.

### Settings, FAQ, About and Privacy pages ([#1](https://github.com/Fahd-Siddiqui/VoteBot/pull/1), Sep 28)

- [x] Settings moves to its own page: web search, sources, and picks and notes.
- [x] Three new pages:
  - FAQ;
  - About, which credits every source;
  - Privacy: what VoteBot sends and keeps, where, and for how long.
- [x] The same left pane on every page, showing the remembered address. Change opens the ballot page with its form open.
- [x] The ballot reloads when settings changed while it was open. Notes and write-ins save as soon as their box loses focus.

### Campaign finance ([#2](https://github.com/Fahd-Siddiqui/VoteBot/pull/2), Sep 28)

- [x] `tec_cache` builds a snapshot of state candidates' money from the Texas Ethics Commission's nightly 1 GB export:
  - totals since the last November general election;
  - donations by kind, size and state;
  - the largest donors;
  - outside spending naming each candidate.

  When the export hasn't changed, a refresh costs one small request; otherwise it's one streaming download. `--zip` reads a zip downloaded in a browser.
- [x] The FEC as a source:
  - one cached call per congressional race, for the race's money;
  - with a free api.data.gov key, where the money came from, donation sizes, donors' states and employers, and outside spending.

  The key travels in a header and is never stored.
- [x] Money breakdowns as labelled bars in Details, and each race's money at the top of the race, in party colours.
- [x] README, About, FAQ and Privacy cover both sources.

### Caching and Settings fixes ([#3](https://github.com/Fahd-Siddiqui/VoteBot/pull/3), Sep 28)

- [x] After a failed request, VoteBot serves the old copy and doesn't ask that source again for 15 minutes.
- [x] The cache handles pausing a source: Ballotpedia on 401/403/429, the FEC on 429. A paused source still serves what's stored, and Refresh skips it.
- [x] Settings shows what each source has saved and how the last lookup used it, plus the total size on disk.
- [x] A "Clear all browser data" button. "Clear my picks & notes" now keeps the address, as its label says.
- [x] Configuration can come from a `.env` file.
- [x] Cleanups:
  - TrackAIPAC and TEC share one snapshot class;
  - an unused endpoint, fields and helpers were removed.

### Compare candidates ([#4](https://github.com/Fahd-Siddiqui/VoteBot/pull/4), Sep 28)

- [x] A "Compare candidates" dialog on each race's money box, using the TEC for state races and the FEC for congressional ones. It shows:
  - totals;
  - every breakdown, as grouped bars;
  - largest donors, employers and outside spenders in columns, with a name that appears for more than one candidate flagged.
- [x] A Dollars / Share toggle for the bars.
- [x] `tec_cache` counts donations by donor location, and counts outside expenditures.

### Employer "NULL" fix ([#5](https://github.com/Fahd-Siddiqui/VoteBot/pull/5), Sep 28)

- [x] Some donors' employer is the text "NULL". It no longer shows up as an employer named "Null", or as a name shared between candidates in Compare.

### Address suggestions and the money FAQ ([#6](https://github.com/Fahd-Siddiqui/VoteBot/pull/6), Sep 28)

- [x] Address suggestions from Photon as the voter types:
  - cached for 30 days;
  - marked "street only" when OpenStreetMap doesn't have the house number;
  - with an on/off switch in Settings.
- [x] A "Campaign money" section in the FAQ on how the FEC and TEC figures are put together. The money boxes, the source tabs and Compare link to it.
- [x] Settings fixes:
  - "Paused until" shows a readable local time.
  - Refreshes that download or re-send a lot ask first.
  - Links in source notices can be clicked.
- [x] FEC donation sizes group each donation by its own amount, and the notes now say so.

### Polls ([#7](https://github.com/Fahd-Siddiqui/VoteBot/pull/7), Sep 29)

- [x] Polls from FiftyPlusOne for U.S. Senate, U.S. House and Governor races. Each race gets one stacked bar, showing each candidate's median across each pollster's latest poll. A Polls tab lists the polls.
- [x] FEC outside spending is marked "for" (blue) or "against" (amber), and the notes say none of it went to the campaign.
- [x] TrackAIPAC's notes link to trackaipac.com, not to VoteBot itself.

### Docker ([#8](https://github.com/Fahd-Siddiqui/VoteBot/pull/8), Sep 29)

- [x] A Docker image built in two stages from `uv.lock`, running as a non-root user. `compose.yaml` shares `data/` with `uv run votebot`.
- [x] The README is about using VoteBot, with a Quick start at the top; working on VoteBot moves to DEVELOPMENT.md.

### Roadmap and rules for coding agents (Sep 29, branch `docs/roadmap-and-agents`)

- [x] This roadmap, from a review of the whole codebase: bugs, dead code, improvements, tooling, features, UI and UX ideas, and what's done.
- [x] AGENTS.md, the rules for working on VoteBot:
  - the workflow, starting from the roadmap;
  - which docs to update;
  - code rules;
  - what VoteBot depends on;
  - recording what you notice along the way;
  - the checks before committing.

  CLAUDE.md loads it for Claude Code.
- [x] The README's "Not built yet" list moved into the roadmap's features.
