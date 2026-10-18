"""The seat holders' bundle: the whole lists a lookup asks for, congress-legislators' current
members (public domain) and Open States' legislators (CC0) of Texas and every state with an
official list (states/adapters.py)."""

from __future__ import annotations

from pallot.http_cache import UpstreamError
from pallot.sources.officeholders import Officeholders
from pallot.states.adapters import ADAPTERS

from .entry import BundleError, Context


async def build(ctx: Context) -> dict[str, int]:
    """The lists; counts the members of Congress and the legislators of the states bundled."""
    svc = Officeholders(ctx.cache, ctx.config.ttl)
    try:
        congress = await svc.congress()
        legislatures = {state: await svc.legislature(state) for state in ("TX", *ADAPTERS)}
    except UpstreamError as exc:
        raise BundleError(f"couldn't load a list of seat holders: {exc}") from exc
    if not congress or not any(legislatures.values()):
        raise BundleError("a list of seat holders is empty")
    return {"congress": len(congress), "legislature": sum(map(len, legislatures.values()))}
