# Developing VoteBot

How VoteBot works inside, and how to test and change it. To run it, see the [README's quick start](README.md#quick-start).

VoteBot is one Python process (FastAPI) serving a plain HTML/JS page from `votebot/static/`. There's no frontend build step and no database server: everything it keeps is files in `data/`.

## Commands

`uv sync` installs VoteBot with the dev tools (pytest, respx), pinned by `uv.lock`.

```bash
uv run votebot --reload                    # restart on code changes
uv run pytest                              # offline: recorded responses in tests/fixtures, plus trackaipac_cache's and tec_cache's own tests
uv run pytest -m live                      # smoke tests against the real services (the FEC one needs an FEC key)
uv run python scripts/record_fixtures.py   # re-record tests/fixtures from the live APIs (--only ballots|fec|polls|tec|trackaipac)
```

Keep the default `127.0.0.1` binding (there is a `--host` option, but don't change it), because the Settings actions have no login. The Docker image is the one exception: it binds `0.0.0.0` inside the container, and `compose.yaml` decides where that's published.

The live tests and `record_fixtures.py` call the real services. With `DEMO_KEY`, the FEC's rate limit is shared by everything on your IP address, VoteBot itself included.

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
Dockerfile          the container image; compose.yaml runs it
```

## Caching

Every outbound call goes through `votebot/http_cache.py`, a SQLite cache in `data/cache.sqlite3`. Each `/api/ballot` response reports `meta.external_calls`, and Settings shows the last lookup's, source by source.

- Concurrent identical requests share one fetch.
- Only answers that succeed are cached.
- The lifetimes are `Ttls` in `votebot/config.py`, each overridable with `VOTEBOT_TTL_<NAME>`.

## Sources

Notes on how each source is called, beyond the README's table:
- **Photon:** Nominatim's policy forbids search-as-you-type, hence Photon for suggestions. Only results on a street matching what was typed are kept; without the house in OpenStreetMap, the typed number goes on the street.
- **SBOE districts:** point-in-polygon in pure Python over the PLANE2106 map, downloaded once into `data/`.
- **Ballotpedia:** an unofficial endpoint that needs Ballotpedia's own origin header.
- **FiftyPlusOne:** the site's own JSON API: nationwide lists, 500 polls to a page, filtered to Texas on the server. It answers 403 unless the request looks like a browser's.
- **State-specific text** (the official elections site, the print sheet's voting rules) comes from `STATES` in `votebot/static/js/labels.js`, keyed by the address's state, so adding a state doesn't mean rewriting pages.

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
- Because the install isn't editable, the static files and the bundled snapshots reach the image only as package data (`[tool.setuptools.package-data]` in `pyproject.toml`). A new kind of file, such as an image under `votebot/static/`, needs a pattern there. Otherwise it works with `uv run` but is missing from the container.
- `.dockerignore` keeps `.env`, `data/`, the tests and scripts out of the build. The image has VoteBot and its locked dependencies, not the dev tools or tests.
- Everything VoteBot writes goes under `VOTEBOT_DATA_DIR` (`/data` in the container); a TEC refresh stages its work in `/tmp`.

## Adding a source

Each source contributes `SourceCard`s: badges, facts, quotes, money breakdowns, links and match confidence. A source can also add a card to a race, such as the money comparison. The page renders them all generically, as badges on the candidate row, a tab in Details, and a block at the top of the race. So a new source only needs:

1. A module in `votebot/sources/` that fetches through `HttpCache` and builds cards.
2. A field on `Services` in `ballot.py`, created in `api.py`'s startup.
3. A line in `enrich.py`.
4. An entry in `admin.py` so it appears in Settings, and one in `DEFAULT_SOURCES` in `settings.py` if it can be turned off.
5. A row in the tables on `static/privacy.html` (what the source is sent and kept) and `static/about.html`, and an answer in `static/faq.html` if it raises a question.
