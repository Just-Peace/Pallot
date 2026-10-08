"""The seat holders' bundle: both whole lists a lookup asks for, congress-legislators' current
members (public domain) and Open States' Texas legislators (CC0)."""

from __future__ import annotations

from pallot.sources.officeholders import Officeholders, OfficeholdersUnavailable

from .entry import BundleError, Context


async def build(ctx: Context) -> dict[str, int]:
    """Both lists; counts the Texas seats each one fills."""
    svc = Officeholders(ctx.cache, ctx.config.ttl)
    try:
        congress = await svc.congress()
        legislature = await svc.legislature()
    except OfficeholdersUnavailable as exc:
        raise BundleError(f"couldn't load a list of seat holders: {exc}") from exc
    if not congress or not legislature:
        raise BundleError("a list of seat holders has no Texas seats")
    return {"congress": len(congress), "legislature": len(legislature)}
