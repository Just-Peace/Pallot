"""What the Settings page shows and does: per-source status, on/off, refresh and clear."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ballot import Services
from .models import ActionResult, CacheStatus, Fact, SourcesOverview, SourceStatus, Tone
from .sources import ballotpedia, fec, sos, tec, trackaipac
from .text import display_date, iso_utc


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
    SourceInfo(fec.SOURCE, "FEC (Federal Election Commission)", fec.DESCRIPTION, True, (fec.SOURCE,)),
    SourceInfo(
        tec.SOURCE,
        "Texas Ethics Commission",
        tec.DESCRIPTION,
        True,
        (),
        refresh_label="Refresh from the Texas Ethics Commission (downloads about 1 GB if it changed)",
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
        return SourcesOverview(
            sources=[self._status(info) for info in SOURCES],
            total_bytes=self.svc.cache.file_bytes() + self.svc.sboe.size() + snapshots,
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
        notice, tone = self._notice(info.id)
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
            notice=notice,
            notice_tone=tone,
        )

    def _notice(self, source_id: str) -> tuple[str | None, Tone]:
        """One line under the source's description: what it's missing, or where its data stands."""
        if source_id == fec.SOURCE:
            until = self.svc.fec.paused_until()
            if until:
                return f"Paused until {iso_utc(until)} after reaching the FEC's hourly limit.", "warn"
            if not self.svc.fec.keyed:
                return ("Using the shared DEMO_KEY, so federal races show totals only. For the full breakdown, set "
                        "VOTEBOT_FEC_API_KEY to a free key from api.data.gov and restart VoteBot."), "warn"
            return "Using your api.data.gov key.", "info"
        if source_id == tec.SOURCE:
            if self.svc.tec.last_error:
                return f"The last refresh failed and nothing changed: {self.svc.tec.last_error}", "warn"
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
        if source_id == tec.SOURCE:
            document, meta = self.svc.tec.document(), self.svc.tec.meta()
            return [
                Fact(label="Snapshot", value=document.get("snapshot") or "none"),
                Fact(label="Money raised since", value=(document.get("window") or {}).get("start") or "unknown"),
                Fact(label="TEC data from", value=document.get("tec_updated") or "unknown"),
                Fact(label="Last checked", value=meta.get("last_checked") or "never"),
                Fact(label="Candidates and officeholders", value=str(len(document.get("filers") or []))),
            ]
        if source_id == fec.SOURCE:
            until = self.svc.fec.paused_until()
            return [Fact(label="Paused", value=f"until {iso_utc(until)} after the FEC's hourly limit")] if until else []
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
            if source_id == tec.SOURCE:
                try:
                    return ActionResult(message=await self.svc.tec.refresh())
                except Exception as exc:  # tec_cache writes nothing unless the whole refresh succeeds
                    raise AdminError(502, f"Texas Ethics Commission refresh failed; nothing changed. {exc}") from exc
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
        if source_id == tec.SOURCE:
            self.svc.tec.reset()
            snapshot = self.svc.tec.document().get("snapshot") or "none"
            return ActionResult(message=f"Back to the snapshot bundled with tec_cache ({snapshot}).")
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
        self.svc.tec.reset()
        return ActionResult(
            message=f"Cleared {removed} cached responses and the SBOE map, and reset TrackAIPAC and the Texas Ethics "
            "Commission data to their bundled snapshots."
        )
