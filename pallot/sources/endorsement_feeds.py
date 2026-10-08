"""Organizations' endorsement lists fetched from their own public JSON, through HttpCache, kept a
week (Ttls.endorsement_feeds), and the ones whose organizations agreed bundled with Pallot
(bundles/endorsement_feeds.py). Each organization is a Feed in FEEDS: its names, its endpoint, and
an adapter that turns its answer into an endorsement file's candidates (endorsements.read_entry
checks each, and leaves out one it refuses). Once fetched, a feed is an EndorsementList, so its
cards, matching and Pick by rule flag are the frozen lists'. What differs: the fetch, its pause
after a refusal, a refresh and clear by pallot-cache, and an answer the adapter can't read is refused
(HttpCache.check_answers), so it never replaces a good copy. A site that wants a token it rotates
has its list page fetched first, only when the list itself is (HttpCache.headers_from_page).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import html
import re
import threading
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Callable, Union

from ..config import DAY, HOUR, Ttls
from ..http_cache import Cached, HttpCache, RequestSpec, Unreadable, UpstreamError
from ..models import Fact, Race, Tone
from ..offices import OfficeScope
from ..text import display_time
from . import CardSet, RefreshFailed
from .ballotpedia import BpBallot
from .endorsements import BadList, EndorsementList, read_entry
from .seats import entry_seats

REFUSALS = (403, 429)  # answers that pause a feed for Ttls.endorsement_feeds_backoff
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class Feed:
    """One organization's live list. ``read`` is its adapter: the endpoint's JSON -> candidates in
    an endorsement file's shape (``name``, ``state``, ``office``, and optionally ``district``,
    ``jurisdiction``, ``party``, ``note``, ``url``), raising ValueError for an answer it can't read."""

    source: str  # its id: lowercase letters, digits and _, no other source's
    label: str  # the short name on badges, tabs and Settings
    organization: str  # its full name
    url: str  # the page people read the list on
    api: str  # the public JSON endpoint Pallot asks
    description: str  # one sentence for Settings and the Details tab
    read: Callable[[Any], list[dict[str, Any]]]
    headers: dict[str, str] | None = None  # any the endpoint needs; never a key
    token: Callable[[str], dict[str, str]] | None = None  # headers read from ``url``'s page, fetched just before ``api``


class FeedUnavailable(Exception):
    """The feed couldn't be fetched (refused, paused, down) and nothing was kept."""

    def __init__(self, label: str, reason: str):
        super().__init__(reason)
        self.label = label

    @property
    def warning(self) -> str:
        return f"Couldn't load {self.label}'s endorsements ({self})."


def _lifetime(seconds: float) -> str:
    """604800 -> "7 days", 3600 -> "1 hour"."""
    count, unit = (seconds / DAY, "day") if seconds >= DAY else (seconds / HOUR, "hour")
    return f"{count:g} {unit}{'' if count == 1 else 's'}"


class EndorsementFeed:
    """A Feed on the ballot and in Settings (a KeptSource whose responses are its HttpCache rows,
    under its source id). The parsed list is kept per stored copy (its ``fetched_at``)."""

    busy = False  # a fetch is one small request, never a download to wait for
    live = True

    def __init__(self, feed: Feed, cache: HttpCache, ttl: Ttls):
        self.feed = feed
        self.cache = cache
        self.ttl = ttl
        self._built: tuple[float, EndorsementList] | None = None
        self._lock = threading.Lock()
        cache.pause_on(feed.source, REFUSALS, ttl.endorsement_feeds_backoff)
        cache.check_answers(feed.source, self._check)
        if feed.token:
            cache.headers_from_page(feed.source, RequestSpec("GET", feed.url), feed.token)

    source = property(lambda self: self.feed.source)
    label = property(lambda self: self.feed.label)
    organization = property(lambda self: self.feed.organization)
    url = property(lambda self: self.feed.url)
    description = property(lambda self: self.feed.description)

    @property
    def spec(self) -> RequestSpec:
        return RequestSpec("GET", self.feed.api, headers=self.feed.headers)

    def entries(self, answer: Any) -> list[dict[str, Any]]:
        """The adapter's candidates, each checked as a file's would be; one it refuses is left out."""
        found: list[dict[str, Any]] = []
        for raw in self.feed.read(answer):
            try:
                found.append(read_entry(raw, len(found), self.feed.source))
            except BadList:
                continue
        return found

    def _check(self, answer: Any) -> str | None:
        try:
            found = self.entries(answer)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            return f"an answer Pallot can't read ({exc})"
        return None if found else "a list with no candidate Pallot can read"

    def _list(self, got: Cached) -> EndorsementList:
        with self._lock:
            if self._built and self._built[0] == got.fetched_at:
                return self._built[1]
            found = EndorsementList(
                source=self.source, label=self.label, organization=self.organization, url=self.url,
                captured=dt.date.fromtimestamp(got.fetched_at).isoformat(), description=self.description,
                entries=self.entries(got.value), live=True,
            )
            self._built = (got.fetched_at, found)
            return found

    def _kept(self) -> EndorsementList | None:
        """The stored copy's list, without asking anyone; None if none is kept, or it's refused."""
        got = self.cache.peek(self.spec)
        if got is None or self._check(got.value):
            return None
        return self._list(got)

    @property
    def captured(self) -> str | None:
        """The day the copy kept was fetched, for /api/endorsements."""
        kept = self._kept()
        return kept.captured if kept else None

    async def fetch(self) -> EndorsementList:
        try:
            got = await self.cache.get_json(self.source, self.spec, ttl=self.ttl.endorsement_feeds)
        except UpstreamError as exc:
            if exc.until:
                raise FeedUnavailable(self.label, f"paused until {display_time(exc.until)} after "
                                                  f"{self.organization}'s website refused a request") from exc
            raise FeedUnavailable(self.label, str(exc).removeprefix(f"{self.source}: ")) from exc
        return await asyncio.to_thread(self._list, got)

    async def lookup(
        self,
        races: list[Race],
        scopes: dict[str, OfficeScope],
        county: str | None,
        bp_ballot: BpBallot | None = None,
        state: str = "TX",
        city: str | None = None,
    ) -> CardSet:
        """The list's cards (EndorsementList.cards), fetched or from the copy kept."""
        found = await self.fetch()
        return await found.lookup(races, scopes, county, bp_ballot, state, city)

    # -- Settings (KeptSource) ----------------------------------------------------------------

    def notice(self) -> tuple[str, Tone]:
        got = self.cache.peek(self.spec)
        if got is None:
            return (f"Not fetched yet: the first lookup with it on fetches [{self.organization}'s list]({self.url}) "
                    "from its website."), "info"
        lifetime = next((saved.ttl for saved in self.cache.saved(self.source)), self.ttl.endorsement_feeds)
        return (f"Fetched from [{self.organization}'s website]({self.url}) on {display_time(got.fetched_at)}; "
                f"a lookup fetches it again once it's {_lifetime(lifetime)} old."), "info"

    def details(self) -> list[Fact]:
        kept = self._kept()
        if kept is None:
            return []
        states = kept.states()
        return [
            Fact(label="Texas candidates", value=f"{kept.count('TX'):,}"),
            Fact(label="All candidates", value=f"{kept.count():,} in {states} {'state' if states == 1 else 'states'}"),
        ]

    def size(self) -> int:
        return 0  # its copy is a cache row, counted with the cache

    def stale(self) -> str | None:
        return None  # its cache row has a lifetime, which pallot-cache checks

    async def refresh(self) -> str:
        """pallot-cache refreshed the copy kept already (its cache rows); with none, fetch it now."""
        if self.cache.peek(self.spec) is None:
            try:
                await self.fetch()
            except FeedUnavailable as exc:
                raise RefreshFailed(f"Couldn't fetch {self.label}'s list ({exc}).") from exc
        kept = self._kept()
        if kept is None:
            raise RefreshFailed(f"{self.label}'s list kept can't be read.")
        return f"{kept.count('TX'):,} of its {kept.count():,} candidates are in Texas."

    def clear(self) -> str:
        with self._lock:
            self._built = None
        return "The next lookup fetches the list again."


# -- the organizations ------------------------------------------------------------------------

MUPAC_SITE = "https://muslimsunitedpac.com"
_MUPAC_OFFICES = {"US HOUSE": "U.S. House", "US SENATE": "U.S. Senate"}


def _text(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def muslims_united(answer: Any) -> list[dict[str, Any]]:
    """Muslims United PAC's /api/public/endorsements: an object of categories ("incumbents",
    "challengers"), each a list of candidates (and counts, as "total", which are skipped). The
    office is "U.S. House" or "U.S. Senate" for its officeType "US House" or "US Senate" (with
    district "18", TX-18); otherwise its officeName ("Governor of Georgia") or officeType, the
    first that names a seat, or else the officeName ("Mayor of New York City"). Its jurisdiction
    ("federal", "state", "local") names no county, so it's left out. The note is its "ourTake",
    or the bio."""
    if not isinstance(answer, dict):
        raise ValueError("expected an object of categories")
    found: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for group in answer.values():
        if not isinstance(group, list):
            continue
        for raw in group:
            if not isinstance(raw, dict) or (raw.get("id") is not None and raw.get("id") in seen):
                continue
            seen.add(raw.get("id"))
            kind, name = _text(raw.get("officeType")), _text(raw.get("officeName"))
            federal = _MUPAC_OFFICES.get((kind or "").upper())
            office = federal or next(
                (title for title in (name, kind) if title and entry_seats(
                    {"state": raw.get("state"), "office_title": title, "district": raw.get("district")})),
                name or kind,
            )
            slug = _text(raw.get("slug"))
            found.append({
                "name": _text(raw.get("name")),
                "state": _text(raw.get("state")),
                "office": office,
                "district": raw.get("district"),
                "party": _text(raw.get("party")),
                "note": _text(raw.get("ourTake")) or _text(raw.get("bio")),
                "url": f"{MUPAC_SITE}/endorsements/{slug}" if slug and _SLUG.match(slug) else None,
            })
    return found


CAIR_SITE = "https://cairactionguide.org"
_CAIR_LEVELS = {  # its levels that endorse, and the site's own words on each
    "endorsed": "Endorsed: strong alignment, integrity, and clear community benefit.",
    "preferred": "Preferred: supportive overall and open to stronger partnership.",
    "joint endorsement": "Joint Endorsement: both are viable; choose one candidate.",
    "joint": "Joint Endorsement: both are viable; choose one candidate.",
}
_CAIR_OFFICES = {"congressional": "U.S. Representative", "state_lower": "State Representative",
                 "state_upper": "State Senator"}
_CAIR_LOCAL = ("county", "municipal", "judicial_district", "school_district", "special_district")
_CAIR_DISTRICT = re.compile(r"^[A-Z]{2}-(\d+)$|\b(?:District|LD|Precinct|Pct\.?)\s*(\d+)\b", re.IGNORECASE)
_CAIR_COUNTY = re.compile(r"^(.+?)\s+County\b")


def _cair_seat(raw: dict[str, Any]) -> dict[str, Any]:
    """An entry's state, office, district and county, from its jurisdiction (kind, name) and
    office (title). The district is its districtHint, or the number in the name ("TX-18", "State
    House District 131", "Fort Bend County Commissioner Pct 4"). The office is the title, or the
    kind's ("State Representative" for a "State Assembly Member"), the first that names a seat;
    else, for a local office, "<county> County <title>" when the name starts with a county
    ("Fort Bend County Judge"), which is then its jurisdiction, or else the name itself ("Houston
    City Council District C", without a district); else the title."""
    place = raw.get("jurisdiction") if isinstance(raw.get("jurisdiction"), dict) else {}
    office = raw.get("office") if isinstance(raw.get("office"), dict) else {}
    state, kind, title = _text(place.get("state")), _text(place.get("kind")), _text(office.get("title"))
    name = _text(place.get("name")) or ""
    number = _CAIR_DISTRICT.search(_text(raw.get("districtHint")) or name)
    district = str(int(number.group(1) or number.group(2))) if number else None
    county = _CAIR_COUNTY.match(name) if kind in _CAIR_LOCAL else None
    county = county.group(1) if county else None
    found = next((t for t in (title, _CAIR_OFFICES.get(kind or "")) if t and entry_seats(
        {"state": state, "office_title": t, "district": district})), None)
    if found is None and county and title:
        bare = re.sub(r"^County\s+", "", title)
        found = title if title.lower().startswith(f"{county} county".lower()) else f"{county} County {bare}"
    elif found is None and kind in _CAIR_LOCAL and name:
        found, district = name, None
    return {"state": state, "office": found or title or name, "district": district, "jurisdiction": county}


def cair_action(answer: Any) -> list[dict[str, Any]]:
    """CAIR Action Guide's /api/endorsements: a list of endorsements, one per candidate and
    election, so a candidate endorsed for a primary and its runoff is there twice; they're one
    entry, the latest election's (_cair_seat reads the seat). Only its endorsing levels count
    (not "Oppose" or "No Recommendation"), whatever the candidate's result in a primary. The note
    is the level, in the site's words, and its notes. The site has no page per candidate, so the
    link is the list's section for the state (its own permalink)."""
    if not isinstance(answer, list):
        raise ValueError("expected a list of endorsements")
    latest: dict[tuple[Any, ...], tuple[str, dict[str, Any]]] = {}
    for raw in answer:
        if not isinstance(raw, dict) or raw.get("status", "published") != "published":
            continue
        level = _CAIR_LEVELS.get((_text(raw.get("endorsementLevel")) or "").lower())
        name = _text(raw.get("candidateName"))
        if not level or not name:
            continue
        seat = _cair_seat(raw)
        state = seat["state"]
        election = raw.get("election") if isinstance(raw.get("election"), dict) else {}
        key = (raw.get("candidateId") or name.lower(), state, seat["office"], seat["district"], seat["jurisdiction"])
        when = str(election.get("electionDate") or "")
        notes = _text(raw.get("notes"))
        entry = {
            "name": name, **seat, "party": _text(raw.get("party")),
            "note": f"{level} {notes}" if notes else level,
            "url": f"{CAIR_SITE}/explore#state-{state.lower()}" if state and re.match(r"^[A-Z]{2}$", state) else None,
        }
        if key not in latest or when >= latest[key][0]:
            latest[key] = (when, entry)
    return [entry for _, entry in latest.values()]


class _Meta(HTMLParser):
    def __init__(self, name: str):
        super().__init__()
        self.name = name.lower()
        self.content: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        found = dict(attrs)
        if tag == "meta" and (found.get("name") or "").lower() == self.name and self.content is None:
            self.content = (found.get("content") or "").strip() or None


def meta_token(meta: str, header: str) -> Callable[[str], dict[str, str]]:
    """A Feed's ``token``: the page's ``<meta name=meta content=...>``, sent as ``header``."""

    def read(page: str) -> dict[str, str]:
        parser = _Meta(meta)
        parser.feed(page)
        if parser.content is None:
            raise Unreadable(f"its page has no {meta} to send")
        return {header: parser.content}

    return read


EMGAGE_SITE = "https://candidates.emgagepac.org"
EMGAGE_PAGE = f"{EMGAGE_SITE}/page/SupportOurCandidates"
_EMGAGE_PARTIES = {"D": "Democratic", "R": "Republican", "I": "Independent", "L": "Libertarian", "G": "Green"}
_EMGAGE_DISTRICT = re.compile(r"^([A-Z])-([A-Z]{2})(?:-0*(\d+))?$")


def _plain(value: Any) -> str | None:
    """HTML as its text: "<p>Chair&nbsp;of</p>" -> "Chair of"."""
    if not isinstance(value, str):
        return None
    text = re.sub(r"<[^>]*>", "", re.sub(r"<(?:br|/p|/div|/li|/h\d)\b[^>]*>", " ", value, flags=re.IGNORECASE))
    return " ".join(html.unescape(text).split()) or None


def emgage(answer: Any) -> list[dict[str, Any]]:
    """Emgage PAC's donation page: ``recipients``, each a candidate ("FederalCandidate"; other
    kinds are skipped) with its office ("U.S. House", "U.S. Senate") and ``district`` its party's
    letter, state and number: "D-TX-35", or "D-MI" for a senator (empty for some). The note is
    its teaser or description as plain text (most are only an image, so none). The page lists
    every candidate together, so none has a link of its own."""
    if not isinstance(answer, dict) or not isinstance(answer.get("recipients"), list):
        raise ValueError("expected an object with recipients")
    found: list[dict[str, Any]] = []
    for raw in answer["recipients"]:
        if not isinstance(raw, dict) or not str(raw.get("recipientType") or "").endswith("Candidate"):
            continue
        seat = _EMGAGE_DISTRICT.match((_text(raw.get("district")) or "").upper())
        party = seat.group(1) if seat else None
        found.append({
            "name": _text(raw.get("displayName")),
            "state": _text(raw.get("state")) or (seat.group(2) if seat else None),
            "office": _text(raw.get("office")),
            "district": seat.group(3) if seat else None,
            "party": _EMGAGE_PARTIES.get(party, party) if party else _text(raw.get("politicalParty")),
            "note": _plain(raw.get("profileTeaser")) or _plain(raw.get("description")),
        })
    return found


FEEDS = (
    Feed(
        source="mupac",
        label="Muslims United PAC",
        organization="Muslims United PAC",
        url=f"{MUPAC_SITE}/endorsements",
        api=f"{MUPAC_SITE}/api/public/endorsements",
        description="The candidates Muslims United PAC endorses, from the public list on its website. The list "
        "comes with Pallot, with its permission; once that copy is two days old, Pallot downloads the whole list "
        "again, so nothing about you is sent.",
        read=muslims_united,
    ),
    Feed(
        source="cair",
        label="CAIR Action",
        organization="CAIR Action",
        url=f"{CAIR_SITE}/explore",
        api=f"{CAIR_SITE}/api/endorsements",
        description="The candidates CAIR Action endorses or prefers, from the public list in its Action Guide. "
        "The list comes with Pallot, with its permission; once that copy is two days old, Pallot downloads the "
        "whole list again, so nothing about you is sent.",
        read=cair_action,
        headers={"accept": "*/*"},
    ),
    Feed(
        source="emgage",
        label="Emgage PAC",
        organization="Emgage PAC",
        url=EMGAGE_PAGE,
        api=f"{EMGAGE_SITE}/api/v2/donation-page/SupportOurCandidates",
        description="The candidates Emgage PAC endorses, from the list on its donation page. The list comes with "
        "Pallot, with its permission; once that copy is two days old, Pallot downloads that page, for the token the "
        "list asks for, and then the whole list again, so nothing about you is sent.",
        read=emgage,
        headers={"Accept": "application/json", "Content-Type": "application/json; charset=UTF-8", "Referer": EMGAGE_PAGE},
        token=meta_token("RequestVerificationToken", "RequestVerificationToken"),
    ),
)

EndorsementSource = Union[EndorsementList, EndorsementFeed]  # what Services.endorsements holds


def make_feeds(cache: HttpCache, ttl: Ttls) -> list[EndorsementFeed]:
    return [EndorsementFeed(feed, cache, ttl) for feed in FEEDS]
