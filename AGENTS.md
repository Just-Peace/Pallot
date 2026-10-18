# AGENTS.md

Rules for coding agents (and people) changing Pallot. Read these first:

- [README.md](README.md) for what Pallot does;
- [DEVELOPMENT.md](DEVELOPMENT.md) for the commands, the test setup, what the sources do, and the checklists for adding a source, bundle or endorsement list;
- [GitHub issues](https://github.com/Just-Peace/Pallot/issues) for known bugs and what's planned (`gh issue list`).

## Workflow

1. **Start from an issue.** Find the feature or fix with `gh issue list` (filter by type with `--search "type:Bug"`, or by area with `--label ui-ux`). Read it with `gh issue view <N>`. If there's none, open one first (see [Issues](#issues)). Every piece of work has an issue, so every pull request closes one.
2. **Branch off** `develop`**.** Name the branch `feat/<topic>`, `fix/<topic>`, `docs/<topic>` or `refactor/<topic>`. Never commit to `develop` directly.
3. Ensure optimal user experience UI/UX
4. **Finish the whole change before committing:**
   - the code;
   - the tests (see [Before committing](#before-committing));
   - the docs (see [Docs to update](#docs-to-update));
   - the dead code removed (see [Code](#code)).
5. **Make one commit per feature, with a Conventional Commits subject:**
   - The subject is `type: summary`, where `type` is one of `feat`, `fix`, `docs`, `refactor`, `perf`, `test` or `chore`. For example: `feat: poll bars from FiftyPlusOne`.
   - The body is bullets saying what changed and why, then a `Checked:` paragraph saying how it was verified (tests run, what was looked at in the app). Recent commits on `develop` follow this pattern.
   - If you committed along the way, fold everything into one commit before pushing: `git reset --soft $(git merge-base HEAD develop)`, then commit again. Don't use interactive rebase.
6. **Push the branch** with `git push -u origin <branch>`, and open its pull request into `develop` (`gh pr create --base develop`), with `Closes #<issue>` in its description. Merging it then closes the issue and links the two. Pull requests are squash-merged. After amending a commit on your own branch, use `git push --force-with-lease`, never a plain `--force`.
7. **Wait for the checks.** GitHub Actions runs the tests on the pull request (see [Before committing](#before-committing)). Watch them with `gh pr checks <N>`. If one fails, fix it, amend, and push again before asking for a merge.



## Issues

Every piece of work is a GitHub issue, with one type and any area labels.

- **Type** (every issue has one):
  - `Bug`: something works wrong.
  - `Feature`: something new for the voter, or a new source.
  - `Task`: refactors, tooling, reviews, releases and docs.
- **Area labels**, as many as fit: `ui-ux`, `mobile`, `accessibility`, `performance`, `source`, `tooling`, `documentation`, `review` (spot checks included), `investigate`. Add `deferred` when it's put off, and say why in the issue.
- Duplicates and won't-fix are closed with GitHub's close reasons ("duplicate", "not planned"), not labels.
- The title says what's wrong or what's wanted. The body says what it is and where it is (`file:line`), and suggests a fix.
- Open one with `gh issue create --title … --label … --body-file …`, then set its type (this machine's `gh` has no `--type`): `gh api -X PATCH repos/Just-Peace/Pallot/issues/<N> -f type=Bug`.
- `gh issue list --search "type:Bug"` lists a type's open ones, `gh issue list --label mobile` an area's.



## Things you notice along the way

While working on a feature, you may stumble on a bug, something odd, or an idea for another feature:

- Open an issue for it (see [Issues](#issues)).
  - Mention it when you report back.
- Then carry on with the feature you're working on.
- Don't go hunting for these.
- Don't fix one in the same change, unless the feature can't work without the fix.



## UX reviews

- Phone first: iPhone 393×852, Galaxy S 360×780. Then desktop. Light and dark.
- Walk the voter's whole journey, from a first visit to the printed sheet and every page.
- Measure, don't eyeball: where the first race starts, row heights, page height, what wraps.
- Look for: rows that could share a line, wrapped labels, duplicate controls, one idea with several names, text about the screen instead of what the voter gets, server details shown to voters.
- One small type scale; nothing under 12px; text boxes 16px.
- 44px hit areas; nothing floating over a control; main actions within thumb reach.
- Keyboard and screen reader: focus returns, names read right.
- Party colours on picks are intended.
- Report findings first. Open issues only for the ones the maintainer agrees to.



## Docs to update

Update the docs in the same commit as the change.


| What changed                                                              | Update                                                                                                                                   |
| ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| A feature the voter sees                                                  | usually nothing: the FAQ if it raises a question. `README.md`'s "Using it" only for a new feature big enough for its short tour          |
| What a self-hoster runs, configures or keeps                              | `README.md` ("Quick start", "Caching", "Keeping the cache", "Configuration", "Docker")                                                   |
| A command, the test setup, or what an outside source does                 | `DEVELOPMENT.md`                                                                                                                         |
| The steps for adding a source, bundle, endorsement list or feed           | `DEVELOPMENT.md`'s checklist for it                                                                                                     |
| Something a voter might ask about, especially how a figure is worked out  | `pallot/static/faq.html`                                                                                                                |
| A source's row in Settings (label, description, notices) or in `pallot-cache` | `SOURCES` in `pallot/catalog.py` (a pause's wording is its `Pause`; a source kept in files words its notice, staleness, refresh and clear in its `KeptSource` methods), and `pallot/static/settings.html` if the page's text changes |
| Which sources start on | `pallot/sources.toml`, and README's "Which sources start on" |
| A page, or a link in the left pane                                        | `PAGES` in `pallot/static/js/chrome.js`, which draws the left pane and the footer on every page                                         |
| A new source, or what's sent to or kept from one                          | the tables in `pallot/static/privacy.html` and `pallot/static/about.html`; the sources named in About's "What it does" (`about.html`)            |
| A new endorsement list                                                    | only its file, `pallot/endorsements/<source>.json` (DEVELOPMENT.md's "Endorsement lists"): the pages name the lists from it |
| A source's answers bundled with Pallot | a `Bundle` in `bundles/registry.py`, its builder, `Ttls.<source>_bundle` (DEVELOPMENT.md's "Bundled snapshots"), and a line in README's "Bundled snapshots" |
| A new environment variable or cache lifetime                              | `.env.example`, `Ttls` or `Config` in `pallot/config.py`, and README's "Configuration"                                                  |
| Something found along the way                                             | a GitHub issue (see [Things you notice along the way](#things-you-notice-along-the-way))                                                 |


How to write them:

- Plain, short sentences about what the voter sees.
- Never walk through the code in a doc: no modules, functions, fields, file trees or UI internals. The code says them, and they go stale with the next feature. The why of a function goes in its docstring.
- Shell commands for Linux (bash), run with `uv`.
- Never paste a key or anything from `.env`.



## Code

- **Leave it clean.** Remove what your change made unused, in the same commit: functions, JS exports, CSS classes, API fields, fixtures, imports. Before deleting a name, grep for it across `pallot/`, `tests/` and `scripts/`.
- **Match the code around you:**
  - `from __future__ import annotations` and type hints;
  - dataclasses for internal shapes, and Pydantic models only in `pallot/models.py` (what the API returns);
  - short docstrings that say what and why, as dense as the neighbouring ones.
- **Frontend:**
  - Plain ES modules in `pallot/static/js/`, with no build step, no framework, and nothing loaded from a CDN (icons are inline SVG). A library the page can't do without is copied into `pallot/static/vendor/`, with its licence, as Leaflet is for the map.
  - Insert data from the API as text with `h()` (`dom.js`), never through `innerHTML`.
  - Build links with `safeUrl`/`extLink`.
- **Dependencies:**
  - Add one only when it's really needed.
  - Declare it in `pyproject.toml`, then run `uv lock` and commit `uv.lock`.
  - A new kind of static file (an image, a font) needs a pattern under `[tool.setuptools.package-data]`, or it will be missing from the Docker image.
- **Line endings:** the repo mixes CRLF (`README.md`) and LF files. Keep each file's endings as they are (`git ls-files --eol` shows them). A tool that rewrites a whole file can turn every line into a diff.
- No need to put comments because only LLM agents will be working on this codebase



## Rules Pallot depends on

- **Every outbound call goes through** `HttpCache` (`pallot/http_cache.py`):
  - A repeat lookup of the same address makes zero external calls.
  - Prefer one bulk call that's cached over a call per candidate.
  - Lifetimes live in `Ttls`, each overridable with `PALLOT_TTL_<NAME>`.
  - Every source appears in Settings and in `pallot-cache` (check, refresh, prune, rebuild), and gets an on/off switch (its default in `pallot/sources.toml`) unless the ballot can't work without it.
  - Settings only shows what the server keeps. Refreshing or deleting it is `pallot-cache`'s, on the host (`pallot/maintain.py`), never an API route: Pallot has no login.
  - A voter's switches stay in their browser and travel with each request (`X-Pallot-Sources`); never keep them on the server, where they'd change everyone's ballot.
- **Keys stay out of the cache.** API keys go in `HttpCache`'s `source_headers`, never in a `RequestSpec`, a cache key, a log line or an error message.
- **Be gentle with the sources:**
  - Throttle with `MIN_INTERVAL` in `services.py`, and pause a source when it refuses a request (`pause_on`).
  - Never fetch TEC's zip in a loop or in many ranges: its server blocks an IP after a burst. Use one streaming request, or `--zip` with a copy you downloaded.
  - FiftyPlusOne answers 403 unless the request carries browser headers.
  - Nominatim forbids search-as-you-type, which is why Google's Places Autocomplete does the suggestions, held to a daily cap.
  - Ballotpedia's ballot endpoint is unofficial and for personal use only.
  - OpenStreetMap's tiles come through the server and are kept at least 7 days, fetched only as the voter looks at them. Never prefetch them or re-download them in bulk, which its tile policy forbids: that's why `pallot-cache` prunes and deletes the street map's tiles but never refreshes them.
  - The Texas Legislative Council's precinct map (about 45 MB) is downloaded only when its portal's index lists a newer one, one download at a time, never in a loop. A map that fails isn't started again by a lookup until the index lists a changed one, or for a week (15 minutes while none is kept). Tests make the map up (`conftest.py`); only the live test downloads the real one.
- **Match across sources by name, with seat and party as corroboration** (`pallot/matching.py`). Label every match exact or likely, and leave an ambiguous one unmatched rather than guessing.
- **Picks, notes and write-ins stay in the browser** (`localStorage`). Never send them to the server. Anything new sent to a third party goes in `privacy.html`.
- **Pallot has no login.** Keep `uv run pallot` bound to `127.0.0.1`; only the Docker image binds `0.0.0.0`. Keep the middleware in `api.py` that refuses unknown `Host` names, requests other sites start, and `/api/*` calls that aren't from Pallot's own pages, and the one that adds the security headers.
  - Every page call goes through `api.js`, which always sends `X-Pallot-Sources`. Only the street map's tiles and the calendar file are asked without it.
  - The pages' Content-Security-Policy allows no inline script or style: give an element a `style` through `h()`, which sets it through the CSSOM. A new image host goes in its `img-src`.
- **Don't reinstall** `trackaipac_cache` **from its own repo.** It's a copy of the maintainer's library, and edits here aren't synced back.
- **Bundled snapshots** (`trackaipac_cache/data/`, `voteforpeace_cache/data/`, `tec_cache/data/`, `bundles/data/`) are updated with their own commands (`uv run trackaipac-cache refresh`, `uv run voteforpeace-cache refresh`, `uv run tec-cache refresh`, `uv run pallot-bundle refresh`). Never edit them by hand.



## Before committing

- GitHub Actions checks every pull request (`.github/workflows/tests.yml`):
  - the whole suite, `uv run pytest`, offline against the recorded responses in `tests/fixtures/`;
  - ruff, for unused imports and variables, undefined names and syntax errors;
  - the Docker build, when `Dockerfile`, `compose.yaml`, `.dockerignore`, `pyproject.toml` or `uv.lock` changed.
  - A change to Markdown files only skips them.
- Locally, run just the tests for what you touched, for example `uv run pytest tests/test_fec.py`. Leave the whole suite to GitHub.
- Run `uv run ruff check` before committing code. `uv run ruff check --fix` removes what it finds.
- After pushing, check the pull request with `gh pr checks <N>`, and fix what fails. A pull request is ready to merge only when its checks are green.
- Add tests for new behaviour, mocking HTTP with `respx`.
  - Re-record fixtures with `uv run python scripts/record_fixtures.py --only <source>` (DEVELOPMENT.md's "Commands" lists them).
- `uv run pytest -m live` only when you change how a source is called. It hits the real services, and with `DEMO_KEY` the FEC's rate limit is shared with the whole IP address. The maintainer can also start the Live tests workflow from the Actions tab.
- For a change to a source, look the same address up twice. The second lookup must make 0 external calls (the server's log line for it: `lookup: 0 external calls, …`; the map's is `district outlines: …`).
- For a UI change, run `uv run pallot` and look at what changed:
  - the ballot, Details, Compare, Settings and the print preview;
  - at phone widths first, then desktop (see [UX reviews](#ux-reviews));
  - in light and dark mode.
- For a Docker change, build the image and test it against a copy of `data/`, never the live one. Don't run the container and `uv run pallot` on the same `data/` at once, because they'd share one SQLite file.
- Never commit `data/`, `.env` or a key. `docker compose config` prints `.env`, the FEC key included.

