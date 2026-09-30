# Roadmap

What to fix, tidy up and build next, then what's already done. The open items come from a review of the whole codebase in September 2026. `trackaipac_cache/` and `tec_cache/` were only skimmed, since they're libraries copied into this repo. For how VoteBot works inside, see [DEVELOPMENT.md](DEVELOPMENT.md).

- [Bugs](#bugs)
- [Improvements](#improvements)
- [Tooling](#tooling)
- [Features](#features)
- [UI and UX](#ui-and-ux)
- [Reviews](#reviews)
- [Spot checks](#spot-checks)
- [Done](#done)

## Bugs

Nothing open right now.

## Improvements

Nothing open right now.

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

Roughly in order of value to a voter. Items marked *(README)* were on the README's old "Not built yet" list.

1. **Where to vote.** "When to vote" is done (under [Done](#done)); what's left:
   - **The county elections office**, with its sample ballot. The SOS publishes every county's elections official (name, address, phone, email) on [county.shtml](https://www.sos.state.tx.us/elections/voter/county.shtml), also as a spreadsheet (`election-duties-1.xlsx`), with no website column. Read it like the key dates (one cached page, `HttpCache.get_text`), and show the voter's county on the When to vote card instead of the link to the whole list.
   - **Early-voting and Election Day locations**, also on the printed sheet and the wallet card. There's no free statewide lookup by address:
     - My Voter Portal shows a voter's polling place only after a login with name and date of birth.
     - Google's Civic Information API (`voterinfo`) still returns `pollingLocations` and `earlyVoteSites`. But it needs a key, its Texas coverage is uncertain, and it only fills in days before an election. If it's added, make it optional (like the FEC key), with the county office as the fallback.
     - Counties publish their own lists, in different formats (Harris has an ArcGIS layer, most have PDFs or web apps). Not worth a scraper per county.
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
11. **Your election precinct.** The "Pct 227" on a voter registration certificate, shown as "Precinct 227" on the Your districts card and as "Pct 227" on the printed sheet. What was found:
    - **The Census doesn't have it.** The geocoder's "Current" vintage has no voting-district layer (see `tests/fixtures/census_capitol.json`).
    - **The Texas Legislative Council publishes it.** Its dataset `vtds` on data.capitol.texas.gov, the portal the SBOE map comes from, has VTDs, "the census geographic equivalent of county election precincts". The newest, `VTDs_24PG.zip` (46.6 MB, 9,712 precincts, modified 2025-01-29), matches the precincts of the 2024 primary and general elections. Counties may have changed some since, especially after the 2025 congressional map, so say which elections the number is from, and that the certificate wins.
    - **Its API finds the newest map.** The portal is CKAN: `https://data.capitol.texas.gov/api/3/action/package_show?id=vtds` lists the resources (`name`, `format` "SHP", `url`, `created`, `last_modified`, `size`), so a `VTDs_26…` is picked up without a code change.
    - **The file is a shapefile, not KML.**
      - The zip holds `.shp` (73 MB unzipped, polygons), `.shx` and `.dbf`.
      - The `.dbf` fields are `CNTY`, `VTD` ("0011"), `CNTYKEY`, `VTDKEY` and `CNTYVTD`.
      - `CNTY` is the county's alphabetical number, the same as the SOS's `county_id`, and equals `(county FIPS + 1) / 2` (Travis: 227).
      - A precinct in pieces is suffixed ("0001A", "0001B"), so show the VTD without its suffix or leading zeros.
    - **It's in the Texas State Mapping System (EPSG:3081).** That's a Lambert conformal conic on NAD83 (GRS 1980), with central meridian −100°, standard parallels 27°25′ and 34°55′, latitude of origin 31°10′, and false easting and northing of 1,000,000 m. The projection is a short formula, so no GIS library is needed.
    - **The server ignores `Range`,** so it's one streaming GET for the whole zip.

    How to build it: its own source in Settings, with an on/off switch, a Refresh that asks first (about 45 MB), and Clear. The index is cached through `HttpCache` for a week. The zip is downloaded into `data/vtds/` like the SBOE map, and again only when the index shows a newer one. A lookup keeps the voter's county, then the polygons whose bounding box holds the point, then does an even-odd ray cast, off the event loop. Nothing is guessed near a boundary.

    Then draw the precinct on the map of your districts: a `precinct` kind in `GET /api/district-outlines` (`outlines.py`), its polygons simplified like the SBOE's (`sboe.simplify`), and a fifth colour and dash in `district-map.js` and `app.css`, checked like the other four.

## UI and UX

- **Offline:** make VoteBot installable (a web app manifest and a service worker), keeping the last ballot, picks and notes for use without a connection. For example, in line at the polls.

  Deferred, because browsers only run a service worker on `https://` or on `localhost`. A phone that reaches the Docker image at `http://<LAN address>:8000` would get nothing from it; it would need HTTPS in front of VoteBot (Caddy, or Tailscale serve), and the README would have to explain that. Until then, the printed sheet and the wallet card cover the polls.

## Reviews

Whole-codebase reviews, to run once the open work above has settled. Each one reads the code afresh and files what it finds in this roadmap's sections (Bugs, Improvements, Tooling, Features, UI and UX), with `file:line` and a suggested fix.

1. **Backend.** All of `votebot/` except `static/`, plus `trackaipac_cache/` and `tec_cache/`, which the September review only skimmed:
   - correctness against each source's real answers, and how old the recorded fixtures are;
   - `HttpCache`: lifetimes, pauses, the zero-calls rule on a repeat lookup, and the work done in threads;
   - matching: exact or likely, and namesakes;
   - dead code, duplication, type hints, and the tests' coverage and speed.
2. **Frontend code.** `votebot/static/js/`, `css/app.css` and the five pages:
   - module structure, shared helpers, and dead exports and CSS classes;
   - API data inserted with `h()`, never `innerHTML`, and links built with `safeUrl`/`extLink`;
   - what's kept in `localStorage` (versions, Undo), event listeners, and redraws;
   - accessibility in the markup: landmarks, labels, focus order, `aria-*`.
3. **UX.** The voter's whole journey, at desktop and phone widths, in light and dark mode:
   - a first visit: entering an address, suggestions, errors, and the first lookup's wait;
   - working through the ballot: Next, the section chips, picks, notes, write-ins, Details and Compare;
   - When to vote, Your districts, the printed sheet and the wallet card; then Settings, FAQ, About and Privacy;
   - wording, visual hierarchy, contrast, tap targets, and use with a keyboard or screen reader.
4. **Security.**
   - the Settings actions, which have no login: the `Host` and cross-site checks in `api.py`, and the `127.0.0.1` binding;
   - keys: the FEC key only ever in `source_headers`, never in the cache, a log line or an error;
   - what reaches the page from the sources: cross-site scripting through `h()`, `linkedText` and `safeUrl`;
   - outbound requests: whether anything the voter types could send a request somewhere unintended, and the `.ics` endpoint's inputs;
   - the Docker image (non-root user, what's copied in), and dependencies in `uv.lock` with known vulnerabilities.

## Spot checks

The tests only check VoteBot against recorded answers (`tests/fixtures/`). These checks compare what it shows with the sources' own websites. Run them before an election, and after a change to how a source is read.

What to check, for each address:
1. **The ballot against VoteTexas.gov:** the county, the districts (U.S. House, State Senate, State House, SBOE), the commissioner and JP precincts, every race, and each candidate's name, party and ballot order. Compare with My Voter Portal (**Am I registered?**), which shows the voter's county, precinct and districts, and with the county's sample ballot, which VoteTexas.gov links to.
2. **The ballot against Ballotpedia:** the same, against Ballotpedia's sample ballot for the address. Also compare the city, school and special-district races, the city council district, and how each candidate's name is written.
3. **TrackAIPAC:** each badge and its Israel-lobby total, against the candidate's entry on trackaipac.com (Candidates, Endorsements or Congress). The snapshot's date is in Settings.
4. **Campaign finance:** raised, spent and cash on hand for a few candidates, plus one breakdown each (donation sizes, largest donors):
   - congressional candidates, against their page on fec.gov for the whole election (2021–2026 for the Senate);
   - state candidates, against their reports in the Texas Ethics Commission's campaign finance search: the latest report's cash on hand, and the reports added up since the date the card gives.
5. **Polls:** each poll in a race's Polls tab (pollster, dates, sample, each candidate's share), against FiftyPlusOne. Then work out the bar's median by hand from each pollster's latest poll.

Before comparing, press Refresh on the source in Settings, or allow for its "data as of" date: a copy can be up to a day old, and a week for the FEC. File each mismatch under [Bugs](#bugs), with:
- the address;
- what VoteBot showed;
- what the source's site showed, with a link;
- the "data as of" date.

### 1. By hand

- Use your own address, since only you can log in to My Voter Portal, and the Capitol (1100 Congress Ave, Austin, TX 78701).
- Check in the running app, at what a voter sees: the ballot, Your districts, the badges, Details, Compare and the poll bars.
- Note the date of each pass here.

### 2. By an LLM

A repeatable pass for a coding agent with web access:
- Run VoteBot on a copy of `data/` (`VOTEBOT_DATA_DIR=<copy> uv run votebot --port 8765`). Read each ballot as JSON with `POST /api/ballot` and `{"address": …}`: the figures are in each card's `facts`, `badges` and `breakdowns`, and in the race cards.
- Use only the public addresses in `tests/conftest.py` (the Capitol, UT Austin, downtown Houston, north Austin), never the maintainer's own.
- Skip My Voter Portal, which needs a name and a date of birth. For check 1, use the county's published sample ballot (from the county elections office, on the SOS's county list), and say in the report that the portal wasn't checked.
- Read each source's public pages, one request at a time and within their terms:
  - Ballotpedia's pages for the races, not its API;
  - fec.gov;
  - the TEC's search;
  - trackaipac.com;
  - fiftyplusone.news.
- Report a table for each address: the check, what VoteBot says, what the source says, the link, and whether they match. File each mismatch under Bugs, as [AGENTS.md](AGENTS.md) describes.

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
- [x] The cache reads a row's times and value in one query, and a missing row is a cache miss. So a Clear in another process can't crash a lookup halfway through. Within one process this couldn't happen yet; it could once cache work moved to threads, which [#14](https://github.com/Fahd-Siddiqui/VoteBot/pull/14) did.
- [x] Dead code removed: `h()`'s unused `text`, `dataset` and `on…` props, and the `export` on two functions only `source-cards.js` uses. The API fields the page doesn't read stay on purpose:
  - they're small;
  - the tests check them;
  - `precinct_source` and `school_district` are planned for the UI (see [UI and UX](#ui-and-ux)).

### UI and UX ([#11](https://github.com/Fahd-Siddiqui/VoteBot/pull/11), Sep 29)

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

### When to vote ([#12](https://github.com/Fahd-Siddiqui/VoteBot/pull/12), Sep 29)

The "when" half of [Feature 1](#features). "Where" isn't possible yet, because Texas's polling-place lookup needs a login.
- [x] Key election dates from the Texas SOS's [Important Election Dates](https://www.sos.state.tx.us/elections/voter/important-election-dates.shtml) page (`sources/key_dates.py`): the last day to register, early voting, and the last day for a mail-ballot application to arrive, for every election on the page. The page is read as text through `HttpCache` (new `get_text`), cached for a day, and parsed with the standard library. It has an on/off switch, Refresh and Clear in Settings, and pauses for an hour after a refusal. votetexas.gov was the other candidate, but it shows only day and month for the next election.
- [x] "When to vote" at the top of the ballot (`key-dates.js`), as a compact list:
  - register by, early voting, and Election Day with the polls' hours;
  - the next date still to come in bold with how far off it is ("in 6 days"), and past ones dimmed;
  - "Am I registered?" (My Voter Portal), "Where to vote" (the SOS's list of county elections offices), and the source.
- [x] The mail-ballot deadline sits apart, in a closed "Voting by mail?" with who qualifies and how to apply, since most Texans can't vote by mail. It's never the bold "next" date, and "Add all to calendar" leaves it out.
- [x] Calendar files (`GET /api/key-dates.ics`, `ics.py`): one per date from its calendar icon, or every date still to come with "Add all to calendar". The events are all-day, have no place, and have fixed UIDs, so adding a file again updates its events. votetexas.gov has no `.ics` of its own.
- [x] Print: the full page and the wallet card add the early-voting dates under the election day, and the full page adds the polls' hours.
- [x] FAQ: a "When and where to vote" group (where the dates come from, calendar files, why there's no polling place, voting by mail). README, DEVELOPMENT, About, Privacy and the welcome steps updated. The FAQ's "Why is a source paused?" now names FiftyPlusOne too, which it had left out.

### Your districts ([#13](https://github.com/Fahd-Siddiqui/VoteBot/pull/13), Sep 29)

- [x] "Your districts" at the top of the ballot, like a voter registration certificate, in three lines: U.S. House, State Senate, State House and SBOE; the county with its commissioner and JP & constable precincts; the city, city council district and school district. "—" marks a district that isn't known. An approximate address gets a line saying to check the districts.
- [x] The city council district, from Ballotpedia's "City-town subdivision" (`council_district_in`), in the API's `districts.city_council`.
- [x] The precinct form moved from "Depends on your precinct" and the address card into Your districts. It's open by itself while races wait on a missing number, and says which one to enter from the voter registration certificate; otherwise **Edit** opens it. After **Update my ballot**, a toast offers **Show**, which goes to the precinct's races. "Depends on your precinct" keeps a link up to the form, and the line above the races that linked to it is gone.
- [x] One number for the JP and the constable, since each justice precinct elects one of each (`_jp_is_constable`). The commissioner precinct only takes 1 to 4 (`PrecinctInput`).
- [x] A precinct from Ballotpedia can be cleared: the form sends `null` for an empty field, and `_precincts()` reads the request with `exclude_unset`. **Use Ballotpedia's numbers** puts them back.
- [x] The two cards sit under the sticky strip, so "Next race to pick" and the section chips stay on a phone's first screen, and side by side on a wide screen. They share one panel style.
- [x] The address card in the left pane shows the address, city and county, without the districts, which Your districts now shows.
- [x] When to vote, from a UX review:
  - past dates are grey without being faded, for contrast (about 6.3:1 in light mode instead of 3.6:1);
  - the calendar icons have a 24×24px tap area, with no layout shift;
  - "Where to vote" links to "county elections offices", since the page is the statewide list;
  - VoteTexas.gov moved from the line under the heading to the card's links, next to "Am I registered?".
- [x] AGENTS.md: a roadmap group is headed with the pull request's assumed number, one more than the last one on `develop`, rather than the branch; the When to vote group above now links #12.
- [x] Two features added to the roadmap for later: [your election precinct](#features), with what was found about the Texas Legislative Council's VTD map, and a [map of your districts](#features).

### Faster lookups, shared page chrome, and the top of the ballot ([#14](https://github.com/Fahd-Siddiqui/VoteBot/pull/14), Sep 30)

The six improvements from the September review, UI feedback on the top of the ballot, and the order of the tabs in Details.
- [x] The card sources are asked at once (`enrich.run`, `asyncio.gather`): on a lookup that isn't cached yet, the Texas SOS candidate list, the FEC and FiftyPlusOne no longer wait for each other. A source that can't answer is still a warning, not a failed lookup.
- [x] Heavy work runs off the event loop, so other requests (suggestions typed in another tab, Settings) aren't held up:
  - `HttpCache` reads and writes rows in worker threads, with its lock guarding the connection and the in-memory copies;
  - the TrackAIPAC and TEC snapshots are read under a lock, so threads parse each version once and never read one that Reset is still copying;
  - the SBOE point-in-polygon test, and the card builders with no I/O (Ballotpedia, TrackAIPAC, the TEC);
  - the Settings routes that only touch files are plain functions, which FastAPI runs in its thread pool.

  Parsing a big JSON value still holds the GIL; the gain is in the SQLite and file I/O and the Python work around it. A cached lookup takes as long as before: about 0.45 s for the Capitol with an FEC key, on this branch and on `develop`.
- [x] "Paused until …" in Settings is built in one place, from each source's wording on `SourceInfo` (`Pause`). The five sources' `paused_until()` methods, which only Settings used, are gone.
- [x] `chrome.js` draws the left pane on every page from one list of pages, so the five copies in the HTML are gone, and the favicon is one `favicon.svg`. On a phone, the empty pane already has the top bar's height, so nothing moves when it's drawn. It's drawn in the browser rather than templated on the server, since the pages are static files and need their scripts anyway. The ballot's footer and welcome steps now mention the polls.
- [x] On a ballot from Ballotpedia alone (Texas SOS off), a state race's seat for the TEC match comes from Ballotpedia's district type and office name (`bp_seat`), so a match can be exact, and a namesake elsewhere in Texas is ruled out. On the Capitol's ballot, Greg Abbott, Catherine Mauzy, Darlene Byrne and Scott Brister went from likely to exact.
- [x] At startup, the cache deletes Photon's rows and the addresses the Census or Nominatim didn't find, once they've been expired for 30 days (`VOTEBOT_TTL_PRUNE_AFTER`), and expired flags, then runs `VACUUM` if anything went. Addresses that were found stay, as the copy to use when the Census is down.
- [x] When to vote: **Am I registered?**, **Where to vote** and **Add all to calendar** are a row of buttons under the dates, where "Where to vote" used to be plain text before a link, on one cramped line. VoteTexas.gov moved to the card's source line. The two cards at the top are as tall as each other, with their source lines at the foot.
- [x] "State Senate District 14 (yours) isn't up for election" moved from a box above the races into Your districts: the district is grey, with a line under the row. The API sends it as `districts.not_up`.
- [x] The tabs in Details, and the badges on a candidate's row, come in one order: the money (the FEC, or the TEC for state offices), Texas SOS, Polls, Ballotpedia, TrackAIPAC (`CARD_ORDER` in `enrich.py`), and Details opens on the first. The order is set on the server, so the API's card order stays the order shown.
- [x] A [Reviews](#reviews) section in this roadmap: backend, frontend code, UX and security.
- [x] A [Spot checks](#spot-checks) section: the ballot against VoteTexas.gov and Ballotpedia, and the TrackAIPAC, campaign finance and poll figures against their sites, once by hand and once by an LLM.
- [x] Found along the way: county courts on Ballotpedia-only ballots, fixed in [#16](#roadmap-bugs-13-16-sep-30).

### Map of your districts ([#15](https://github.com/Fahd-Siddiqui/VoteBot/pull/15), Sep 30)

What was Feature 12: a street map with the voter's districts on it, always under the two cards at the top of the ballot.
- [x] The map (`district-map.js`, drawn by Leaflet): OpenStreetMap's street map, the outline of each district (U.S. House, State Senate, State House, SBOE) and a pin at the address. Drag, **+**/**−**, the arrow keys, and the scroll wheel once the map has been clicked, so scrolling the page never zooms it by accident. On a touch screen, two fingers move and zoom it and one scrolls the page. A scale in miles, and OpenStreetMap's attribution.
- [x] It opens centred on the address, zoomed so the smallest district fits around it (zooms 10 to 14). Right above the map, a button per district with a sample of its line is the legend: picking one, or clicking its line on the map, highlights it and zooms to it, and picking it again, or the pin button under + and −, goes back to the address. Hovering over a line names the district. Focus stays on the button, and on a phone the map scrolls into view. A precinct update leaves the map where the voter left it. The Your districts card stays as it was.
- [x] The map's heading folds it away, with the same chevron as a race's heading. It's shown by default, and the choice is remembered in the browser with the other view choices. While it's folded, nothing is fetched for it.
- [x] The outlines come from `GET /api/district-outlines` (`outlines.py`), which the page asks once the ballot is on screen, so a ballot lookup waits for nothing new. A second request for the same districts makes 0 external calls.
  - U.S. House, State Senate and State House from the Census's TIGERweb (`sources/tigerweb.py`): the service's layer list, then one request per district by GEOID, simplified on the server to about 50 m. Its layers are found by name, as the geocoder's are, so they follow the same maps. A new source in Settings, "District map (US Census TIGERweb)", with an on/off switch, Refresh and Clear; cached for 30 days (`VOTEBOT_TTL_OUTLINES`) and paused for an hour after a 403 or 429.
  - SBOE from the PLANE2106 map already kept for the lookup, simplified with Douglas–Peucker (`sboe.simplify`) once per district: the largest goes from 42,704 points to 4,639.
  - An outline that's off or can't be had is a note under the map, never a failed request.
- [x] The street map's tiles come from OpenStreetMap through the server (`GET /api/tiles/{z}/{x}/{y}.png`, `sources/osm_tiles.py`), following its tile usage policy:
  - a User-Agent that names VoteBot and links to it (the default `VOTEBOT_USER_AGENT` now includes the project's URL);
  - each tile kept 7 days (`VOTEBOT_TTL_TILES`), and a day in the browser;
  - only the tiles being looked at: its Settings row, "Street map (OpenStreetMap)", has an on/off switch and Clear but no Refresh (`SourceInfo.refreshable`), since a bulk re-download isn't allowed;
  - paused for an hour after a 403, 418 or 429;
  - only zooms 5 to 18 over Texas and 2° around it, so VoteBot can't be used as a tile proxy for anywhere else, and a view near the state line still has streets.

  `HttpCache` keeps an image as base64 text (`get_bytes`, `RequestSpec.as_bytes`), and old tiles are deleted at startup like address suggestions.
- [x] Leaflet 1.9.4 is copied into `static/vendor/leaflet/` (its ES module build, CSS and licence, checked against npm's hash), with a `package-data` pattern, and imported only once there's a ballot. `.map-canvas` is its own stacking context, so Leaflet's controls stay under the sticky strip. In dark mode, the tiles are inverted.
- [x] Decisions:
  - always shown rather than behind a Map button, which was easy to miss (the first version of this branch had one, over a plain SVG drawing);
  - the district buttons right above the map rather than on the Your districts card, which was too far from it, and left the card as it was;
  - OpenStreetMap's tiles through the server, rather than straight from the browser: the server keeps them, as the policy asks, repeat views make no calls, and OpenStreetMap never sees the voter's browser. The street map is on by default, with its switch in Settings, and Privacy says what it sends;
  - Leaflet, copied in, rather than a map drawn by hand: dragging, pinch zoom and keyboard use it has already got right;
  - TIGERweb rather than the Texas Legislative Council's plan files: one small cached request per district, from the same maps as the geocoder, instead of three large downloads;
  - a panel under both cards, so the two cards stay as tall as each other;
  - it opens centred on the address, close enough to read the streets, rather than fitted to all four districts, which put the address off to one side at a regional scale;
  - outlines simplified to about 50 m, both TIGERweb's and the SBOE's, so shared boundaries still meet when zoomed to a State House district;
  - four colours with no party blue or red (violet, orange, teal, plum), checked for colour blindness across every pair and for 3:1 contrast against the panel colour in light and dark mode, each with its own dash (solid, dashed, dotted, dash-dot) and a halo in the panel colour, so the contrast holds over the streets.
- [x] README, DEVELOPMENT, FAQ ("What does the map of my districts show?", and TIGERweb and OpenStreetMap's tile server in "Why is a source paused?"), About, Privacy, AGENTS.md (a rule for OpenStreetMap's tiles, and where a copied-in library goes) and the welcome steps updated. `scripts/record_fixtures.py --only tigerweb` records the new fixtures.
- [x] Found along the way: no SBOE district with Texas SOS off, fixed in [#16](#roadmap-bugs-13-16-sep-30).

### Roadmap bugs 1–3 ([#16](https://github.com/Fahd-Siddiqui/VoteBot/pull/16), Sep 30)

The three minor bugs found while building #14 and #15.
- [x] An address-suggestion call cancelled after its headers arrived, but before its body did, no longer comes back as `null`. `request()` in `api.js` now passes on the AbortError from `response.json()`, and still turns other errors into `null`. So the suggestion box no longer closes, and flickers, while the voter's newer request is on its way.
- [x] On a ballot from Ballotpedia alone (Texas SOS off), county courts at law and probate courts no longer get a Texas Ethics Commission card matched by name. Ballotpedia lists them as judicial districts, but their judges file with the county, so a namesake elsewhere in Texas could show up as a "likely" match. `tec.cards` now leaves them out (`_BP_COUNTY_COURT`), as it does the Texas SOS's county courts. Criminal district courts are state courts, so they keep their TEC cards.
- [x] The State Board of Education district is known whichever ballot source is on. The lookup (`_sboe`) runs beside the Texas SOS and Ballotpedia work instead of inside the SOS path, so with Texas SOS off, or when the SOS doesn't list the county, Your districts shows the SBOE district and the map draws its outline. `SosData.sboe` is gone. When the map can't be loaded, the warning now says the SBOE district isn't known, which is true on both paths.
- [x] Decisions:
  - Bug 2 is fixed in `tec.cards`, as suggested. Moving Ballotpedia's county courts to the `county` group would also have moved them on the ballot.
  - "SBOE seat not up" (`not_up`) still comes only from the Texas SOS's races, as for the State Senate.
  - The branch is `fix/three-roadmap-bugs`, since `fix/roadmap-bugs` is #10's.
