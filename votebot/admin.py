"""What the Settings page shows and does: per-source status, on/off, refresh and clear."""

from __future__ import annotations

from dataclasses import dataclass

from .ballot import Services
from .models import ActionResult, CacheStatus, Fact, SourcesOverview, SourceStatus
from .sources import ballotpedia, sos, trackaipac
from .text import iso_utc


@dataclass(frozen=True)
class SourceInfo:
    id: str
    label: str
    description: str
    toggleable: bool
    cache_tags: tuple[str, ...]  # HttpCache source names holding this source's responses
    refresh_label: str = "Refresh now"
    clear_label: str = "Clear cache"


SOURCES = (
    SourceInfo(
        "geocoding",
        "Address lookup & districts",
        "US Census geocoder (county and districts), OpenStreetMap Nominatim when the Census can't match an "
        "address, and the Texas Legislative Council's State Board of Education map. Always on.",
        False,
        ("census", "nominatim"),
    ),
    SourceInfo(sos.SOURCE, "Texas Secretary of State", sos.DESCRIPTION, True, (sos.SOURCE,)),
    SourceInfo(ballotpedia.SOURCE, "Ballotpedia", ballotpedia.DESCRIPTION, True, (ballotpedia.SOURCE,)),
    SourceInfo(
        trackaipac.SOURCE,
        "TrackAIPAC",
        trackaipac.DESCRIPTION,
        True,
        (),
        refresh_label="Refresh from trackaipac.com",
        clear_label="Reset to bundled snapshot",
    ),
)
BY_ID = {info.id: info for info in SOURCES}
_SLOW = {"ballotpedia", "nominatim"}  # one request at a time when refreshing


class AdminError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _size(num: int) -> str:
    return f"{num / 1_048_576:.1f} MB" if num >= 1_048_576 else f"{num / 1024:.0f} KB"


class Admin:
    def __init__(self, svc: Services):
        self.svc = svc
        self._busy: set[str] = set()

    def _info(self, source_id: str) -> SourceInfo:
        if source_id not in BY_ID:
            raise AdminError(404, f"Unknown source: {source_id}")
        return BY_ID[source_id]

    def overview(self) -> SourcesOverview:
        tracker_dir = self.svc.trackaipac.data_dir
        tracker_bytes = sum(p.stat().st_size for p in tracker_dir.rglob("*") if p.is_file()) if tracker_dir.exists() else 0
        return SourcesOverview(
            sources=[self._status(info) for info in SOURCES],
            total_bytes=self.svc.cache.file_bytes() + self.svc.sboe.size() + tracker_bytes,
        )

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
        return SourceStatus(
            id=info.id,
            label=info.label,
            description=info.description,
            toggleable=info.toggleable,
            enabled=self.svc.settings.enabled(info.id) if info.toggleable else True,
            busy=info.id in self._busy,
            cache=cache,
            details=self._details(info.id),
            refresh_label=info.refresh_label,
            clear_label=info.clear_label,
        )

    def _details(self, source_id: str) -> list[Fact]:
        if source_id == "geocoding":
            sboe = self.svc.sboe
            downloaded = sboe.downloaded_at()
            value = (
                f"downloaded {iso_utc(downloaded)} · {_size(sboe.size())}"
                if downloaded else "fetched on the first lookup"
            )
            return [Fact(label="SBOE map", value=value)]
        if source_id == "ballotpedia":
            until = self.svc.ballotpedia.paused_until()
            return [Fact(label="Paused", value=f"until {iso_utc(until)} after Ballotpedia refused a request")] if until else []
        if source_id == "trackaipac":
            tracker = self.svc.trackaipac
            meta = tracker.meta()
            return [
                Fact(label="Snapshot", value=meta.get("latest_snapshot") or "none"),
                Fact(label="Last changed", value=meta.get("last_refresh") or "never"),
                Fact(label="Last checked", value=meta.get("last_checked") or "never"),
                Fact(label="Texas entries", value=str(len(tracker.people("TX")))),
                Fact(label="All entries", value=str(len(tracker.people()))),
            ]
        return []

    def set_enabled(self, source_id: str, enabled: bool) -> None:
        if not self._info(source_id).toggleable:
            raise AdminError(400, "This source is required and can't be turned off.")
        self.svc.settings.set_enabled(source_id, enabled)

    async def refresh(self, source_id: str) -> ActionResult:
        info = self._info(source_id)
        if source_id in self._busy:
            raise AdminError(409, f"{info.label} is already refreshing.")
        self._busy.add(source_id)
        try:
            if source_id == trackaipac.SOURCE:
                try:
                    return ActionResult(message=await self.svc.trackaipac.refresh())
                except Exception as exc:  # the package raises FetchError/ValidationError without writing anything
                    raise AdminError(502, f"TrackAIPAC refresh failed; nothing changed. {exc}") from exc
            refreshed = failed = 0
            errors: list[str] = []
            for tag in info.cache_tags:
                report = await self.svc.cache.refresh(tag, concurrency=1 if tag in _SLOW else 3)
                refreshed += report.refreshed
                failed += report.failed
                errors += report.errors
            message = f"Refreshed {refreshed} cached response{'s' if refreshed != 1 else ''}."
            if source_id == "geocoding":
                await self.svc.sboe.download()
                message += " Re-downloaded the State Board of Education map."
            if failed:
                message += f" {failed} failed and kept their old copy ({'; '.join(errors)})."
            return ActionResult(message=message)
        finally:
            self._busy.discard(source_id)

    def clear(self, source_id: str) -> ActionResult:
        info = self._info(source_id)
        if source_id in self._busy:
            raise AdminError(409, f"{info.label} is refreshing; try again when it's done.")
        if source_id == trackaipac.SOURCE:
            self.svc.trackaipac.reset()
            snapshot = self.svc.trackaipac.meta().get("latest_snapshot") or "none"
            return ActionResult(message=f"Back to the snapshot bundled with trackaipac_cache ({snapshot}).")
        removed = sum(self.svc.cache.clear(tag) for tag in info.cache_tags)
        message = f"Cleared {removed} cached response{'s' if removed != 1 else ''}."
        if source_id == "geocoding":
            self.svc.sboe.clear()
            message += " The State Board of Education map will be downloaded again on the next lookup."
        return ActionResult(message=message)

    def clear_all(self) -> ActionResult:
        if self._busy:
            raise AdminError(409, "A refresh is running; try again when it's done.")
        removed = self.svc.cache.clear()
        self.svc.sboe.clear()
        self.svc.trackaipac.reset()
        return ActionResult(
            message=f"Cleared {removed} cached responses and the SBOE map, and reset TrackAIPAC to its bundled snapshot."
        )
