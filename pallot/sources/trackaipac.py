"""TrackAIPAC (trackaipac.com) data, through the trackaipac_cache package in this repo.

The package ships a snapshot of the site. We copy it into data/trackaipac on first use,
so it works offline without calling trackaipac.com, and only fetch the site when asked
from the Settings page (the package's refresh() validates before writing and writes only
when the site changed). Its members of Congress are listed by current seat, so matching
to the 2026 ballot goes by name first (see matching.match_trackaipac).
"""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin

import trackaipac_cache

from ..matching import NameIndex, match_trackaipac
from ..models import Badge, Fact, Link, Match, Race, SourceCard
from ..text import display_date, display_time, money, web_url
from .snapshot import BundledSnapshot, summary_of

SOURCE = "trackaipac"
LABEL = "TrackAIPAC"
DESCRIPTION = (
    "Pro-Israel lobby money (AIPAC and affiliated PACs) and endorsements for congressional "
    "candidates, as tracked by trackaipac.com."
)
SITE = "https://www.trackaipac.com"
CATEGORY_PAGES = {"watchlist": f"{SITE}/candidates", "endorsed": f"{SITE}/endorsements", "congress": f"{SITE}/congress"}
CATEGORY_NAMES = {"watchlist": "Watchlist", "endorsed": "Endorsements", "congress": "Congress"}
_CATEGORY_BADGES = {
    "watchlist": ("TrackAIPAC watchlist", "warn"),
    "endorsed": ("TrackAIPAC endorsed", "good"),
    "congress": ("TrackAIPAC: member of Congress", "info"),
}
_LINK = re.compile(r"(\[[^\]]+\]\()([^)\s]+)(\))")  # a markdown link: [label](target)


def _absolute_links(text: str) -> str:
    """The site's notes link to its own pages by path ("/james-talarico"); point those at
    trackaipac.com, not at wherever Pallot runs. Full URLs are left as they are."""
    return _LINK.sub(lambda m: m[1] + urljoin(SITE + "/", m[2]) + m[3], text)


class TrackAipac(BundledSnapshot):
    """The package's current.json: every person with all their listings."""

    EMPTY = {"snapshot": None, "candidates": []}
    LABEL = "TrackAIPAC"

    def __init__(
        self,
        data_dir: Path,
        *,
        refresh_fn: Callable[..., Any] | None = None,
        bundled_dir: Path | None = None,
    ):
        super().__init__(data_dir, trackaipac_cache, refresh_fn=refresh_fn, bundled_dir=bundled_dir)

    def _discard(self) -> None:
        shutil.rmtree(self.data_dir, ignore_errors=True)  # refreshes add history files too

    async def _refresh(self) -> str:
        return summary_of(await asyncio.to_thread(self._refresh_fn or trackaipac_cache.refresh, data_dir=self.data_dir))

    def people(self, state: str | None = None) -> list[dict[str, Any]]:
        people = self.document().get("candidates", [])
        return [p for p in people if p.get("state") == state] if state else people

    def name_index(self, state: str) -> NameIndex:
        def build(document: dict[str, Any]) -> NameIndex:
            index = NameIndex()
            for person in document.get("candidates", []):
                if person.get("state") == state and person.get("name"):
                    index.add(person["name"], person)
            return index

        return self._index(state, build)

    def snapshot_date(self) -> str | None:
        return self.meta().get("latest_snapshot")

    def details(self) -> list[Fact]:
        meta = self.meta()
        return [
            Fact(label="Snapshot", value=display_date(meta.get("latest_snapshot")) or "none"),
            Fact(label="Last changed", value=display_time(meta.get("last_refresh")) or "never"),
            Fact(label="Last checked", value=display_time(meta.get("last_checked")) or "never"),
            Fact(label="Texas entries", value=f"{len(self.people('TX')):,}"),
            Fact(label="All entries", value=f"{len(self.people()):,}"),
        ]


def card(person: dict[str, Any], match: Match, snapshot: str | None) -> SourceCard:
    listings = person.get("listings") or []
    categories = [c for c in person.get("categories") or [] if c in CATEGORY_PAGES]
    badges = []
    for category in categories:  # one badge per list, with that listing's Israel-lobby total when shown
        text, tone = _CATEGORY_BADGES[category]
        totals = [item["israel_lobby_total"] for item in listings
                  if item.get("category") == category and item.get("israel_lobby_total") is not None]
        hint = None
        if totals:
            text = f"{text} {money(max(totals))}"
            hint = "Israel lobby total, as tracked by TrackAIPAC"
            if category == "congress" and max(totals) > 0:
                tone = "warn"
        badges.append(Badge(text=text, tone=tone, url=CATEGORY_PAGES[category], hint=hint))

    facts = [Fact(label="Seat on TrackAIPAC", value=person.get("seat") or "not shown")]
    for item in listings:
        category = item.get("category")
        where = item.get("section") or item.get("title")
        facts.append(
            Fact(
                label="Listed on",
                value=f"{CATEGORY_NAMES.get(category, category)} page" + (f" ({where})" if where else ""),
                url=CATEGORY_PAGES.get(category),
            )
        )
        if item.get("seat_text"):
            facts.append(Fact(label="Seat as listed", value=item["seat_text"]))
        for label, key in (("Israel lobby total", "israel_lobby_total"), ("PAC money", "donations"),
                           ("Independent expenditures", "ie")):
            if item.get(key) is not None:
                facts.append(Fact(label=label, value=money(item[key]) or ""))
        if item.get("pacs"):
            facts.append(Fact(label="PACs", value=", ".join(item["pacs"])))
        if item.get("election_date"):
            facts.append(Fact(label="Election date", value=item["election_date"]))

    quotes = [_absolute_links(note) for item in listings for note in item.get("notes") or []]
    lobby = [item["israel_lobby_total"] for item in listings
             if item.get("category") in categories and item.get("israel_lobby_total") is not None]

    links = [Link(label=f"TrackAIPAC {CATEGORY_NAMES[c]} page", url=CATEGORY_PAGES[c]) for c in categories]
    for item in listings:
        if campaign := web_url(item.get("campaign_url")):
            links.append(Link(label="Campaign website (from TrackAIPAC)", url=campaign))
        if donate := web_url(item.get("donate_url")):
            links.append(Link(label="Donation page (listed by TrackAIPAC)", url=donate))

    return SourceCard(
        source=SOURCE,
        label=LABEL,
        description=DESCRIPTION,
        url=CATEGORY_PAGES.get(categories[0]) if categories else SITE,
        as_of=snapshot,
        match=match,
        badges=badges,
        facts=facts,
        quotes=quotes,
        links=list({link.url: link for link in links}.values()),
        figures={"israel_lobby": max(lobby)} if lobby else {},
        flags=categories,
    )


def cards(tracker: TrackAipac, races: list[Race]) -> dict[str, SourceCard]:
    """Cards for candidates in congressional races who appear on TrackAIPAC."""
    congressional = [race for race in races if race.seat]
    if not congressional:
        return {}
    index = tracker.name_index("TX")
    snapshot = tracker.document().get("snapshot")
    out = {}
    for race in congressional:
        for candidate in race.candidates:
            found = match_trackaipac(index, candidate.name, candidate.party, race.seat)
            if found:
                out[candidate.key] = card(found[0], found[1], snapshot)
    return out
