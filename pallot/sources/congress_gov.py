"""A member of Congress's bills, from the Library of Congress's Congress.gov API (public domain).

Only a candidate who surely is the member holding the seat they run for gets them
(officeholders.members), by the Bioguide ID congress-legislators gives, so nothing is matched by
name. Two calls each: the newest bills they sponsored and cosponsored, with how many in all. They're
asked live, the first time a lookup needs them, and kept a day so the same ballot asks nothing
again; once expired they're deleted (services.prune), never refreshed ahead. The key is the FEC's
(an api.data.gov key works for both), sent in a header HttpCache never stores; one Congress.gov
rate limits or refuses rests for an hour while the others carry on. Votes aren't covered: its
House votes list members per roll call, and it has no Senate votes.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Any, Mapping

from ..config import DEMO_KEY, Ttls
from ..http_cache import HttpCache, RequestSpec, UpstreamError
from ..models import Item, ItemList, Link, Race, SourceCard
from ..states import ordinal
from ..text import display_date, iso_utc
from . import CardSet
from .officeholders import Holder, Officeholders, holder_match, members

log = logging.getLogger("uvicorn.error")

SOURCE = "congress_gov"
LABEL = "In Congress"
SETTINGS_DESCRIPTION = (
    "The newest bills a member of Congress running again sponsored and cosponsored, from the Library of Congress's "
    "Congress.gov, asked when a ballot needs them and kept a day; it needs Seat holders on."
)
API = "https://api.congress.gov/v3"
SITE = "https://www.congress.gov"
NEWEST = 5  # bills shown of each list
# A bill's type -> how it's written, and its kind in Congress.gov's addresses.
TYPES = {
    "HR": ("H.R.", "house-bill"), "S": ("S.", "senate-bill"),
    "HRES": ("H.Res.", "house-resolution"), "SRES": ("S.Res.", "senate-resolution"),
    "HJRES": ("H.J.Res.", "house-joint-resolution"), "SJRES": ("S.J.Res.", "senate-joint-resolution"),
    "HCONRES": ("H.Con.Res.", "house-concurrent-resolution"), "SCONRES": ("S.Con.Res.", "senate-concurrent-resolution"),
}
LISTS = (("sponsored", "Sponsored"), ("cosponsored", "Cosponsored"))


class CongressGov:
    def __init__(self, cache: HttpCache, ttl: Ttls, api_keys: Mapping[str, str]):
        """``api_keys``: the FEC's, each by the variable it's in (Config.fec_api_keys)."""
        self.cache = cache
        self.ttl = ttl
        names = tuple(api_keys) if DEMO_KEY not in api_keys.values() else ("the shared DEMO_KEY",)
        cache.share_keys(SOURCE, "X-Api-Key", tuple(api_keys.values()),
                         {429: ttl.congress_gov_backoff, 403: ttl.congress_gov_backoff}, names=names)

    async def bills(self, bioguide: str, which: str) -> tuple[dict[str, Any], float]:
        """The member's newest ``which`` ("sponsored" or "cosponsored") bills, and when they were fetched."""
        spec = RequestSpec("GET", f"{API}/member/{bioguide}/{which}-legislation",
                           params={"format": "json", "limit": str(NEWEST)})
        got = await self.cache.get_json(SOURCE, spec, ttl=self.ttl.congress_gov)
        return got.value or {}, got.fetched_at


def bill_item(row: dict[str, Any]) -> Item | None:
    """A bill or resolution as a list entry, linked to its page; None for an amendment."""
    kind = TYPES.get((row.get("type") or "").upper())
    if not kind or not row.get("number") or not row.get("congress"):
        return None
    words, path = kind
    action = row.get("latestAction") or {}
    meta = " · ".join(filter(None, (f"{words} {row['number']}", display_date(row.get("introducedDate")))))
    return Item(
        title=row.get("title") or f"{words} {row['number']}",
        url=f"{SITE}/bill/{ordinal(int(row['congress']))}-congress/{path}/{row['number']}",
        meta=meta,
        note=" ".join(filter(None, (display_date(action.get("actionDate")), action.get("text")))) or None,
    )


def card(holder: Holder, key: str, answers: dict[str, dict[str, Any]], fetched_at: float) -> SourceCard | None:
    """The In Congress tab: the member's newest sponsored and cosponsored bills, with how many in
    all, and a link to their page; None when Congress.gov has neither."""
    lists = []
    for which, title in LISTS:
        answer = answers.get(which) or {}
        items = [item for row in answer.get(f"{which}Legislation") or [] if (item := bill_item(row))]
        total = (answer.get("pagination") or {}).get("count")
        if items:
            lists.append(ItemList(title=title, items=items, total=total if isinstance(total, int) else None))
    if not lists:
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", holder.name.lower()).strip("-")
    return SourceCard(
        source=SOURCE,
        kind="record",
        label=LABEL,
        as_of=iso_utc(fetched_at),
        match=holder_match(holder, key),
        lists=lists,
        links=[Link(label="All their bills on Congress.gov", url=f"{SITE}/member/{slug}/{holder.ids['bioguide']}")],
    )


async def cards(svc: CongressGov, holders: Officeholders, races: list[Race], day: dt.date | None) -> CardSet:
    """A card for each candidate who surely is their seat's member of Congress. Raises
    UpstreamError when the list of members can't be had; a member whose bills can't be had has
    no card, with a warning."""
    out = CardSet()
    found = {key: holder for key, holder in (await members(holders, races, day)).items() if "bioguide" in holder.ids}
    failed = False
    for key, holder in found.items():
        answers, fetched = {}, []
        try:
            for which, _ in LISTS:
                answers[which], at = await svc.bills(holder.ids["bioguide"], which)
                fetched.append(at)
        except UpstreamError as exc:
            log.warning("%s", exc)
            failed = True
            continue
        if made := card(holder, key, answers, min(fetched)):
            out.candidates[key] = made
    if failed:
        out.warnings.append("Congress.gov isn't answering right now, so some members' bills aren't shown.")
    return out
