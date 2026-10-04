# trackaipac_cache (copied into Pallot)

A local JSON copy of the congressional AIPAC funding and endorsement data on [trackaipac.com](https://www.trackaipac.com).

This folder is a copy of `trackaipac_cache` from `git@github.com:Fahd-Siddiqui/TrackAipacCache.git` (branch `develop`, commit `423443a`), brought into this repo instead of being installed as a dependency. Its tests are in `tests/trackaipac/`. Changes made here are not synced back to that repo.

| Page on the site | Category    |
|------------------|-------------|
| `/candidates`    | `watchlist` |
| `/endorsements`  | `endorsed`  |
| `/congress`      | `congress`  |

## How Pallot uses it

Pallot copies `trackaipac_cache/data/` into `data/trackaipac/` on first run and reads `current.json` from there. The **Refresh from trackaipac.com** button on the Settings page calls `refresh(data_dir="data/trackaipac")`; **Reset to bundled snapshot** goes back to the files in this folder.

## Read

```python
import trackaipac_cache as t

c = t.get_candidate("Mary Peltola")        # a name or an id ("ak-mary-peltola")
c.categories                               # ("watchlist",)
w = c.listing("watchlist")
w.israel_lobby_total, w.pacs               # parsed values (None if the site doesn't show them)
w.lines                                    # the entry's text exactly as shown on the site

t.list_watchlist(state="TX", party="R")
t.list_endorsed(incumbents_only=True)      # True: incumbents, False: challengers, None: all
t.list_congress(state="CA", chamber="senate")
t.search("AIPAC")
t.history("Mary Peltola")                  # one Snapshot per listing for each saved day
t.last_refreshed()
```

When a name matches more than one person (e.g. "Mike Rogers"), the lookup raises `AmbiguousNameError`. Use the id instead.

## Refresh the bundled snapshot

```
uv run trackaipac-cache refresh              # writes only if the site changed
uv run trackaipac-cache refresh --dry-run    # show what would change, write nothing
uv run trackaipac-cache refresh --force      # write a snapshot even if nothing changed
```

Without `--data-dir`, this updates `trackaipac_cache/data/` in this repo (commit it to keep it). If a page looks broken, the refresh aborts without writing anything (`FetchError` / `ValidationError`).

## Data (`trackaipac_cache/data/`)

- `history/YYYY-MM-DD.json`: one row per entry on the site, in page order. Each row holds the entry's verbatim `lines` plus the parsed fields. A file is written only when the site changed; a second change on the same day overwrites that day's file.
- `registry.json`: `candidate_id` → name, state, district, party, chamber. Entries are never removed.
- `current.json`: the latest snapshot, grouped per person. It is generated, so don't edit it.
- `meta.json`: `last_refresh`, `last_checked`, and a hash of each page's data.

## Tests

```
uv run pytest tests/trackaipac                            # offline, uses tests/trackaipac/fixtures/
uv run python scripts/capture_trackaipac_fixtures.py      # re-capture the test pages (tests assert on their contents)
```
