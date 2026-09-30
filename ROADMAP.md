# Roadmap

What to fix, tidy up and build next, then what's already done. The open items come from a review of the whole codebase in September 2026. `trackaipac_cache/` and `tec_cache/` were only skimmed, since they're libraries copied into this repo. For how VoteBot works inside, see [DEVELOPMENT.md](DEVELOPMENT.md).

- [Bugs](#bugs)
- [Improvements](#improvements)
- [Tooling](#tooling)
- [Features](#features)
- [UI and UX](#ui-and-ux)
- [Done](#done)

## Bugs

Most severe first.

### 1. An abort during the body read comes back as `null` (minor)

`request()` in [static/js/api.js:17](votebot/static/js/api.js#L17) reads the body with `response.json().catch(() => null)`. So when a call is aborted after its headers arrived but before its body did, it returns `null` instead of throwing the AbortError. `lookup()` in `ballot.js` checks its signal, so it's safe. But `ask()` in [static/js/suggest.js:86](votebot/static/js/suggest.js#L86) destructures the `null`, catches the TypeError and closes the suggestion box while the voter's newer request is still on its way, so the box can flicker.

Fix: in `request()`, rethrow an AbortError from `response.json()` and turn only other errors into `null`.

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
- `HttpCache` parses and serializes JSON and talks to SQLite synchronously (`_load`, `_store`). Some payloads are large: the statewide candidate list is 2.6 MB and a poll page up to 800 KB.
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
   - early-voting and election-day locations, also on the printed sheet and the wallet card;
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

- **Offline:** make VoteBot installable (a web app manifest and a service worker), keeping the last ballot, picks and notes for use without a connection. For example, in line at the polls.

  Deferred, because browsers only run a service worker on `https://` or on `localhost`. A phone that reaches the Docker image at `http://<LAN address>:8000` would get nothing from it; it would need HTTPS in front of VoteBot (Caddy, or Tailscale serve), and the README would have to explain that. Until then, the printed sheet and the wallet card cover the polls.

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

### Roadmap and rules for coding agents ([#9](https://github.com/Fahd-Siddiqui/VoteBot/pull/9), Sep 29)

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

### Roadmap bugs and dead code ([#10](https://github.com/Fahd-Siddiqui/VoteBot/pull/10), Sep 29)

- [x] Other websites can no longer use the Settings actions from the voter's browser. A POST or PUT that another page started is refused (`Sec-Fetch-Site`, `Origin`). So is any request whose `Host` isn't `localhost`, an IP address or a name in the new `VOTEBOT_ALLOWED_HOSTS`, which stops DNS rebinding.
- [x] When Refresh can't download the State Board of Education map again, its message says so and the old map is kept. It used to fail with "Request failed (500)".
- [x] A new ballot lookup cancels one still running, so an older answer can't replace a newer ballot.
- [x] When a county has no ballot order, the statewide candidate list no longer puts judge and DA races from elsewhere in Texas on the ballot. It only keeps races it can place (federal, statewide, congressional, legislative, SBOE), and a note says the others aren't listed.
- [x] The cache reads a row's times and value in one query, and a missing row is a cache miss. So a Clear in another process can't crash a lookup halfway through. Within one process this couldn't happen yet; it could once cache work moves to threads ([Improvement 2](#2-keep-heavy-work-off-the-event-loop)).
- [x] Dead code removed: `h()`'s unused `text`, `dataset` and `on…` props, and the `export` on two functions only `source-cards.js` uses. The API fields the page doesn't read stay on purpose:
  - they're small;
  - the tests check them;
  - `precinct_source` and `school_district` are planned for the UI (see [UI and UX](#ui-and-ux)).

### UI and UX (Sep 29, branch `feat/ui-ux`)

- [x] On a phone or a narrow window, the left pane is a one-line top bar, with the address and the pages each behind a button (`topbar.js`, added to every page from JS). On the ballot, the section chips stay in view in the sticky strip, with the progress and Next; View, Clear picks and Print sit under the heading.
- [x] The progress counts propositions too: "5 of 12 races · 1 of 2 propositions", in one bar.
- [x] The address card shows the school district. On the ballot it also says where the precincts came from ("Precincts from Ballotpedia" or "Precincts you entered"), with Edit to change them, even when no race is waiting on them.
- [x] When races depend on the voter's precinct, a line at the top of the ballot links to the precinct form.
- [x] Getting through a long ballot:
  - "Next race to pick" opens the next unpicked race and goes to it;
  - `j`/`k` move between races;
  - a View menu holds Collapse all, Expand all, "Collapse a race when I pick" and "Only races I haven't picked". A race picked while the filter is on stays until the filter runs again, so it doesn't vanish mid-pick.
- [x] Details: ‹ and › step through a race's candidates without closing it. A "?" now marks a likely match on the candidate's row too: on that source's first badge, or on the Details button when the source has no badge.
- [x] A lookup that takes more than a moment shows a skeleton ballot, and a line saying later lookups of the address are instant.
- [x] "Clear picks" on the ballot, and "Clear my picks & notes" and "Clear all browser data" in Settings, clear at once and offer Undo for 10 seconds (`toast.js`). Clearing what the server saved still asks first, since it can't be put back.
- [x] The section on screen is marked in the section list as you scroll; on a phone the chip row scrolls to it.
- [x] Fixed: after a lookup failed, the precinct forms looked up the address that failed, because `lastRequest` was set before the answer came back. The ballot now keeps the request behind the ballot on screen (`shownRequest`), set only when a lookup succeeds.
- [x] Print: a wallet card to cut out and fold, and "Election day: <weekday, date>" at the top of both layouts. The polling place waits for [Feature 1](#features).
- [x] Offline is deferred, with the reason written in [UI and UX](#ui-and-ux).
