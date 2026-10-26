"""The states' official lists of candidates: one bundle each (state_<st>), holding the next
general election's list as its parsed candidates (StateList.shape), not the raw file, which
carries their addresses and phone numbers. One state failing never holds back another. A list
saved by hand (ManualList) has a manual bundle, written only by its import (manual.py); the part
of its ballot that's fetched (ManualList.fetched: Georgia's nominees) has a daily one of its own,
state_<st>_results, under the same source."""

from __future__ import annotations

from typing import Awaitable, Callable

from pallot.sources.fec import general_day
from pallot.states import ManualList, StateList
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


def imported(cls: type[ManualList]) -> Callable[[Context], Awaitable[dict[str, int]]]:
    async def build(ctx: Context) -> dict[str, int]:
        """Never fetched: its site blocks scripts, so the list is saved by hand and imported."""
        raise BundleError(f"the {cls.label}'s list is imported by hand: see {cls.folder}/README.md")

    return build


def _bundles(cls: type[StateList]) -> tuple[Bundle, ...]:
    if not issubclass(cls, ManualList):
        return (Bundle(cls.source, builder(cls), "daily", lifetime=lambda ttl, _spec: ttl.state_list_bundle,
                       shape=cls.shape),)
    manual = Bundle(cls.source, imported(cls), "manual", lifetime=lambda ttl, _spec: ttl.state_list_imported,
                    include=ManualList.imported, shape=cls.shape)
    if not cls.fetched:
        return (manual,)
    return manual, Bundle(cls.source, builder(cls), "daily", lifetime=lambda ttl, _spec: ttl.state_list_bundle,
                          name=f"{cls.source}_results", include=lambda spec: not ManualList.imported(spec),
                          shape=cls.shape)


BUNDLES = tuple(bundle for cls in ADAPTERS.values() for bundle in _bundles(cls))
LABELS = {
    **{cls.source: (f"{cls.label} candidate list", {"candidates": ("c", ""), "races": ("o", "races")})
       for cls in ADAPTERS.values()},
    **{f"{cls.source}_results": (f"{cls.label} party nominees", {"candidates": ("c", ""), "races": ("o", "races")})
       for cls in ADAPTERS.values() if issubclass(cls, ManualList) and cls.fetched},
}
