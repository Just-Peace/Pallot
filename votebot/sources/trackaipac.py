"""TrackAIPAC (trackaipac.com) data, through the trackaipac_cache package in this repo.

The package ships a snapshot of the site. We copy it into data/trackaipac on first use,
so it works offline without calling trackaipac.com, and only fetch the site when asked
from the Settings page (the package's refresh() validates before writing and writes only
when the site changed). Its members of Congress are listed by current seat, so matching
to the 2026 ballot goes by name first (see matching.match_trackaipac).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import shutil
from importlib import resources
from pathlib import Path
from typing import Any, Callable, ContextManager

import trackaipac_cache

from ..matching import NameIndex, match_trackaipac
from ..models import Badge, Fact, Link, Match, Race, SourceCard
from ..text import money, web_url

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


class TrackAipac:
    def __init__(
        self,
        data_dir: Path,
        *,
        refresh_fn: Callable[..., Any] | None = None,
        bundled_dir: Path | None = None,
    ):
        self.data_dir = data_dir
        self._refresh_fn = refresh_fn
        self._bundled_dir = bundled_dir
        self._doc: tuple[tuple[int, int], dict[str, Any]] | None = None
        self._indexes: dict[str, NameIndex] = {}

    @property
    def current_path(self) -> Path:
        return self.data_dir / "current.json"

    @property
    def meta_path(self) -> Path:
        return self.data_dir / "meta.json"

    def _bundled(self) -> ContextManager[Path]:
        if self._bundled_dir is not None:
            return contextlib.nullcontext(self._bundled_dir)
        return resources.as_file(resources.files(trackaipac_cache) / "data")

    def ensure_seeded(self) -> bool:
        """Copy in the package's bundled snapshot if we have no data yet; True if copied."""
        if self.current_path.exists():
            return False
        with self._bundled() as source:
            shutil.copytree(source, self.data_dir, dirs_exist_ok=True)
        return True

    def reset(self) -> None:
        """Throw away refreshed data and go back to the package's bundled snapshot."""
        shutil.rmtree(self.data_dir, ignore_errors=True)
        self._doc = None
        self.ensure_seeded()

    async def refresh(self) -> str:
        self.ensure_seeded()
        result = await asyncio.to_thread(self._refresh_fn or trackaipac_cache.refresh, data_dir=self.data_dir)
        return result.summary() if hasattr(result, "summary") else str(result)

    def _signature(self) -> tuple[int, int] | None:
        try:
            stat = self.current_path.stat()
        except FileNotFoundError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def document(self) -> dict[str, Any]:
        """The package's current.json: every person with all their listings."""
        signature = self._signature()
        if signature is None:
            return {"snapshot": None, "candidates": []}
        if self._doc is None or self._doc[0] != signature:
            self._doc = (signature, json.loads(self.current_path.read_text(encoding="utf-8")))
            self._indexes = {}
        return self._doc[1]

    def meta(self) -> dict[str, Any]:
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}

    def etag(self) -> str:
        signature = self._signature()
        basis = json.dumps([self.meta().get("source_hashes"), signature], sort_keys=True)
        return '"' + hashlib.sha256(basis.encode()).hexdigest()[:32] + '"'

    def people(self, state: str | None = None) -> list[dict[str, Any]]:
        people = self.document().get("candidates", [])
        return [p for p in people if p.get("state") == state] if state else people

    def name_index(self, state: str) -> NameIndex:
        document = self.document()  # (re)loads, clearing indexes when the file changed
        if state not in self._indexes:
            index = NameIndex()
            for person in document.get("candidates", []):
                if person.get("state") == state and person.get("name"):
                    index.add(person["name"], person)
            self._indexes[state] = index
        return self._indexes[state]


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

    quotes = [note for item in listings for note in item.get("notes") or []]

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
