"""refresh(): build Texas's federal races from Texas SOS -> ask the FEC what a lookup would -> write if changed.

It runs Pallot's own Sos and Fec on a throwaway cache, so the snapshot holds exactly the requests
a lookup makes, asked with the configured keys at their offline pace (http_cache.offline).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import httpx

from pallot.config import Config, load_config
from pallot.http_cache import HttpCache, RequestSpec, offline
from pallot.models import Candidate, Race
from pallot.offices import classify
from pallot.services import MIN_INTERVAL
from pallot.sources import fec
from pallot.sources.sos import Election, Sos, still_running
from pallot.text import display_office, display_person

from . import store

ROUNDS = 3  # how many times the FEC is asked for what failed, after waiting out a pause of its keys


class RefreshError(Exception):
    """Nothing was written: the FEC or Texas SOS couldn't be asked for everything."""


@dataclass(frozen=True)
class RefreshResult:
    status: str  # "updated", "no_changes" or "would_update"
    answers: int
    races: int
    candidates: int

    def summary(self) -> str:
        what = f"{self.answers:,} FEC answers for {self.races} races and {self.candidates} candidates"
        return {"updated": f"Updated the snapshot: {what}.", "no_changes": f"No changes ({what}).",
                "would_update": f"Would update the snapshot: {what}."}[self.status]


class _Counted(fec.Fec):
    """Fec, noting each call that couldn't be answered (Fec.cards leaves those parts out)."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.failed: list[str] = []

    async def _get(self, path: str, params: dict[str, str], ttl: float) -> Any:
        try:
            return await super()._get(path, params, ttl)
        except fec.FecUnavailable as exc:
            self.failed.append(f"{path}: {exc}")
            raise


def federal_races(election: Election, rows: list[dict[str, Any]]) -> list[Race]:
    """The congressional races in Texas SOS's statewide list of an election's candidates."""
    offices: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        if still_running(row) and row.get("idOffice"):
            offices.setdefault(row["idOffice"], []).append(row)
    races = []
    for office_id, office_rows in sorted(offices.items()):
        scope = classify(office_rows[0].get("txOfficeName") or "", office_rows[0].get("cdOfficeType"))
        if not scope.seat:
            continue
        races.append(Race(
            key=f"sos:{election.id}:{office_id}", name=display_office(scope.name), group=scope.group, seat=scope.seat,
            election_id=election.id, source="sos",
            candidates=[
                Candidate(key=f"sos:{election.id}:{row['idCandidate']}", name=display_person(row.get("txFullNameBallot") or ""),
                          party=None if row.get("cdParty") == "W" else row.get("cdParty"), write_in=row.get("cdParty") == "W")
                for row in office_rows
            ],
        ))
    return races


async def build(
    config: Config, today: Callable[[], dt.date] = dt.date.today, min_interval: Mapping[str, float] = MIN_INTERVAL,
) -> tuple[list[dict[str, Any]], int, int]:
    """The answers a lookup would get from the FEC for every upcoming election's federal races,
    sorted by request; and how many races and candidates they cover. Raises RefreshError."""
    if fec.DEMO_KEY in config.fec_api_keys.values():
        raise RefreshError("set PALLOT_FEC_API_KEY: with the shared DEMO_KEY, the FEC answers race totals only")
    with tempfile.TemporaryDirectory() as tmp:
        async with httpx.AsyncClient(
            timeout=config.http_timeout, headers={"User-Agent": config.user_agent}, follow_redirects=True
        ) as client:
            cache = HttpCache(Path(tmp) / "cache.sqlite3", client, min_interval=dict(min_interval))
            try:
                sos = Sos(cache, config.ttl, today)
                money = _Counted(cache, config.ttl, config.fec_api_keys, today)
                try:
                    elections = [e for day in (await sos.upcoming()).values() for e in day]
                    ballots = [(e, federal_races(e, (await sos.candidates(e)).value or [])) for e in elections]
                except Exception as exc:
                    raise RefreshError(f"couldn't load Texas SOS's candidates: {exc}") from exc
                ballots = [(e, races) for e, races in ballots if races]
                if not ballots:
                    raise RefreshError("Texas SOS lists no federal races in an upcoming election")
                with offline():
                    for _ in range(ROUNDS):
                        money.failed.clear()
                        for election, races in ballots:
                            try:
                                await fec.cards(money, races, election.day)
                            except fec.FecUnavailable:
                                pass  # its calls are in money.failed
                        if not money.failed:
                            break
                        if until := cache.paused_until(fec.SOURCE):
                            await asyncio.sleep(max(0.0, until - time.time()) + 1)
                    if money.failed:
                        raise RefreshError(f"{len(money.failed)} FEC calls failed, e.g. {money.failed[0]}")
                answers = []
                for saved in cache.saved(fec.SOURCE):
                    spec = RequestSpec.loads(saved.request)
                    kept = cache.peek(spec)
                    if kept is not None:
                        answers.append({"request": json_request(spec), "value": kept.value})
            finally:
                cache.close()
    answers.sort(key=lambda answer: (answer["request"]["url"], sorted((answer["request"]["params"] or {}).items())))
    races = sum(len(races) for _, races in ballots)
    candidates = sum(len(race.candidates) for _, races in ballots for race in races)
    return answers, races, candidates


def json_request(spec: RequestSpec) -> dict[str, Any]:
    """What RequestSpec(**…) needs again for an FEC request: its key, without the defaults."""
    return {"method": spec.method, "url": spec.url, "params": spec.params}


def refresh(
    force: bool = False,
    dry_run: bool = False,
    *,
    data_dir: str | Path | None = None,
    config: Config | None = None,
    today: Callable[[], dt.date] = dt.date.today,
    now: dt.datetime | None = None,
    min_interval: Mapping[str, float] = MIN_INTERVAL,
) -> RefreshResult:
    """Rebuild the snapshot in ``data_dir`` (the package's by default). It's written only when the
    answers changed (or ``force``); meta.json's last_checked is updated either way, unless ``dry_run``.
    Raises RefreshError without touching any file."""
    root = Path(data_dir) if data_dir else store.PACKAGE_DATA_DIR
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    answers, races, candidates = asyncio.run(build(config or load_config(), today, min_interval))
    digest = store.answers_hash(answers)
    meta = store.read_json(root / "meta.json", default={}) or {}
    stamp = now.isoformat(timespec="seconds")
    counts = dict(answers=len(answers), races=races, candidates=candidates)
    if meta.get("answers_hash") == digest and (root / "current.json").exists() and not force:
        if not dry_run:
            store.write_json(root / "meta.json", {**meta, "last_checked": stamp})
        return RefreshResult("no_changes", **counts)
    if dry_run:
        return RefreshResult("would_update", **counts)
    store.write_json(root / "current.json", {"snapshot": now.date().isoformat(), "answers": answers})
    store.write_json(root / "meta.json", {"schema_version": store.SCHEMA_VERSION, "last_refresh": stamp,
                                          "last_checked": stamp, "answers_hash": digest, **counts})
    return RefreshResult("updated", **counts)
