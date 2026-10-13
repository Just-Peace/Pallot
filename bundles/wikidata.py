"""Wikidata's bundle: the list of Texas officeholders every lookup matches against (CC0). The
matched people's details are asked per ballot, so they aren't in it."""

from __future__ import annotations

from pallot.sources.wikidata import Wikidata, WikidataUnavailable

from .entry import BundleError, Context

MIN_PEOPLE = 300  # far fewer means the query or Wikidata's data went wrong


async def build(ctx: Context) -> dict[str, int]:
    """The list; counts the people and those with a seat Pallot has races for."""
    try:
        people, _, _ = await Wikidata(ctx.cache, ctx.config.ttl).people()
    except WikidataUnavailable as exc:
        raise BundleError(f"couldn't load Wikidata's Texas officeholders: {exc}") from exc
    if len(people) < MIN_PEOPLE:
        raise BundleError(f"Wikidata listed only {len(people)} Texas officeholders")
    return {"people": len(people), "with_seats": sum(1 for p in people if p.seats)}
