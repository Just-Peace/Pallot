# Pallot

A voter's personal ballot, currently for Texas addresses. Enter a home address and Pallot shows every race on that voter's ballot, with candidates in ballot order. Each candidate carries information from several sources. You can pick candidates, write notes, and print your picks to take to the polls.

You run it yourself, in Docker or with uv, and use it in your browser.

Pallot is made by [Just-Peace](https://github.com/Just-Peace) for American voters who'd rather see the whole ballot for themselves. We don't back any candidate or party. Your vote is yours.

## Quick start

Get the code, and optionally a settings file:

```bash
git clone https://github.com/Just-Peace/Pallot.git
cd Pallot
cp .env.example .env    # optional: this is where the FEC key goes (see below)
```

Then run it one of two ways.

### With Docker

Needs [Docker](https://docs.docker.com/get-docker/) with Compose 2.24 or later.

```bash
mkdir -p data                   # where Pallot keeps its cache and settings
docker compose up -d --build    # build the image and start Pallot in the background
```

Open http://localhost:8000, or `http://<this machine's address>:8000` from another device. It listens on every network interface, and Pallot has no login, so run it only on a network you trust. To keep it to this machine, see [Docker](#docker).

```bash
docker compose logs -f                     # follow the server log
docker compose down                        # stop it (data/ stays)
git pull && docker compose up -d --build   # update to the latest version
```

### With uv (local)

Needs [uv](https://docs.astral.sh/uv/): `curl -LsSf https://astral.sh/uv/install.sh | sh`.

```bash
uv sync           # installs Pallot and its dependencies (and Python, if needed) into .venv, pinned by uv.lock
uv run pallot    # serves http://127.0.0.1:8000 until Ctrl+C (--port picks another port)
```

Open http://127.0.0.1:8000. It only listens on this machine, because Pallot has no login; to use Pallot from other devices, run it with Docker on a network you trust. To update: `git pull && uv sync`, then start it again.

### The FEC key (optional)

Pallot needs no keys to run. To break down congressional candidates' money (where it came from, donation sizes, largest donors, outside spending), it needs a free FEC key:
1. Get one from the [OpenFEC developers page](https://api.open.fec.gov/developers/); api.data.gov emails it to you.
2. Put it in `.env` as `PALLOT_FEC_API_KEY=...`. The FEC lets each key make 60 calls a minute, and Pallot paces itself to stay under that. For more, add up to four more keys as `PALLOT_FEC_API_KEY2` to `PALLOT_FEC_API_KEY5`: Pallot uses them in turn.
3. Restart Pallot: `docker compose up -d`, or Ctrl+C and `uv run pallot` again.

Without a key, Pallot uses the shared `DEMO_KEY`, which only allows race totals and runs out after a few requests. Pallot says so in its log at startup. Its log also names a key the FEC refuses, and `pallot-cache check` lists the keys in use and any resting. Voters never see your keys or their names. The other settings are under [Configuration](#configuration).

## Using it

The FAQ (linked from every page) explains the figures and the features in detail. In short:

- **Look up your ballot** by home address (with suggestions as you type), or under **My voter card** by county and precinct number, so no address is sent anywhere. Pick the election, and a party for a primary. The first lookup can take several seconds, and the very first after installing also downloads the precinct map (about 45 MB); looking the same address up again is instant.
- **Your ballot** lists every race in ballot order, with the candidates' party, Incumbent and Open seat, the declared write-ins, and a write-in line. Ballotpedia, when you turn it on, adds city, school board and special district races. Races that depend on a district or precinct Pallot doesn't know are left out, with a note saying which number to enter.
- **When to vote** has the election's key dates, each downloadable to your calendar, and links to check your registration and find where to vote.
- **Your districts** shows your districts and precincts, as on your voter registration certificate. You can correct any number from your certificate. A **map** shows their outlines over OpenStreetMap.
- **Each candidate** has their endorsements, a **Funding** summary (small donors, Texas donors, outside spending), polls where there are any, a note, a web search, and **Profile**: their filing, Wikidata and Ballotpedia profiles, issue searches, and a tab per source. **Compare funding** puts a race's candidates side by side.
- **View** chooses how much detail to show (Minimal, Simple, Detailed) and what matters to you (Funding, Endorsements, Polls, Where they stand).
- **Help me pick**: **Trust** picks the candidates of the endorsers you trust, and **Avoid** marks the ones you won't vote for, from watchlists or your own list. **More conditions** picks across the ballot, or in one race, by party, endorsements, money or polls. It never guesses in a race with more matches than seats.
- **Avoid** on a candidate adds them to your own list, which you can also fill by name or pattern in Settings. Trust never picks them.
- **Print my picks** as a full page or a wallet card. Your address isn't printed.
- On a phone, the left pane becomes a top bar, and the ballot's buttons are under **More**.

Your picks, notes, write-ins, Help me pick choices, the people you avoid and your settings are kept in your browser's `localStorage`, never on the server.

## Where the data comes from

| Source | Used for | Notes |
|---|---|---|
| US Census geocoder | address → county, U.S. House, State Senate and State House districts; for a voter card, the same at points inside your precinct | already on the 2026 maps (120th Congress, 2026 legislative districts). A voter card sends only those points, never an address |
| OpenStreetMap Nominatim | fallback when the Census can't match an address | results flagged as approximate unless they hit a building |
| Google Geocoding API | last fallback, when neither the Census nor Nominatim can match an address (new streets, mostly) | needs `PALLOT_GOOGLE_API_KEY`; without one it's never asked; results flagged as approximate unless they hit a building |
| Ballotpedia's address search | address suggestions while typing | an **unofficial** endpoint (Esri data), like Ballotpedia's ballot below; it has its own switch in Settings |
| Texas Legislative Council map (PLANE2106) | State Board of Education district, and its outline on the map | comes with Pallot (see [Bundled snapshots](#bundled-snapshots)), so lookups never download it. Nothing about you is sent |
| Texas Legislative Council precinct map (data.capitol.texas.gov, the `precincts` maps) | your election precinct, and its outline on the map; for a voter card, the points inside your precinct that the Census and Ballotpedia are asked about | the portal's list of maps is asked once a week; the newest map, a primary's or a general's (now the 2026 primary's, about 45 MB), is downloaded on the first lookup and again only when a newer one is listed. Nothing about you is sent |
| County map servers: Harris, Dallas, Tarrant, Travis, Fort Bend, Bexar and Denton | your commissioner and JP precincts, from your election precinct | each county's list of its election precincts, or its maps of its commissioner and JP precincts, found by name (the newest year, never a proposal), bundled with Pallot (see [Bundled snapshots](#bundled-snapshots)); once the bundled copy is two weeks old, downloaded whole, at most once a week, when you look up an address there. Nothing about you is sent |
| US Census TIGERweb | the outlines of your U.S. House, State Senate and State House districts, for the map | every Texas district's outline, bundled with Pallot (see [Bundled snapshots](#bundled-snapshots)); once the bundled copy is 37 days old, one request per district, with its number and never your address |
| OpenStreetMap tiles (tile.openstreetmap.org) | the street map under the outlines | through the Pallot server, only the tiles of the area you look at, following OpenStreetMap's [tile usage policy](https://operations.osmfoundation.org/policies/tiles/); drawn with [Leaflet](https://leafletjs.com), which comes with Pallot |
| Texas Secretary of State | official ballot order per county, candidate filings | the public API behind goelect.txelections.civixapps.com |
| Texas Secretary of State, Important Election Dates | each election's last day to register, early voting and mail-ballot deadline | one public web page (sos.state.tx.us), read whole |
| Ballotpedia | city council, school board and special-district races, and others the state doesn't list (appraisal district boards); notes on races; JP/constable/commissioner precinct (when it has a race on this ballot) and city council district; candidate profiles | for a voter card, asked at three points inside your precinct, keeping only what all three have. An **unofficial** endpoint. Its terms forbid commercial scraping, so it starts off: turn it on in Settings for personal use |
| [Wikidata](https://www.wikidata.org) | profiles of candidates who hold or held a Texas office: a photo, a description, birth date, party, the Texas offices they've held, and stable links to their Wikidata item, Wikipedia article and campaign and government websites | Wikidata's public query service (CC0, no key). The list of every living Texas officeholder comes with Pallot (see [Bundled snapshots](#bundled-snapshots)), and the matched candidates' details are asked once per ballot, by their Wikidata ids. Nothing about you is sent. Photos load from Wikimedia Commons |
| TrackAIPAC | pro-Israel lobby money and endorsements for congressional candidates | bundled with Pallot (see [Bundled snapshots](#bundled-snapshots)) |
| Vote for Peace (voteforpeace.info, from Organize for Peace) | whether it calls a candidate an Ally, Neutral or Opposed, on war, human rights and lobby money, with the groups it cites and its notes; every level, from Congress to county courts and city councils | bundled with Pallot, used with Organize for Peace's permission (see [Bundled snapshots](#bundled-snapshots)); starts off, turn it on in Settings |
| Endorsement lists (one file per organization, in `pallot/endorsements/`) | the candidates an organization endorses, with its note and the office as it lists it | each a copy made once, frozen, part of Pallot and never fetched. About and the FAQ name the lists in your version |
| Live endorsement lists: Muslims United PAC (muslimsunitedpac.com) | the candidates it endorses, with its take on each and a link to their page on its site | the site's public JSON list of its endorsements, the whole list in one request, the same for everyone; it comes with Pallot, with its permission (see [Bundled snapshots](#bundled-snapshots)), and is downloaded again once the bundled copy is two days old |
| Live endorsement lists: CAIR Action (cairactionguide.org) | the candidates its Action Guide endorses or prefers, with that level in its words and a link to its list for the state | the site's public JSON list of its endorsements, the whole list in one request, the same for everyone; it comes with Pallot, with its permission (see [Bundled snapshots](#bundled-snapshots)), and is downloaded again once the bundled copy is two days old |
| Live endorsement lists: Emgage PAC (candidates.emgagepac.org) | the candidates it endorses, with its note on each when it has one, and a link to its list | the JSON list behind its donation page, the whole list in one request, the same for everyone; that request needs a token the page hands out, so the page is fetched first, and only when the list is. The list comes with Pallot, with its permission (see [Bundled snapshots](#bundled-snapshots)), and is downloaded again once the bundled copy is two days old; the token is never kept |
| FEC (Federal Election Commission) | money raised and spent by congressional campaigns, where it came from, and outside spending for or against them | the OpenFEC API, with a snapshot of its answers for Texas's federal races bundled with Pallot (see [Bundled snapshots](#bundled-snapshots)). Without your own key, race totals only (see [The FEC key](#the-fec-key-optional)) |
| Texas Ethics Commission | the same for state candidates and officeholders, plus their largest donors | bundled with Pallot, built from TEC's nightly CSV export (see [Bundled snapshots](#bundled-snapshots)) |
| FiftyPlusOne (fiftyplusone.news) | public polls of U.S. Senate, U.S. House and Governor races | the site's own JSON API; its lists come with Pallot, with its permission (see [Bundled snapshots](#bundled-snapshots)), and are downloaded again once the bundled copy is two days old |
| Seat holders: the [congress-legislators](https://github.com/unitedstates/congress-legislators) project and [Open States](https://openstates.org) | who holds each U.S. Senate, U.S. House, State Senate and State House seat now, and their party: Open seat, Party holds seat, and Incumbent where the filing doesn't say | two public files (public domain and CC0), bundled with Pallot (see [Bundled snapshots](#bundled-snapshots)); once the bundled copy is two weeks old, each is downloaded whole at most once a week, and only when the ballot has a race of that body. Nothing about you is sent. Statewide offices, the SBOE, courts and local races aren't covered |

Commissioner, JP and constable races depend on your commissioner and JP precincts. These come from the numbers you enter, then your county's records (in the seven counties above), then Ballotpedia. When none of them gives a number, those races are left out with a note. A race with only write-ins is shown when Pallot can place it. When Texas SOS has no ballot for the county (a special election), Pallot uses its statewide candidate list and shows only federal, statewide, congressional, legislative and SBOE races, with a note.

Your election precinct comes from the newest precinct map, a primary's or a general's. When your address and the middle of its census block fall in different precincts, Pallot names both and picks neither. Your voter registration certificate wins.

Campaign money covers congressional races (FEC) and state races (TEC): statewide offices, the Legislature, the SBOE, appellate and district courts and district attorneys. County, precinct, city and school candidates file with their county or city, so their races show none. The FAQ goes through how every figure is worked out.

Candidates are matched across sources by name, with seat and party as corroboration. Every match is labeled **exact** or **likely**, and ambiguous ones are left unmatched.

## Caching

Pallot saves every answer it gets in `data/`, so looking up the same address (or the same voter card's precinct) again makes **zero** external calls, even after a restart. The server's log has one line per lookup with how many requests it sent (`lookup: 0 external calls, 41 cache hits, 180 ms`), with no address, and `pallot-cache check` shows what the server keeps for each source.

- Each source's answers have a lifetime: from a day (ballot data, polls, key dates) to 30 days (geocodes, district outlines). OpenStreetMap's tiles are kept at least 7 days, as its policy asks. `.env.example` lists every lifetime, each overridable with `PALLOT_TTL_<NAME>` in seconds.
- Once an answer is past its lifetime, the next lookup asks again. If that fails, the old copy is shown with a "data as of" note, and the request isn't retried for 15 minutes. An error a source sends as if it were an answer counts as a failure too, so it never replaces a good copy.
- If a source refuses a request, Pallot stops asking it for an hour (2 minutes for an FEC key at its rate limit, while your other keys carry on). What it already has still shows.
- When a source fails, the ballot names it and says what still works. Why it failed goes to the server's log, never to the page.
- The snapshots that come with Pallot (see [Bundled snapshots](#bundled-snapshots)) mean lookups never contact TrackAIPAC, Vote for Peace or the Texas Ethics Commission, and ask the other bundled sources only once the bundled copy is a few days old.
- Address suggestions, street map tiles and addresses that weren't found are deleted once they've been expired for 30 days. Tiles and suggestions are kept under 512 MB and 64 MB, and each address lookup's answers (the Census's, OpenStreetMap's, Google's and Ballotpedia's) under 128 MB, the oldest going first. Everything else stays as the copy to show when a source is down.
- `pallot-cache` asks the FEC more slowly than a lookup does, leaving room for a running Pallot, and doesn't ask a paused source.

## Settings

The **Settings** page has **Ballot view**, **Web search**, **People you avoid**, **Sources**, **Appearance** and **Clear data**. Everything you choose there is saved in your browser, so it changes only what you see, not anyone else using the same Pallot.

- **Sources** lists every source in groups, with a switch for each (except the address lookup), a line on what it holds and how old it is, and a warning when it's paused or can't be used. Your switches travel with each request, so the server builds your ballot with them. A source you haven't switched follows the defaults (see [Which sources start on](#which-sources-start-on)).
- **Clear data** clears your picks and notes, or everything Pallot keeps in this browser, each with **Undo**.

Settings can't refresh or clear what the server saved: anyone who opens Pallot can open Settings, and it has no login. That's for whoever runs Pallot, on the machine it runs on: see [Keeping the cache](#keeping-the-cache).

Ballotpedia and Vote for Peace start off. Turn Ballotpedia on to add city council, school board and special district races, and Vote for Peace to add its Allies and Opposed. With Texas SOS off, the ballot comes entirely from Ballotpedia.

### Which sources start on

`pallot/sources.toml` declares which sources are on for someone who hasn't switched them, under `[sources]`, one `id = true` or `false` each (the ids `pallot-cache check` shows in brackets). Every endorsement list starts on. To change the defaults for everyone using your Pallot, don't edit that file: put a `sources.toml` in the data folder (`data/`, or `PALLOT_DATA_DIR`), listing only what you change, and restart Pallot. For example, to share Pallot with others without Ballotpedia's unofficial endpoints:

```toml
[sources]
ballotpedia = false
suggestions = false
```

A file Pallot can't use (a source that doesn't exist, a value that isn't `true` or `false`) stops it from starting, with a message saying what's wrong. Each person's own switches in Settings still win.

## Keeping the cache

`pallot-cache` checks, refreshes and prunes what Pallot keeps in its data folder. Run it on the machine Pallot runs on, with uv, or inside the container with Docker. It can run while Pallot does: the server picks up what it fetched.

```bash
uv run pallot-cache check                          # each source's saved copies, and how many are stale (past their lifetime)
uv run pallot-cache refresh                        # soft refresh: fetch again only what's stale, and a missing or newer map
uv run pallot-cache prune                          # delete what's no use even as a fallback, then shrink the file
uv run pallot-cache hard-refresh                   # fetch everything again, and refresh the bundled snapshots
uv run pallot-cache rebuild                        # delete everything saved, then fetch it all again (asks first)
docker compose exec pallot pallot-cache check      # the same, in the container
```

- **check** changes nothing and asks no one: for each source, its saved responses, their size, how many are stale, when they were fetched, whether it's paused, how many answers came with Pallot, its maps or snapshot, and whether a map is missing or the portal lists a newer one.
- **refresh** asks again only for the responses past their lifetime, downloads the precinct map when none is kept or when the portal lists a newer one (about 45 MB). The snapshots have no lifetime, so it leaves them.
- **prune** deletes expired address suggestions and street map tiles, addresses that weren't found, and the oldest tiles, suggestions and address lookups past their caps, then shrinks the file. Pallot does the same when it starts, and every 6 hours without shrinking the file. It never deletes another source's copies, which stay to show when a source is down.
- **hard-refresh** asks again for every saved response, re-downloads the SBOE map (so a host picks up a newer plan), checks for a newer precinct map, and refreshes TrackAIPAC, Vote for Peace and the Texas Ethics Commission (see [Bundled snapshots](#bundled-snapshots); TEC's may download about 1 GB).
- **rebuild** deletes every saved response, pause and map, then fetches them all again, as hard-refresh does. The snapshots aren't deleted, only refreshed; `--reset-snapshots` puts them back as they came with Pallot first. `--delete-only` deletes and fetches nothing again: the next lookups fetch what they need, which is how to erase the addresses Pallot saved (`--only geocoding suggestions ballotpedia`). It asks first, unless you add `--yes`.
- The street map's tiles and the address suggestions are never fetched in bulk: they're only fetched as someone looks at the map or types an address, as OpenStreetMap's tile policy asks.
- `--only` takes source ids (`--only sos fec`) for every command but prune.
- It exits with 1 when something couldn't be fetched (the old copy stays), so it can run from cron or a systemd timer, for example once a night: `uv run pallot-cache refresh`.

## Bundled snapshots

The TrackAIPAC, Vote for Peace and Texas Ethics Commission data come with Pallot as snapshots in the repo. Pallot copies them into `data/` on first run, so ballot lookups never contact trackaipac.com, voteforpeace.info or TEC. Each has a row in Settings, which says how old it is:
- `pallot-cache hard-refresh` (or with `--only trackaipac`, `voteforpeace` or `tec`) fetches a new copy.
  - TrackAIPAC's checks the site's pages and saves only if the site changed.
  - Vote for Peace's fetches its All Candidates page (one request, about 7 MB) and saves only if a candidate changed.
  - TEC's first makes one small request to see whether TEC's nightly export (`TEC_CF_CSV.zip`, about 1 GB) has changed; if not, that's all. If it has, it downloads the zip in one request (a minute or two on a fast connection) and rebuilds the snapshot.
- `pallot-cache rebuild --reset-snapshots --only trackaipac` (or `voteforpeace`, `tec`) goes back to the snapshot that came with Pallot, then refreshes it.
- **TEC's download server blocks bursts of requests.** If a refresh says it was refused, try later, or download the zip in a browser, save it as `data/tec/TEC_CF_CSV.zip`, and run the refresh again.

Pallot also comes with some sources' answers (`bundles/data/`). For now that's:
- the FEC's answers for Texas's federal races: each seat's list of candidates and their totals, and the breakdowns of the candidates on the ballot;
- Texas SOS's statewide data: the elections of this year and next, its tables of counties, parties and filing statuses, and each upcoming election's statewide list of candidates (about 2.6 MB);
- Texas SOS's ballot order for every county in each upcoming election (about 10 MB). A county whose ballot order isn't published yet is left out, so a lookup there still asks Texas SOS for it, and asks again after 6 hours while it's empty;
- the seat holders' two lists, the congress-legislators project's current members of Congress (public domain) and Open States' Texas legislators (CC0), about 1.1 MB;
- Wikidata's list of every living person who holds or held a Texas office, with the offices (CC0), about 750 KB. The matched candidates' details aren't in it, so a ballot's first lookup asks for them;
- TIGERweb's outlines of every Texas U.S. House, State Senate and State House district (public domain), about 2.7 MB;
- the seven counties' records of their commissioner and JP precincts: Harris's, Dallas's, Tarrant's, Travis's and Fort Bend's lists of their election precincts, and Bexar's and Denton's maps, about 1.9 MB;
- FiftyPlusOne's nationwide lists of polls of U.S. Senate, U.S. House and Governor races, used with FiftyPlusOne's permission, about 2.2 MB;
- the live endorsement lists of Muslims United PAC, CAIR Action and Emgage PAC, each used with its organization's permission: about 37 KB, 1.3 MB and 36 KB. Emgage's token is never kept, in the bundle or the cache.

At startup, Pallot puts them in its cache, dated when they were last checked, unless the cache has a newer copy. So a lookup asks a source only for what the bundle doesn't have, or once the bundle's answer is older than its bundle lifetime: the FEC's 7 days (`PALLOT_TTL_FEC_BUNDLE`); Texas SOS's elections 3 days, tables 30 days, candidate lists and ballot orders 2 days (`PALLOT_TTL_SOS_ELECTIONS_BUNDLE`, `PALLOT_TTL_SOS_REFERENCE_BUNDLE`, `PALLOT_TTL_SOS_CANDIDATES_BUNDLE`, `PALLOT_TTL_SOS_BALLOT_ORDER_BUNDLE`); the seat holders' 14 days (`PALLOT_TTL_OFFICEHOLDERS_BUNDLE`); Wikidata's 14 days (`PALLOT_TTL_WIKIDATA_BUNDLE`); the district outlines 37 days (`PALLOT_TTL_TIGERWEB_BUNDLE`); the counties' records 14 days (`PALLOT_TTL_COUNTY_PRECINCTS_BUNDLE`); the polls 2 days (`PALLOT_TTL_POLLS_BUNDLE`); the endorsement lists 2 days (`PALLOT_TTL_ENDORSEMENT_FEEDS_BUNDLE`). After that, the live answer is kept for the source's usual lifetime. This matters most on a host whose `data/` starts empty at each restart. `pallot-cache check` says how many answers came with Pallot for each source, and when they were checked.
- `uv run pallot-bundle refresh` rebuilds every bundle in the repo; `--only fec` (or `sos`, `sos_ballot_order`, `officeholders`, `wikidata`, `tigerweb`, `county_precincts`, `polls`, `mupac`, `cair`, `emgage`) limits it to the FEC's. `--due` skips a bundle checked more recently than it's worth (daily or weekly; the FEC's, Texas SOS's, the polls and the endorsement lists are daily, the seat holders', Wikidata's, the outlines and the counties' weekly), `--dry-run` says what would change, and `--force` writes even if nothing changed.
- Until 15 November 2026, a GitHub Action refreshes every snapshot in the repo each day (`pallot-bundle refresh --due`, then TrackAIPAC, Vote for Peace and TEC), updates [What the snapshots hold](#what-the-snapshots-hold), and commits the changes to the `chore/refresh-caches` branch, which the maintainer merges into `develop`, so a fresh deploy comes with answers only a few days old (see DEVELOPMENT.md's "The daily refresh").

Pallot also comes with the Texas Legislative Council's State Board of Education map (plan E2106, about 1.9 MB, `pallot/data/plane2106_kml.zip`). At startup, Pallot copies it into `data/` when no map is kept, so lookups never download it. The plan stays until the next redistricting, so the map has no lifetime. Settings says whether the map kept came with Pallot or was downloaded, and when.
- `pallot-cache hard-refresh --only geocoding` downloads it again from the portal, in case a newer plan is published there. A rebuild puts back the map that came with Pallot before downloading it again.

### What the snapshots hold

Each daily run rewrites this table (`uv run pallot-bundle stats --since HEAD --readme README.md`), so you can see whether a source is still adding candidates. A change in brackets is since the run before. **Data changed** is when the source's answers last changed, and **Checked** when it was last asked; a check later than the source's cadence (daily or weekly) is marked overdue, which usually means its refresh failed. The same table is on each run's summary page in Actions.

<!-- source-stats:start -->
| Source | Candidates | Also | Data changed | Checked |
|---|---|---|---|---|
| FEC | **93** | 39 races | 2026-10-14 | 2026-10-14 |
| Texas SOS candidate lists | **3,971** · 2026 November General Election: 3,967 · 2026 Special Election House District 93: 2 · 2026 Special Election Senate District 22: 2 | 3 elections | 2026-10-14 | 2026-10-14 |
| Texas SOS ballot orders | — | 254 county ballot orders · 3 elections | 2026-10-11 | 2026-10-12 ⚠ overdue (daily) |
| Seat holders | — | 39 Texas members of Congress · 178 Texas legislators | 2026-10-08 | 2026-10-08 |
| Wikidata | — | 662 Texas officeholders · 653 with their seat | 2026-10-13 | 2026-10-13 |
| TIGERweb district outlines | — | 38 U.S. House · 31 State Senate · 150 State House | 2026-10-08 | 2026-10-08 |
| County precinct records | — | 7 counties | 2026-10-08 | 2026-10-08 |
| FiftyPlusOne polls | — | 57 Texas Senate polls (+4) · 16 Texas House polls (+1) · 44 Texas Governor polls (+4) | 2026-10-14 | 2026-10-14 |
| Muslims United PAC | **26** · Texas: 3 | — | 2026-10-08 | 2026-10-14 |
| CAIR Action | **1,020** (+107) · Texas: 101 (+24) | — | 2026-10-14 | 2026-10-14 |
| Emgage PAC | **39** · Texas: 3 | — | 2026-10-08 | 2026-10-14 |
| TrackAIPAC | **626** (+1) · Texas: 56 · House: 509 (+1) · Other: 1 · Senate: 116 | — | 2026-10-14 | 2026-10-14 |
| Vote for Peace | **919** (+69) · Texas: 164 · State legislature: 336 (+34) · Federal: 240 (+9) · County: 160 (-3) · Local: 109 (+23) · Statewide: 58 (+7) · Judicial: 9 · Special district: 4 · State: 3 (-1) | — | 2026-10-14 | 2026-10-14 |
| Texas Ethics Commission | **2,153** | 802,982 contributions (+7) · 8,284 reports (+3) | 2026-10-14 | 2026-10-14 |
<!-- source-stats:end -->

## Configuration

Set these as environment variables, for example `PALLOT_DATA_DIR=/var/lib/pallot uv run pallot`, or in a `.env` file in the project folder: `cp .env.example .env` and fill it in. Pallot reads `.env` at startup, and git ignores it. Variables already set in the environment win over `.env`. Docker Compose reads the same `.env` and passes it to the container, where `PALLOT_DATA_DIR` is always `/data`: the folder it names on the host is mounted there.

| Variable | Default |
|---|---|
| `PALLOT_DATA_DIR` | `data/` in the project (cache, SBOE and precinct maps, TrackAIPAC, Vote for Peace and TEC data, and your `sources.toml` if you add one; git-ignored) |
| `PALLOT_FEC_API_KEY`, `PALLOT_FEC_API_KEY2` to `PALLOT_FEC_API_KEY5` | `DEMO_KEY`, which only allows race totals and runs out after a few requests. Get a free key from the [OpenFEC developers page](https://api.open.fec.gov/developers/). The extra keys are optional: Pallot uses all of them in turn, and skips one the FEC has rate limited or refused. They are only sent to the FEC, in a header, and Pallot never writes them anywhere (a resting key is noted by a short hash of it) |
| `PALLOT_GOOGLE_API_KEY` | none, so Google is never asked and Settings leaves it out. A [Google Geocoding API key](https://developers.google.com/maps/documentation/geocoding/get-api-key), to find addresses the Census and OpenStreetMap can't. It's only sent to Google, in a header, and Pallot never writes it anywhere. Google bills by the request, though Pallot asks only for an address both others missed, and keeps the answer for 30 days |
| `PALLOT_USER_AGENT` | `Pallot/0.1 (personal ballot helper; +https://github.com/Just-Peace/Pallot)`. Nominatim and OpenStreetMap's tile server require one that names the app and how to reach whoever runs it; add your email if you like |
| `PALLOT_HTTP_TIMEOUT` | `30` seconds |
| `PALLOT_ALLOWED_HOSTS` | none: Pallot answers to `localhost` and IP addresses only. List any other names you open it by, comma-separated (for example `nas.local`, or a reverse proxy's domain), or `*` for any. Other names get an error, which protects Settings from DNS rebinding; the log names the one refused |
| `PALLOT_TTL_*` | cache lifetimes, in seconds: `.env.example` lists each one with its default, including how long a source is left alone after refusing a request and how long the answers that came with Pallot are used (see [Caching](#caching) and [Bundled snapshots](#bundled-snapshots)). `PALLOT_TTL_TILES` can't go under 7 days, as OpenStreetMap asks |
| `PALLOT_TILES_MAX_MB` | `512`: the most the street map's tiles take in the cache; past it, the oldest are deleted when Pallot prunes |
| `PALLOT_SUGGEST_MAX_MB` | `64`: the same for the address suggestions |
| `PALLOT_ADDRESSES_MAX_MB` | `128`: the same for each address lookup's answers: the Census's, OpenStreetMap's, Google's and Ballotpedia's, each up to this much |
| `PALLOT_CACHE_MEMORY_MB` | `64`: the most the cache's answers take in memory. Past it, the least recently used are read from disk again when asked, which is slower. Pallot takes about 110 MB besides. A cap well under what one lookup reads saves nothing, since each lookup then reads its answers again |
| `PALLOT_GOOGLE_DAILY_MAX` | `300`: the most Google is asked in a day (UTC), about 9,000 a month. Past it, Google is paused until midnight UTC, and Settings says so. `0` for no limit |
| `PALLOT_LIMIT_BALLOT`, `PALLOT_LIMIT_SUGGEST`, `PALLOT_LIMIT_OUTLINES`, `PALLOT_LIMIT_TILES` | `30/hour`, `600/hour`, `60/hour`, `2000/hour`: how often one internet address may look up a ballot, get address suggestions, the district map's outlines, and street map tiles. A count over a period, such as `10/min` or `500/10min`; `off` for no limit. Past it, Pallot answers "Too many requests" with how long to wait. Pallot's own machine (`127.0.0.1`) is never limited (see [Running it publicly](#running-it-publicly)) |
| `PALLOT_MAX_LOOKUPS` | `8`: how many ballots Pallot looks up at once, counting those still adding money, polls and endorsements after the voter left. Past it, a lookup is asked to try again in a few seconds |
| `PALLOT_TRUSTED_PROXIES` | `127.0.0.1`: the reverse proxies whose `X-Forwarded-For` header says who the visitor is, comma-separated IP addresses or networks (`10.0.0.0/8`), or `*` for any. The limits count each visitor by that address (see [Running it publicly](#running-it-publicly)) |
| `PALLOT_PRUNE_EVERY` | `21600` seconds (6 hours): how often a running Pallot prunes the street map's tiles and the address suggestions |
| `PALLOT_PORT` | `8000`: the port `uv run pallot` listens on (`--port` wins), and in Docker the port published on the host |
| `PALLOT_DEFAULT_ENTRY` | `address`: the entry card's tab on a first visit. `voter_card` starts on **My voter card** (County and Precinct number) instead; a voter's last lookup still picks its own tab |

### Docker

- `compose.yaml` mounts `data/` (or the folder `PALLOT_DATA_DIR` names) at `/data`, so Docker and `uv run pallot` share the cache, `sources.toml`, TrackAIPAC, Vote for Peace and TEC data, and nothing is fetched twice. Don't run both at once, because they'd share one SQLite file.
- It's published on every network interface. To keep it to this machine, change the `ports` line in `compose.yaml` to `"127.0.0.1:8000:8000"`. `PALLOT_PORT` in `.env` changes the port.
- To open it by a name rather than an address (`http://nas.local:8000`, or through a reverse proxy), add the name to `PALLOT_ALLOWED_HOSTS` in `.env`. A reverse proxy must pass the original `Host` header on.
- Pallot's API answers only Pallot's own pages in a browser. Another website, or a script such as `curl`, gets an error.
- The container runs as user and group 1000, which must be able to write `data/`. That's why the quick start creates it: otherwise Docker creates it owned by root. If your ids differ (`id -u`, `id -g`), set `PALLOT_UID` and `PALLOT_GID` in `.env`.
- `.env` is passed in when the container starts, never built into the image.

### Running it publicly

Pallot has no login, so anyone who can reach it can look up ballots, and each new address makes Pallot ask the sources, with your FEC and Google keys. These settings keep one visitor from running up your Google bill, using up your FEC keys, or getting a source to refuse everyone:

- **The rate limits** (`PALLOT_LIMIT_BALLOT` and the rest) count each internet address. The defaults leave room for a household, and a script stops at a few dozen lookups an hour.
- **Behind a reverse proxy**, every request comes from the proxy, so set `PALLOT_TRUSTED_PROXIES` to its address, or the limits count all your visitors as one. On a host that's only reached through its own proxy (Render, Fly.io), `*` is fine. Anywhere else, never use `*`: a visitor could then claim any address and dodge the limits.
- A proxy on the same machine can stay at the default, `127.0.0.1`. Without one, a visitor on `127.0.0.1` is someone on the machine itself, and isn't limited.
- **`PALLOT_GOOGLE_DAILY_MAX`** caps what Google can cost in a day, and **`PALLOT_MAX_LOOKUPS`** how many lookups run at once.
- **`PALLOT_ALLOWED_HOSTS`** must list the name visitors open Pallot by.
- To keep Ballotpedia's unofficial endpoints off for everyone, see [Which sources start on](#which-sources-start-on).

## Not built yet

Known bugs, planned improvements and features, and UI ideas are [GitHub issues](https://github.com/Just-Peace/Pallot/issues).

## Working on Pallot

The commands, the tests, and adding a source: [DEVELOPMENT.md](DEVELOPMENT.md). The rules for a change: [AGENTS.md](AGENTS.md).

## License

Pallot's code is under the [MIT License](LICENSE).

The data that comes with it isn't: each source's data belongs to that source, under its own terms. That covers the snapshots (`trackaipac_cache/data/`, `voteforpeace_cache/data/`, `tec_cache/data/`, `bundles/data/`), the SBOE map (`pallot/data/`) and the endorsement lists (`pallot/endorsements/`). [Leaflet](https://leafletjs.com), in `pallot/static/vendor/leaflet/`, keeps its own BSD 2-Clause license.
