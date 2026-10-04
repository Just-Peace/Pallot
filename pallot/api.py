"""HTTP API plus the static frontend, in one FastAPI app (run: python -m pallot)."""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import ipaddress
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Collection, Mapping
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from . import __version__, ics
from .admin import SOURCES, Admin, AdminError
from .ballot import BallotError, Services, build_ballot, election_dates
from .config import Config, load_config
from .http_cache import HttpCache, UpstreamError
from .models import (
    ActionResult, Ballot, BallotRequest, DistrictOutlines, ElectionDate, EndorsementListInfo, SourcesOverview,
    SourceToggle, SuggestResult,
)
from .outlines import district_outlines
from .settings import Settings
from .version import short_commit
from .sources import census, key_dates, nominatim, osm_tiles, suggestions
from .sources.ballotpedia import Ballotpedia
from .sources.census import Census
from .sources.county_precincts import CountyPrecincts
from .sources.election_precincts import ElectionPrecincts
from .sources.endorsement_feeds import FEEDS, make_feeds
from .sources.endorsements import ENDORSEMENTS_DIR, load_all
from .sources.fec import Fec
from .sources.nominatim import Nominatim
from .sources.osm_tiles import Tiles
from .sources.polls import Polls
from .sources.sboe import SboeMap
from .sources.sos import Sos
from .sources.suggestions import Suggestions
from .sources.tec import Tec
from .sources.tigerweb import Tigerweb
from .sources.trackaipac import TrackAipac
from .sources.voteforpeace import VoteForPeace

STATIC_DIR = Path(__file__).resolve().parent / "static"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
MIN_INTERVAL = {
    "nominatim": 1.0, "suggestions": 0.5, "ballotpedia": 1.0, "fec": 0.1, "tigerweb": 0.25, "election_precincts": 1.0,
    "sboe": 1.0, "county_precincts": 0.25, **{feed.source: 1.0 for feed in FEEDS},
}


def _hostname(host: str) -> str:
    """"LocalHost:8000" -> "localhost", "[::1]:8000" -> "::1"; "" if it can't be read."""
    try:
        return urlsplit(f"//{host}").hostname or ""
    except ValueError:
        return ""


def host_allowed(host: str, allowed: Collection[str]) -> bool:
    """localhost, any IP address (how other devices reach the Docker image), or a name in
    ``allowed``. Any other name may be DNS rebinding: an attacker's domain pointed at this
    machine, which makes the attacker's page the same origin as Pallot."""
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


async def warm_up(svc: Services) -> None:
    """Read, in the background at startup, what the first lookup would otherwise read: the
    precinct map's index, the SBOE map, and the TEC's, TrackAIPAC's and Vote for Peace's name indexes. Only files
    already kept, for sources that are on; nothing is fetched. A lookup meanwhile waits on the
    same locks, and a failure is left for the lookup to report."""
    jobs = [svc.sboe.warm()]
    if svc.settings.enabled("election_precincts"):
        jobs.append(asyncio.to_thread(svc.election_precincts.warm))
    if svc.settings.enabled("tec"):
        jobs += [asyncio.to_thread(svc.tec.name_index), asyncio.to_thread(svc.tec.outside_index)]
    if svc.settings.enabled("trackaipac"):
        jobs.append(asyncio.to_thread(svc.trackaipac.name_index, "TX"))
    if svc.settings.enabled("voteforpeace"):
        jobs.append(asyncio.to_thread(svc.voteforpeace.name_index, "TX"))
    await asyncio.gather(*jobs, return_exceptions=True)


class RevalidatedFiles(StaticFiles):
    """The frontend's files, which the browser keeps but checks with their ETag before each use
    (a short 304 when unchanged), so after an update no page mixes old modules with new ones."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers.setdefault("Cache-Control", "no-cache")
        return response


def create_app(
    config: Config | None = None,
    *,
    today: Callable[[], dt.date] = dt.date.today,
    trackaipac_refresh: Callable[..., Any] | None = None,
    trackaipac_bundled: Path | None = None,
    voteforpeace_refresh: Callable[..., Any] | None = None,
    voteforpeace_bundled: Path | None = None,
    tec_refresh: Callable[..., Any] | None = None,
    tec_bundled: Path | None = None,
    endorsements_dir: Path = ENDORSEMENTS_DIR,
    min_interval: Mapping[str, float] = MIN_INTERVAL,
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
                min_interval=dict(min_interval),
                source_headers={"fec": {"X-Api-Key": config.fec_api_key}},
                retry_after=config.ttl.retry_after,
            )
            election_precincts = ElectionPrecincts(cache, config.ttl, config.election_precincts_dir)
            try:
                await asyncio.to_thread(
                    cache.prune, {suggestions.SOURCE, osm_tiles.SOURCE}, {census.SOURCE, nominatim.SOURCE},
                    config.ttl.prune_after,
                )
                lists = sorted(
                    [*load_all(endorsements_dir, reserved={info.id for info in SOURCES} | {f.source for f in FEEDS}),
                     *make_feeds(cache, config.ttl)],
                    key=lambda found: found.label.lower(),
                )
                svc = Services(
                    config=config,
                    settings=Settings(config.settings_path, (found.source for found in lists)),
                    cache=cache,
                    census=Census(cache, config.ttl),
                    nominatim=Nominatim(cache, config.ttl),
                    suggestions=Suggestions(cache, config.ttl),
                    sboe=SboeMap(cache, config.ttl, config.sboe_path),
                    election_precincts=election_precincts,
                    county_precincts=CountyPrecincts(cache, config.ttl, election_precincts),
                    sos=Sos(cache, config.ttl, today),
                    ballotpedia=Ballotpedia(cache, config.ttl, today),
                    trackaipac=TrackAipac(
                        config.trackaipac_dir, refresh_fn=trackaipac_refresh, bundled_dir=trackaipac_bundled
                    ),
                    voteforpeace=VoteForPeace(
                        config.voteforpeace_dir, refresh_fn=voteforpeace_refresh, bundled_dir=voteforpeace_bundled
                    ),
                    endorsements=lists,
                    fec=Fec(cache, config.ttl, config.fec_api_key, today),
                    tec=Tec(config.tec_dir, refresh_fn=tec_refresh, bundled_dir=tec_bundled, user_agent=config.user_agent),
                    polls=Polls(cache, config.ttl, today),
                    key_dates=key_dates.KeyDatesPage(cache, config.ttl),
                    tigerweb=Tigerweb(cache, config.ttl),
                    tiles=Tiles(cache, config.ttl),
                    today=today,
                )
                await asyncio.to_thread(svc.trackaipac.ensure_seeded)
                await asyncio.to_thread(svc.voteforpeace.ensure_seeded)
                await asyncio.to_thread(svc.tec.ensure_seeded)
                app.state.svc = svc
                app.state.admin = Admin(svc)
                app.state.warm_up = warming = asyncio.create_task(warm_up(svc))
                try:
                    yield
                finally:
                    warming.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await warming
            finally:
                await election_precincts.aclose()  # before the client closes under a download
                cache.close()

    app = FastAPI(title="Pallot", version=__version__, lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)

    def services(request: Request) -> Services:
        return request.app.state.svc

    def admin(request: Request) -> Admin:
        return request.app.state.admin

    @app.middleware("http")
    async def own_pages_only(request: Request, call_next: Callable[[Request], Any]) -> Response:
        """Settings has no login, so its actions must only come from Pallot's own pages."""
        host = request.headers.get("host", "")
        if not host_allowed(host, config.allowed_hosts):
            return JSONResponse(
                {"detail": f"Pallot doesn't answer to the name {_hostname(host) or '(none)'}. "
                           "To use it, add it to PALLOT_ALLOWED_HOSTS."},
                status_code=400,
            )
        if request.method not in SAFE_METHODS and from_another_site(request):
            return JSONResponse({"detail": "Refused: this request came from another website."}, status_code=403)
        return await call_next(request)

    @app.exception_handler(AdminError)
    async def admin_error(_request: Request, exc: AdminError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.get("/api/elections", response_model=list[ElectionDate])
    async def elections(request: Request) -> list[ElectionDate]:
        svc = services(request)
        if not svc.settings.enabled("sos"):
            return []
        try:
            dates = await election_dates(svc.sos)
        except UpstreamError as exc:
            raise HTTPException(502, f"Texas SOS isn't responding ({exc}).") from exc
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

    @app.get("/api/district-outlines", response_model=DistrictOutlines)
    async def outlines(
        request: Request,
        cd: int | None = Query(None, ge=1, le=38),
        sd: int | None = Query(None, ge=1, le=31),
        hd: int | None = Query(None, ge=1, le=150),
        sboe: int | None = Query(None, ge=1, le=15),
        election_precinct: str | None = Query(None, max_length=16),
        county: int | None = Query(None, ge=1, le=999),
    ) -> DistrictOutlines:
        """The outlines of the voter's Texas districts, for the map on Your districts. The election
        precinct is asked by the map's code for it ("0300") and the county's FIPS code; an
        unknown one is a note, so it can't fail the other outlines."""
        precinct = (county, election_precinct) if election_precinct and county else None
        return await district_outlines(services(request), {"cd": cd, "sd": sd, "hd": hd, "sboe": sboe}, precinct)

    @app.get("/api/tiles/{z}/{x}/{y}.png")
    async def tile(request: Request, z: int, x: int, y: int) -> Response:
        """One OpenStreetMap tile for the street map, kept by the server (see sources/osm_tiles.py)."""
        svc = services(request)
        if not svc.settings.enabled(osm_tiles.SOURCE):
            raise HTTPException(404, "The street map is turned off in Settings.")
        if not osm_tiles.wanted(z, x, y):
            raise HTTPException(404, "Pallot only shows the street map over Texas.")
        try:
            body = await svc.tiles.tile(z, x, y)
        except UpstreamError as exc:
            raise HTTPException(502, f"OpenStreetMap's tile server isn't responding ({exc}).") from exc
        return Response(body, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})

    @app.get("/api/suggest", response_model=SuggestResult)
    async def suggest(request: Request, q: str = "") -> SuggestResult:
        """Addresses for what's in the address box so far. With an empty ``q`` it only says
        whether suggestions are on. Nothing here is worth an error: a failure is no suggestions."""
        svc = services(request)
        if not svc.settings.enabled(suggestions.SOURCE):
            return SuggestResult(enabled=False, suggestions=[])
        try:
            found = await svc.suggestions.suggest(q[:200])
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
    def sources(request: Request) -> SourcesOverview:
        return admin(request).overview()

    @app.get("/api/endorsements", response_model=list[EndorsementListInfo])
    def endorsements(request: Request) -> list[EndorsementListInfo]:
        """The endorsement lists that came with Pallot and the live feeds, for About, Privacy, the
        FAQ and the welcome steps, which list them without naming any in their HTML."""
        svc = services(request)
        return [
            EndorsementListInfo(
                source=found.source, label=found.label, organization=found.organization, url=found.url,
                captured=found.captured, description=found.description, live=found.live,
                enabled=svc.settings.enabled(found.source),
            )
            for found in svc.endorsements
        ]

    @app.put("/api/sources/{source_id}", response_model=SourcesOverview)
    def toggle(source_id: str, body: SourceToggle, request: Request) -> SourcesOverview:
        admin(request).set_enabled(source_id, body.enabled)
        return admin(request).overview()

    @app.put("/api/source-groups/{group_id}", response_model=SourcesOverview)
    def toggle_group(group_id: str, body: SourceToggle, request: Request) -> SourcesOverview:
        admin(request).set_group_enabled(group_id, body.enabled)
        return admin(request).overview()

    @app.post("/api/sources/{source_id}/refresh", response_model=ActionResult)
    async def refresh(source_id: str, request: Request) -> ActionResult:
        return await admin(request).refresh(source_id)

    @app.post("/api/sources/{source_id}/clear", response_model=ActionResult)
    def clear(source_id: str, request: Request) -> ActionResult:
        return admin(request).clear(source_id)

    @app.post("/api/cache/clear", response_model=ActionResult)
    def clear_all(request: Request) -> ActionResult:
        return admin(request).clear_all()

    version_js = f"export const VERSION = {json.dumps(__version__)};\nexport const COMMIT = {json.dumps(short_commit())};\n"

    @app.get("/js/version.js")
    def version_module() -> Response:
        """The running version and commit, as a module the footer imports, so the page never fetches them."""
        return Response(version_js, media_type="text/javascript", headers={"Cache-Control": "no-cache"})

    app.mount("/", RevalidatedFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()
