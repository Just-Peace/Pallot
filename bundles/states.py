"""The states' official lists of candidates: one bundle each (state_<st>), holding the next
general election's list as its parsed candidates (StateList.shape), not the raw file, which
carries their addresses and phone numbers. One state failing never holds back another."""

from __future__ import annotations

from typing import Awaitable, Callable

from pallot.sources.fec import general_day
from pallot.states import StateList
from pallot.states.adapters import ADAPTERS

from .entry import Bundle, BundleError, Context


def builder(cls: type[StateList]) -> Callable[[Context], Awaitable[dict[str, int]]]:
    async def build(ctx: Context) -> dict[str, int]:
        """The state's list for the next general election; counts its races and candidates."""
        day = general_day(ctx.today())
        lists = cls(ctx.cache, ctx.config.ttl)
        try:
            found = await lists.filings(day)
        except Exception as exc:
            raise BundleError(f"couldn't load the list from the {cls.label}: {exc}") from exc
        if not found:
            raise BundleError(f"the list from the {cls.label} has no candidates for {day.isoformat()} yet")
        return {"races": len({f.office_id for f in found}), "candidates": len(found)}

    return build


BUNDLES = tuple(
    Bundle(cls.source, builder(cls), "daily", lifetime=lambda ttl, _spec: ttl.state_list_bundle, shape=cls.shape)
    for cls in ADAPTERS.values()
)
LABELS = {cls.source: (f"{cls.label} candidate list", {"candidates": ("c", ""), "races": ("o", "races")})
          for cls in ADAPTERS.values()}
