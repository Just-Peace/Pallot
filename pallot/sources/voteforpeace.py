"""Vote for Peace (voteforpeace.info) ratings, through the voteforpeace_cache package in this repo.

The package ships a snapshot of the site's All Candidates page. We copy it into
data/voteforpeace on first use, so lookups never call voteforpeace.info, and only fetch the
site when asked from the Settings page (the package's refresh() validates before writing and
writes only when the site changed). The site rates candidates at every level, from Congress to
a county's courts, so its entries are matched to races by seat and name (seats.py).
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any, Callable

import voteforpeace_cache
from voteforpeace_cache.models import SOURCE_URL

from ..matching import NameIndex
from ..models import Badge, Fact, Link, Match, Race, SourceCard, Tone
from ..offices import OfficeScope
from ..text import display_date, display_time, web_url
from . import CardSet
from .ballotpedia import BpBallot
from .seats import match_entries, office_text, without_title
from .snapshot import BundledSnapshot, summary_of

SOURCE = "voteforpeace"
LABEL = "Vote for Peace"
DESCRIPTION = (
    "Candidates rated Ally, Neutral or Opposed by Vote for Peace (voteforpeace.info, from Organize for Peace), "
    "on their stance on war, human rights and lobby money such as AIPAC's."
)
CANDIDATES_PAGE = SOURCE_URL
RATINGS = voteforpeace_cache.RATINGS  # "vote" -> "Ally"
FLAGS = {"vote": "ally", "reject": "opposed", "neutral": "neutral"}  # what Pick by rule tests
_TONES: dict[str, Tone] = {"vote": "good", "reject": "warn", "neutral": "info"}


class VoteForPeace(BundledSnapshot):
    """The package's current.json: {"snapshot", "candidates": [...]}, a row per candidate."""

    EMPTY = {"snapshot": None, "candidates": []}
    LABEL = LABEL

    def __init__(
        self,
        data_dir: Path,
        *,
        refresh_fn: Callable[..., Any] | None = None,
        bundled_dir: Path | None = None,
    ):
        super().__init__(data_dir, voteforpeace_cache, refresh_fn=refresh_fn, bundled_dir=bundled_dir)

    def _discard(self) -> None:
        shutil.rmtree(self.data_dir, ignore_errors=True)  # refreshes add history files too

    async def _refresh(self) -> str:
        refresh = self._refresh_fn or voteforpeace_cache.refresh
        return summary_of(await asyncio.to_thread(refresh, data_dir=self.data_dir))

    def people(self, state: str | None = None) -> list[dict[str, Any]]:
        people = self.document().get("candidates", [])
        return [p for p in people if p.get("state") == state] if state else people

    def name_index(self, state: str) -> NameIndex:
        def build(document: dict[str, Any]) -> NameIndex:
            index = NameIndex()
            for person in document.get("candidates", []):
                if person.get("state") == state and person.get("name"):
                    index.add(without_title(person["name"]), person)
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
            Fact(label="Texas candidates", value=f"{len(self.people('TX')):,}"),
            Fact(label="All candidates", value=f"{len(self.people()):,}"),
        ]


def card(person: dict[str, Any], match: Match, snapshot: str | None) -> SourceCard:
    rating = person.get("rating")
    label = RATINGS.get(rating or "", "Not rated")
    page = web_url(person.get("url")) or CANDIDATES_PAGE
    badges = [Badge(text=f"Vote for Peace: {label}", tone=_TONES.get(rating or "", "neutral"), url=page,
                    hint="How Vote for Peace rates them")]

    facts = [Fact(label="Rating", value=label), Fact(label="Office on Vote for Peace", value=office_text(person))]
    if person.get("party"):
        facts.append(Fact(label="Party on Vote for Peace", value=person["party"]))
    if person.get("election_label"):
        facts.append(Fact(label="Election", value=person["election_label"]))
    if person.get("election_result") not in (None, "pending"):
        facts.append(Fact(label="Result", value=person["election_result"].capitalize()))
    organizations = [e["organization"] for e in person.get("endorsements") or [] if e.get("organization")]
    if organizations:
        facts.append(Fact(label="Sources it cites", value=", ".join(organizations)))

    quotes = (person.get("notes") or "").splitlines()
    for article in person.get("articles") or []:
        title, url = article.get("title"), web_url(article.get("url"))
        head = f"[{title or url}]({url})" if url else title
        quotes.append(": ".join(filter(None, (head, article.get("description")))))

    links = []  # the candidate's page there is the card's own link
    for endorsement in person.get("endorsements") or []:
        if link := web_url(endorsement.get("link")):
            links.append(Link(label=f"{endorsement['organization']} (cited by Vote for Peace)", url=link))

    return SourceCard(
        source=SOURCE,
        label=LABEL,
        description=DESCRIPTION,
        url=page,
        as_of=snapshot,
        match=match,
        badges=badges,
        facts=facts,
        quotes=[quote for quote in quotes if quote],
        links=list({link.url: link for link in links}.values()),
        flags=[FLAGS[rating]] if rating in FLAGS else [],
    )


def cards(
    vfp: VoteForPeace,
    races: list[Race],
    scopes: dict[str, OfficeScope],
    county: str | None,
    bp_ballot: BpBallot | None = None,
) -> CardSet:
    """Cards for the candidates Vote for Peace rates in Texas, in any race (seats.match_entries)."""
    snapshot = vfp.document().get("snapshot")
    found = match_entries(vfp.name_index("TX"), races, scopes, county, bp_ballot, source=LABEL, entry_id="candidate_id")
    return CardSet(candidates={key: card(person, match, snapshot) for key, (person, match) in found.items()})
