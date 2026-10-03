"""What the Settings page shows and does: per-source status, on/off, refresh and clear."""

from __future__ import annotations

from dataclasses import dataclass

from .ballot import Services
from .models import ActionResult, CacheStatus, SourcesOverview, SourceStatus, Tone
from .sources import (
    KeptSource, RefreshFailed, ballotpedia, county_precincts, election_precincts, fec, key_dates, osm_tiles, polls,
    sos, suggestions, tec, tigerweb, trackaipac,
)
from .text import display_size, display_time, iso_utc


@dataclass(frozen=True)
class Pause:
    """How Settings words a pause: "Paused until <time> after <after>; <kept>."."""

    after: str
    kept: str


@dataclass(frozen=True)
class SourceInfo:
    id: str
    label: str
    description: str
    toggleable: bool
    cache_tags: tuple[str, ...]  # HttpCache source names holding this source's responses
    refresh_label: str = "Refresh now"
    clear_label: str = "Clear cache"
    resettable: bool = False  # a bundled snapshot rather than cached responses: "clear" resets to it
    refresh_confirm: str | None = None  # asked before refreshing: what a refresh sends or downloads
    pause: Pause | None = None  # the source can be paused after refusing a request (HttpCache.pause_on)
    refreshable: bool = True  # False: no Refresh, since a bulk re-download isn't allowed (OpenStreetMap's tiles)
    kept: str | None = None  # the Services field of a source kept in files (KeptSource), asked for its row


SOURCES = (
    SourceInfo(
        "geocoding",
        "Address lookup & districts",
        "US Census geocoder (county and districts), OpenStreetMap Nominatim when the Census can't match an "
        "address, and the Texas Legislative Council's State Board of Education map. Always on.",
        False,
        ("census", "nominatim"),
        refresh_confirm="Refresh sends every saved address to the US Census geocoder again (and to OpenStreetMap "
        "Nominatim the ones the Census couldn't match), and downloads the State Board of Education map again. Continue?",
        kept="sboe",
    ),
    SourceInfo(
        election_precincts.SOURCE,
        "Election precincts (Texas Legislative Council)",
        election_precincts.DESCRIPTION,
        True,
        (election_precincts.SOURCE,),
        refresh_confirm="Refresh asks the Texas Legislative Council for its newest precinct map and, if it's newer than "
        "the one kept, downloads it ({size}). Continue?",
        pause=Pause("the Texas Legislative Council's portal refused a request", "the precinct map already kept still shows"),
        kept="election_precincts",
    ),
    SourceInfo(
        county_precincts.SOURCE,
        "Commissioner & JP precincts (counties)",
        county_precincts.DESCRIPTION,
        True,
        (county_precincts.SOURCE,),
        pause=Pause("a county's map server refused a request", "what the counties already sent still shows"),
    ),
    SourceInfo(
        tigerweb.SOURCE, "District map (US Census TIGERweb)", tigerweb.DESCRIPTION, True, (tigerweb.SOURCE,),
        pause=Pause("the Census's map service refused a request", "outlines it already sent still show"),
    ),
    SourceInfo(
        osm_tiles.SOURCE, "Street map (OpenStreetMap)", osm_tiles.DESCRIPTION, True, (osm_tiles.SOURCE,),
        pause=Pause("OpenStreetMap's tile server refused a request", "tiles it already sent still show"),
        refreshable=False,
    ),
    SourceInfo(
        suggestions.SOURCE,
        "Address suggestions (Ballotpedia)",
        suggestions.DESCRIPTION,
        True,
        (suggestions.SOURCE,),
        refresh_confirm="Refresh sends everything saved from the address box to Ballotpedia again, one request every "
        "half second. Continue?",
        pause=Pause("Ballotpedia refused an address search", "suggestions it already sent still show"),
    ),
    SourceInfo(sos.SOURCE, "Texas Secretary of State", sos.DESCRIPTION, True, (sos.SOURCE,)),
    SourceInfo(
        key_dates.SOURCE, "Key election dates (Texas SOS)", key_dates.DESCRIPTION, True, (key_dates.SOURCE,),
        pause=Pause("the Texas SOS website refused a request", "dates it already sent still show"),
    ),
    SourceInfo(
        ballotpedia.SOURCE, "Ballotpedia", ballotpedia.DESCRIPTION, True, (ballotpedia.SOURCE,),
        pause=Pause("Ballotpedia refused a request", "ballots it already sent still show"),
    ),
    SourceInfo(
        trackaipac.SOURCE,
        "TrackAIPAC",
        trackaipac.DESCRIPTION,
        True,
        (),
        refresh_label="Refresh from trackaipac.com",
        clear_label="Reset to bundled snapshot",
        resettable=True,
        kept="trackaipac",
    ),
    SourceInfo(
        fec.SOURCE, "FEC (Federal Election Commission)", fec.DESCRIPTION, True, (fec.SOURCE,),
        pause=Pause("reaching the FEC's rate limit", "what it already sent still shows"),
    ),
    SourceInfo(
        tec.SOURCE,
        "Texas Ethics Commission",
        tec.DESCRIPTION,
        True,
        (),
        refresh_label="Refresh from the Texas Ethics Commission (downloads about 1 GB if it changed)",
        clear_label="Reset to bundled snapshot",
        resettable=True,
        refresh_confirm="Refresh first asks the Texas Ethics Commission whether its data has changed. If it has, it "
        "downloads about 1 GB (a minute or two on a fast connection) and rebuilds the data. Continue?",
        kept="tec",
    ),
    SourceInfo(
        polls.SOURCE, "Polls (FiftyPlusOne)", polls.DESCRIPTION, True, (polls.SOURCE,),
        pause=Pause("FiftyPlusOne refused a request", "polls it already sent still show"),
    ),
)
BY_ID = {info.id: info for info in SOURCES}
_SLOW = {"ballotpedia", "nominatim", "polls", "suggestions"}  # one request at a time when refreshing


class AdminError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class Admin:
    def __init__(self, svc: Services):
        self.svc = svc
        self._busy: set[str] = set()

    def _info(self, source_id: str) -> SourceInfo:
        if source_id not in BY_ID:
            raise AdminError(404, f"Unknown source: {source_id}")
        return BY_ID[source_id]

    def _kept(self, info: SourceInfo) -> KeptSource | None:
        return getattr(self.svc, info.kept) if info.kept else None

    def _all_kept(self) -> list[KeptSource]:
        return [kept for info in SOURCES if (kept := self._kept(info))]

    def overview(self) -> SourcesOverview:
        return SourcesOverview(
            sources=[self._status(info) for info in SOURCES],
            total_bytes=self.svc.cache.file_bytes() + sum(kept.size() for kept in self._all_kept()),
            last_lookup=self.svc.last_lookup,
            clear_all_confirm=self._clear_all_confirm(),
        )

    @staticmethod
    def _clear_all_confirm() -> str:
        snapshots = " and ".join(info.label for info in SOURCES if info.resettable)
        return (f"Clear everything the server saved from every source? The {snapshots} data go back to the snapshots "
                "that came with VoteBot, and the next lookups fetch everything again.")

    @staticmethod
    def _clear_confirm(info: SourceInfo) -> str:
        if info.resettable:
            return f"Throw away refreshed {info.label} data and go back to the bundled snapshot?"
        return f"Clear everything cached from {info.label}? The next lookup will fetch it again."

    def _running(self, info: SourceInfo) -> bool:
        """A refresh from Settings, or a source kept in files downloading for a lookup."""
        kept = self._kept(info)
        return info.id in self._busy or (kept is not None and kept.busy)

    def _refresh_confirm(self, info: SourceInfo) -> str | None:
        kept = self._kept(info)
        if info.refresh_confirm is None or kept is None:
            return info.refresh_confirm
        size = kept.refresh_size()
        return info.refresh_confirm.format(size=display_size(size) if size else "a large file")

    def _status(self, info: SourceInfo) -> SourceStatus:
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
        kept = self._kept(info)
        return SourceStatus(
            id=info.id,
            label=info.label,
            description=info.description,
            toggleable=info.toggleable,
            resettable=info.resettable,
            enabled=self.svc.settings.enabled(info.id) if info.toggleable else True,
            busy=self._running(info),
            cache=cache,
            details=kept.details() if kept else [],
            refresh_label=info.refresh_label,
            clear_label=info.clear_label,
            refresh_confirm=self._refresh_confirm(info),
            clear_confirm=self._clear_confirm(info),
            refreshable=info.refreshable,
            notice=notice,
            notice_tone=tone,
            last_use=self.svc.last_uses.get(info.id),
        )

    def _paused(self, info: SourceInfo) -> str | None:
        """ "Paused until …" while the source is paused after refusing a request."""
        if info.pause is None:
            return None
        until = max(filter(None, (self.svc.cache.paused_until(tag) for tag in info.cache_tags)), default=None)
        if until is None:
            return None
        return f"Paused until {display_time(until)} after {info.pause.after}; {info.pause.kept}."

    def _notice(self, info: SourceInfo) -> tuple[str | None, Tone]:
        """One line under the source's description: what it's missing, or where its data stands."""
        paused = self._paused(info)
        if info.id == fec.SOURCE:
            if not self.svc.fec.keyed:
                return " ".join(filter(None, (
                    paused,
                    "Using the shared DEMO_KEY, so federal races show totals only. For the full breakdown, set "
                    f"VOTEBOT_FEC_API_KEY to a [free key from the OpenFEC developers page]({fec.KEY_SIGNUP}) and restart "
                    "VoteBot.",
                ))), "warn"
            return (paused, "warn") if paused else ("Using your api.data.gov key.", "info")
        if paused:
            return paused, "warn"
        kept = self._kept(info)
        return (kept.notice() if kept else None) or (None, "info")

    def set_enabled(self, source_id: str, enabled: bool) -> None:
        if not self._info(source_id).toggleable:
            raise AdminError(400, "This source is required and can't be turned off.")
        self.svc.settings.set_enabled(source_id, enabled)

    async def refresh(self, source_id: str) -> ActionResult:
        info = self._info(source_id)
        if not info.refreshable:
            raise AdminError(400, f"{info.label} is only fetched as you look at it, never all at once.")
        if self._running(info):
            raise AdminError(409, f"{info.label} is already refreshing.")
        self._busy.add(source_id)
        try:
            return ActionResult(message=await self._refresh(info))
        finally:
            self._busy.discard(source_id)

    async def _refresh(self, info: SourceInfo) -> str:
        """Its cached responses, then what it keeps in files. When those files are all the row
        has, a refresh that changed nothing is a 502; otherwise it's a sentence in the message."""
        parts: list[str] = []
        refreshed = failed = skipped = 0
        errors: list[str] = []
        paused_until: float | None = None
        for tag in info.cache_tags:
            report = await self.svc.cache.refresh(tag, concurrency=1 if tag in _SLOW else 3)
            refreshed += report.refreshed
            failed += report.failed
            skipped += report.skipped
            errors += report.errors
            paused_until = paused_until or report.paused_until
        if info.cache_tags:
            parts.append(f"Refreshed {refreshed} cached response{'s' if refreshed != 1 else ''}.")
        if kept := self._kept(info):
            try:
                parts.append(await kept.refresh())
            except RefreshFailed as exc:
                if not info.cache_tags:
                    raise AdminError(502, str(exc)) from exc
                parts.append(str(exc))
        if failed:
            parts.append(f"{failed} failed and kept their old copy ({'; '.join(errors)}).")
        if paused_until:
            parts.append(f"{info.label} is paused until {display_time(paused_until)} after refusing a request"
                         + (f", so {skipped} weren't asked." if skipped else "."))
        return " ".join(parts)

    def clear(self, source_id: str) -> ActionResult:
        info = self._info(source_id)
        if self._running(info):
            raise AdminError(409, f"{info.label} is refreshing; try again when it's done.")
        parts: list[str] = []
        if info.cache_tags:
            removed = sum(self.svc.cache.clear(tag) for tag in info.cache_tags)
            parts.append(f"Cleared {removed} cached response{'s' if removed != 1 else ''}.")
        if kept := self._kept(info):
            parts.append(kept.clear())
        return ActionResult(message=" ".join(parts))

    def clear_all(self) -> ActionResult:
        kept = self._all_kept()
        if self._busy or any(source.busy for source in kept):
            raise AdminError(409, "A refresh is running; try again when it's done.")
        removed = self.svc.cache.clear()
        for source in kept:
            source.clear()
        return ActionResult(
            message=f"Cleared {removed} cached responses, the SBOE map and the precinct map, and reset TrackAIPAC and "
            "the Texas Ethics Commission data to their bundled snapshots."
        )
