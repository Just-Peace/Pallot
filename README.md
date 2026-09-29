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
| Photon (photon.komoot.io) | address suggestions while typing | OpenStreetMap data; free for reasonable use, no key |
| Texas Legislative Council map (PLANE2106) | State Board of Education district | downloaded once |
| Texas Secretary of State | official ballot order per county, candidate filings | the public API behind goelect.txelections.civixapps.com |
| Ballotpedia | city council, school board and special-district races; JP/constable/commissioner precinct; candidate profiles | an **unofficial** endpoint. Its terms forbid commercial scraping, so keep it personal or turn it off in Settings |
| TrackAIPAC | pro-Israel lobby money and endorsements for congressional candidates | bundled with VoteBot (see [TrackAIPAC and TEC snapshots](#trackaipac-and-tec-snapshots)) |
| FEC (Federal Election Commission) | money raised and spent by congressional campaigns, where it came from, and outside spending for or against them | the OpenFEC API. Without your own key, race totals only (see [The FEC key](#the-fec-key-optional)) |
| Texas Ethics Commission | the same for state candidates and officeholders, plus their largest donors | bundled with VoteBot, built from TEC's nightly CSV export (see [TrackAIPAC and TEC snapshots](#trackaipac-and-tec-snapshots)) |
| FiftyPlusOne (fiftyplusone.news) | public polls of U.S. Senate, U.S. House and Governor races | the site's own JSON API |

The Texas SOS data covers every race touching a county. VoteBot keeps only the voter's congressional, legislative and SBOE districts; judicial and DA districts are whole counties. Commissioner, JP and constable races depend on the voter's precinct. That comes from Ballotpedia or from numbers the voter types in; otherwise those races are listed under "Depends on your precinct". Ballotpedia lists MUDs and water districts for a whole county, so those appear under "Special districts" as "may be on your ballot". When Texas SOS has no ballot for the county, as for a special election, VoteBot uses its statewide candidate list instead. That list doesn't say which counties judicial, DA and county races cover, so only federal, statewide, congressional, legislative and SBOE races are shown, and a note says so.

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

Candidates are matched across sources by name, with seat and party as corroboration. Every match is labelled **exact** or **likely**, and ambiguous ones are left unmatched. TrackAIPAC lists members of Congress by their current seat, so a 2026 seat change after the 2025 redistricting shows up as "likely" unless TrackAIPAC's entry mentions the new seat.

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
  - after a failed request: its old copy is served for 15 minutes before the source is asked again
  - Override any of these with `VOTEBOT_TTL_<NAME>` in seconds; see [Configuration](#configuration).
- The TrackAIPAC and Texas Ethics Commission data come with VoteBot, so lookups never contact either; they're only fetched again when you press Refresh.
- Candidate details come from one statewide list per election (~2.6 MB, one request per day), not one request per candidate.
- If a refresh fails, the old copy is shown with a "data as of" note, and that request isn't retried for 15 minutes, so a source that's down doesn't slow every lookup. A source that fails before answering once has nothing to fall back on.
- If Ballotpedia, Photon or FiftyPlusOne refuses a request, VoteBot stops asking it for an hour. What it already sent still shows.
- If the FEC answers that its rate limit is reached, VoteBot stops asking it for an hour and shows what it already has meanwhile. With `DEMO_KEY`, that limit is shared by everything on your IP address.
- Refresh in Settings doesn't ask a paused source either, and stops when a source pauses partway through.

## Settings

The **Settings** page, linked from the left pane:
- picks the web search engine;
- turns address suggestions, Texas SOS, Ballotpedia, TrackAIPAC, the FEC, the Texas Ethics Commission and polls on or off;
- says whether the FEC is using your key, whether a source is paused, and how old the Texas Ethics Commission snapshot is;
- shows what the server has saved for each source (responses, size, when they were fetched) and how the last lookup used it (requests made, how old the data was), plus the total on disk;
- has a refresh or clear button per source, plus "Clear all caches", which also resets TrackAIPAC and the Texas Ethics Commission to their bundled snapshots. Refreshes that send or download a lot (every saved address, every saved suggestion, TEC's 1 GB zip) ask first;
- has "Clear my picks & notes", and "Clear all browser data", which also forgets your address and search engine.

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
| `VOTEBOT_USER_AGENT` | `VoteBot/0.1 (personal ballot helper)` (Nominatim requires an identifying one) |
| `VOTEBOT_HTTP_TIMEOUT` | `30` seconds |
| `VOTEBOT_ALLOWED_HOSTS` | none: VoteBot answers to `localhost` and IP addresses only. List any other names you open it by, comma-separated (for example `nas.local`, or a reverse proxy's domain), or `*` for any. Other names get an error, which protects Settings from DNS rebinding |
| `VOTEBOT_TTL_*` | cache lifetimes, see [Caching](#caching) |

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
