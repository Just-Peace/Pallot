"""What the Settings page shows and does: per-source status, on/off, refresh and clear."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from .ballot import Services
from .http_cache import UpstreamError, describe_error
from .models import ActionResult, CacheStatus, Fact, SourcesOverview, SourceStatus, Tone
from .sources import (
    ballotpedia, election_precincts, fec, key_dates, osm_tiles, photon, polls, sos, tec, tigerweb, trackaipac,
)
from .text import display_date, display_time, iso_utc


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
        photon.SOURCE,
        "Address suggestions",
        photon.DESCRIPTION,
        True,
        (photon.SOURCE,),
        refresh_confirm="Refresh sends everything saved from the address box to Photon again, one request every half "
        "second. Continue?",
        pause=Pause("Photon refused a request", "suggestions it already sent still show"),
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
    ),
    SourceInfo(
        polls.SOURCE, "Polls (FiftyPlusOne)", polls.DESCRIPTION, True, (polls.SOURCE,),
        pause=Pause("FiftyPlusOne refused a request", "polls it already sent still show"),
    ),
)
BY_ID = {info.id: info for info in SOURCES}
_SLOW = {"ballotpedia", "nominatim", "photon", "polls"}  # one request at a time when refreshing


class AdminError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _size(num: int) -> str:
    return f"{num / 1_048_576:.1f} MB" if num >= 1_048_576 else f"{num / 1024:.0f} KB"


def _dir_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.exists() else 0


class Admin:
    def __init__(self, svc: Services):
        self.svc = svc
        self._busy: set[str] = set()

    def _info(self, source_id: str) -> SourceInfo:
        if source_id not in BY_ID:
            raise AdminError(404, f"Unknown source: {source_id}")
        return BY_ID[source_id]

    def overview(self) -> SourcesOverview:
        snapshots = _dir_bytes(self.svc.trackaipac.data_dir) + _dir_bytes(self.svc.tec.data_dir)
        maps = self.svc.sboe.size() + self.svc.election_precincts.size()
        return SourcesOverview(
            sources=[self._status(info) for info in SOURCES],
            total_bytes=self.svc.cache.file_bytes() + maps + snapshots,
            last_lookup=self.svc.last_lookup,
        )

    def _running(self, source_id: str) -> bool:
        """A refresh from Settings, or the precinct map downloading for a lookup."""
        return source_id in self._busy or (
            source_id == election_precincts.SOURCE and self.svc.election_precincts.downloading
        )

    def _refresh_confirm(self, info: SourceInfo) -> str | None:
        if info.id != election_precincts.SOURCE or info.refresh_confirm is None:
            return info.refresh_confirm
        listed = self.svc.election_precincts.newest_listed()
        return info.refresh_confirm.format(size=_size(listed.size) if listed else "a large file")

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
        return SourceStatus(
            id=info.id,
            label=info.label,
            description=info.description,
            toggleable=info.toggleable,
            resettable=info.resettable,
            enabled=self.svc.settings.enabled(info.id) if info.toggleable else True,
            busy=self._running(info.id),
            cache=cache,
            details=self._details(info.id),
            refresh_label=info.refresh_label,
            clear_label=info.clear_label,
            refresh_confirm=self._refresh_confirm(info),
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
        source_id = info.id
        paused = self._paused(info)
        if source_id == fec.SOURCE:
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
        if source_id == election_precincts.SOURCE:
            precincts = self.svc.election_precincts
            if precincts.downloading:
                return "Downloading the precinct map…", "info"
            if precincts.last_error:
                kept = "the map kept still shows" if precincts.stored() else "Refresh tries again"
                return f"The last download of the precinct map failed ({precincts.last_error}); {kept}.", "warn"
        if source_id in (trackaipac.SOURCE, tec.SOURCE):
            snapshot = self.svc.trackaipac if source_id == trackaipac.SOURCE else self.svc.tec
            if snapshot.last_error:
                return f"The last refresh failed and nothing changed: {snapshot.last_error}", "warn"
        if source_id == tec.SOURCE:
            document = self.svc.tec.document()
            if not document.get("snapshot"):
                return "No snapshot yet: refresh to download one from the Texas Ethics Commission.", "warn"
            since = display_date((document.get("window") or {}).get("start"))
            return f"Snapshot of {display_date(document['snapshot'])}: money raised since {since}.", "info"
        return None, "info"

    def _details(self, source_id: str) -> list[Fact]:
        if source_id == "geocoding":
            sboe = self.svc.sboe
            downloaded = sboe.downloaded_at()
            value = (
                f"downloaded {display_time(downloaded)} · {_size(sboe.size())}"
                if downloaded else "fetched on the first lookup"
            )
            return [Fact(label="SBOE map", value=value)]
        if source_id == election_precincts.SOURCE:
            precincts = self.svc.election_precincts
            stored, listed = precincts.stored(), precincts.newest_listed()
            kept = (
                f"“{stored.resource.label}”, downloaded {display_time(stored.downloaded_at)} · {_size(precincts.size())}"
                if stored else "downloaded on the first lookup"
            )
            return [
                Fact(label="Map kept", value=kept),
                Fact(label="Newest on the portal", value=f"“{listed.label}” · {_size(listed.size)}" if listed else "not asked yet"),
            ]
        if source_id == "trackaipac":
            tracker = self.svc.trackaipac
            meta = tracker.meta()
            return [
                Fact(label="Snapshot", value=display_date(meta.get("latest_snapshot")) or "none"),
                Fact(label="Last changed", value=display_time(meta.get("last_refresh")) or "never"),
                Fact(label="Last checked", value=display_time(meta.get("last_checked")) or "never"),
                Fact(label="Texas entries", value=str(len(tracker.people("TX")))),
                Fact(label="All entries", value=str(len(tracker.people()))),
            ]
        if source_id == tec.SOURCE:
            document, meta = self.svc.tec.document(), self.svc.tec.meta()
            return [
                Fact(label="Snapshot", value=display_date(document.get("snapshot")) or "none"),
                Fact(label="Money raised since", value=display_date((document.get("window") or {}).get("start")) or "unknown"),
                Fact(label="TEC data from", value=display_time(document.get("tec_updated")) or "unknown"),
                Fact(label="Last checked", value=display_time(meta.get("last_checked")) or "never"),
                Fact(label="Candidates and officeholders", value=str(len(document.get("filers") or []))),
            ]
        return []

    def set_enabled(self, source_id: str, enabled: bool) -> None:
        if not self._info(source_id).toggleable:
            raise AdminError(400, "This source is required and can't be turned off.")
        self.svc.settings.set_enabled(source_id, enabled)

    async def refresh(self, source_id: str) -> ActionResult:
        info = self._info(source_id)
        if not info.refreshable:
            raise AdminError(400, f"{info.label} is only fetched as you look at it, never all at once.")
        if self._running(source_id):
            raise AdminError(409, f"{info.label} is already refreshing.")
        self._busy.add(source_id)
        try:
            if source_id == trackaipac.SOURCE:
                try:
                    return ActionResult(message=await self.svc.trackaipac.refresh())
                except Exception as exc:  # the package raises FetchError/ValidationError without writing anything
                    raise AdminError(502, f"TrackAIPAC refresh failed; nothing changed. {exc}") from exc
            if source_id == tec.SOURCE:
                try:
                    return ActionResult(message=await self.svc.tec.refresh())
                except Exception as exc:  # tec_cache writes nothing unless the whole refresh succeeds
                    raise AdminError(502, f"Texas Ethics Commission refresh failed; nothing changed. {exc}") from exc
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
            message = f"Refreshed {refreshed} cached response{'s' if refreshed != 1 else ''}."
            if source_id == "geocoding":
                try:
                    await self.svc.sboe.download()
                except (httpx.HTTPError, ValueError, OSError, zipfile.BadZipFile) as exc:  # nothing was replaced
                    kept = "kept the old one" if self.svc.sboe.downloaded_at() else "the next lookup will try again"
                    message += f" Couldn't re-download the State Board of Education map ({describe_error(exc)}); {kept}."
                else:
                    message += " Re-downloaded the State Board of Education map."
            if source_id == election_precincts.SOURCE:
                precincts = self.svc.election_precincts
                try:
                    message += f" {await precincts.update()}"
                except (UpstreamError, OSError, ValueError, zipfile.BadZipFile) as exc:  # nothing was replaced
                    why = str(exc).removeprefix(f"{election_precincts.SOURCE}: ")
                    kept = "kept the old one" if precincts.stored() else "the next lookup will try again later"
                    message += f" Couldn't download the precinct map ({why}); {kept}."
            if failed:
                message += f" {failed} failed and kept their old copy ({'; '.join(errors)})."
            if paused_until:
                message += (f" {info.label} is paused until {display_time(paused_until)} after refusing a request"
                            + (f", so {skipped} weren't asked." if skipped else "."))
            return ActionResult(message=message)
        finally:
            self._busy.discard(source_id)

    def clear(self, source_id: str) -> ActionResult:
        info = self._info(source_id)
        if self._running(source_id):
            raise AdminError(409, f"{info.label} is refreshing; try again when it's done.")
        if source_id == trackaipac.SOURCE:
            self.svc.trackaipac.reset()
            snapshot = display_date(self.svc.trackaipac.meta().get("latest_snapshot")) or "none"
            return ActionResult(message=f"Back to the snapshot bundled with trackaipac_cache ({snapshot}).")
        if source_id == tec.SOURCE:
            self.svc.tec.reset()
            snapshot = display_date(self.svc.tec.document().get("snapshot")) or "none"
            return ActionResult(message=f"Back to the snapshot bundled with tec_cache ({snapshot}).")
        removed = sum(self.svc.cache.clear(tag) for tag in info.cache_tags)
        message = f"Cleared {removed} cached response{'s' if removed != 1 else ''}."
        if source_id == "geocoding":
            self.svc.sboe.clear()
            message += " The State Board of Education map will be downloaded again on the next lookup."
        if source_id == election_precincts.SOURCE:
            self.svc.election_precincts.clear()
            message += " The precinct map will be downloaded again on the next lookup."
        return ActionResult(message=message)

    def clear_all(self) -> ActionResult:
        if self._busy or self.svc.election_precincts.downloading:
            raise AdminError(409, "A refresh is running; try again when it's done.")
        removed = self.svc.cache.clear()
        self.svc.sboe.clear()
        self.svc.election_precincts.clear()
        self.svc.trackaipac.reset()
        self.svc.tec.reset()
        return ActionResult(
            message=f"Cleared {removed} cached responses, the SBOE map and the precinct map, and reset TrackAIPAC and "
            "the Texas Ethics Commission data to their bundled snapshots."
        )
