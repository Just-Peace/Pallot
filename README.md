# VoteBot

A voter's personal ballot, currently for Texas addresses. Enter a home address and VoteBot shows every race on that voter's ballot, with candidates in ballot order. Each candidate carries information from several sources. You can pick candidates, write notes, and print your picks to take to the polls.

You run it yourself, in Docker or with uv, and use it in your browser.

## Quick start

Get the code, and optionally a settings file:

```bash
git clone https://github.com/Fahd-Siddiqui/VoteBot.git
cd VoteBot
cp .env.example .env    # optional: this is where the FEC key goes (see below)
```

Then run it one of two ways.

### With Docker

Needs [Docker](https://docs.docker.com/get-docker/) with Compose 2.24 or later.

```bash
mkdir -p data                   # where VoteBot keeps its cache and settings
docker compose up -d --build    # build the image and start VoteBot in the background
```

Open http://localhost:8000, or `http://<this machine's address>:8000` from another device. It listens on every network interface, and the Settings page has no login, so run it only on a network you trust. To keep it to this machine, see [Docker](#docker).

```bash
docker compose logs -f                     # follow the server log
docker compose down                        # stop it (data/ stays)
git pull && docker compose up -d --build   # update to the latest version
```

### With uv (local)

Needs [uv](https://docs.astral.sh/uv/): `curl -LsSf https://astral.sh/uv/install.sh | sh`.

```bash
uv sync           # installs VoteBot and its dependencies (and Python, if needed) into .venv, pinned by uv.lock
uv run votebot    # serves http://127.0.0.1:8000 until Ctrl+C (--port picks another port)
```

Open http://127.0.0.1:8000. It only listens on this machine, because the Settings page has no login; to use VoteBot from other devices, run it with Docker on a network you trust. To update: `git pull && uv sync`, then start it again.

### The FEC key (optional)

VoteBot needs no keys to run. To break down congressional candidates' money (where it came from, donation sizes, largest donors, outside spending), it needs a free FEC key:
1. Get one from the [OpenFEC developers page](https://api.open.fec.gov/developers/); api.data.gov emails it to you.
2. Put it in `.env` as `VOTEBOT_FEC_API_KEY=...`.
3. Restart VoteBot: `docker compose up -d`, or Ctrl+C and `uv run votebot` again.

Without a key, VoteBot uses the shared `DEMO_KEY`, which only allows race totals and runs out after a few requests. The other settings are under [Configuration](#configuration).

## Using it

- **Left pane**, the same on every page. On a phone or a narrow window it's a **top bar** instead, with your address and the pages each behind a button.
  - at the top, **Your ballot**, with your address under it. After a lookup the address is saved in the browser and shown as a card with its city and county. **Change** opens the form again; on the other pages it takes you to the ballot with the form open.
  - while you type an address, **suggestions** from Photon appear under the box: ↑/↓ and Enter pick one, which only fills the box in. "Street only" means OpenStreetMap has the street but not that house number, so the suggestion keeps the number you typed. Turn them off in Settings to get the browser's own address autofill back.
  - on the ballot, the list of sections, with how many races in each you've picked. The section on screen is highlighted as you scroll. On a phone they're a row of chips that stays in view.
  - at the bottom, links to **Settings**, **FAQ**, **About** and **Privacy**
- **First lookup:** a lookup whose data isn't saved yet can take several seconds, and a skeleton ballot shows meanwhile. Looking the same address up again is instant.
- **Top of the ballot**, staying in view as you scroll:
  - a progress bar counting races and propositions ("5 of 12 races · 1 of 2 propositions");
  - **Next race to pick** opens the next race you haven't picked and goes to it. `j` and `k` move to the next and previous race.
  - **View**: Collapse all, Expand all, **Collapse a race when I pick**, and **Only races I haven't picked**. Both options are remembered in the browser.
  - **Clear picks** clears your picks, notes and write-ins at once, and offers **Undo** for 10 seconds.
  - **Print my picks** (below).
- Under it, two cards, side by side (and as tall as each other) on a wide screen, and one above the other on a phone, then the map of your districts.
- **When to vote:**
  - the election's key dates from the Texas Secretary of State: the last day to register, early voting, and Election Day with the polls' hours. The next date still to come is in bold with how far off it is ("in 6 days"); past ones are in grey.
  - a calendar icon next to each date downloads it as a calendar file (`.ics`), and **Add all to calendar** downloads every date still to come. The events are all-day and have no place, since polling places aren't known. Importing a file again updates its events rather than adding copies.
  - three buttons under the dates: **Am I registered?** opens the state's My Voter Portal, which also shows your polling place once you log in; **Where to vote** opens the list of county elections offices, since each county sets its own polling places; **Add all to calendar** (above). The card's source line links to **VoteTexas.gov**, the state's voter site.
  - **Voting by mail?**, closed at first, says who can vote by mail in Texas and when the application must arrive (received, not postmarked), with its own calendar icon.
- **Your districts**, like your voter registration certificate, in three lines:
  - U.S. House, State Senate, State House and State Board of Education;
  - your county, with your commissioner precinct and your justice of the peace precinct (which is also your constable's);
  - your city, city council district and school district.

  A State Senate or State Board of Education seat that isn't up this time is in grey, with a line saying so ("State Senate 14 isn't up for election this time"). The precincts and the city council district come from Ballotpedia, when it has them. **Edit** changes the precincts, and **Use Ballotpedia's numbers** puts its numbers back. When races depend on a precinct VoteBot doesn't know, the fields are already open, and the card says which number to enter from your voter registration certificate. After **Update my ballot**, a message at the foot of the window offers **Show**, which goes to your precinct's races. If the address could only be placed approximately, the card says to check the districts.

- **Map of your districts:** a street map from OpenStreetMap with the outline of each district, in its own colour and line (solid, dashed, dotted, or dashes and dots), and a pin at your address. It opens centred on your address, close enough to see your streets.
  - Right above the map, a button for each district, with a sample of its line: pick one, or its line on the map, to highlight it and zoom to it; pick it again, or the pin button on the map, to come back to your address. Hover over a line to see which district it is.
  - Drag the map to move it, and zoom with **+** and **−**, or with the scroll wheel once you've clicked the map (so scrolling the page never zooms it by accident). On a phone, move and zoom it with two fingers; one finger scrolls the page. With the map selected, the arrow keys move it.
  - The outlines are simplified to about 50 m, so near a boundary, go by the district numbers.
  - The street map's tiles come from OpenStreetMap through the VoteBot server, which keeps them. Turn the street map off in Settings to see the outlines alone.
  - Click the map's heading to fold it away, as you would a race, and again to bring it back. It's shown at first, and your choice is remembered in the browser. While it's folded, nothing is fetched for it.
- **Precincts:** until your precincts are known, the races that depend on them are listed under "Depends on your precinct", with a link up to Your districts.
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
  - **Details**, with one tab per source that has something on them, in this order: the money (FEC for Congress, Texas Ethics Commission for state offices), Texas SOS, Polls, Ballotpedia and TrackAIPAC. It opens on the first. The badges on the candidate's row come in the same order. **‹** and **›** step through the race's other candidates without closing it.
  - a **Web search ↗** link that searches for their name, office and place, using Google unless you pick another engine (Bing, DuckDuckGo, Brave, Yahoo, Startpage, Ecosia, Kagi or Perplexity) in Settings

  A **?** on a source's badge, its tab in Details, or the Details button means that source only likely matched the candidate, so check it.
- **Print my picks:** a **full page** (with your notes and blank lines for races you haven't picked, if you want them), or a **wallet card** to cut out and fold. Both start with the election day and the early-voting dates.

Picks, notes and collapsed races are kept in the browser's `localStorage`, never on the server.

## Where the data comes from

| Source | Used for | Notes |
|---|---|---|
| US Census geocoder | address → county, U.S. House, State Senate and State House districts | already on the 2026 maps (120th Congress, 2026 legislative districts) |
| OpenStreetMap Nominatim | fallback when the Census can't match an address | results flagged as approximate unless they hit a building |
| Photon (photon.komoot.io) | address suggestions while typing | OpenStreetMap data; free for reasonable use, no key |
| Texas Legislative Council map (PLANE2106) | State Board of Education district, and its outline on the map | downloaded once |
| US Census TIGERweb | the outlines of your U.S. House, State Senate and State House districts, for the map | one request per district, with its number and never your address |
| OpenStreetMap tiles (tile.openstreetmap.org) | the street map under the outlines | through the VoteBot server, only the tiles of the area you look at, following OpenStreetMap's [tile usage policy](https://operations.osmfoundation.org/policies/tiles/); drawn with [Leaflet](https://leafletjs.com), which comes with VoteBot |
| Texas Secretary of State | official ballot order per county, candidate filings | the public API behind goelect.txelections.civixapps.com |
| Texas Secretary of State, Important Election Dates | each election's last day to register, early voting and mail-ballot deadline | one public web page (sos.state.tx.us), read whole |
| Ballotpedia | city council, school board and special-district races; JP/constable/commissioner precinct and city council district; candidate profiles | an **unofficial** endpoint. Its terms forbid commercial scraping, so keep it personal or turn it off in Settings |
| TrackAIPAC | pro-Israel lobby money and endorsements for congressional candidates | bundled with VoteBot (see [TrackAIPAC and TEC snapshots](#trackaipac-and-tec-snapshots)) |
| FEC (Federal Election Commission) | money raised and spent by congressional campaigns, where it came from, and outside spending for or against them | the OpenFEC API. Without your own key, race totals only (see [The FEC key](#the-fec-key-optional)) |
| Texas Ethics Commission | the same for state candidates and officeholders, plus their largest donors | bundled with VoteBot, built from TEC's nightly CSV export (see [TrackAIPAC and TEC snapshots](#trackaipac-and-tec-snapshots)) |
| FiftyPlusOne (fiftyplusone.news) | public polls of U.S. Senate, U.S. House and Governor races | the site's own JSON API |

The Texas SOS data covers every race touching a county. VoteBot keeps only the voter's congressional, legislative and SBOE districts; judicial and DA districts are whole counties. Commissioner, JP and constable races depend on the voter's precinct. That comes from Ballotpedia or from the numbers the voter enters under Your districts, where one number covers both the JP and the constable, since each justice precinct elects one of each; otherwise those races are listed under "Depends on your precinct". Ballotpedia lists MUDs and water districts for a whole county, so those appear under "Special districts" as "may be on your ballot". When Texas SOS has no ballot for the county, as for a special election, VoteBot uses its statewide candidate list instead. That list doesn't say which counties judicial, DA and county races cover, so only federal, statewide, congressional, legislative and SBOE races are shown, and a note says so.

Campaign money covers congressional races (FEC) and state races (TEC), which includes:
- statewide offices;
- the Legislature;
- the State Board of Education;
- appellate and district courts;
- district attorneys.

County candidates (county courts at law and probate courts included), precinct, city and school candidates file with their county or city, so their races show none.

What "raised" covers (the FAQ's "How are the FEC figures put together?" and "How are the Texas Ethics Commission figures put together?" go through every figure):
- **TEC totals:** the reports whose period ends after the last November general election, excluding daily pre-election and special-session reports, whose money is reported again later.
- **FEC totals:** the whole election period (two years for the House, six for the Senate).

Candidates are matched across sources by name, with seat and party as corroboration. Every match is labelled **exact** or **likely**, and ambiguous ones are left unmatched. With Texas SOS off, a state race's seat for the Texas Ethics Commission match comes from Ballotpedia's district ("Texas House of Representatives District 49" is State Representative, District 49), so a namesake elsewhere in Texas isn't taken for the candidate. TrackAIPAC lists members of Congress by their current seat, so a 2026 seat change after the 2025 redistricting shows up as "likely" unless TrackAIPAC's entry mentions the new seat.

## Caching

VoteBot saves every answer it gets in `data/`, so looking up the same address again makes **zero** external calls, even after a restart. Settings shows how the last lookup used each source.

- Lifetimes:
  - reference data: 30 days
  - elections, ballot order and statewide candidate lists: 24 hours (a year for past elections)
  - empty ballot orders: 6 hours
  - geocodes: 30 days (an address that wasn't found: 1 day)
  - address suggestions: 30 days
  - Ballotpedia: 24 hours
  - FEC: 7 days (a year for past elections)
  - polls: 24 hours
  - key election dates: 24 hours
  - district outlines for the map: 30 days
  - street map tiles: 7 days, the least OpenStreetMap's policy allows
  - after a failed request: its old copy is served for 15 minutes before the source is asked again
  - address suggestions, street map tiles, and addresses that weren't found, are deleted when VoteBot starts once they've been expired for 30 days (`VOTEBOT_TTL_PRUNE_AFTER`). Everything else stays as the copy to show when a source is down.
  - Override any of these with `VOTEBOT_TTL_<NAME>` in seconds; see [Configuration](#configuration).
- The TrackAIPAC and Texas Ethics Commission data come with VoteBot, so lookups never contact either; they're only fetched again when you press Refresh.
- Candidate details come from one statewide list per election (~2.6 MB, one request per day), not one request per candidate.
- If a refresh fails, the old copy is shown with a "data as of" note, and that request isn't retried for 15 minutes, so a source that's down doesn't slow every lookup. A source that fails before answering once has nothing to fall back on.
- If Ballotpedia, Photon, FiftyPlusOne, the Texas SOS's dates page, TIGERweb or OpenStreetMap's tile server refuses a request, VoteBot stops asking it for an hour. What it already sent still shows.
- If the FEC answers that its rate limit is reached, VoteBot stops asking it for an hour and shows what it already has meanwhile. With `DEMO_KEY`, that limit is shared by everything on your IP address.
- Refresh in Settings doesn't ask a paused source either, and stops when a source pauses partway through.

## Settings

The **Settings** page, linked from the left pane:
- picks the web search engine;
- turns the district outlines, the street map, address suggestions, Texas SOS, the key election dates, Ballotpedia, TrackAIPAC, the FEC, the Texas Ethics Commission and polls on or off;
- says whether the FEC is using your key, whether a source is paused, and how old the Texas Ethics Commission snapshot is;
- shows what the server has saved for each source (responses, size, when they were fetched) and how the last lookup used it (requests made, how old the data was), plus the total on disk;
- has a refresh or clear button per source (the street map has Clear only: OpenStreetMap doesn't allow re-downloading its tiles in bulk), plus "Clear all caches", which also resets TrackAIPAC and the Texas Ethics Commission to their bundled snapshots. Refreshes that send or download a lot (every saved address, every saved suggestion, TEC's 1 GB zip) ask first;
- has "Clear my picks & notes", and "Clear all browser data", which also forgets your address, search engine and view choices. Both clear at once and offer **Undo** for 10 seconds.

Settings has no login, but its buttons only work from VoteBot's own pages: a request that another website makes from your browser is refused.

When you go back to your ballot after changing a setting, it reloads with the new one. That includes a ballot kept by the Back button or left open in another tab. With Texas SOS off, the ballot comes entirely from Ballotpedia.

## TrackAIPAC and TEC snapshots

The TrackAIPAC and Texas Ethics Commission data come with VoteBot as snapshots in the repo. VoteBot copies them into `data/` on first run, so ballot lookups never contact trackaipac.com or TEC. Each has a row in Settings:
- **Refresh** fetches a new copy.
  - TrackAIPAC's checks the site's pages and saves only if the site changed.
  - TEC's first makes one small request to see whether TEC's nightly export (`TEC_CF_CSV.zip`, about 1 GB) has changed; if not, that's all. If it has, it downloads the zip in one request (a minute or two on a fast connection) and rebuilds the snapshot.
- **Reset** goes back to the bundled copy.
- **TEC's download server blocks bursts of requests.** If a refresh says it was refused, try later, or download the zip in a browser, save it as `data/tec/TEC_CF_CSV.zip`, and press Refresh again.

## Configuration

Set these as environment variables, for example `VOTEBOT_DATA_DIR=/var/lib/votebot uv run votebot`, or in a `.env` file in the project folder: `cp .env.example .env` and fill it in. VoteBot reads `.env` at startup, and git ignores it. Variables already set in the environment win over `.env`. Docker Compose reads the same `.env` and passes it to the container, where `VOTEBOT_DATA_DIR` is always `/data`: the folder it names on the host is mounted there.

| Variable | Default |
|---|---|
| `VOTEBOT_DATA_DIR` | `data/` in the project (cache, settings, SBOE map, TrackAIPAC and TEC data; git-ignored) |
| `VOTEBOT_FEC_API_KEY` | `DEMO_KEY`, which only allows race totals and runs out after a few requests. Get a free key from the [OpenFEC developers page](https://api.open.fec.gov/developers/). It's only sent to the FEC, in a header, and VoteBot never writes it anywhere |
| `VOTEBOT_USER_AGENT` | `VoteBot/0.1 (personal ballot helper; +https://github.com/Fahd-Siddiqui/VoteBot)`. Nominatim and OpenStreetMap's tile server require one that names the app and how to reach whoever runs it; add your email if you like |
| `VOTEBOT_HTTP_TIMEOUT` | `30` seconds |
| `VOTEBOT_ALLOWED_HOSTS` | none: VoteBot answers to `localhost` and IP addresses only. List any other names you open it by, comma-separated (for example `nas.local`, or a reverse proxy's domain), or `*` for any. Other names get an error, which protects Settings from DNS rebinding |
| `VOTEBOT_TTL_*` | cache lifetimes, see [Caching](#caching); for example `VOTEBOT_TTL_KEY_DATES` for the key election dates, `VOTEBOT_TTL_KEY_DATES_BACKOFF` for how long that page is left alone after refusing a request, `VOTEBOT_TTL_OUTLINES` for the district map's outlines, `VOTEBOT_TTL_TILES` for the street map's tiles (at least 7 days, as OpenStreetMap asks), and `VOTEBOT_TTL_PRUNE_AFTER` for how long expired address suggestions and addresses not found are kept |

### Docker

- `compose.yaml` mounts `data/` (or the folder `VOTEBOT_DATA_DIR` names) at `/data`, so Docker and `uv run votebot` share the cache, settings, TrackAIPAC and TEC data, and nothing is fetched twice. Don't run both at once, because they'd share one SQLite file.
- It's published on every network interface. To keep it to this machine, change the `ports` line in `compose.yaml` to `"127.0.0.1:8000:8000"`. `VOTEBOT_PORT` in `.env` changes the port.
- To open it by a name rather than an address (`http://nas.local:8000`, or through a reverse proxy), add the name to `VOTEBOT_ALLOWED_HOSTS` in `.env`. A reverse proxy must pass the original `Host` header on.
- The container runs as user and group 1000, which must be able to write `data/`. That's why the quick start creates it: otherwise Docker creates it owned by root. If your ids differ (`id -u`, `id -g`), set `VOTEBOT_UID` and `VOTEBOT_GID` in `.env`.
- `.env` is passed in when the container starts, never built into the image.

## Not built yet

Known bugs, planned improvements and features, and UI ideas are in [ROADMAP.md](ROADMAP.md).

## Working on VoteBot

How it's put together, the tests, and adding a source: [DEVELOPMENT.md](DEVELOPMENT.md).
