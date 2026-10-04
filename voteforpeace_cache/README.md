# voteforpeace_cache

A local JSON copy of the candidates rated on [Vote for Peace](https://voteforpeace.info/candidates) (Organize for Peace), used in VoteBot with their permission.

The site rates each candidate **Ally** (`vote`), **Neutral** (`neutral`) or **Opposed** (`reject`), on their stance on war, human rights and lobby money such as AIPAC's, and cites the groups behind each rating. It covers every level, from Congress to county courts and city councils, in about 34 states.

## How VoteBot uses it

VoteBot copies `voteforpeace_cache/data/` into `data/voteforpeace/` on first run and reads `current.json` from there. The **Refresh from voteforpeace.info** button on the Settings page calls `refresh(data_dir="data/voteforpeace")`; **Reset to the snapshot that came with VoteBot** goes back to the files in this folder.

## Refresh the bundled snapshot

```bash
uv run voteforpeace-cache refresh              # writes only if the site changed
uv run voteforpeace-cache refresh --dry-run    # show what would change, write nothing
uv run voteforpeace-cache refresh --force      # write a snapshot even if nothing changed
uv run voteforpeace-cache refresh --save-raw raw   # also keep the fetched page in raw/
```

Without `--data-dir`, this updates `voteforpeace_cache/data/` in this repo (commit it to keep it). Each refresh is one request for the All Candidates page (about 7 MB). If the page looks broken, the refresh aborts without writing anything (`FetchError`, `ParseError` or `ValidationError`).

## Data (`voteforpeace_cache/data/`)

- `history/YYYY-MM-DD.json`: one row per candidate, in page order (state by state). A file is written only when the site changed; a second change on the same day overwrites that day's file.
- `current.json`: `{"snapshot": "YYYY-MM-DD", "candidates": [...]}`, the latest day's rows. It is generated, so don't edit it.
- `meta.json`: `last_refresh`, `last_checked`, `latest_snapshot`, and a hash of the rows.

A row keeps the site's own fields: `candidate_id`, `name`, `slug`, `url` (the candidate's page), `state`, `section`, `party`, `rating`, `office_title`, `district`, `level`, `jurisdiction`, the election (`election_date`, `election_label`, `election_stage`, `election_result`), `featured_text`, `notes` (as plain text), `endorsements` (the groups it cites: `organization`, `type`, `notes`, `link`) and `articles` (`title`, `url`, `description`).

## Tests

```bash
uv run pytest tests/voteforpeace                                # offline, uses tests/voteforpeace/fixtures/
uv run python scripts/capture_voteforpeace_fixture.py           # re-capture the test page (one request; tests assert on its contents)
```
