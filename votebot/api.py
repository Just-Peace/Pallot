"""HTTP API plus the static frontend, in one FastAPI app (run: python -m votebot)."""

from __future__ import annotations

import asyncio
import datetime as dt
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .admin import Admin, AdminError
from .ballot import BallotError, Services, build_ballot, election_dates
from .config import Config, load_config
from .http_cache import HttpCache, UpstreamError
from .models import ActionResult, Ballot, BallotRequest, ElectionDate, SourcesOverview, SourceToggle, SuggestResult
from .settings import Settings
from .sources.ballotpedia import Ballotpedia
from .sources.census import Census
from .sources.fec import Fec
from .sources.nominatim import Nominatim
from .sources.photon import Photon
from .sources.sboe import SboeMap
from .sources.sos import Sos
from .sources.tec import Tec
from .sources.trackaipac import TrackAipac

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(
    config: Config | None = None,
    *,
    today: Callable[[], dt.date] = dt.date.today,
    trackaipac_refresh: Callable[..., Any] | None = None,
    trackaipac_bundled: Path | None = None,
    tec_refresh: Callable[..., Any] | None = None,
    tec_bundled: Path | None = None,
) -> FastAPI:
    config = config or load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config.data_dir.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(
            timeout=config.http_timeout, headers={"User-Agent": config.user_agent}, follow_redirects=True
        ) as client:
            cache = HttpCache(
                config.cache_path,
                client,
                min_interval={"nominatim": 1.0, "photon": 0.5, "ballotpedia": 1.0, "fec": 0.1},
                source_headers={"fec": {"X-Api-Key": config.fec_api_key}},
                retry_after=config.ttl.retry_after,
            )
            try:
                svc = Services(
                    config=config,
                    settings=Settings(config.settings_path),
                    cache=cache,
                    census=Census(cache, config.ttl),
                    nominatim=Nominatim(cache, config.ttl),
                    photon=Photon(cache, config.ttl),
                    sboe=SboeMap(config.sboe_path, client),
                    sos=Sos(cache, config.ttl, today),
                    ballotpedia=Ballotpedia(cache, config.ttl),
                    trackaipac=TrackAipac(
                        config.trackaipac_dir, refresh_fn=trackaipac_refresh, bundled_dir=trackaipac_bundled
                    ),
                    fec=Fec(cache, config.ttl, config.fec_api_key, today),
                    tec=Tec(config.tec_dir, refresh_fn=tec_refresh, bundled_dir=tec_bundled, user_agent=config.user_agent),
                    today=today,
                )
                await asyncio.to_thread(svc.trackaipac.ensure_seeded)
                await asyncio.to_thread(svc.tec.ensure_seeded)
                app.state.svc = svc
                app.state.admin = Admin(svc)
                yield
            finally:
                cache.close()

    app = FastAPI(title="VoteBot", version=__version__, lifespan=lifespan)

    def services(request: Request) -> Services:
        return request.app.state.svc

    def admin(request: Request) -> Admin:
        return request.app.state.admin

    @app.exception_handler(AdminError)
    async def admin_error(_request: Request, exc: AdminError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.get("/api/elections", response_model=list[ElectionDate])
    async def elections(request: Request, response: Response) -> list[ElectionDate]:
        svc = services(request)
        if not svc.settings.enabled("sos"):
            return []
        try:
            dates = await election_dates(svc.sos)
        except UpstreamError as exc:
            raise HTTPException(502, f"Texas SOS isn't responding ({exc}).") from exc
        response.headers["Cache-Control"] = "private, max-age=600"
        return dates

    @app.get("/api/suggest", response_model=SuggestResult)
    async def suggest(request: Request, q: str = "") -> SuggestResult:
        """Addresses for what's in the address box so far. With an empty ``q`` it only says
        whether suggestions are on. Nothing here is worth an error: a failure is no suggestions."""
        svc = services(request)
        if not svc.settings.enabled("photon"):
            return SuggestResult(enabled=False, suggestions=[])
        try:
            found = await svc.photon.suggest(q[:200])
        except UpstreamError:
            found = []
        return SuggestResult(enabled=True, suggestions=found)

    @app.post("/api/ballot", response_model=Ballot)
    async def ballot(body: BallotRequest, request: Request) -> Ballot:
        try:
            return await build_ballot(services(request), body)
        except BallotError as exc:
            raise HTTPException(exc.status, exc.message) from exc

    @app.get("/api/sources", response_model=SourcesOverview)
    async def sources(request: Request) -> SourcesOverview:
        return admin(request).overview()

    @app.put("/api/sources/{source_id}", response_model=SourcesOverview)
    async def toggle(source_id: str, body: SourceToggle, request: Request) -> SourcesOverview:
        admin(request).set_enabled(source_id, body.enabled)
        return admin(request).overview()

    @app.post("/api/sources/{source_id}/refresh", response_model=ActionResult)
    async def refresh(source_id: str, request: Request) -> ActionResult:
        return await admin(request).refresh(source_id)

    @app.post("/api/sources/{source_id}/clear", response_model=ActionResult)
    async def clear(source_id: str, request: Request) -> ActionResult:
        return admin(request).clear(source_id)

    @app.post("/api/cache/clear", response_model=ActionResult)
    async def clear_all(request: Request) -> ActionResult:
        return admin(request).clear_all()

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()
