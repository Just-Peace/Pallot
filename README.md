# Pallot

**Your vote is yours.**

A voter's personal ballot, for any address in the 50 states and DC. Enter a home address and Pallot shows the races on that voter's ballot, with what several sources say about each candidate. You can pick candidates, write notes, and print your picks to take to the polls.

You run it yourself, in Docker or with uv, and use it in your browser.

Pallot is made by [Just-Peace](https://github.com/Just-Peace) for American voters who'd rather see the whole ballot for themselves. We don't back any candidate or party, and the choice is always yours.

## Where it covers

How much of a ballot Pallot has depends on the state:

| | States | What you get |
|---|---|---|
| **Full ballot** | Texas | Every federal, state, district, county and precinct race, in ballot order, from the Texas Secretary of State; your election precinct, commissioner and JP precincts; the election's key dates; a map of your districts |
| **The state's official list** | Alaska, Arizona, Arkansas, California, Colorado, Delaware, the District of Columbia, Florida, Georgia, Hawaii, Idaho, Illinois, Indiana, Iowa, Kansas, Kentucky, Louisiana, Maine, Maryland, Massachusetts, Michigan, Minnesota, Mississippi, Missouri, Montana, Nebraska, Nevada, New Hampshire, New Jersey, New Mexico, New York, North Carolina, North Dakota, Oklahoma, Oregon, Pennsylvania, South Carolina, South Dakota, Tennessee, Utah, Vermont, Virginia, Washington, West Virginia, Wisconsin, Wyoming | The races on the candidate list the state's election office publishes for the November ballot: Congress, statewide offices, the Legislature and the courts the list places, with each judge standing for retention as a Yes-or-No question. Georgia's, Nevada's, North Carolina's and Wisconsin's lists also have county and city races, Indiana's its county offices and courts, Delaware's its county offices, and Vermont's its county offices and judges (not its justices of the peace). Maryland's has no county races or circuit court judges. Missouri's has no county races, and your U.S. House district there is on its 2022 map, which the courts kept for 2026. South Carolina's also has its solicitors and the county offices elected countywide (sheriff, probate judge, auditor and the like), but not county council or school board races. Kentucky's has its courts and Commonwealth's Attorneys, but not its county races or the constitutional amendments, and its Governor's race and the other statewide offices in an odd year. Oklahoma's has only the races with more than one candidate, as its ballot does (a candidate with no opponent is elected without a vote), with its district judges and some county offices, but not the judges standing for retention or the state questions. Kansas's has its State Board of Education, placed by your State Senate district, its judges standing for retention and its district judges, but not its district magistrate judges or its county races. Montana's has its Public Service Commission, placed by your State House district, and its Supreme Court, but not its district judges or its county races. South Dakota's has its Public Utilities Commission and its other statewide offices, but not its county races. Hawaii's has its Office of Hawaiian Affairs trustees, elected statewide, and only the races still contested after the primary (a candidate unopposed then is elected), but not its county races. North Dakota's has its statewide offices, but not its Public Service Commission (two races its list doesn't tell apart), its judges or its county races. Mississippi's has Congress, its Court of Appeals and its special elections in 2026, but not its chancery and circuit judges, its county races or its Supreme Court, whose race a federal court has stopped. Minnesota's has Congress, its statewide offices and both chambers of its Legislature, but not its judges or its county races. Arkansas's has Congress, its statewide offices and its Legislature, but not the runoffs for circuit judge and prosecuting attorney or its county races. New Hampshire's has Governor, Congress and its Legislature, a floterial House district's race on the ballot of every district it's made of, but not its Executive Council or its county races. Tennessee's has Governor, Congress and its Legislature, but not its county races or the constitutional amendments. Massachusetts's has Congress, its Governor and Lieutenant Governor as one ticket, its other statewide offices and its Legislature, but not its Governor's Council, its district attorneys or its county races. Louisiana's has Congress and any special election for its Legislature, its U.S. House races an open primary where candidates of every party run together (the top two meet again in December if no one wins a majority), but not its Public Service Commission, BESE, its judges, district attorneys or its parish and city races. Utah's has Congress, its Legislature and its judges standing for retention, but not its State Board of Education, its justice court judges or its county races. West Virginia's has Congress and its Legislature, but not the unexpired terms of its circuit and family court judges or its county races. Idaho's has Congress, its Governor and other statewide offices and its Legislature, each House seat (A and B) a race of its own, but not its judges or its county races. DC's has its Delegate, Mayor, Council Chairman and at-large members, Attorney General and shadow Senator and Representative, but not its ward races or its Advisory Neighborhood Commissions. Maine's has only Congress, Governor and the Legislature. New Jersey's has Congress in an even year, and the State Senate and General Assembly (not Governor) in an odd year. Virginia's has Congress in an even year, with any special election for the General Assembly on the same day, and the General Assembly and the statewide offices in an odd year. Nebraska's Legislature is nonpartisan, so its candidates have no party. Washington's candidates are shown with the party they prefer, as its ballot prints it. Alaska's races are ranked-choice, so are Maine's for Congress, and so is any of DC's with three candidates or more. All of them also have their key dates. Races the state's list doesn't have (most county and city races) aren't shown |
| **Statewide races** | Ohio | Its statewide races (Governor, the other statewide offices, the Supreme Court and the U.S. Senate) from the Secretary of State's sample ballot, your U.S. House race from the FEC (Unverified, as below), and its key dates. The Legislature's, county and local races aren't shown |
| **Congress only** | Every other state | Your U.S. Senate and U.S. House races, from the candidates who filed with the FEC and raised $5,000 or more. These aren't confirmed: someone who lost a primary or dropped out may still be listed, so each is marked **Unverified** |

Everywhere, each candidate gets the money, endorsements, polls and profiles the sources have for them, and Your districts names your U.S. House, State Senate and State House districts, as your state calls them (State Assembly, House of Delegates, Nebraska's one Legislature), with a map that outlines them. DC has only its Delegate's district.

Some election offices' sites turn away programs like Pallot or have no file to download, so their lists are saved by hand from the site and come with Pallot: Arizona's, Arkansas's, Idaho's, Iowa's, Louisiana's, Massachusetts's, Nevada's, New Hampshire's, New York's, Oregon's, Tennessee's, Utah's, West Virginia's and Wisconsin's, Georgia's list of qualified candidates (its party nominees come from its election results site, which Pallot asks itself), and Ohio's sample ballot, typed in. Settings says when each was imported.

## Before you rely on it

- **It can be wrong.** Pallot puts together what public sources say, and a source can be late, incomplete or mistaken, or Pallot can match the wrong record. Always check your official sample ballot from your county or state elections office before you vote.
- **It isn't official.** It isn't tied to any government, election office, party, campaign or source.
- **It endorses no one.** Pallot doesn't back any candidate, party or cause. It shows what each source says, including endorsements made by others, and the choice is yours.
- **No warranty, no liability.** Pallot is provided as is, without warranty of any kind, as its [MIT License](LICENSE) says. Its makers and contributors aren't liable for any decision made with it, or for anything a source got wrong.

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

- **Look up your ballot** by home address (with suggestions as you type), or under the **Voter card** tab by state, county and the districts on the card (in Texas, the precinct number too), so no address is sent anywhere. Pick the election, and in Texas a party for a primary. The first lookup can take several seconds, and in Texas the very first after installing also downloads the precinct map (about 45 MB); looking the same address up again is instant.
- **Your ballot** lists the races Pallot has for your state (see [Where it covers](#where-it-covers)), with the candidates' party, Incumbent and Open seat, and a write-in line; in Texas, in ballot order with the declared write-ins. Races that depend on a district or precinct Pallot doesn't know are left out, with a note saying which number to enter.
- **When to vote** has the election's key dates, each downloadable to your calendar, and links to check your registration and find where to vote, in the states that have their key dates (see [Where it covers](#where-it-covers)). Elsewhere it links to your state's election office.
- **Ranked-choice races** (Alaska's, and Maine's for Congress) let you rank the candidates 1st, 2nd, 3rd and on, and a judge standing for retention is a Yes-or-No question.
- **Your districts** shows your districts, and in Texas your precincts, as on your voter registration certificate. You can correct a number from your certificate. A **map** shows your address on OpenStreetMap, with your districts' outlines.
- **Each candidate** has their endorsements, a **Funding** summary (small donors, home-state donors, outside spending), polls where there are any, a note, a web search, and **Profile**: their filing and Wikidata profile, issue searches, and a tab per source. **Compare funding** puts a race's candidates side by side.
- **View** chooses how much detail to show (Minimal, Simple, Detailed) and what matters to you (Funding, Endorsements, Polls, Where they stand).
- **Help me pick**: **Trust** picks the candidates of the endorsers you trust, and **Avoid** marks the ones you won't vote for, from watchlists or your own list. **More conditions** picks across the ballot, or in one race, by party, endorsements, money or polls. It never guesses in a race with more matches than seats.
- **Avoid** on a candidate adds them to your own list, which you can also fill by name or pattern in Settings. Trust never picks them.
- **Print my picks** as a full page or a wallet card. Your address isn't printed.
- **Save everything** in Settings as a `.pallot` file (picks for every election, notes, address and settings) and open it on another device to pick up where you left off, even on a first visit.
- **Share picks** as a link, to send them to a friend. You tick what it carries (picks, notes, your Avoid list); it also carries your districts but never your address. It travels in the link itself, so the server never sees it, though anyone given the link can; the dialog warns of that. Links and files are locked with a phrase unless you untick it, and the phrase never leaves the browser. Opening one shows what it holds before anything changes.
- On a phone, the left pane becomes a top bar, and the ballot's buttons are under **More**.

Your picks, notes, write-ins, Help me pick choices, the people you avoid and your settings are kept in your browser's `localStorage`, never on the server, even when you share them.

## Where the data comes from

| Source | Used for | Notes |
|---|---|---|
| US Census geocoder | address → state, county, U.S. House, State Senate and State House districts, anywhere in the US; for a Texas voter card with a precinct, the same at points inside it | already on the 2026 maps (120th Congress, 2026 legislative districts). A voter card sends only those points, never an address. When its districts lookup is down, the point comes from its plain address lookup and the districts from TIGERweb |
| OpenStreetMap Nominatim | fallback when the Census can't match an address | results flagged as approximate unless they hit a building |
| Google Geocoding API | last fallback, when neither the Census nor Nominatim can match an address (new streets, mostly) | needs `PALLOT_GOOGLE_API_KEY`; without one it's never asked; results flagged as approximate unless they hit a building |
| Google Places Autocomplete | address suggestions while typing, anywhere in the US | needs `PALLOT_GOOGLE_API_KEY` with the Places API (New) enabled; without one, nothing is suggested. Held to `PALLOT_SUGGEST_DAILY_MAX` a day; it has its own switch in Settings |
| Texas Legislative Council map (PLANE2106) | State Board of Education district, and its outline on the map | comes with Pallot (see [Bundled snapshots](#bundled-snapshots)), so lookups never download it. Nothing about you is sent |
| Texas Legislative Council precinct map (data.capitol.texas.gov, the `precincts` maps) | your election precinct, and its outline on the map; for a voter card, the points inside your precinct that the Census is asked about | the portal's list of maps is asked once a week; the newest map, a primary's or a general's (now the 2026 primary's, about 45 MB), is downloaded on the first lookup and again only when a newer one is listed. Nothing about you is sent |
| County map servers: Harris, Dallas, Tarrant, Travis, Fort Bend, Bexar and Denton | your commissioner and JP precincts, from your election precinct | each county's list of its election precincts, or its maps of its commissioner and JP precincts, found by name (the newest year, never a proposal), bundled with Pallot (see [Bundled snapshots](#bundled-snapshots)); once the bundled copy is two weeks old, downloaded whole, at most once a week, when you look up an address there. Nothing about you is sent |
| US Census TIGERweb | the outlines of your U.S. House, State Senate and State House districts, for the map; your districts at a point when the geocoder can't give them; in Missouri, your U.S. House district on its 2022 map, in force for 2026, where the geocoder has the 2025 one | every Texas district's outline, bundled with Pallot (see [Bundled snapshots](#bundled-snapshots)); once the bundled copy is 37 days old, and in other states, one request per district, with its state and number (or name) and never your address; in Missouri, one request with the point the geocoder found for your address |
| OpenStreetMap tiles (tile.openstreetmap.org) | the street map around your address | through the Pallot server, only the tiles of the area you look at, following OpenStreetMap's [tile usage policy](https://operations.osmfoundation.org/policies/tiles/); drawn with [Leaflet](https://leafletjs.com), which comes with Pallot |
| Texas Secretary of State | Texas's official ballot order per county, candidate filings | the public API behind goelect.txelections.civixapps.com |
| Other states' election offices: Alaska's, California's, Colorado's, Delaware's, the District of Columbia's, Florida's, Hawaii's, Illinois's, Indiana's, Kansas's, Kentucky's, Maine's, Maryland's, Michigan's, Minnesota's, Mississippi's, Missouri's, Montana's, Nebraska's, New Jersey's, New Mexico's, North Carolina's, North Dakota's, Oklahoma's, Pennsylvania's, South Carolina's, South Dakota's, Vermont's, Virginia's, Washington's and Wyoming's | the candidates each state lists for its November ballot, with withdrawn and disqualified candidates left out | each state's public candidate list (a spreadsheet, a PDF or a web page), the same for everyone, bundled with Pallot as just the candidates (see [Bundled snapshots](#bundled-snapshots)); once the bundled copy is two days old, downloaded whole again, as just the candidates: their addresses, phones and emails are never kept. Nothing about you is sent. Each has its own switch in Settings |
| Election offices whose sites turn programs away or have no file to download: Arizona's, Arkansas's, Georgia's, Idaho's, Iowa's, Louisiana's, Massachusetts's, Nevada's, New Hampshire's, New York's, Ohio's, Oregon's, Tennessee's, Utah's, West Virginia's and Wisconsin's | the same | saved by hand from the office's site and imported (`pallot-bundle import-list`, see [Bundled snapshots](#bundled-snapshots)); never fetched. Georgia's party nominees come from its election results site (results.sos.ga.gov): each primary's and runoff's results, the same for everyone, bundled and downloaded again once two days old |
| Texas Secretary of State, Important Election Dates | each election's last day to register, early voting and mail-ballot deadline | one public web page (sos.state.tx.us), read whole |
| California Secretary of State, Election Dates and Resources | the last day to register and to ask for a replacement mail ballot | one public web page (sos.ca.gov), read whole. Other states' key dates are worked out from Election Day by their election law, with nothing fetched |
| [Wikidata](https://www.wikidata.org) | profiles of candidates who hold or held an office in their state: a photo, a description, birth date, party, the offices they've held there, and stable links to their Wikidata item, Wikipedia article and campaign and government websites | Wikidata's public query service (CC0, no key). The list of every living Texas officeholder comes with Pallot (see [Bundled snapshots](#bundled-snapshots)); another state's is asked for once a week. The matched candidates' details are asked once per ballot, by their Wikidata ids. Nothing about you is sent but your state. Photos load from Wikimedia Commons |
| TrackAIPAC | pro-Israel lobby money and endorsements for congressional candidates | bundled with Pallot (see [Bundled snapshots](#bundled-snapshots)) |
| Vote for Peace (voteforpeace.info, from Organize for Peace) | whether it calls a candidate an Ally, Neutral or Opposed, on war, human rights and lobby money, with the groups it cites and its notes; every level, from Congress to county courts and city councils | bundled with Pallot, used with Organize for Peace's permission (see [Bundled snapshots](#bundled-snapshots)); starts on, turn it off in Settings |
| Endorsement lists (one file per organization, in `pallot/endorsements/`) | the candidates an organization endorses, with its note and the office as it lists it | each a copy made once, frozen, part of Pallot and never fetched. About and the FAQ name the lists in your version |
| Live endorsement lists: Muslims United PAC (muslimsunitedpac.com) | the candidates it endorses, with its take on each and a link to their page on its site | the site's public JSON list of its endorsements, the whole list in one request, the same for everyone; it comes with Pallot, with its permission (see [Bundled snapshots](#bundled-snapshots)), and is downloaded again once the bundled copy is two days old |
| Live endorsement lists: CAIR Action (cairactionguide.org) | the candidates its Action Guide endorses or prefers, with that level in its words and a link to its list for the state | the site's public JSON list of its endorsements, the whole list in one request, the same for everyone; it comes with Pallot, with its permission (see [Bundled snapshots](#bundled-snapshots)), and is downloaded again once the bundled copy is two days old |
| Live endorsement lists: Emgage PAC (candidates.emgagepac.org) | the candidates it endorses, with its note on each when it has one, and a link to its list | the JSON list behind its donation page, the whole list in one request, the same for everyone; that request needs a token the page hands out, so the page is fetched first, and only when the list is. The list comes with Pallot, with its permission (see [Bundled snapshots](#bundled-snapshots)), and is downloaded again once the bundled copy is two days old; the token is never kept |
| FEC (Federal Election Commission) | money raised and spent by congressional campaigns, where it came from, and outside spending for or against them; in a state with no list above, the candidates for Congress themselves | the OpenFEC API, with every state's lists of who filed for each seat, and the breakdowns for Texas's candidates, bundled with Pallot (see [Bundled snapshots](#bundled-snapshots)). Without your own key, race totals only (see [The FEC key](#the-fec-key-optional)) |
| Texas Ethics Commission | the same for state candidates and officeholders, plus their largest donors | bundled with Pallot, built from TEC's nightly CSV export (see [Bundled snapshots](#bundled-snapshots)) |
| FiftyPlusOne (fiftyplusone.news) | public polls of U.S. Senate, U.S. House and Governor races | the site's own JSON API; its lists come with Pallot, with its permission (see [Bundled snapshots](#bundled-snapshots)), and are downloaded again once the bundled copy is two days old |
| Seat holders: the [congress-legislators](https://github.com/unitedstates/congress-legislators) project and [Open States](https://openstates.org) | who holds each U.S. Senate, U.S. House, State Senate and State House seat now, and their party: Open seat, Party holds seat, and Incumbent where the filing doesn't say | two public files (public domain and CC0), bundled with Pallot (see [Bundled snapshots](#bundled-snapshots)); once the bundled copy is two weeks old, each is downloaded whole at most once a week, and only when the ballot has a race of that body. Nothing about you is sent. Statewide offices, the SBOE, courts and local races aren't covered |
| [Congress.gov](https://www.congress.gov) (the Library of Congress) | the newest bills a member of Congress running for their own seat sponsored and cosponsored, with how many in all, in their **In Congress** tab | the Congress.gov API (public domain), with your FEC key, which api.data.gov issues for both. Two requests per member, asked when a lookup needs them, by the member's id from the seat holders' list; kept a day, then deleted. Needs Seat holders on. Votes aren't shown: the API lists House votes one roll call at a time and has no Senate votes |

In Texas, commissioner, JP and constable races depend on your commissioner and JP precincts. These come from the numbers you enter, then your county's records (in the seven counties above). When neither gives a number, those races are left out with a note. A race with only write-ins is shown when Pallot can place it. When Texas SOS has no ballot for the county (a special election), Pallot uses its statewide candidate list and shows only federal, statewide, congressional, legislative and SBOE races, with a note.

A Texas election precinct comes from the newest precinct map, a primary's or a general's. When your address and the middle of its census block fall in different precincts, Pallot names both and picks neither. Your voter registration certificate wins.

Campaign money covers congressional races in every state (FEC), and Texas's state races (TEC): statewide offices, the Legislature, the SBOE, appellate and district courts and district attorneys. Other states' state candidates, and county, precinct, city and school candidates, file elsewhere, so their races show none yet.

In a state with only its races for Congress, the candidates are the people who filed with the FEC for the seat and raised $5,000 or more. The FEC doesn't say who is on the November ballot, so a primary loser or someone who dropped out may be listed, and a small campaign may be missing. Each such candidate is marked **Unverified**: check your state's official candidate list. The FAQ goes through how every figure is worked out.

Candidates are matched across sources by name, with seat and party as corroboration. Every match is labeled **exact** or **likely**, and ambiguous ones are left unmatched.

## Caching

Pallot saves every answer it gets in `data/`, so looking up the same address (or the same voter card's precinct) again makes **zero** external calls, even after a restart. The server's log has one line per lookup with how many requests it sent (`lookup: 0 external calls, 41 cache hits, 180 ms`), with no address, and `pallot-cache check` shows what the server keeps for each source.

- Each source's answers have a lifetime: from a day (ballot data, polls, key dates) to 30 days (geocodes, district outlines). OpenStreetMap's tiles are kept at least 7 days, as its policy asks. `.env.example` lists every lifetime, each overridable with `PALLOT_TTL_<NAME>` in seconds.
- Once an answer is past its lifetime, the next lookup asks again. If that fails, the old copy is shown with a "data as of" note, and the request isn't retried for 15 minutes. An error a source sends as if it were an answer counts as a failure too, so it never replaces a good copy.
- If a source refuses a request, Pallot stops asking it for an hour (2 minutes for an FEC key at its rate limit, while your other keys carry on). What it already has still shows.
- When a source fails, the ballot names it and says what still works. Why it failed goes to the server's log, never to the page.
- The snapshots that come with Pallot (see [Bundled snapshots](#bundled-snapshots)) mean lookups never contact TrackAIPAC, Vote for Peace or the Texas Ethics Commission, and ask the other bundled sources only once the bundled copy is a few days old.
- Congress.gov's answers are kept a day, then deleted at the next prune: they're asked live when a lookup needs them, never refreshed ahead.
- Address suggestions, street map tiles and addresses that weren't found are deleted once they've been expired for 30 days. Tiles and suggestions are kept under 512 MB and 64 MB, and each address lookup's answers (the Census's, OpenStreetMap's and Google's) under 128 MB, the oldest going first. Everything else stays as the copy to show when a source is down.
- `pallot-cache` asks the FEC more slowly than a lookup does, leaving room for a running Pallot, and doesn't ask a paused source.

## Settings

The **Settings** page has **Ballot view**, **Web search**, **People you avoid**, **Sources**, **Appearance** and **Your data**. Everything you choose there is saved in your browser, so it changes only what you see, not anyone else using the same Pallot.

- **Sources** lists every source in groups, with a switch for each (except the address lookup), a line on what it holds and how old it is, and a warning when it's paused or can't be used. Your switches travel with each request, so the server builds your ballot with them. A source you haven't switched follows the defaults (see [Which sources start on](#which-sources-start-on)).
- **Your data** saves your session as a Pallot file or opens one, and clears your picks and notes, or everything Pallot keeps in this browser, each with **Undo**.

Settings can't refresh or clear what the server saved: anyone who opens Pallot can open Settings, and it has no login. That's for whoever runs Pallot, on the machine it runs on: see [Keeping the cache](#keeping-the-cache).

Vote for Peace starts on, adding its Allies and Opposed. A ballot needs its source on: a Texas ballot comes from Texas SOS, a covered state's from its election office's list, and anywhere else from the FEC. With a state's list off, its ballot falls back to the FEC's races for Congress.

### Which sources start on

`pallot/sources.toml` declares which sources are on for someone who hasn't switched them, under `[sources]`, one `id = true` or `false` each (the ids `pallot-cache check` shows in brackets). Every endorsement list starts on. To change the defaults for everyone using your Pallot, don't edit that file: put a `sources.toml` in the data folder (`data/`, or `PALLOT_DATA_DIR`), listing only what you change, and restart Pallot. For example, to share Pallot with others without Google's address lookups, which Google bills by the request:

```toml
[sources]
google = false
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
- **rebuild** deletes every saved response, pause and map, then fetches them all again, as hard-refresh does. The snapshots aren't deleted, only refreshed; `--reset-snapshots` puts them back as they came with Pallot first. `--delete-only` deletes and fetches nothing again: the next lookups fetch what they need, which is how to erase the addresses Pallot saved (`--only geocoding suggestions`). It asks first, unless you add `--yes`.
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
- the FEC's list of who filed for every other U.S. House and U.S. Senate seat up this cycle, in the 50 states and DC, with their totals, so a ballot anywhere shows its races for Congress without asking the FEC. A candidate's breakdowns are asked for the first time someone looks up their seat;
- the official candidate lists of the 46 states and DC Pallot reads (see [Where it covers](#where-it-covers)) for the next November election, as just each candidate's name, party and race (the states' files also carry candidates' addresses and phone numbers, which aren't kept), and Georgia's primary and runoff results, for its party nominees;
- Texas SOS's statewide data: the elections of this year and next, its tables of counties, parties and filing statuses, and each upcoming election's statewide list of candidates (about 2.6 MB);
- Texas SOS's ballot order for every county in each upcoming election (about 10 MB). A county whose ballot order isn't published yet is left out, so a lookup there still asks Texas SOS for it, and asks again after 6 hours while it's empty;
- the seat holders' two lists, the congress-legislators project's current members of Congress (public domain) and Open States' legislators of Texas and of each state whose list Pallot reads (CC0);
- Wikidata's list of every living person who holds or held a Texas office, with the offices (CC0), about 750 KB. The matched candidates' details aren't in it, so a ballot's first lookup asks for them;
- TIGERweb's outlines of every Texas U.S. House, State Senate and State House district (public domain), about 2.7 MB;
- the seven counties' records of their commissioner and JP precincts: Harris's, Dallas's, Tarrant's, Travis's and Fort Bend's lists of their election precincts, and Bexar's and Denton's maps, about 1.9 MB;
- FiftyPlusOne's nationwide lists of polls of U.S. Senate, U.S. House and Governor races, used with FiftyPlusOne's permission, about 2.2 MB;
- the live endorsement lists of Muslims United PAC, CAIR Action and Emgage PAC, each used with its organization's permission: about 37 KB, 1.3 MB and 36 KB. Emgage's token is never kept, in the bundle or the cache.

At startup, Pallot puts them in its cache, dated when they were last checked, unless the cache has a newer copy. So a lookup asks a source only for what the bundle doesn't have, or once the bundle's answer is older than its bundle lifetime: the FEC's 7 days (`PALLOT_TTL_FEC_BUNDLE`, and `PALLOT_TTL_FEC_RACES_BUNDLE` for the other states' lists); the states' candidate lists 2 days (`PALLOT_TTL_STATE_LIST_BUNDLE`), and a year for a list imported by hand, which is never fetched (`PALLOT_TTL_STATE_LIST_IMPORTED`); Texas SOS's elections 3 days, tables 30 days, candidate lists and ballot orders 2 days (`PALLOT_TTL_SOS_ELECTIONS_BUNDLE`, `PALLOT_TTL_SOS_REFERENCE_BUNDLE`, `PALLOT_TTL_SOS_CANDIDATES_BUNDLE`, `PALLOT_TTL_SOS_BALLOT_ORDER_BUNDLE`); the seat holders' 14 days (`PALLOT_TTL_OFFICEHOLDERS_BUNDLE`); Wikidata's 14 days (`PALLOT_TTL_WIKIDATA_BUNDLE`); the district outlines 37 days (`PALLOT_TTL_TIGERWEB_BUNDLE`); the counties' records 14 days (`PALLOT_TTL_COUNTY_PRECINCTS_BUNDLE`); the polls 2 days (`PALLOT_TTL_POLLS_BUNDLE`); the endorsement lists 2 days (`PALLOT_TTL_ENDORSEMENT_FEEDS_BUNDLE`). After that, the live answer is kept for the source's usual lifetime. This matters most on a host whose `data/` starts empty at each restart. `pallot-cache check` says how many answers came with Pallot for each source, and when they were checked.
- `uv run pallot-bundle refresh` rebuilds every bundle in the repo; `--only fec` (or `fec_races`, a state's list by its id in `pallot/sources.toml` such as `state_mi`, `state_ga_results`, `sos`, `sos_ballot_order`, `officeholders`, `wikidata`, `tigerweb`, `county_precincts`, `polls`, `mupac`, `cair`, `emgage`) limits it to the FEC's. `--due` skips a bundle checked more recently than it's worth (daily or weekly; the FEC's, the states' lists, Texas SOS's, the polls and the endorsement lists are daily, the seat holders', Wikidata's, the outlines and the counties' weekly), `--dry-run` says what would change, and `--force` writes even if nothing changed. A list imported by hand is skipped: it's never fetched.
- `uv run pallot-bundle import-list <state> <file>` imports a list saved by hand from a site that turns programs away or has no file to download (Arizona's, Arkansas's, Georgia's, Idaho's, Iowa's, Louisiana's, Massachusetts's, Nevada's, New Hampshire's, New York's, Ohio's, Oregon's, Tennessee's, Utah's, West Virginia's and Wisconsin's). Tennessee's is saved as five spreadsheets, so its import takes their folder (`manual/state_tn`). Each state's folder in `manual/` has its README with the steps to save it. The import refuses a file it can't read, or one for another election, and keeps only the candidates, never their addresses, phones or emails.
- Until 15 November 2026, a GitHub Action refreshes every snapshot in the repo each day (`pallot-bundle refresh --due`, then TrackAIPAC, Vote for Peace and TEC), updates [What the snapshots hold](#what-the-snapshots-hold), and commits the changes to the `chore/refresh-caches` branch, which the maintainer merges into `develop`, so a fresh deploy comes with answers only a few days old (see DEVELOPMENT.md's "The daily refresh").

Pallot also comes with the Texas Legislative Council's State Board of Education map (plan E2106, about 1.9 MB, `pallot/data/plane2106_kml.zip`). At startup, Pallot copies it into `data/` when no map is kept, so lookups never download it. The plan stays until the next redistricting, so the map has no lifetime. Settings says whether the map kept came with Pallot or was downloaded, and when.
- `pallot-cache hard-refresh --only geocoding` downloads it again from the portal, in case a newer plan is published there. A rebuild puts back the map that came with Pallot before downloading it again.

### What the snapshots hold

Each daily run rewrites this table (`uv run pallot-bundle stats --since HEAD --readme README.md`), so you can see whether a source is still adding candidates. A change in brackets is since the run before. **Data changed** is when the source's answers last changed, and **Checked** when it was last asked; a check later than the source's cadence (daily or weekly) is marked overdue, which usually means its refresh failed. The same table is on each run's summary page in Actions.

<!-- source-stats:start -->
| Source | Candidates | Also | Data changed | Checked |
|---|---|---|---|---|
| FEC | **93** | 39 races | 2026-10-30 | 2026-10-31 |
| FEC race lists, other states | — | 431 races · 50 states | 2026-10-31 | 2026-10-31 |
| Texas SOS candidate lists | **3,971** · 2026 November General Election: 3,967 · 2026 Special Election House District 93: 2 · 2026 Special Election Senate District 22: 2 | 3 elections | 2026-10-31 | 2026-10-31 |
| Texas SOS ballot orders | — | 254 county ballot orders · 3 elections | 2026-10-31 | 2026-10-31 |
| Seat holders | — | 539 members of Congress · 2,292 state legislators | 2026-10-25 | 2026-10-25 |
| Wikidata | — | 662 Texas officeholders · 653 with their seat | 2026-10-27 | 2026-10-27 |
| TIGERweb district outlines | — | 38 U.S. House · 31 State Senate · 150 State House | 2026-10-08 | 2026-10-26 |
| County precinct records | — | 7 counties | 2026-10-26 | 2026-10-26 |
| FiftyPlusOne polls | — | 615 Senate polls (+12) · 373 House polls · 655 Governor polls (+14) | 2026-10-31 | 2026-10-31 |
| Muslims United PAC | **26** · Texas: 3 | — | 2026-10-08 | 2026-10-31 |
| CAIR Action | **1,450** (+83) · Texas: 390 | — | 2026-10-31 | 2026-10-31 |
| Emgage PAC | **39** · Texas: 3 | — | 2026-10-08 | 2026-10-31 |
| NC State Board of Elections candidate list | **2,484** | 1,324 races | 2026-10-26 | 2026-10-31 |
| Michigan Bureau of Elections candidate list | **707** | 331 races | 2026-10-28 | 2026-10-31 |
| Pennsylvania Department of State candidate list | **436** | 247 races | 2026-10-26 | 2026-10-31 |
| Florida Division of Elections candidate list | **367** | 168 races | 2026-10-30 | 2026-10-31 |
| Virginia Department of Elections candidate list | **40** | 13 races | 2026-10-29 | 2026-10-31 |
| California Secretary of State candidate list | **388** | 228 races | 2026-10-26 | 2026-10-31 |
| Arizona Secretary of State candidate list | **232** | 91 races | 2026-10-26 | 2026-10-26 |
| Nevada Secretary of State candidate list | **633** | 364 races | 2026-10-22 | 2026-10-22 |
| Georgia Secretary of State candidate list | **292** | 184 races | 2026-10-26 | 2026-10-26 |
| Georgia Secretary of State party nominees | **451** | 271 races | 2026-10-31 | 2026-10-31 |
| Wisconsin Elections Commission candidate list | **445** | 293 races | 2026-10-26 | 2026-10-26 |
| Ohio Secretary of State candidate list | **20** | 8 races | 2026-10-26 | 2026-10-26 |
| Iowa Secretary of State candidate list | **245** | 137 races | 2026-10-26 | 2026-10-26 |
| New Jersey Division of Elections candidate list | **39** | 13 races | 2026-10-29 | 2026-10-31 |
| New York State Board of Elections candidate list | **502** | 253 races | 2026-10-26 | 2026-10-26 |
| Colorado Secretary of State candidate list | **397** | 236 races | 2026-10-26 | 2026-10-31 |
| Wyoming Secretary of State candidate list | **151** | 107 races | 2026-10-26 | 2026-10-31 |
| Illinois State Board of Elections candidate list | **501** | 391 races | 2026-10-26 | 2026-10-31 |
| Alaska Division of Elections candidate list | **156** | 74 races | 2026-10-27 | 2026-10-31 |
| Maine Secretary of State candidate list | **362** | 190 races | 2026-10-29 | 2026-10-31 |
| Nebraska Secretary of State candidate list | **81** | 38 races | 2026-10-29 | 2026-10-31 |
| New Mexico Secretary of State candidate list | **129** | 85 races | 2026-10-29 | 2026-10-31 |
| Washington Secretary of State candidate list | **269** | 149 races | 2026-10-29 | 2026-10-31 |
| Indiana Election Division candidate list | **1,696** | 1,239 races | 2026-10-29 | 2026-10-31 |
| Maryland State Board of Elections candidate list | **323** | 131 races | 2026-10-29 | 2026-10-31 |
| Missouri Secretary of State candidate list | **425** | 248 races | 2026-10-29 | 2026-10-31 |
| South Carolina State Election Commission candidate list | **415** | 257 races | 2026-10-29 | 2026-10-31 |
| Kentucky Secretary of State candidate list | **348** | 251 races | 2026-10-29 | 2026-10-31 |
| Oklahoma State Election Board candidate list | **261** | 123 races | 2026-10-29 | 2026-10-31 |
| Kansas Secretary of State candidate list | **362** | 247 races | 2026-10-29 | 2026-10-29 ⚠ overdue (daily) |
| Montana Secretary of State candidate list | **256** | 131 races | 2026-10-29 | 2026-10-31 |
| South Dakota Secretary of State candidate list | **178** | 81 races | 2026-10-29 | 2026-10-31 |
| Hawaii Office of Elections candidate list | **94** | 43 races | 2026-10-29 | 2026-10-31 |
| North Dakota Secretary of State candidate list | **141** | 57 races | 2026-10-29 | 2026-10-31 |
| Delaware Department of Elections candidate list | **130** | 77 races | 2026-10-29 | 2026-10-31 |
| Vermont Secretary of State candidate list | **422** | 202 races | 2026-10-30 | 2026-10-31 |
| Mississippi Secretary of State candidate list | **39** | 14 races | 2026-10-30 | 2026-10-31 |
| Arkansas Secretary of State candidate list | **190** | 131 races | 2026-10-30 | 2026-10-30 |
| Minnesota Secretary of State candidate list | **420** | 214 races | 2026-10-30 | 2026-10-31 |
| New Hampshire Secretary of State candidate list | **769** | 231 races | 2026-10-30 | 2026-10-30 |
| Tennessee Secretary of State candidate list | **266** | 126 races | 2026-10-30 | 2026-10-30 |
| Massachusetts Secretary of the Commonwealth candidate list | **293** | 215 races | 2026-10-30 | 2026-10-30 |
| Louisiana Secretary of State candidate list | **44** | 8 races | 2026-10-30 | 2026-10-30 |
| Oregon Secretary of State candidate list | **167** | 83 races | 2026-10-30 | 2026-10-30 |
| Utah Lieutenant Governor's Office candidate list | **241** | 126 races | 2026-10-30 | 2026-10-30 |
| West Virginia Secretary of State candidate list | **244** | 122 races | 2026-10-30 | 2026-10-30 |
| Idaho Secretary of State candidate list | **231** | 115 races | 2026-10-30 | 2026-10-30 |
| DC Board of Elections candidate list | **18** | 7 races | 2026-10-30 | 2026-10-30 |
| TrackAIPAC | **659** (+3) · Texas: 61 · House: 541 (+2) · Other: 2 (+1) · Senate: 116 | — | 2026-10-31 | 2026-10-31 |
| Vote for Peace | **1,429** · Texas: 193 · State legislature: 501 · Federal: 276 · County: 268 · Local: 178 · Statewide: 95 · State: 89 · Special district: 14 · Judicial: 8 | — | 2026-10-28 | 2026-10-28 ⚠ overdue (daily) |
| Texas Ethics Commission | **2,154** | 1,082,913 contributions (+2) · 8,796 reports (+2) | 2026-10-31 | 2026-10-31 |
<!-- source-stats:end -->

## Configuration

Set these as environment variables, for example `PALLOT_DATA_DIR=/var/lib/pallot uv run pallot`, or in a `.env` file in the project folder: `cp .env.example .env` and fill it in. Pallot reads `.env` at startup, and git ignores it. Variables already set in the environment win over `.env`. Docker Compose reads the same `.env` and passes it to the container, where `PALLOT_DATA_DIR` is always `/data`: the folder it names on the host is mounted there.

| Variable | Default |
|---|---|
| `PALLOT_DATA_DIR` | `data/` in the project (cache, SBOE and precinct maps, TrackAIPAC, Vote for Peace and TEC data, and your `sources.toml` if you add one; git-ignored) |
| `PALLOT_FEC_API_KEY`, `PALLOT_FEC_API_KEY2` to `PALLOT_FEC_API_KEY5` | `DEMO_KEY`, which only allows race totals and runs out after a few requests. Get a free key from the [OpenFEC developers page](https://api.open.fec.gov/developers/). The extra keys are optional: Pallot uses all of them in turn, and skips one the FEC has rate limited or refused. They are only sent to the FEC and to Congress.gov (api.data.gov issues the keys for both), in a header, and Pallot never writes them anywhere (a resting key is noted by a short hash of it) |
| `PALLOT_GOOGLE_API_KEY` | none, so Google is never asked and Settings leaves it out. A [Google Geocoding API key](https://developers.google.com/maps/documentation/geocoding/get-api-key), to find addresses the Census and OpenStreetMap can't. It's only sent to Google, in a header, and Pallot never writes it anywhere. The same key suggests addresses as voters type, with the Places API (New) enabled for it. Google bills by the request, though Pallot asks only for an address both others missed, and keeps each answer for 30 days |
| `PALLOT_USER_AGENT` | `Pallot/0.1 (personal ballot helper; +https://github.com/Just-Peace/Pallot)`. Nominatim and OpenStreetMap's tile server require one that names the app and how to reach whoever runs it; add your email if you like |
| `PALLOT_HTTP_TIMEOUT` | `30` seconds |
| `PALLOT_ALLOWED_HOSTS` | none: Pallot answers to `localhost` and IP addresses only. List any other names you open it by, comma-separated (for example `nas.local`, or a reverse proxy's domain), or `*` for any. Other names get an error, which protects Settings from DNS rebinding; the log names the one refused |
| `PALLOT_TTL_*` | cache lifetimes, in seconds: `.env.example` lists each one with its default, including how long a source is left alone after refusing a request and how long the answers that came with Pallot are used (see [Caching](#caching) and [Bundled snapshots](#bundled-snapshots)). `PALLOT_TTL_TILES` can't go under 7 days, as OpenStreetMap asks |
| `PALLOT_TILES_MAX_MB` | `512`: the most the street map's tiles take in the cache; past it, the oldest are deleted when Pallot prunes |
| `PALLOT_SUGGEST_MAX_MB` | `64`: the same for the address suggestions |
| `PALLOT_ADDRESSES_MAX_MB` | `128`: the same for each address lookup's answers: the Census's, OpenStreetMap's and Google's, each up to this much |
| `PALLOT_CACHE_MEMORY_MB` | `64`: the most the cache's answers take in memory. Past it, the least recently used are read from disk again when asked, which is slower. Pallot takes about 110 MB besides. A cap well under what one lookup reads saves nothing, since each lookup then reads its answers again |
| `PALLOT_GOOGLE_DAILY_MAX` | `300`: the most Google is asked in a day (UTC), about 9,000 a month. Past it, Google is paused until midnight UTC, and Settings says so. `0` for no limit |
| `PALLOT_SUGGEST_DAILY_MAX` | `1000`: the same for address suggestions, which ask Google once per new text typed (about 30,000 a month). Past it, suggestions stop until midnight UTC. `0` for no limit |
| `PALLOT_LIMIT_BALLOT`, `PALLOT_LIMIT_SUGGEST`, `PALLOT_LIMIT_OUTLINES`, `PALLOT_LIMIT_TILES` | `30/hour`, `600/hour`, `60/hour`, `2000/hour`: how often one internet address may look up a ballot, get address suggestions, the district map's outlines, and street map tiles. A count over a period, such as `10/min` or `500/10min`; `off` for no limit. Past it, Pallot answers "Too many requests" with how long to wait. Pallot's own machine (`127.0.0.1`) is never limited (see [Running it publicly](#running-it-publicly)) |
| `PALLOT_MAX_LOOKUPS` | `8`: how many ballots Pallot looks up at once, counting those still adding money, polls and endorsements after the voter left. Past it, a lookup is asked to try again in a few seconds |
| `PALLOT_TRUSTED_PROXIES` | `127.0.0.1`: the reverse proxies whose `X-Forwarded-For` header says who the visitor is, comma-separated IP addresses or networks (`10.0.0.0/8`), or `*` for any. The limits count each visitor by that address (see [Running it publicly](#running-it-publicly)) |
| `PALLOT_PRUNE_EVERY` | `21600` seconds (6 hours): how often a running Pallot prunes the street map's tiles and the address suggestions |
| `PALLOT_PORT` | `8000`: the port `uv run pallot` listens on (`--port` wins), and in Docker the port published on the host |
| `PALLOT_DEFAULT_ENTRY` | `address`: the entry card's tab on a first visit. `voter_card` starts on the **Voter card** tab (state, county and districts) instead; a voter's last lookup still picks its own tab |

A value Pallot can't read, such as a port that isn't a whole number or a limit that isn't a rate, stops `pallot` and `pallot-cache` from starting, with one line naming the variable and its value.

### Docker

- `compose.yaml` mounts `data/` (or the folder `PALLOT_DATA_DIR` names) at `/data`, so Docker and `uv run pallot` share the cache, `sources.toml`, TrackAIPAC, Vote for Peace and TEC data, and nothing is fetched twice. Don't run both at once, because they'd share one SQLite file.
- It's published on every network interface. To keep it to this machine, change the `ports` line in `compose.yaml` to `"127.0.0.1:8000:8000"`. `PALLOT_PORT` in `.env` changes the port.
- To open it by a name rather than an address (`http://nas.local:8000`, or through a reverse proxy), add the name to `PALLOT_ALLOWED_HOSTS` in `.env`. A reverse proxy must pass the original `Host` header on.
- Pallot's API answers only Pallot's own pages in a browser. Another website, or a script such as `curl`, gets an error.
- The container runs as user and group 1000, which must be able to write `data/`. That's why the quick start creates it: otherwise Docker creates it owned by root. If your ids differ (`id -u`, `id -g`), set `PALLOT_UID` and `PALLOT_GID` in `.env`.
- `.env` is passed in when the container starts, never built into the image.
- The image sets `MALLOC_ARENA_MAX=2`, which keeps Pallot's memory use about 20 MB lower without slowing lookups. Set it yourself when running `uv run pallot` on Linux to get the same.

### Running it publicly

Pallot has no login, so anyone who can reach it can look up ballots, and each new address makes Pallot ask the sources, with your FEC and Google keys. These settings keep one visitor from running up your Google bill, using up your FEC keys, or getting a source to refuse everyone:

- **The rate limits** (`PALLOT_LIMIT_BALLOT` and the rest) count each internet address. The defaults leave room for a household, and a script stops at a few dozen lookups an hour.
- **Behind a reverse proxy**, every request comes from the proxy, so set `PALLOT_TRUSTED_PROXIES` to its address, or the limits count all your visitors as one. On a host that's only reached through its own proxy (Render, Fly.io), `*` is fine. Anywhere else, never use `*`: a visitor could then claim any address and dodge the limits.
- A proxy on the same machine can stay at the default, `127.0.0.1`. Without one, a visitor on `127.0.0.1` is someone on the machine itself, and isn't limited.
- **`PALLOT_GOOGLE_DAILY_MAX`** and **`PALLOT_SUGGEST_DAILY_MAX`** cap what Google can cost in a day, and **`PALLOT_MAX_LOOKUPS`** how many lookups run at once.
- **`PALLOT_ALLOWED_HOSTS`** must list the name visitors open Pallot by.

## Not built yet

Known bugs, planned improvements and features, and UI ideas are [GitHub issues](https://github.com/Just-Peace/Pallot/issues).

## Working on Pallot

The commands, the tests, and adding a source: [DEVELOPMENT.md](DEVELOPMENT.md). The rules for a change: [AGENTS.md](AGENTS.md).

## License

Pallot's code is under the [MIT License](LICENSE).

The data that comes with it isn't: each source's data belongs to that source, under its own terms. That covers the snapshots (`trackaipac_cache/data/`, `voteforpeace_cache/data/`, `tec_cache/data/`, `bundles/data/`), the SBOE map (`pallot/data/`) and the endorsement lists (`pallot/endorsements/`). [Leaflet](https://leafletjs.com), in `pallot/static/vendor/leaflet/`, keeps its own BSD 2-Clause license.
