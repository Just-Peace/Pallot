# Developing VoteBot

How VoteBot works inside, and how to test and change it. To run it, see the [README's quick start](README.md#quick-start). The rules for a change (branches, commits, which docs to update) are in [AGENTS.md](AGENTS.md), and known bugs and planned work in [ROADMAP.md](ROADMAP.md).

VoteBot is one Python process (FastAPI) serving a plain HTML/JS page from `votebot/static/`. There's no frontend build step and no database server: everything it keeps is files in `data/`.

## Commands

`uv sync` installs VoteBot with the dev tools (pytest, pytest-xdist, respx), pinned by `uv.lock`.

```bash
uv run votebot --reload                    # restart on code changes
uv run pytest                              # offline: recorded responses in tests/fixtures, plus trackaipac_cache's and tec_cache's own tests
uv run pytest -n 0 --pdb                   # the same in one process, to use the debugger or see print()
uv run pytest -m live                      # smoke tests against the real services (the FEC one needs an FEC key)
uv run python scripts/record_fixtures.py   # re-record tests/fixtures from the live APIs (--only ballots|suggest|fec|polls|key_dates|tigerweb|election_precincts|tec|trackaipac)
```

Keep the default `127.0.0.1` binding (there is a `--host` option, but don't change it), because the Settings actions have no login. The Docker image is the one exception: it binds `0.0.0.0` inside the container, and `compose.yaml` decides where that's published.

A middleware in `api.py` guards the Settings actions from the voter's own browser:
- It answers only to `localhost`, IP addresses and the names in `VOTEBOT_ALLOWED_HOSTS`. Any other `Host` could be DNS rebinding, which makes an attacker's page the same origin as VoteBot.
- It refuses a POST or PUT that another page started: `Sec-Fetch-Site` other than `same-origin`, or an `Origin` that isn't the `Host`. That includes another port on localhost.
- The tests' `make_app` allows `testserver`, TestClient's host name.

The live tests and `record_fixtures.py` call the real services. With `DEMO_KEY`, the FEC's rate limit is shared by everything on your IP address, VoteBot itself included.

How the tests run:
- **In parallel.** `pytest-xdist` runs one worker per CPU (`-n auto --dist loadgroup` in `pyproject.toml`). Each test has its own data folder under `tmp_path`, so no test depends on another.
- **The live tests, one at a time.** They share one worker (`xdist_group("live")`), so the real services never get more than one call at once.
- **Without throttling waits.** The tests' `make_app` passes `min_interval={}`, so the calls to a source aren't spaced out. `test_calls_to_one_source_are_spaced_out` in `test_http_cache.py` checks the throttling itself. `uv run votebot` and the live tests use the real intervals, `MIN_INTERVAL` in `api.py`.
- **Fixtures read once.** `conftest.py` keeps each recorded response in memory (`fixture_bytes`) for the rest of the run.
- **Made-up maps.** `conftest.py` makes the SBOE map (KML) and the precinct map (a shapefile in EPSG:3081, written with `struct`, with the real `.prj`). Every exact fixture address's two points fall in one precinct; the rest are a precinct in two pieces, one with a hole another fills, two that overlap, two that meet, and another county's over the Capitol. `record_fixtures.py --only election_precincts` records only the portal's index, never the 45 MB map.

## Layout

```
votebot/
  api.py            routes + static files          ballot.py   assembles the ballot
  http_cache.py     persistent request cache       enrich.py   adds each source's cards to candidates
  offices.py        SOS office names -> districts  matching.py cross-source name matching
  admin.py          Settings actions               settings.py source on/off switches (data/settings.json)
  ics.py            calendar files of key dates    outlines.py the district map's outlines
  sources/          census, nominatim, photon, sboe, election_precincts, tigerweb, osm_tiles, sos, key_dates, ballotpedia,
                    trackaipac, fec, tec, polls
                    (snapshot.py: the bundled-snapshot handling TrackAIPAC and TEC share;
                    compare.py: the Compare dialog's sections, shared by the FEC and TEC)
  static/           index.html (the ballot), settings.html, faq.html, about.html, privacy.html, favicon.svg,
                    vendor/leaflet/ (Leaflet 1.9.4, copied in), css/app.css,
                    js/ (ballot.js, key-dates.js, district-map.js, suggest.js, compare.js, settings.js,
                    chrome.js, page.js, topbar.js, toast.js, source-cards.js, print.js, …)
trackaipac_cache/   TrackAIPAC library (copied in)
tec_cache/          Texas Ethics Commission snapshot and its builder
scripts/            record_fixtures.py, capture_trackaipac_fixtures.py
tests/              VoteBot tests + tests/trackaipac/ + tests/tec/
Dockerfile          the container image; compose.yaml runs it
```

## Caching

Every outbound call goes through `votebot/http_cache.py`, a SQLite cache in `data/cache.sqlite3`. Each `/api/ballot` response reports `meta.external_calls`, and Settings shows the last lookup's, source by source.

- Concurrent identical requests share one fetch.
- Only answers that succeed are cached.
- `get_json` stores the parsed JSON. `get_text` stores a web page's body as a string (`RequestSpec.as_text`), so Refresh fetches it as text again. `get_bytes` stores an image (the street map's tiles) as base64 text (`RequestSpec.as_bytes`).
- `download` streams a file too big for the database (the precinct map) into a path: the same pause, throttling, call count and refusals as `get_json`, refused past `max_bytes` or when a redirect leaves `hosts`, but nothing is stored, so whoever keeps the file decides when it's fetched again. `peek` reads a stored copy without asking anyone, for Settings' plain-function routes.
- The lifetimes are `Ttls` in `votebot/config.py`, each overridable with `VOTEBOT_TTL_<NAME>`.
- Reading and writing a row (`_load`, `_store`) runs in a worker thread (`asyncio.to_thread`), and `self._lock` guards the SQLite connection and the in-memory copies. SQLite and file I/O release the GIL, so other requests (address suggestions typed during a first lookup, say) go on meanwhile. `json.loads` of a big value (the 2.6 MB candidate list) still holds the GIL while it parses, in C.
- Expired rows stay, as the copy to serve when a source is down. At startup, `prune()` deletes what's no use even then, once it's been expired for `Ttls.prune_after` (30 days): Photon's rows (half-typed addresses) and the street map's tiles, census and Nominatim rows stored with their shorter "not found" lifetime, and expired flags. It runs `VACUUM` when it deleted anything, so the typed text doesn't linger in free pages.

Other work that would hold up the server runs in threads too:
- `enrich.run` asks every card source at once (`asyncio.gather`); the ones with no I/O (Ballotpedia, TrackAIPAC, the TEC) build their cards in threads. The cards are then attached in `CARD_ORDER`, which is the order of the tabs in Details and of the badges on a candidate's row: the money (FEC or TEC), Texas SOS, polls, Ballotpedia, TrackAIPAC.
- The SBOE point-in-polygon test (`SboeMap.district_at`), and simplifying an SBOE district for the map (`SboeMap.outline`).
- The election precinct's lookup and outline, and unpacking and checking a new precinct map (`ElectionPrecincts`).
- `BundledSnapshot` (TrackAIPAC, TEC) is read from threads, so a lock makes each version of `current.json` parse once, and keeps a Reset's copy from being read half-written.
- The Settings routes that only touch files (`GET /api/sources`, the on/off switch, Clear, Clear all) are plain `def`, which FastAPI runs in its thread pool.

## Sources

Notes on how each source is called, beyond the README's table:
- **Photon:** Nominatim's policy forbids search-as-you-type, hence Photon for suggestions. Only results on a street matching what was typed are kept; without the house in OpenStreetMap, the typed number goes on the street.
- **SBOE districts:** point-in-polygon in pure Python over the PLANE2106 map, downloaded once into `data/`. It runs for every ballot, beside the Texas SOS and Ballotpedia work, so a ballot from Ballotpedia alone still has the voter's SBOE district.
- **Election precincts** (`sources/election_precincts.py`): the Texas Legislative Council's maps of every county's voting precincts, the `precincts` dataset on its CKAN portal (data.capitol.texas.gov).
  - **Which map.** The portal's index (`package_show?id=precincts`, cached a week, `Ttls.election_precincts`) lists a shapefile zip after each statewide election. The dataset's name is the only thing written in the code: the newest map is a zip of format SHP on the portal itself, ranked by the year in its description, then a general's after a primary's, then `created`, so an older election's map uploaded later doesn't win. A primary's map serves its general: the TLC publishes a general's only after that election, and counties can only redraw precincts in March or April of odd-numbered years (Election Code §42.031), so 99.5% of precincts carried over in 2022 and 99.9% in 2024. The map's label and whether it's a primary's come from the description, its size from the index.
  - **Downloading.** One streaming GET through `HttpCache.download` (the server ignores `Range`), into `data/election_precincts/`, and again only when the index lists a newer map. One download runs at a time, whoever starts it: the lookup that starts the first one waits up to 20 s for it beside the other sources (`first_wait`), then goes on with a note while it carries on, and a lookup that finds it already running goes on with the note at once; a newer map downloads in the background while lookups use the one kept. Before anything is replaced, the download must be the size the index gives, hold one `.shp`/`.shx`/`.dbf`/`.prj`, with a projection `read_prj` can read and polygon records with `CNTY` and `PREC`. The files are unpacked under a new name, then `map.json` is rewritten to point at them, which is the moment the new map takes over, and the old files go. Reads take a lock and open the `.shp` each time, so no file is open during a swap or a Clear. A map that fails, for any reason (an unexpected error while unpacking is a `ValueError` like the rest), isn't started again by a lookup until the index lists a changed one, or for a week (15 minutes while no map is kept): a flag in the cache (`failed:…`), which Clear removes. A 403 or 429 pauses the portal for an hour instead. Refresh always tries. At shutdown, `aclose()` stops a download still streaming and removes its partial file; one already unpacking finishes in its thread, which can't be stopped, and that thread removes the zip. `stored()` doesn't wait for the lock once the map is known, so the event loop never waits on a thread reading the map, and an outline worked out from a map that a newer one or a Clear replaced meanwhile isn't kept.
  - **Reading it.** A shapefile, read with `struct`: the `.dbf` gives `CNTY` (the county's FIPS code, as `Place.county_fips`; not the alphabetical number the SOS uses) and `PREC` (the county's name for the precinct: `0300`, or `101A`, `03-3`, `01CR`), the `.shx` each record's offset, and each record's bounding box is read from the `.shp` by seek (a 1 MB buffer, since the records are in order). Only that index stays in memory, about 3 MB; it takes about 0.06 s to build, 0.4 s on WSL's `/mnt/c`. The projection is a Lambert conformal conic (EPSG:3081, on GRS 1980) whose parameters come from the `.prj`; `Lambert.project`/`unproject` are EPSG method 9802's formulas (checked against its worked example), and any other projection is refused.
  - **The lookup.** The county's records, those whose box holds the point, then even-odd over all of a record's rings, for two points: the address's, and its census block's internal point (`INTPTLAT`/`INTPTLON` from the geocoder's `2020 Census Blocks`, in `Place.block_point`). Both must be in the same single precinct. When they're in two, the ballot names both and picks neither; in none, or in two at once, it says so; there's no nearest-precinct fallback. The block comes from the geocoder's own point, so this only catches a precinct line that cuts through the block, or a sliver where the TLC's lines and TIGER's differ. It can't catch the geocoder putting an address on the wrong side of a street that's a precinct line, so the FAQ says the certificate wins. Without a block point, the address's point alone decides. An approximate address (OpenStreetMap's street) gets no precinct, since both points would come from the same rough spot. `display_name` drops an all-digit name's leading zeros (`0300` is 300).
- **District outlines** (`GET /api/district-outlines?cd=&sd=&hd=&sboe=&election_precinct=&county=`, `outlines.py`), asked by the page once the ballot is on screen, so a ballot lookup never waits on them. A missing outline is a note in the answer, never a failed request. The answer's `street_map` says whether the street map is on.
  - U.S. House, State Senate and State House come from the Census's TIGERweb (`sources/tigerweb.py`), one cached request per district plus the service's layer list. Its "Current" service has the geocoder's maps under the same names ("120th Congressional Districts", "2026 State Legislative Districts - Upper"), so a layer is found by the end of its name, newest vintage first, which skips each one's "… Labels" twin. A district is asked by GEOID: `48` plus the number in 2 digits for Congress, 3 for the Legislature. The query asks for Esri JSON in lon/lat (`outSR=4326`), simplified on the server with `maxAllowableOffset` of 0.0005° (about 50 m); TX-10 is about 2,200 points. The rings come as one list, outer rings and holes alike, which the map fills even-odd.
  - SBOE comes from the PLANE2106 map already kept for the lookup, simplified to the same 0.0005° with Douglas–Peucker (`sboe.simplify`), once per district. The full map has 264,000 points; simplified, its largest district has about 4,600.
  - The election precinct comes from the precinct map the ballot lookup downloaded, never downloaded here. It's asked by the map's code for it (`0300`) and the county's FIPS code, since two codes can share a display name, and comes back with `Outline.number` set to the display name (`"300"`). It's simplified to 0.00005° (about 5 m), since a precinct is a few streets across: a city precinct goes from 58–165 points to 20–40. The parameter only has a length limit, no pattern: one that a real code failed would make FastAPI refuse the whole request, the other outlines with it; an unknown code is the usual note.
- **Street map** (`GET /api/tiles/{z}/{x}/{y}.png`, `sources/osm_tiles.py`): OpenStreetMap's standard tiles, which the server fetches for the browser and keeps. Its [tile usage policy](https://operations.osmfoundation.org/policies/tiles/) sets the rules:
  - a User-Agent that names the app and a way to reach it (`Config.user_agent` includes the project's URL);
  - each tile kept at least 7 days (`Ttls.tiles`); the browser also keeps a tile for a day (`Cache-Control`);
  - only the tiles someone is looking at: no prefetching, and no bulk re-download, so its Settings row has Clear but no Refresh (`SourceInfo.refreshable`), and `POST …/refresh` answers 400;
  - the attribution on the map, bottom right.

  The server only fetches zooms 5 to 18 over Texas and 2° around it (`osm_tiles.wanted`), so VoteBot can't be used as a tile proxy for anywhere else, while a view near the state line still has streets; the page's map keeps to the same box (`maxBounds`). A 403, 418 or 429 pauses it for an hour.
- **Key dates:** the Texas SOS's "Important Election Dates" page (`sources/key_dates.py`), fetched as text and parsed with the standard library's `HTMLParser`. Each election is a `<table class="norm-5px">`, titled by its `summary` attribute or its heading row ("Tuesday, November 3, 2026 - Uniform Election Date"); the ballot takes the table whose date is its election day. Its quirks:
  - earlier years' tables are still in the page, inside HTML comments, which the parser skips;
  - labels vary between tables ("First Day of Early Voting" or "… by Personal Appearance"), so a row is known by how its label starts, and look-alikes ("Last Day for Candidates … to Register to Vote", "First day to apply for a ballot by mail") are left out;
  - a date cell can add a footnote, a note or a time after the date, so the first full date in it is taken.

  `GET /api/key-dates.ics?date=…[&event=…]` builds the calendar files (`ics.py`). Without `event`, the mail-ballot deadline is left out, since most voters can't vote by mail.
- **Ballotpedia:** an unofficial endpoint that needs Ballotpedia's own origin header.
- **TEC seats:** a Texas SOS race's seat comes from its office (`tec_seat`); on a ballot from Ballotpedia alone, from Ballotpedia's district type and office name (`bp_seat`: "State Legislative (Lower)" and "District 49" is `STATEREP:49`, "Texas Third District Court of Appeals Chief Justice" is `CHIEFJUSTICE_COA:3`). Without a seat, a match by name is only ever "likely". Ballotpedia lists county courts at law and probate courts as judicial districts, but their judges file with the county, so those races get no TEC card (`_BP_COUNTY_COURT`), as the Texas SOS's county courts don't.
- **FiftyPlusOne:** the site's own JSON API: nationwide lists, 500 polls to a page, filtered to Texas on the server. It answers 403 unless the request looks like a browser's.
- **State-specific text** (the official elections site, the registration check, who can vote by mail, the polls' hours, the print sheet's voting rules) comes from `STATES` in `votebot/static/js/labels.js`, keyed by the address's state, so adding a state doesn't mean rewriting pages.

## The pages

Every page has an empty `<aside class="sidebar">`, and `chrome.js` draws the left pane into it: the brand, "Your ballot", the address card, and the other pages from its `PAGES` list, marking the current one. The ballot page puts its own parts in the aside: the form and status line (`data-slot="address"`) go under the address card, and the section list (`#jump`) above the other pages. `page.js` and `ballot.js` import `chrome.js` first, so the pane exists before their own code looks for it. The favicon is `favicon.svg`.

At 960px and less (a phone), the left pane becomes a top bar. `chrome.js` then calls `initTopBar()` in `topbar.js`, which adds its two buttons (the address and Menu). The empty aside is already the closed bar's height, so the page doesn't move when it's drawn. On the ballot, `placeForWidth()` in `ballot.js` moves the section list (`#jump`) into the sticky progress strip, and the View, Clear picks and Print buttons (`#ballot-tools`) under the heading. A `ResizeObserver` keeps `scroll-padding-top` at the strip's height, so links, Next and `j`/`k` land below it. `markCurrentSection()` marks the section on screen in the list (`aria-current`) as the page scrolls, and on a phone scrolls the chip row to it. The View menu's two options are saved with the other view choices in `localStorage` under `votebot.ui.v1`.

Under the strip, `.ballot-top` holds When to vote (`key-dates.js`) and Your districts (`renderDistricts()` in `ballot.js`), side by side when there's room and stacked on a phone (flex-wrap, 340px each at least). The map of your districts (`district-map.js`) is always under them, the full width, so the cards stay as tall as each other. Right above it, a row of buttons, one per district, is its legend and picks a district; picking only flips `aria-pressed`, so focus stays on the button. Leaflet draws it:
- `vendor/leaflet/` holds Leaflet 1.9.4's ES module build, its CSS and its licence, copied from the npm package (checked against the registry's hash), with only the source-map comment removed. `district-map.js` imports it with `import()` once there's a ballot, so the other pages never load it.
- The card's heading is a button that folds the map away, with a race's chevron (`.map-toggle`, `.district-map.collapsed`), remembered as `showMap` in `votebot.ui.v1` (shown when unset). While it's folded, nothing is fetched or drawn: `syncMap` only notes the new districts, and showing the map loads and draws them, at the map's real size.
- The map is made once and kept: a precinct update leaves it where the voter left it; new districts load new outlines and go back to the address. The outlines are fetched once per set of districts and kept for the page's life.
- It opens centred on the pin, zoomed so the smallest district's outline fits around it, within zooms 10 to 14 (`fitView`, `HOME_ZOOM`), so the streets are always readable. With an election precinct, that's the precinct, so it usually opens at zoom 14. A picked district fills the map instead; picking it again, or the pin button under + and −, goes back.
- `.map-canvas` is its own stacking context (`z-index: 0`), so Leaflet's panes and controls (z-index up to 1000) stay under the sticky strip.
- It never traps the page's scrolling: the scroll wheel zooms only while the map has focus (after a click), and on a touch screen (`pointer: coarse`) dragging is off, so one finger scrolls the page and two move and zoom the map.
- Each district has its colour (`--map-cd`, `--map-sd`, `--map-hd`, `--map-sboe`, `--map-election-precinct`, checked for colour blindness and for 3:1 contrast against `--panel`) and its own dash (solid, dashed, dotted, dash-dot, dash-dot-dot), so it's never told apart by colour alone. Under each line, a wider halo in `--panel`'s colour keeps that contrast over the streets, and is what the pointer hits: hovering shows the district's name, and a click picks it. In dark mode, the tiles are inverted with a CSS filter.

The strip comes first so that Next and the section chips stay on a phone's first screen. The precinct form lives in the districts card, open by itself while a race waits on a missing number. It always sends both numbers, `null` for an empty field: `_precincts()` in `ballot.py` reads the request with `exclude_unset`, so a `null` clears Ballotpedia's number while a missing key keeps it. A JP number also sets the constable, and the other way round (`_jp_is_constable`), since each justice precinct elects one of each.

Clearing what the voter keeps in the browser (Clear picks on the ballot, and the two Clear buttons in Settings) happens at once, then `toast.js` offers Undo for 10 seconds. The clear functions in `picks.js` return what they removed, for Undo to put back. Clearing what the server saved can't be undone, so those buttons still ask first.

## trackaipac_cache

`trackaipac_cache/` is a copy of the TrackAIPAC library from `git@github.com:Fahd-Siddiqui/TrackAipacCache.git` (develop, commit `423443a`), with its tests in `tests/trackaipac/`. VoteBot copies its bundled snapshot into `data/trackaipac/` on first run, so it works without calling trackaipac.com.

- **Refresh** (TrackAIPAC's row in Settings) runs the package's `refresh()`, which validates the pages and writes only if the site changed.
- **Reset** goes back to the copy in the repo.
- To update the bundled copy itself, run `uv run trackaipac-cache refresh` and see `trackaipac_cache/README.md`.

## tec_cache

`tec_cache/` builds the Texas Ethics Commission snapshot from TEC's nightly export, `TEC_CF_CSV.zip` (about 1 GB), and bundles it in the repo. VoteBot copies it into `data/tec/` on first run, so ballot lookups never contact TEC.
- **Refresh** (the Texas Ethics Commission row in Settings) rebuilds it in a separate process (`python -m tec_cache`), which reads a couple of GB of CSV.
  - It first makes one small request to see whether TEC's zip has changed; if not, that's all.
  - If it has, it downloads the zip in one request, reading just the files it needs as they arrive.
- **Reset** goes back to the bundled copy.
- TEC's download server blocks bursts of requests, so never fetch the zip in many small ranges.
- To update the bundled copy itself, run `uv run tec-cache refresh` (or `--zip PATH`) and see `tec_cache/README.md`.

## Docker image

- The `Dockerfile` installs VoteBot as a regular (not editable) package into `/app/.venv`, from `uv.lock` with `--locked` and without the dev tools. After changing dependencies in `pyproject.toml`, run `uv lock`, or the build fails.
- Because the install isn't editable, the static files and the bundled snapshots reach the image only as package data (`[tool.setuptools.package-data]` in `pyproject.toml`). A new kind of file, such as an image under `votebot/static/`, needs a pattern there (Leaflet's files have `static/vendor/*/*`). Otherwise it works with `uv run` but is missing from the container.
- `.dockerignore` keeps `.env`, `data/`, the tests and scripts out of the build. The image has VoteBot and its locked dependencies, not the dev tools or tests.
- Everything VoteBot writes goes under `VOTEBOT_DATA_DIR` (`/data` in the container); a TEC refresh stages its work in `/tmp`.

## Adding a source

Each source contributes `SourceCard`s: badges, facts, quotes, money breakdowns, links and match confidence. A source can also add a card to a race, such as the money comparison. The page renders them all generically, as badges on the candidate row, a tab in Details, and a block at the top of the race. So a new source only needs:

1. A module in `votebot/sources/` that fetches through `HttpCache` and builds cards.
2. A field on `Services` in `ballot.py`, created in `api.py`'s startup.
3. A job in `enrich.py`, and its place in `CARD_ORDER` (where its tab goes in Details). A `cards()` without I/O runs through `asyncio.to_thread`.
4. An entry in `admin.py` so it appears in Settings, and one in `DEFAULT_SOURCES` in `settings.py` if it can be turned off.
5. A row in the tables on `static/privacy.html` (what the source is sent and kept) and `static/about.html`, and an answer in `static/faq.html` if it raises a question.
