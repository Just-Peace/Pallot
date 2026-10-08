"""What the Settings page shows about each source: on or off for this voter, what the server
keeps, and how the last lookup used it. Refreshing and clearing what the server keeps is
pallot-cache's (maintain.py), run on the host, never the page's."""

from __future__ import annotations

from dataclasses import dataclass

from .ballot import Services
from .models import CacheStatus, SourceGroupInfo, SourcesOverview, SourceStatus, Tone
from .settings import Sources
from .sources import (
    KeptSource, ballotpedia, county_precincts, election_precincts, fec, google, key_dates, officeholders, osm_tiles,
    polls, sos, suggestions, tec, tigerweb, trackaipac, voteforpeace,
)
from .sources.endorsement_feeds import EndorsementSource
from .text import display_time, iso_utc


@dataclass(frozen=True)
class Pause:
    """How Settings words a pause: "Paused until <time> after <after>; <kept>."."""

    after: str
    kept: str


@dataclass(frozen=True)
class SourceGroup:
    """A heading Settings draws its sources under, in GROUPS' order."""

    id: str
    title: str
    description: str
    toggle_all: bool = False  # Settings offers "Turn all on" and "Turn all off" for it


ADDRESS, OFFICIAL, BALLOT, POLLS, SCORECARDS = "address", "official", "ballot", "polls", "scorecards"
GROUPS = (
    SourceGroup(ADDRESS, "Address lookup & maps", "Find your districts and precincts from your address, draw them on "
                "a map, and suggest addresses as you type."),
    SourceGroup(OFFICIAL, "Official ballot data", "Government sources: the state's ballot and election dates, and the "
                "campaign money reported to the FEC and the Texas Ethics Commission."),
    SourceGroup(BALLOT, "Third-party ballot data", "Not official, but it fills in what the state doesn't publish: local "
                "races, notes on a race, candidate profiles and who holds each seat."),
    SourceGroup(POLLS, "Third-party polls", "Public polls of the races that have them, gathered by an independent site."),
    SourceGroup(SCORECARDS, "Third-party endorsements", "Organizations that endorse or warn against "
                "candidates, most of them on Palestinian rights, U.S. military aid to Israel and pro-Israel lobby money. "
                "Each adds badges to the candidates it covers.", toggle_all=True),
)


@dataclass(frozen=True)
class SourceInfo:
    id: str
    label: str
    description: str
    toggleable: bool
    cache_tags: tuple[str, ...]  # HttpCache source names holding this source's responses
    group: str  # the id of its SourceGroup
    bundled: bool = False  # a bundled snapshot rather than cached responses: a clear resets to it
    pause: Pause | None = None  # the source can be paused after refusing a request (HttpCache.pause_on)
    refreshable: bool = True  # False: never refreshed in bulk, only fetched as it's viewed (OpenStreetMap's tiles)
    kept: str | None = None  # the Services field of a source kept in files (KeptSource), asked for its row
    frozen: bool = False  # comes with Pallot as captured and is never fetched: nothing to refresh or clear


SOURCES = (
    SourceInfo(
        "geocoding",
        "Address lookup & districts",
        "US Census geocoder (county and districts), OpenStreetMap Nominatim when the Census can't match an "
        "address, and the Texas Legislative Council's State Board of Education map.",
        False,
        ("census", "nominatim"),
        group=ADDRESS,
        pause=Pause("the address lookup refused a request", "addresses already looked up still work"),
        kept="sboe",
    ),
    SourceInfo(
        google.SOURCE, "Address lookup fallback (Google)", google.DESCRIPTION, True, (google.SOURCE,),
        group=ADDRESS,
        pause=Pause("Google refused an address lookup", "addresses it already found still work"),
        refreshable=False,
    ),
    SourceInfo(
        election_precincts.SOURCE,
        "Election precincts (Texas Legislative Council)",
        election_precincts.DESCRIPTION,
        True,
        (election_precincts.SOURCE,),
        group=ADDRESS,
        pause=Pause("the Texas Legislative Council's portal refused a request", "the precinct map already kept still shows"),
        kept="election_precincts",
    ),
    SourceInfo(
        county_precincts.SOURCE,
        "Commissioner & JP precincts (counties)",
        county_precincts.DESCRIPTION,
        True,
        (county_precincts.SOURCE,),
        group=ADDRESS,
        pause=Pause("a county's map server refused a request", "what the counties already sent still shows"),
    ),
    SourceInfo(
        tigerweb.SOURCE, "District map (US Census TIGERweb)", tigerweb.DESCRIPTION, True, (tigerweb.SOURCE,),
        group=ADDRESS,
        pause=Pause("the Census's map service refused a request", "outlines it already sent still show"),
    ),
    SourceInfo(
        osm_tiles.SOURCE, "Street map (OpenStreetMap)", osm_tiles.DESCRIPTION, True, (osm_tiles.SOURCE,),
        group=ADDRESS,
        pause=Pause("OpenStreetMap's tile server refused a request", "tiles it already sent still show"),
        refreshable=False,
    ),
    SourceInfo(
        suggestions.SOURCE,
        "Address suggestions (Ballotpedia)",
        suggestions.DESCRIPTION,
        True,
        (suggestions.SOURCE,),
        group=ADDRESS,
        pause=Pause("Ballotpedia refused an address search", "suggestions it already sent still show"),
        refreshable=False,
    ),
    SourceInfo(
        sos.SOURCE, "Texas Secretary of State (Texas SOS)", sos.DESCRIPTION, True, (sos.SOURCE,),
        group=OFFICIAL,
        pause=Pause("Texas SOS refused a request", "ballots it already sent still show"),
    ),
    SourceInfo(
        key_dates.SOURCE, "Key election dates (Texas SOS)", key_dates.DESCRIPTION, True, (key_dates.SOURCE,),
        group=OFFICIAL,
        pause=Pause("the Texas SOS website refused a request", "dates it already sent still show"),
    ),
    SourceInfo(
        ballotpedia.SOURCE, "Ballotpedia", ballotpedia.DESCRIPTION, True, (ballotpedia.SOURCE,),
        group=BALLOT,
        pause=Pause("Ballotpedia refused a request", "ballots it already sent still show"),
    ),
    SourceInfo(
        officeholders.SOURCE, "Seat holders (congress-legislators, Open States)", officeholders.DESCRIPTION, True,
        (officeholders.SOURCE,),
        group=BALLOT,
        pause=Pause("a list of seat holders was refused", "the lists already fetched still show"),
    ),
    SourceInfo(
        trackaipac.SOURCE,
        "TrackAIPAC",
        trackaipac.DESCRIPTION,
        True,
        (),
        group=SCORECARDS,
        bundled=True,
        kept="trackaipac",
    ),
    SourceInfo(
        voteforpeace.SOURCE,
        voteforpeace.LABEL,
        voteforpeace.DESCRIPTION,
        True,
        (),
        group=SCORECARDS,
        bundled=True,
        kept="voteforpeace",
    ),
    SourceInfo(
        fec.SOURCE, "FEC (Federal Election Commission)", fec.DESCRIPTION, True, (fec.SOURCE,),
        group=OFFICIAL,
        pause=Pause("every key reached the FEC's rate limit or was refused", "what it already sent still shows"),
    ),
    SourceInfo(
        tec.SOURCE,
        "Texas Ethics Commission (TEC)",
        tec.DESCRIPTION,
        True,
        (),
        group=OFFICIAL,
        bundled=True,
        kept="tec",
    ),
    SourceInfo(
        polls.SOURCE, "Polls (FiftyPlusOne)", polls.DESCRIPTION, True, (polls.SOURCE,),
        group=POLLS,
        pause=Pause("FiftyPlusOne refused a request", "polls it already sent still show"),
    ),
)


def list_info(found: EndorsementSource) -> SourceInfo:
    """An endorsement list's row: its own switch, and nothing to refresh or clear; a live feed's
    also has its cached copy (under its id), and a pause."""
    if found.live:
        return SourceInfo(found.source, f"{found.label} endorsements", found.description, True, (found.source,),
                          SCORECARDS, pause=Pause(f"{found.organization}'s website refused a request",
                                      "the list already fetched still shows"))
    return SourceInfo(found.source, f"{found.label} endorsements", found.description, True, (), SCORECARDS,
                      refreshable=False, frozen=True)


def all_sources(lists: list[EndorsementSource]) -> tuple[SourceInfo, ...]:
    """SOURCES, with the endorsement lists and feeds after Vote for Peace."""
    at = next(i for i, info in enumerate(SOURCES) if info.id == voteforpeace.SOURCE) + 1
    return (*SOURCES[:at], *(list_info(found) for found in lists), *SOURCES[at:])


class Admin:
    def __init__(self, svc: Services):
        self.svc = svc
        self.sources = all_sources(svc.endorsements)
        self._kept_sources: dict[str, KeptSource] = {
            **{info.id: getattr(svc, info.kept) for info in SOURCES if info.kept},
            **{found.source: found for found in svc.endorsements},
        }

    def kept(self, info: SourceInfo) -> KeptSource | None:
        return self._kept_sources.get(info.id)

    def overview(self, sources: Sources) -> SourcesOverview:
        """Every source's row, on or off as ``sources`` (this voter's choices) has it."""
        return SourcesOverview(
            groups=[SourceGroupInfo(id=g.id, title=g.title, description=g.description, toggle_all=g.toggle_all)
                    for g in GROUPS],
            sources=[self._status(info, sources) for info in self.sources],
            total_bytes=self.svc.cache.file_bytes() + sum(kept.size() for kept in self._kept_sources.values()),
            last_lookup=self.svc.last_lookup,
        )

    def _status(self, info: SourceInfo, sources: Sources) -> SourceStatus:
        stats = [self.svc.cache.stats(tag) for tag in info.cache_tags]
        oldest = [s.oldest for s in stats if s.oldest is not None]
        newest = [s.newest for s in stats if s.newest is not None]
        cache = CacheStatus(
            entries=sum(s.entries for s in stats),
            bytes=sum(s.bytes for s in stats),
            expired=sum(s.expired for s in stats),
            oldest=iso_utc(min(oldest)) if oldest else None,
            newest=iso_utc(max(newest)) if newest else None,
        )
        notice, tone = self._notice(info)
        kept = self.kept(info)
        return SourceStatus(
            id=info.id,
            label=info.label,
            description=info.description,
            group=info.group,
            toggleable=info.toggleable,
            bundled=info.bundled,
            enabled=sources.enabled(info.id) if info.toggleable else True,
            busy=kept is not None and kept.busy,
            cache=cache,
            details=kept.details() if kept else [],
            frozen=info.frozen,
            notice=notice,
            notice_tone=tone,
            last_use=self.svc.last_uses.get(info.id),
        )

    def paused(self, info: SourceInfo) -> str | None:
        """ "Paused until …" while the source is paused after refusing a request."""
        if info.pause is None:
            return None
        until = max(filter(None, (self.svc.cache.paused_until(tag) for tag in info.cache_tags)), default=None)
        if until is None:
            return None
        return f"Paused until {display_time(until)} after {info.pause.after}; {info.pause.kept}."

    def _notice(self, info: SourceInfo) -> tuple[str | None, Tone]:
        """One line under the source's description: what it's missing, or where its data stands."""
        paused = self.paused(info)
        if info.id == fec.SOURCE:
            return self._fec_notice(info)
        if info.id == google.SOURCE:
            return (paused, "warn") if paused else ((None, "info") if self.svc.google.keyed else (google.KEY_NOTE, "warn"))
        if paused:
            return paused, "warn"
        kept = self.kept(info)
        return (kept.notice() if kept else None) or (None, "info")

    def _fec_notice(self, info: SourceInfo) -> tuple[str | None, Tone]:
        """Which keys the FEC is asked with, and why any rest: paused once every key does."""
        svc = self.svc.fec
        trouble = svc.key_trouble()
        rests = self.svc.cache.key_rests(fec.SOURCE)
        if until := self.svc.cache.paused_until(fec.SOURCE):
            state = f"Paused until {display_time(until)}: {trouble}; {info.pause.kept}."
        elif trouble:
            soonest = min(rest.until for rest in rests if rest)
            state = (f"Using {rests.count(None)} of your {len(rests)} api.data.gov keys until {display_time(soonest)}: "
                     f"{trouble}.")
        else:
            state = None
        snapshot = svc.snapshot_note()
        if not svc.keyed:
            return " ".join(filter(None, (state, snapshot, f"Using the shared DEMO_KEY. {fec.KEY_NOTE}"))), "warn"
        if state:
            return " ".join(filter(None, (state, snapshot))), "warn"
        keys = "Using your api.data.gov key." if len(rests) == 1 else f"Using your {len(rests)} api.data.gov keys in turn."
        return " ".join(filter(None, (snapshot, keys))), "info"
