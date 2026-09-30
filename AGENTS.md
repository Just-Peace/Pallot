# AGENTS.md

Rules for coding agents (and people) changing VoteBot. Read these first:

- [README.md](README.md) for what VoteBot does;
- [DEVELOPMENT.md](DEVELOPMENT.md) for how it works inside;
- [ROADMAP.md](ROADMAP.md) for known bugs and what's planned.

## Workflow

1. **Start from the roadmap.** Find the feature or fix in [ROADMAP.md](ROADMAP.md). If it isn't there, add it when you finish (step 4). Every piece of work should end up in the roadmap.
2. **Branch off** `develop`**.** Name the branch `feat/<topic>`, `fix/<topic>`, `docs/<topic>` or `refactor/<topic>`. Never commit to `develop` directly.
3. Ensure optimal user experience UI/UX
4. **Finish the whole change before committing:**
   - the code;
   - the tests (see [Before committing](#before-committing));
   - the docs (see [Docs to update](#docs-to-update));
   - the dead code removed (see [Code](#code));
   - `ROADMAP.md`: move the item to "Done" as `- [x]`, in a group for this change, headed with the feature's name, its pull request and the date, like `### Polls ([#7](https://github.com/Fahd-Siddiqui/VoteBot/pull/7), Sep 29)`. The pull request doesn't exist yet when you commit, so assume it's the next number in sequence: one more than the highest `(#N)` in `git log develop --oneline`. Don't use the branch name. If the pull request gets a different number, fix the heading. If the work wasn't in the roadmap, add it straight to "Done".
5. **Make one commit per feature, with a Conventional Commits subject:**
   - The subject is `type: summary`, where `type` is one of `feat`, `fix`, `docs`, `refactor`, `perf`, `test` or `chore`. For example: `feat: poll bars from FiftyPlusOne`.
   - The body is bullets saying what changed and why, then a `Checked:` paragraph saying how it was verified (tests run, what was looked at in the app). Recent commits on `develop` follow this pattern.
   - If you committed along the way, fold everything into one commit before pushing: `git reset --soft $(git merge-base HEAD develop)`, then commit again. Don't use interactive rebase.
6. **Push the branch** with `git push -u origin <branch>`. Pull requests go into `develop`, where they're squash-merged. After amending a commit on your own branch, use `git push --force-with-lease`, never a plain `--force`.



## Things you notice along the way

While working on a feature, you may stumble on a bug, something odd, or an idea for another feature:

- Add it to `ROADMAP.md`, in its section (Bugs, Improvements, Tooling, Features or UI and UX).
  - Say what it is and where it is (`file:line`), and suggest a fix.
  - It goes in the feature's commit.
  - Mention it when you report back.
- Then carry on with the feature you're working on.
- Don't go hunting for these.
- Don't fix one in the same change, unless the feature can't work without the fix.



## Docs to update

Update the docs in the same commit as the change.


| What changed                                                              | Update                                                                                                                                   |
| ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Anything the voter sees or does                                           | `README.md` ("Using it", "Where the data comes from", "Caching", "Settings")                                                             |
| Internals, commands, layout, a source's quirks                            | `DEVELOPMENT.md`                                                                                                                         |
| Something a voter might ask about, especially how a figure is worked out  | `votebot/static/faq.html`                                                                                                                |
| A source's row in Settings (label, description, notices, confirm prompts) | `SOURCES` in `votebot/admin.py` (a pause's wording is its `Pause`), and `votebot/static/settings.html` if the page's text changes        |
| A page, or a link in the left pane                                        | `PAGES` in `votebot/static/js/chrome.js`, which draws the left pane on every page                                                        |
| A new source, or what's sent to or kept from one                          | the tables in `votebot/static/privacy.html` and `votebot/static/about.html`; the footer and welcome steps in `votebot/static/index.html` |
| A new environment variable or cache lifetime                              | `.env.example`, `Ttls` or `Config` in `votebot/config.py`, and README's "Configuration"                                                  |
| Any finished work, or something found along the way                       | `ROADMAP.md` (see [Workflow](#workflow) and [Things you notice along the way](#things-you-notice-along-the-way))                         |


How to write them:

- Plain, short sentences about what the voter sees.
- Shell commands for Linux (bash), run with `uv`.
- Never paste a key or anything from `.env`.



## Code

- **Leave it clean.** Remove what your change made unused, in the same commit: functions, JS exports, CSS classes, API fields, fixtures, imports. Before deleting a name, grep for it across `votebot/`, `tests/` and `scripts/`.
- **Match the code around you:**
  - `from __future__ import annotations` and type hints;
  - dataclasses for internal shapes, and Pydantic models only in `votebot/models.py` (what the API returns);
  - short docstrings that say what and why, as dense as the neighbouring ones.
- **Frontend:**
  - Plain ES modules in `votebot/static/js/`, with no build step, no framework, and nothing loaded from a CDN (icons are inline SVG). A library the page can't do without is copied into `votebot/static/vendor/`, with its licence, as Leaflet is for the map.
  - Insert data from the API as text with `h()` (`dom.js`), never through `innerHTML`.
  - Build links with `safeUrl`/`extLink`.
- **Dependencies:**
  - Add one only when it's really needed.
  - Declare it in `pyproject.toml`, then run `uv lock` and commit `uv.lock`.
  - A new kind of static file (an image, a font) needs a pattern under `[tool.setuptools.package-data]`, or it will be missing from the Docker image.
- **Line endings:** the repo mixes CRLF (`README.md`) and LF files. Keep each file's endings as they are (`git ls-files --eol` shows them). A tool that rewrites a whole file can turn every line into a diff.
- No need to put comments because only LLM agents will be working on this codebase



## Rules VoteBot depends on

- **Every outbound call goes through** `HttpCache` (`votebot/http_cache.py`):
  - A repeat lookup of the same address makes zero external calls.
  - Prefer one bulk call that's cached over a call per candidate.
  - Lifetimes live in `Ttls`, each overridable with `VOTEBOT_TTL_<NAME>`.
  - Every source appears in Settings with Refresh and Clear, and gets an on/off switch (`DEFAULT_SOURCES` in `votebot/settings.py`) unless the ballot can't work without it.
- **Keys stay out of the cache.** API keys go in `HttpCache`'s `source_headers`, never in a `RequestSpec`, a cache key, a log line or an error message.
- **Be gentle with the sources:**
  - Throttle with `min_interval`, and pause a source when it refuses a request (`pause_on`).
  - Never fetch TEC's zip in a loop or in many ranges: its server blocks an IP after a burst. Use one streaming request, or `--zip` with a copy you downloaded.
  - FiftyPlusOne answers 403 unless the request carries browser headers.
  - Nominatim forbids search-as-you-type, which is why Photon does the suggestions.
  - Ballotpedia's endpoint is unofficial and for personal use only.
  - OpenStreetMap's tiles come through the server and are kept at least 7 days, fetched only as the voter looks at them. Never prefetch them or re-download them in bulk, which its tile policy forbids: that's why the street map has Clear in Settings but no Refresh.
- **Match across sources by name, with seat and party as corroboration** (`votebot/matching.py`). Label every match exact or likely, and leave an ambiguous one unmatched rather than guessing.
- **Picks, notes and write-ins stay in the browser** (`localStorage`). Never send them to the server. Anything new sent to a third party goes in `privacy.html`.
- **Settings has no login.** Keep `uv run votebot` bound to `127.0.0.1`; only the Docker image binds `0.0.0.0`. Keep the middleware in `api.py` that refuses unknown `Host` names and requests other sites start.
- **Don't reinstall** `trackaipac_cache` **from its own repo.** It's a copy of the maintainer's library, and edits here aren't synced back.
- **Bundled snapshots** (`trackaipac_cache/data/`, `tec_cache/data/`) are updated with their own commands (`uv run trackaipac-cache refresh`, `uv run tec-cache refresh`). Never edit them by hand.



## Before committing

- `uv run pytest` passes. It runs offline, against the recorded responses in `tests/fixtures/`.
  - Run the whole suite once, just before the feature's commit, and only when code changed. A change to Markdown files only (README, DEVELOPMENT, ROADMAP, AGENTS) needs no test run.
  - While working, run just the tests for what you touched, for example `uv run pytest tests/test_fec.py`. The whole suite takes about two minutes.
  - Add tests for new behaviour, mocking HTTP with `respx`.
  - Re-record fixtures with `uv run python scripts/record_fixtures.py --only ballots|fec|polls|tec|trackaipac`.
- `uv run pytest -m live` only when you change how a source is called. It hits the real services, and with `DEMO_KEY` the FEC's rate limit is shared with the whole IP address.
- For a change to a source, look the same address up twice. The second lookup must make 0 external calls (the ballot's `meta.external_calls`, or the "Last lookup" line in Settings).
- For a UI change, run `uv run votebot` and look at what changed:
  - the ballot, Details, Compare, Settings and the print preview;
  - at desktop and phone widths;
  - in light and dark mode.
- For a Docker change, build the image and test it against a copy of `data/`, never the live one. Don't run the container and `uv run votebot` on the same `data/` at once, because they'd share one SQLite file.
- Never commit `data/`, `.env` or a key. `docker compose config` prints `.env`, the FEC key included.

