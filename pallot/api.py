"""HTTP API plus the static frontend, in one FastAPI app (run: python -m pallot)."""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import datetime as dt
import hashlib
import ipaddress
import json
import logging
import os
import posixpath
import re
import sqlite3
import sys
import traceback
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Collection, Literal, Mapping, Sequence
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.types import Scope

from . import __version__, ics
from .catalog import Catalog
from .ballot import BallotError, Services, election_dates, start_ballot
from .config import Config, load_config
from . import counties, coverage
from .http_cache import UpstreamError
from .limits import ClientLimits
from .models import (
    Ballot, BallotRequest, CardState, DistrictOutlines, ElectionDate, EndorsementListInfo, EntryConfig, SourcesOverview,
    SuggestResult,
)
from .outlines import district_outlines
from .services import MIN_INTERVAL, open_services, prune
from .settings import HEADER, Sources
from .sources import fec, google, osm_tiles, suggestions
from .sources.endorsements import ENDORSEMENTS_DIR
from .states import key_dates as state_key_dates
from .version import short_commit

log = logging.getLogger("uvicorn.error")

STATIC_DIR = Path(__file__).resolve().parent / "static"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SECURITY_HEADERS = {
    "Content-Security-Policy": "; ".join((
        "default-src 'self'", "script-src 'self'", "style-src 'self'",
        "img-src 'self' data: https://commons.wikimedia.org https://upload.wikimedia.org"
        " https://thumb.wikimedia.org",
        "connect-src 'self'", "frame-ancestors 'none'", "base-uri 'none'", "form-action 'self'", "object-src 'none'",
    )),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
}
NDJSON = "application/x-ndjson"
IMMUTABLE = "public, max-age=31536000, immutable"
VERSION_JS = os.path.join("js", "version.js")
_LOCAL_REF = re.compile(r'(<(?:script|link)\b[^>]*?\s(?:src|href)=")(?![\w+.-]*:|/|#)([^"]+)"')
_ENTRY = re.compile(r'^([ \t]*)<script type="module" src="([^"]+)"></script>(\r?\n)', re.M)
_IMPORT = re.compile(r'^import\s[^"]*?"(\.{1,2}/[^"]+)"', re.M)
# What a voter is told when the page sends what Pallot can't take, by the field: one plain sentence, not Pydantic's.
INVALID_FIELDS = {
    "address": "Enter your street address, with the city or ZIP code.",
    "state": "Choose your state.",
    "county": "Enter your county as it's written on your voter registration card.",
    "precinct": "Enter the precinct number on your voter registration card, or leave it empty.",
    "precincts": "Check the commissioner, JP and constable precinct numbers you entered.",
    "districts": "Check the district numbers you entered.",
}
ADDRESS_OR_CARD = "Enter an address, or your state and county."
INVALID = "Pallot couldn't read that request. Reload the page and try again."
CARD_STATES = [
    CardState(code=code, name=name, counties=[c.full_name for c in counties.counties(code)],
              districts=list(coverage.of(code).districts), precincts=coverage.of(code).precincts,
              labels=dict(coverage.of(code).labels))
    for code, name in counties.state_names().items()
]


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


def wait_words(seconds: int) -> str:
    """30 -> "30 seconds", 61 -> "2 minutes": how long a voter is asked to wait."""
    if seconds < 60:
        return f"{seconds} second{'' if seconds == 1 else 's'}"
    minutes = -(-seconds // 60)
    return f"{minutes} minute{'' if minutes == 1 else 's'}"


def from_another_site(request: Request) -> bool:
    """A request another page started in the voter's browser: a form or fetch() from any
    other website, or from another port on this machine (same site, not same origin)."""
    site = request.headers.get("sec-fetch-site")
    if site is not None and site not in ("same-origin", "none"):
        return True
    origin = request.headers.get("origin")
    return origin is not None and urlsplit(origin).netloc.lower() != request.headers.get("host", "").lower()


def from_own_page(request: Request) -> bool:
    """A call to /api/* made by Pallot's own pages. Browsers send ``Sec-Fetch-Site`` only over HTTPS
    and to localhost, so when it's missing (the Docker image reached over plain HTTP) the rest is the
    test. JSON calls carry the header api.js always sends, which no link, form or ``<img>`` can add and
    a cross-site fetch() can't without a CORS preflight Pallot never grants. The street map's tiles are
    ``<img>``s, so they need the same origin, or this site as the referrer. The calendar file is a
    link, also opened from outside (a bookmark, an email): only another site's page is refused."""
    site, path = request.headers.get("sec-fetch-site"), request.url.path
    if path == "/api/key-dates.ics":
        return site in (None, "same-origin", "none")
    if path.startswith("/api/tiles/"):
        if site is not None:
            return site == "same-origin"
        referrer = request.headers.get("referer")
        return referrer is not None and urlsplit(referrer).netloc.lower() == request.headers.get("host", "").lower()
    return site in (None, "same-origin") and HEADER in request.headers


async def warm_up(svc: Services) -> None:
    """Read, in the background at startup, what the first lookup would otherwise read: the
    precinct map's index, the SBOE map, and the TEC's, TrackAIPAC's and Vote for Peace's name indexes. Only files
    already kept, for sources on by default; nothing is fetched. A lookup meanwhile waits on the
    same locks, and a failure is left for the lookup to report. Then the heap freed by startup goes back to the OS."""
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
    trim_heap()


def log_setup(svc: Services) -> None:
    """What the host should fix in its setup, said once at startup in the server log, never on a page."""
    if not svc.fec.keyed:
        log.warning("No FEC key is set in PALLOT_FEC_API_KEY, so Pallot uses the shared DEMO_KEY: federal races show "
                    "FEC totals only, and its rate limit is shared by the whole IP address. A free key: %s",
                    fec.KEY_SIGNUP)
    if trouble := svc.fec.key_trouble():
        log.warning("FEC: %s.", trouble)
    if not svc.google.keyed:
        log.warning("No Google key is set in PALLOT_GOOGLE_API_KEY, so addresses the Census and OpenStreetMap can't "
                    "place aren't found, addresses aren't suggested as voters type, and Settings leaves both out. A key (with the Geocoding and Places APIs): %s", google.KEY_SIGNUP)


def invalid_request(errors: Sequence[Mapping[str, Any]]) -> str:
    """The sentence a 422 answers with: the first field the voter can fix, or the request as a whole."""
    for error in errors:
        where = [part for part in error.get("loc", ()) if part != "body"]
        if not where:
            return ADDRESS_OR_CARD
        if where[0] in INVALID_FIELDS:
            return INVALID_FIELDS[where[0]]
    return INVALID


def trim_heap() -> None:
    """Give back to the OS the heap glibc keeps once startup's parsing is done (the bundles and
    the name indexes, about 50 MB it would otherwise hold for good). Linux with glibc only:
    elsewhere, or where libc.so.6 can't be loaded (musl), nothing."""
    if not sys.platform.startswith("linux"):
        return
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


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


def static_stamp(directory: Path, *extra: str) -> str:
    """A hash of every static file but the pages themselves (and of ``extra``), worked out once at startup:
    the prefix the pages load their files under changes whenever one of them does."""
    digest = hashlib.sha256()
    for path in sorted(p for p in directory.rglob("*") if p.is_file() and not (p.parent == directory and p.suffix == ".html")):
        data = path.read_bytes()
        digest.update(f"{path.relative_to(directory).as_posix()}\0{len(data)}\0".encode() + data)
    for text in extra:
        digest.update(text.encode())
    return digest.hexdigest()[:16]


def _imports(directory: Path, module: str) -> list[str]:
    """Every module ``module`` (a path under ``directory``) imports statically, directly or not."""
    found: list[str] = []
    queue = [module]
    while queue:
        current = queue.pop(0)
        if not (directory / current).is_file():  # js/version.js, made by the server
            continue
        for spec in _IMPORT.findall((directory / current).read_text(encoding="utf-8")):
            target = posixpath.normpath(posixpath.join(posixpath.dirname(current), spec))
            if target != module and target not in found:
                found.append(target)
                queue.append(target)
    return found


def stamped_page(html: str, directory: Path, prefix: str) -> str:
    """A page whose scripts, stylesheets and icon load from under ``prefix``, with every module its entry
    script imports preloaded, so a first visit asks for them all at once rather than level by level."""
    def preload(entry: re.Match[str]) -> str:
        indent, src, newline = entry.groups()
        return entry[0] + "".join(f'{indent}<link rel="modulepreload" href="{prefix}{path}">{newline}'
                                  for path in _imports(directory, src))

    return _LOCAL_REF.sub(lambda ref: f'{ref[1]}{prefix}{ref[2]}"', _ENTRY.sub(preload, html))


@dataclass(frozen=True)
class Page:
    body: bytes
    etag: str


def stamped_pages(directory: Path, prefix: str) -> dict[Path, Page]:
    """Each page as served, worked out once at startup: its full path -> its body and ETag."""
    pages = {}
    for path in directory.glob("*.html"):
        body = stamped_page(path.read_text(encoding="utf-8"), directory, prefix).encode()
        pages[path.resolve()] = Page(body, f'"{hashlib.sha256(body).hexdigest()[:16]}"')
    return pages


class RevalidatedFiles(StaticFiles):
    """The frontend's files at their own addresses, which the browser keeps but checks with their ETag
    before each use (a short 304 when unchanged). The pages, served this way, load their files from
    StampedFiles; the rest stays here for pages and bookmarks from before the update."""

    def __init__(self, *, directory: Path, version_js: str, pages: Mapping[Path, Page] | None = None,
                 html: bool = False) -> None:
        super().__init__(directory=directory, html=html)
        self.version_js, self.pages = version_js, pages or {}

    async def get_response(self, path: str, scope: Scope) -> Response:
        if path == VERSION_JS:
            return Response(self.version_js, media_type="text/javascript", headers={"Cache-Control": "no-cache"})
        return await super().get_response(path, scope)

    def file_response(self, full_path: Any, stat_result: os.stat_result, scope: Scope, status_code: int = 200) -> Response:
        page = self.pages.get(Path(full_path).resolve())
        if page is None:
            response = super().file_response(full_path, stat_result, scope, status_code)
            response.headers.setdefault("Cache-Control", "no-cache")
            return response
        headers = {"Cache-Control": "no-cache", "ETag": page.etag}
        if self.is_not_modified(Headers(headers), Headers(scope=scope)):
            return Response(status_code=304, headers=headers)
        return Response(page.body, status_code, headers, media_type="text/html")


class StampedFiles(RevalidatedFiles):
    """/s/<stamp>/...: the same files under a prefix that changes with them, so the browser keeps them
    a year without asking. Every import is relative, so a page's whole module graph comes from one
    stamp and no page mixes old modules with new ones. Another stamp (a page loaded before an update)
    still gets today's files, checked before each use."""

    def __init__(self, *, stamp: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.stamp = stamp

    async def get_response(self, path: str, scope: Scope) -> Response:
        parts = Path(path).parts
        if len(parts) < 2:
            raise HTTPException(404)
        response = await super().get_response(os.path.join(*parts[1:]), scope)
        response.headers["Cache-Control"] = IMMUTABLE if parts[0] == self.stamp else "no-cache"
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
    sboe_bundled: Path | None = None,
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
            sboe_bundled=sboe_bundled,
            bundles=bundles,
            endorsements_dir=endorsements_dir,
            min_interval=min_interval,
        ) as svc:
            await asyncio.to_thread(prune, svc.cache, config)
            app.state.svc = svc
            app.state.catalog = Catalog(svc)
            log_setup(svc)
            app.state.warm_up = warming = asyncio.create_task(warm_up(svc))
            pruning = asyncio.create_task(keep_pruning(svc))
            app.state.finishing = finishing = set()  # streamed ballots still adding their cards
            app.state.lookups = asyncio.Semaphore(config.max_lookups)  # held until a ballot's cards are added
            try:
                yield
            finally:
                for task in (warming, pruning, *finishing):
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

    app = FastAPI(title="Pallot", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)

    @app.exception_handler(RequestValidationError)
    async def plain_422(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"detail": invalid_request(exc.errors())}, status_code=422)

    def services(request: Request) -> Services:
        return request.app.state.svc

    def catalog(request: Request) -> Catalog:
        return request.app.state.catalog

    def chosen(request: Request) -> Sources:
        """The sources this voter has on: their choices, kept in their browser and sent in a header
        by every call the page makes, on top of the defaults."""
        return services(request).sources.chosen(request.headers.get(HEADER))

    limits = ClientLimits(config.rate_limits)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next: Callable[[Request], Any]) -> Response:
        """Each client gets so many ballots, suggestions, outlines and tiles an hour (limits.py), so
        no one can run up the host's bills or get a source to refuse everyone."""
        wait = limits.wait(request.method, request.url.path, request.client.host if request.client else None)
        if wait:
            return JSONResponse(
                {"detail": f"Too many requests from your connection. Please wait {wait_words(wait)} and try again."},
                status_code=429, headers={"Retry-After": str(wait)},
            )
        return await call_next(request)

    @app.middleware("http")
    async def own_pages_only(request: Request, call_next: Callable[[Request], Any]) -> Response:
        """Pallot has no login, so only its own pages may ask for a ballot from the voter's browser, or use its API."""
        host = request.headers.get("host", "")
        if not host_allowed(host, config.allowed_hosts):
            log.warning("Refused a request for the name %s: to answer to it, add it to PALLOT_ALLOWED_HOSTS.",
                        _hostname(host) or "(none)")
            return JSONResponse({"detail": "Pallot isn't available at this address."}, status_code=400)
        if request.method not in SAFE_METHODS and from_another_site(request):
            return JSONResponse({"detail": "Refused: this request came from another website."}, status_code=403)
        if request.url.path.startswith("/api/") and not from_own_page(request):
            return JSONResponse({"detail": "Refused: Pallot's API only answers Pallot's own pages."}, status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Callable[[Request], Any]) -> Response:
        """On every answer: no other site may frame Pallot, load what isn't Pallot's or the candidates' photos,
        or read a file as another type; links out send only Pallot's origin."""
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    @app.get("/api/config", response_model=EntryConfig)
    def entry_config() -> EntryConfig:
        """What the ballot page's entry card offers: the voter card tab, its states with their
        counties and districts, and the tab a first visit starts on (PALLOT_DEFAULT_ENTRY)."""
        return EntryConfig(default_entry=config.default_entry, voter_card=True, states=CARD_STATES)

    @app.get("/api/elections", response_model=list[ElectionDate])
    async def elections(request: Request) -> list[ElectionDate]:
        svc = services(request)
        if not chosen(request).enabled("sos"):
            return []
        try:
            dates = await election_dates(svc.sos)
        except UpstreamError as exc:
            log.warning("%s", exc)
            raise HTTPException(502, "Texas SOS isn't answering right now. Try again in a minute.") from exc
        return dates

    @app.get("/api/key-dates.ics")
    async def key_dates_calendar(request: Request, date: dt.date, event: ics.EventId | None = None,
                                 state: Literal["TX", "MI", "CA", "AZ", "NV", "GA", "WI", "OH"] = "TX") -> Response:
        """The key dates of the election on ``date`` in ``state`` as a calendar file: the one
        ``event``, or every date still to come (see ics.calendar). Texas's and California's from
        their SOS's pages, other states' worked out by rule. A link, so it carries no choice of
        sources: the page only offers it with the key dates on."""
        svc = services(request)
        guide = state_key_dates.GUIDES[state]
        if state in state_key_dates.RULES:
            found = state_key_dates.computed(state, date)
        else:
            try:
                found = await (svc.ca_key_dates if state == "CA" else svc.key_dates).on(date)
            except UpstreamError as exc:
                log.warning("%s", exc)
                raise HTTPException(502, f"The {guide.source}'s website isn't answering right now. Try again "
                                         "in a minute.") from exc
        body = found and ics.calendar(found, today=svc.today(), stamp=dt.datetime.now(dt.timezone.utc), only=event)
        if not body:
            raise HTTPException(404, f"The {guide.source} lists no such date for this election." if not guide.computed
                                else f"{guide.name} has no such date for a statewide election.")
        name = f"{guide.name.lower()}-election-{date.isoformat()}{f'-{event}' if event else ''}.ics"
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
        map on (Ballot.street_map, DistrictOutlines.street_map)."""
        svc = services(request)
        if not osm_tiles.wanted(z, x, y):
            raise HTTPException(404, "Pallot only shows the street map over the United States.")
        try:
            body = await svc.tiles.tile(z, x, y)
        except UpstreamError as exc:
            log.warning("%s", exc)
            raise HTTPException(502, "OpenStreetMap's tile server isn't answering right now.") from exc
        return Response(body, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})

    @app.get("/api/suggest", response_model=SuggestResult)
    async def suggest(request: Request, q: str = "") -> SuggestResult:
        """Addresses for what's in the address box so far. With an empty ``q`` it only says
        whether suggestions are on: the voter's switch, and a Google key on the server. Nothing
        here is worth an error: a failure is no suggestions."""
        svc = services(request)
        if not (svc.suggestions.keyed and chosen(request).enabled(suggestions.SOURCE)):
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
        on = chosen(request)
        lookups: asyncio.Semaphore = request.app.state.lookups
        if lookups.locked():
            raise HTTPException(503, "Pallot is busy with other lookups. Please try again in a few seconds.",
                                headers={"Retry-After": "5"})
        await lookups.acquire()
        held = True
        try:
            try:
                builder = await start_ballot(services(request), body, on)
            except BallotError as exc:
                raise HTTPException(exc.status, exc.message) from exc
            builder.ballot.sources_off = catalog(request).rule_sources_off(on)
            builder.ballot.street_map = on.enabled(osm_tiles.SOURCE)
            if NDJSON not in request.headers.get("accept", ""):
                return await builder.finish()
            first = _line(builder.ballot, done=False)  # before finish() adds the cards to the same races
            # Started here, so its calls count in this lookup's CallStats; it runs on if the voter leaves,
            # holding its place among the lookups until it's done.
            finishing = asyncio.create_task(builder.finish())
            request.app.state.finishing.add(finishing)
            finishing.add_done_callback(request.app.state.finishing.discard)
            finishing.add_done_callback(lambda _: lookups.release())
            held = False
        finally:
            if held:
                lookups.release()

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
        return catalog(request).overview(chosen(request))

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

    # The running version and commit, as a module the footer imports, so the page never fetches them.
    version_js = f"export const VERSION = {json.dumps(__version__)};\nexport const COMMIT = {json.dumps(short_commit())};\n"
    stamp = static_stamp(STATIC_DIR, version_js)
    app.state.static_prefix = prefix = f"/s/{stamp}/"
    app.mount("/s", StampedFiles(directory=STATIC_DIR, version_js=version_js, stamp=stamp), name="stamped")
    app.mount("/", RevalidatedFiles(directory=STATIC_DIR, version_js=version_js, html=True,
                                    pages=stamped_pages(STATIC_DIR, prefix)), name="static")
    return app
