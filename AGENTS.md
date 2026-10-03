# AGENTS.md

Rules for coding agents (and people) changing VoteBot. Read these first:

- [README.md](README.md) for what VoteBot does;
- [DEVELOPMENT.md](DEVELOPMENT.md) for how it works inside;
- [GitHub issues](https://github.com/Fahd-Siddiqui/VoteBot/issues) for known bugs and what's planned (`gh issue list`).

## Workflow

1. **Start from an issue.** Find the feature or fix with `gh issue list` (and `--label bug`, `improvement`, …). Read it with `gh issue view <N>`. If there's none, open one first (see [Issues](#issues)). Every piece of work has an issue, so every pull request closes one.
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



## Issues

Every piece of work is a GitHub issue, labelled with its section.

- Label it with its section: `bug`, `improvement`, `tooling`, `enhancement` (Features), `ui-ux`, `review` or `spot-check`. Add `deferred` when it's put off, and say why in the issue.
- The title says what's wrong or what's wanted. The body says what it is and where it is (`file:line`), and suggests a fix.
- Open one with `gh issue create --title … --label … --body-file …`.
- `gh issue list --label bug` lists a section's open ones.



## Things you notice along the way

While working on a feature, you may stumble on a bug, something odd, or an idea for another feature:

- Open an issue for it (see [Issues](#issues)).
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
| A source's row in Settings (label, description, notices, confirm prompts) | `SOURCES` in `votebot/admin.py` (a pause's wording is its `Pause`; a source kept in files words its notice, Refresh and Clear in its `KeptSource` methods), and `votebot/static/settings.html` if the page's text changes |
| A page, or a link in the left pane                                        | `PAGES` in `votebot/static/js/chrome.js`, which draws the left pane and the footer on every page                                         |
| A new source, or what's sent to or kept from one                          | the tables in `votebot/static/privacy.html` and `votebot/static/about.html`; the welcome steps in `votebot/static/index.html`            |
| A new environment variable or cache lifetime                              | `.env.example`, `Ttls` or `Config` in `votebot/config.py`, and README's "Configuration"                                                  |
| Something found along the way                                             | a GitHub issue (see [Things you notice along the way](#things-you-notice-along-the-way))                                                 |


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
  - Throttle with `MIN_INTERVAL` in `api.py`, and pause a source when it refuses a request (`pause_on`).
  - Never fetch TEC's zip in a loop or in many ranges: its server blocks an IP after a burst. Use one streaming request, or `--zip` with a copy you downloaded.
  - FiftyPlusOne answers 403 unless the request carries browser headers.
  - Nominatim forbids search-as-you-type, which is why Ballotpedia's address search does the suggestions.
  - Ballotpedia's endpoints (the ballot and the address search) are unofficial and for personal use only.
  - OpenStreetMap's tiles come through the server and are kept at least 7 days, fetched only as the voter looks at them. Never prefetch them or re-download them in bulk, which its tile policy forbids: that's why the street map has Clear in Settings but no Refresh.
  - The Texas Legislative Council's precinct map (about 45 MB) is downloaded only when its portal's index lists a newer one, one download at a time, never in a loop. A map that fails isn't started again by a lookup until the index lists a changed one, or for a week (15 minutes while none is kept). Tests make the map up (`conftest.py`); only the live test downloads the real one.
- **Match across sources by name, with seat and party as corroboration** (`votebot/matching.py`). Label every match exact or likely, and leave an ambiguous one unmatched rather than guessing.
- **Picks, notes and write-ins stay in the browser** (`localStorage`). Never send them to the server. Anything new sent to a third party goes in `privacy.html`.
- **Settings has no login.** Keep `uv run votebot` bound to `127.0.0.1`; only the Docker image binds `0.0.0.0`. Keep the middleware in `api.py` that refuses unknown `Host` names and requests other sites start.
- **Don't reinstall** `trackaipac_cache` **from its own repo.** It's a copy of the maintainer's library, and edits here aren't synced back.
- **Bundled snapshots** (`trackaipac_cache/data/`, `tec_cache/data/`) are updated with their own commands (`uv run trackaipac-cache refresh`, `uv run tec-cache refresh`). Never edit them by hand.



## Before committing

- `uv run pytest` passes. It runs offline, against the recorded responses in `tests/fixtures/`.
  - Run the whole suite once, just before the feature's commit, and only when code changed. A change to Markdown files only (README, DEVELOPMENT, AGENTS) needs no test run.
  - While working, run just the tests for what you touched, for example `uv run pytest tests/test_fec.py`. The whole suite runs in parallel, one worker per CPU, and takes about 30 seconds.
  - Add tests for new behaviour, mocking HTTP with `respx`.
  - Re-record fixtures with `uv run python scripts/record_fixtures.py --only ballots|suggest|fec|polls|key_dates|tigerweb|election_precincts|tec|trackaipac`.
- `uv run pytest -m live` only when you change how a source is called. It hits the real services, and with `DEMO_KEY` the FEC's rate limit is shared with the whole IP address.
- For a change to a source, look the same address up twice. The second lookup must make 0 external calls (the ballot's `meta.external_calls`, or the "Last lookup" line in Settings).
- For a UI change, run `uv run votebot` and look at what changed:
  - the ballot, Details, Compare, Settings and the print preview;
  - at desktop and phone widths;
  - in light and dark mode.
- For a Docker change, build the image and test it against a copy of `data/`, never the live one. Don't run the container and `uv run votebot` on the same `data/` at once, because they'd share one SQLite file.
- Never commit `data/`, `.env` or a key. `docker compose config` prints `.env`, the FEC key included.

