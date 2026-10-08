"""The live endorsement lists whose organizations agreed to have them bundled (PERMITTED), one
bundle each, so a feed that fails is left out (asked live) without losing the others. Each is
asked exactly as a lookup asks (EndorsementFeed.fetch): Emgage's page is fetched first for its
token, which HttpCache never stores, so neither the page nor the token is in the bundle."""

from __future__ import annotations

from typing import Awaitable, Callable

from pallot.config import Ttls
from pallot.http_cache import RequestSpec
from pallot.sources.endorsement_feeds import FEEDS, EndorsementFeed, Feed, FeedUnavailable

from .entry import Bundle, BundleError, Context

PERMITTED = ("mupac", "cair", "emgage")  # Muslims United PAC, CAIR Action, Emgage PAC: each agreed to it


def builder(feed: Feed) -> Callable[[Context], Awaitable[dict[str, int]]]:
    async def build(ctx: Context) -> dict[str, int]:
        """The feed's whole list; counts its Texas candidates and all of them."""
        try:
            found = await EndorsementFeed(feed, ctx.cache, ctx.config.ttl).fetch()
        except FeedUnavailable as exc:
            raise BundleError(f"couldn't load {feed.organization}'s list: {exc}") from exc
        return {"texas": found.count("TX"), "candidates": found.count()}

    return build


def lifetime(ttl: Ttls, spec: RequestSpec) -> float:
    return ttl.endorsement_feeds_bundle


BUNDLES = tuple(Bundle(feed.source, builder(feed), "daily", lifetime=lifetime)
                for feed in FEEDS if feed.source in PERMITTED)
