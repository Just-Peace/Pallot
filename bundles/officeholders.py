"""The seat holders' bundle: both whole lists a lookup asks for, congress-legislators' current
members (public domain) and Open States' Texas legislators (CC0)."""

from __future__ import annotations

from pallot.http_cache import UpstreamError
from pallot.sources.officeholders import STATE, Officeholders

from .entry import BundleError, Context


async def build(ctx: Context) -> dict[str, int]:
    """Both lists; counts the Texas seats each one fills."""
    svc = Officeholders(ctx.cache, ctx.config.ttl)
    try:
        congress = [h for h in await svc.congress() if h.seat.startswith(f"{STATE}-")]
        legislature = await svc.legislature()
    except UpstreamError as exc:
        raise BundleError(f"couldn't load a list of seat holders: {exc}") from exc
    if not congress or not legislature:
        raise BundleError("a list of seat holders has no Texas seats")
    return {"congress": len(congress), "legislature": len(legislature)}
