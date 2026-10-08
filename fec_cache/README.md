# fec_cache

A snapshot of the FEC's answers for Texas's federal races, bundled with Pallot so that a lookup asks the FEC only for what's missing or stale. Unlike the other `*_cache` packages, it's part of Pallot, not a copy of another library: building it runs Pallot's own Texas SOS and FEC code.

```bash
uv run fec-cache refresh             # ask the FEC again; write if anything changed
uv run fec-cache refresh --dry-run   # say what would change, write nothing
uv run fec-cache refresh --force     # write even if nothing changed
```

- It needs an FEC key (`PALLOT_FEC_API_KEY`, and `2` to `5` if you have them), from the environment or `.env`. With the shared `DEMO_KEY` it refuses, since the FEC would answer race totals only.
- It asks Texas SOS for each upcoming election's statewide candidate list, takes the federal races from it, and asks the FEC what a lookup of those races would: each seat's race list, and five or six breakdowns for each candidate the FEC lists (about 470 requests in October 2026). It goes at `pallot-cache`'s gentle pace: one request every 2 seconds per key, so about 5 minutes with 3 keys.
- It writes `data/current.json` only if every request succeeded and the answers changed. `data/meta.json`'s `last_checked` is updated either way: Pallot dates the answers by it, so a daily run keeps them fresh.

See DEVELOPMENT.md's "fec_cache" for how Pallot loads it.
