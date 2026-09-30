"""HTTP API plus the static frontend, in one FastAPI app (run: python -m votebot)."""

from __future__ import annotations

import asyncio
import datetime as dt
import ipaddress
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Collection
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, ics
from .admin import Admin, AdminError
from .ballot import BallotError, Services, build_ballot, election_dates
from .config import Config, load_config
from .http_cache import HttpCache, UpstreamError
from .models import ActionResult, Ballot, BallotRequest, ElectionDate, SourcesOverview, SourceToggle, SuggestResult
from .settings import Settings
from .sources import key_dates
from .sources.ballotpedia import Ballotpedia
from .sources.census import Census
from .sources.fec import Fec
from .sources.nominatim import Nominatim
from .sources.photon import Photon
from .sources.polls import Polls
from .sources.sboe import SboeMap
from .sources.sos import Sos
from .sources.tec import Tec
from .sources.trackaipac import TrackAipac

STATIC_DIR = Path(__file__).resolve().parent / "static"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _hostname(host: str) -> str:
    """"LocalHost:8000" -> "localhost", "[::1]:8000" -> "::1"; "" if it can't be read."""
    try:
        return urlsplit(f"//{host}").hostname or ""
    except ValueError:
        return ""


def host_allowed(host: str, allowed: Collection[str]) -> bool:
    """localhost, any IP address (how other devices reach the Docker image), or a name in
    ``allowed``. Any other name may be DNS rebinding: an attacker's domain pointed at this
    machine, which makes the attacker's page the same origin as VoteBot."""
    name = _hostname(host)
    if "*" in allowed or name == "localhost" or (name and name in allowed):
        return True
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return False
    return True


def from_another_site(request: Request) -> bool:
    """A request another page started in the voter's browser: a form or fetch() from any
    other website, or from another port on this machine (same site, not same origin)."""
    site = request.headers.get("sec-fetch-site")
    if site is not None and site not in ("same-origin", "none"):
        return True
    origin = request.headers.get("origin")
    return origin is not None and urlsplit(origin).netloc.lower() != request.headers.get("host", "").lower()


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
                    polls=Polls(cache, config.ttl, today),
                    key_dates=key_dates.KeyDatesPage(cache, config.ttl),
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

    @app.middleware("http")
    async def own_pages_only(request: Request, call_next: Callable[[Request], Any]) -> Response:
        """Settings has no login, so its actions must only come from VoteBot's own pages."""
        host = request.headers.get("host", "")
        if not host_allowed(host, config.allowed_hosts):
            return JSONResponse(
                {"detail": f"VoteBot doesn't answer to the name {_hostname(host) or '(none)'}. "
                           "To use it, add it to VOTEBOT_ALLOWED_HOSTS."},
                status_code=400,
            )
        if request.method not in SAFE_METHODS and from_another_site(request):
            return JSONResponse({"detail": "Refused: this request came from another website."}, status_code=403)
        return await call_next(request)

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

    @app.get("/api/key-dates.ics")
    async def key_dates_calendar(request: Request, date: dt.date, event: ics.EventId | None = None) -> Response:
        """The key dates of the election on ``date`` as a calendar file: the one ``event``, or
        every date still to come (see ics.calendar)."""
        svc = services(request)
        if not svc.settings.enabled(key_dates.SOURCE):
            raise HTTPException(404, "Key dates are turned off in Settings.")
        try:
            found = await svc.key_dates.on(date)
        except UpstreamError as exc:
            raise HTTPException(502, f"The Texas Secretary of State's website isn't responding ({exc}).") from exc
        body = found and ics.calendar(found, today=svc.today(), stamp=dt.datetime.now(dt.timezone.utc), only=event)
        if not body:
            raise HTTPException(404, "The Texas Secretary of State lists no such date for this election.")
        name = f"texas-election-{date.isoformat()}{f'-{event}' if event else ''}.ics"
        return Response(body, media_type="text/calendar; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

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
