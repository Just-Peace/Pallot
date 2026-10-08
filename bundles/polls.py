"""FiftyPlusOne's bundle, bundled with its permission: its nationwide list of each kind of race's
polls, asked exactly as a lookup asks (Polls.polls, with its browser headers), so the cache keys match."""

from __future__ import annotations

from pallot.sources.polls import KINDS, Polls

from .entry import BundleError, Context


async def build(ctx: Context) -> dict[str, int]:
    """Every page of the Senate, House and Governor lists; counts each kind's Texas polls."""
    svc = Polls(ctx.cache, ctx.config.ttl, ctx.today)
    counts = {}
    try:
        for kind in KINDS:
            counts[kind.removesuffix("_general")] = len(await svc.polls(kind))
    except Exception as exc:
        raise BundleError(f"couldn't load FiftyPlusOne's polls: {exc}") from exc
    return counts
