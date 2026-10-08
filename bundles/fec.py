"""The FEC's bundle: Texas's federal races from Texas SOS, then what a lookup of them asks the FEC."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pallot.models import Candidate, Race
from pallot.offices import classify
from pallot.sources import fec
from pallot.sources.sos import Election, Sos, still_running
from pallot.text import display_office, display_person

from .entry import BundleError, Context

ROUNDS = 3  # how many times the FEC is asked for what failed, after waiting out a pause of its keys


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


async def build(ctx: Context) -> dict[str, int]:
    """Every upcoming election's federal races, and the FEC's answers for them; counts the races and candidates."""
    if fec.DEMO_KEY in ctx.config.fec_api_keys.values():
        raise BundleError("set PALLOT_FEC_API_KEY: with the shared DEMO_KEY, the FEC answers race totals only")
    sos = Sos(ctx.cache, ctx.config.ttl, ctx.today)
    money = _Counted(ctx.cache, ctx.config.ttl, ctx.config.fec_api_keys, ctx.today)
    try:
        elections = [e for day in (await sos.upcoming()).values() for e in day]
        ballots = [(e, federal_races(e, (await sos.candidates(e)).value or [])) for e in elections]
    except Exception as exc:
        raise BundleError(f"couldn't load Texas SOS's candidates: {exc}") from exc
    ballots = [(e, races) for e, races in ballots if races]
    if not ballots:
        raise BundleError("Texas SOS lists no federal races in an upcoming election")
    for _ in range(ROUNDS):
        money.failed.clear()
        for election, races in ballots:
            try:
                await fec.cards(money, races, election.day)
            except fec.FecUnavailable:
                pass  # its calls are in money.failed
        if not money.failed:
            break
        if until := ctx.cache.paused_until(fec.SOURCE):
            await asyncio.sleep(max(0.0, until - time.time()) + 1)
    if money.failed:
        raise BundleError(f"{len(money.failed)} FEC calls failed, e.g. {money.failed[0]}")
    return {"races": sum(len(races) for _, races in ballots),
            "candidates": sum(len(race.candidates) for _, races in ballots for race in races)}
