"""HTTP API plus the static frontend, in one FastAPI app (run: python -m pallot)."""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import ipaddress
import json
import sqlite3
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Collection, Mapping
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from . import __version__, ics
from .admin import Admin
from .ballot import BallotError, Services, election_dates, start_ballot
from .config import Config, load_config
from .http_cache import UpstreamError
from .models import Ballot, BallotRequest, DistrictOutlines, ElectionDate, EndorsementListInfo, SourcesOverview, SuggestResult
from .outlines import district_outlines
from .services import MIN_INTERVAL, open_services, prune
from .settings import HEADER, Sources
from .sources import osm_tiles, suggestions
from .sources.endorsements import ENDORSEMENTS_DIR
from .version import short_commit

STATIC_DIR = Path(__file__).resolve().parent / "static"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
NDJSON = "application/x-ndjson"


def _line(ballot: Ballot, *, done: bool) -> bytes:
    """One line of the streamed ballot."""
    return b'{"done":' + (b"true" if done else b"false") + b',"ballot":' + ballot.model_dump_json().encode() + b"}\n"


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
    already kept, for sources on by default; nothing is fetched. A lookup meanwhile waits on the
    same locks, and a failure is left for the lookup to report."""
    jobs = [svc.sboe.warm()]
    if svc.sources.enabled("election_precincts"):
        jobs.append(asyncio.to_thread(svc.election_precincts.warm))
    if svc.sources.enabled("tec"):
        jobs += [asyncio.to_thread(svc.tec.name_index), asyncio.to_thread(svc.tec.outside_index)]
    if svc.sources.enabled("trackaipac"):
        jobs.append(asyncio.to_thread(svc.trackaipac.name_index, "TX"))
    if svc.sources.enabled("voteforpeace"):
        jobs.append(asyncio.to_thread(svc.voteforpeace.name_index, "TX"))
    await asyncio.gather(*jobs, return_exceptions=True)


async def keep_pruning(svc: Services, every: float | None = None) -> None:
    """Prune the transient caches every ``every`` seconds (``Config.prune_every``) while the server runs, so the street
    map's tiles and the address suggestions stay under their caps between restarts. Without
    VACUUM, which would hold up lookups: the freed pages are reused. A round that meets the
    database locked (pallot-cache vacuuming it) waits for the next."""
    every = every or svc.config.prune_every
    while True:
        await asyncio.sleep(every)
        with contextlib.suppress(sqlite3.Error):
            await asyncio.to_thread(prune, svc.cache, svc.config, vacuum=False)


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
    bundles: Path | None = None,
    endorsements_dir: Path = ENDORSEMENTS_DIR,
    min_interval: Mapping[str, float] = MIN_INTERVAL,
) -> FastAPI:
    config = config or load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with open_services(
            config,
            today=today,
            trackaipac_refresh=trackaipac_refresh,
            trackaipac_bundled=trackaipac_bundled,
            voteforpeace_refresh=voteforpeace_refresh,
            voteforpeace_bundled=voteforpeace_bundled,
            tec_refresh=tec_refresh,
            tec_bundled=tec_bundled,
            bundles=bundles,
            endorsements_dir=endorsements_dir,
            min_interval=min_interval,
        ) as svc:
            await asyncio.to_thread(prune, svc.cache, config)
            app.state.svc = svc
            app.state.admin = Admin(svc)
            app.state.warm_up = warming = asyncio.create_task(warm_up(svc))
            pruning = asyncio.create_task(keep_pruning(svc))
            app.state.finishing = finishing = set()  # streamed ballots still adding their cards
            try:
                yield
            finally:
                for task in (warming, pruning, *finishing):
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

    app = FastAPI(title="Pallot", version=__version__, lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)

    def services(request: Request) -> Services:
        return request.app.state.svc

    def admin(request: Request) -> Admin:
        return request.app.state.admin

    def chosen(request: Request) -> Sources:
        """The sources this voter has on: their choices, kept in their browser and sent in a header
        by every call the page makes, on top of the defaults."""
        return services(request).sources.chosen(request.headers.get(HEADER))

    @app.middleware("http")
    async def own_pages_only(request: Request, call_next: Callable[[Request], Any]) -> Response:
        """Pallot has no login, so only its own pages may ask for a ballot from the voter's browser."""
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

    @app.get("/api/elections", response_model=list[ElectionDate])
    async def elections(request: Request) -> list[ElectionDate]:
        svc = services(request)
        if not chosen(request).enabled("sos"):
            return []
        try:
            dates = await election_dates(svc.sos)
        except UpstreamError as exc:
            raise HTTPException(502, f"Texas SOS isn't responding ({exc}).") from exc
        return dates

    @app.get("/api/key-dates.ics")
    async def key_dates_calendar(request: Request, date: dt.date, event: ics.EventId | None = None) -> Response:
        """The key dates of the election on ``date`` as a calendar file: the one ``event``, or
        every date still to come (see ics.calendar). A link, so it carries no choice of sources:
        the page only offers it with the key dates on."""
        svc = services(request)
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
        return await district_outlines(
            services(request), {"cd": cd, "sd": sd, "hd": hd, "sboe": sboe}, precinct, chosen(request)
        )

    @app.get("/api/tiles/{z}/{x}/{y}.png")
    async def tile(request: Request, z: int, x: int, y: int) -> Response:
        """One OpenStreetMap tile for the street map, kept by the server (see sources/osm_tiles.py).
        An image, so it carries no choice of sources: the map only asks for tiles with the street
        map on (DistrictOutlines.street_map)."""
        svc = services(request)
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
        if not chosen(request).enabled(suggestions.SOURCE):
            return SuggestResult(enabled=False, suggestions=[])
        try:
            found = await svc.suggestions.suggest(q[:200])
        except UpstreamError:
            found = []
        return SuggestResult(enabled=True, suggestions=found)

    @app.post("/api/ballot", response_model=Ballot)
    async def ballot(body: BallotRequest, request: Request) -> Any:
        """The ballot. A page that accepts NDJSON gets it in two lines: without cards as soon as the
        races are known (``done: false``), then whole (``done: true``), or ``{"error"}`` instead."""
        try:
            builder = await start_ballot(services(request), body, chosen(request))
        except BallotError as exc:
            raise HTTPException(exc.status, exc.message) from exc
        if NDJSON not in request.headers.get("accept", ""):
            return await builder.finish()
        first = _line(builder.ballot, done=False)  # before finish() adds the cards to the same races
        # Started here, so its calls count in this lookup's CallStats; it runs on if the voter leaves.
        finishing = asyncio.create_task(builder.finish())
        request.app.state.finishing.add(finishing)
        finishing.add_done_callback(request.app.state.finishing.discard)

        async def lines() -> AsyncIterator[bytes]:
            yield first
            try:
                done = await asyncio.shield(finishing)
            except Exception:
                traceback.print_exc()
                yield json.dumps({"error": "Couldn't load money, polls and endorsements."}).encode() + b"\n"
                return
            yield _line(done, done=True)

        return StreamingResponse(lines(), media_type=NDJSON, headers={"X-Accel-Buffering": "no"})

    @app.get("/api/sources", response_model=SourcesOverview)
    def sources(request: Request) -> SourcesOverview:
        return admin(request).overview(chosen(request))

    @app.get("/api/endorsements", response_model=list[EndorsementListInfo])
    def endorsements(request: Request) -> list[EndorsementListInfo]:
        """The endorsement lists that came with Pallot and the live feeds, for About, Privacy, the
        FAQ and the welcome steps, which list them without naming any in their HTML."""
        svc, on = services(request), chosen(request)
        return [
            EndorsementListInfo(
                source=found.source, label=found.label, organization=found.organization, url=found.url,
                captured=found.captured, description=found.description, live=found.live,
                enabled=on.enabled(found.source),
            )
            for found in svc.endorsements
        ]

    version_js = f"export const VERSION = {json.dumps(__version__)};\nexport const COMMIT = {json.dumps(short_commit())};\n"

    @app.get("/js/version.js")
    def version_module() -> Response:
        """The running version and commit, as a module the footer imports, so the page never fetches them."""
        return Response(version_js, media_type="text/javascript", headers={"Cache-Control": "no-cache"})

    app.mount("/", RevalidatedFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()
