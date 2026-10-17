"""The seat holders' bundle: the whole lists a lookup asks for, congress-legislators' current
members (public domain) and Open States' legislators (CC0) of Texas and every state with an
official list (states/adapters.py)."""

from __future__ import annotations

from pallot.http_cache import UpstreamError
from pallot.sources.officeholders import STATE, Officeholders
from pallot.states.adapters import ADAPTERS

from .entry import BundleError, Context


async def build(ctx: Context) -> dict[str, int]:
    """The lists; counts the Texas seats Congress's and Texas's fill."""
    svc = Officeholders(ctx.cache, ctx.config.ttl)
    try:
        congress = [h for h in await svc.congress() if h.seat.startswith(f"{STATE}-")]
        legislature = await svc.legislature()
        for state in ADAPTERS:
            await svc.legislature(state)
    except UpstreamError as exc:
        raise BundleError(f"couldn't load a list of seat holders: {exc}") from exc
    if not congress or not legislature:
        raise BundleError("a list of seat holders has no Texas seats")
    return {"congress": len(congress), "legislature": len(legislature)}
