"""The services a ballot lookup uses, made the same way for the server (api.py) and for
pallot-cache (maintain.py), which refreshes and prunes what the server keeps from the host."""

from __future__ import annotations

import asyncio
import datetime as dt
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Mapping

import httpx

from bundles.registry import seed as seed_bundles
from bundles.store import PACKAGE_DATA_DIR as BUNDLES_DIR

from .admin import SOURCES
from .ballot import Services
from .config import Config
from .http_cache import HttpCache
from .settings import Sources, defaults
from .sources import census, google, key_dates, nominatim, osm_tiles, sboe, suggestions
from .sources.ballotpedia import Ballotpedia
from .sources.census import Census
from .sources.county_precincts import CountyPrecincts
from .sources.election_precincts import ElectionPrecincts
from .sources.endorsement_feeds import FEEDS, make_feeds
from .sources.endorsements import ENDORSEMENTS_DIR, load_all
from .sources.fec import Fec
from .sources.google import Google
from .sources.nominatim import Nominatim
from .sources.osm_tiles import Tiles
from .sources.officeholders import Officeholders
from .sources.polls import Polls
from .sources.sboe import SboeMap
from .sources.sos import Sos
from .sources.suggestions import Suggestions
from .sources.tec import Tec
from .sources.tigerweb import Tigerweb
from .sources.trackaipac import TrackAipac
from .sources.voteforpeace import VoteForPeace

MIN_INTERVAL = {
    "nominatim": 1.0, "suggestions": 0.5, "ballotpedia": 1.0, "fec": 0.1, "tigerweb": 0.25, "election_precincts": 1.0,
    "sboe": 1.0, "county_precincts": 0.25, "officeholders": 1.0, **{feed.source: 1.0 for feed in FEEDS},
}
TRANSIENT = frozenset({suggestions.SOURCE, osm_tiles.SOURCE})  # no use as a fallback once expired, and capped
MISSES = frozenset({census.SOURCE, nominatim.SOURCE, google.SOURCE})  # whose "not found" answers are pruned once expired


def prune(cache: HttpCache, config: Config, *, vacuum: bool = True) -> int:
    """Delete what's no use even as a fallback (expired suggestions and tiles, addresses that
    weren't found, expired flags), and keep the street map's tiles and the address suggestions
    under their caps, dropping the oldest first. Every other source's answers stay, as the copy
    to show when it's down. Returns the rows deleted."""
    return cache.prune(
        TRANSIENT, MISSES, config.ttl.prune_after,
        caps={osm_tiles.SOURCE: config.tiles_max_bytes, suggestions.SOURCE: config.suggest_max_bytes},
        vacuum=vacuum,
    )


@asynccontextmanager
async def open_services(
    config: Config,
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
    tidy: bool = True,
) -> AsyncIterator[Services]:
    """Every service, on one HTTP client and the cache in ``config.data_dir``, with the bundled
    snapshots and SBOE map seeded and the answers bundled with Pallot in the cache (from ``bundles``, a data folder
    in tests). ``tidy``: remove what an interrupted precinct map download left (the server, at
    startup; never pallot-cache, which may run beside a server's download)."""
    config.data_dir.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(
        timeout=config.http_timeout, headers={"User-Agent": config.user_agent}, follow_redirects=True
    ) as client:
        cache = HttpCache(
            config.cache_path,
            client,
            min_interval=dict(min_interval),
            source_headers={
                **({google.SOURCE: {google.KEY_HEADER: config.google_api_key}} if config.google_api_key else {}),
            },
            retry_after=config.ttl.retry_after,
        )
        election_precincts = ElectionPrecincts(cache, config.ttl, config.election_precincts_dir, tidy=tidy)
        try:
            lists = sorted(
                [*load_all(endorsements_dir, reserved={info.id for info in SOURCES} | {f.source for f in FEEDS}),
                 *make_feeds(cache, config.ttl)],
                key=lambda found: found.label.lower(),
            )
            svc = Services(
                config=config,
                sources=Sources(defaults((found.source for found in lists), config.sources_path)),
                cache=cache,
                census=Census(cache, config.ttl),
                nominatim=Nominatim(cache, config.ttl),
                google=Google(cache, config.ttl, config.google_api_key),
                suggestions=Suggestions(cache, config.ttl),
                sboe=SboeMap(cache, config.ttl, config.sboe_path, sboe_bundled or sboe.BUNDLED),
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
                fec=Fec(cache, config.ttl, config.fec_api_keys, today),
                tec=Tec(config.tec_dir, refresh_fn=tec_refresh, bundled_dir=tec_bundled, user_agent=config.user_agent),
                polls=Polls(cache, config.ttl, today),
                officeholders=Officeholders(cache, config.ttl),
                key_dates=key_dates.KeyDatesPage(cache, config.ttl),
                tigerweb=Tigerweb(cache, config.ttl),
                tiles=Tiles(cache, config.ttl),
                today=today,
            )
            await asyncio.to_thread(svc.trackaipac.ensure_seeded)
            await asyncio.to_thread(svc.voteforpeace.ensure_seeded)
            await asyncio.to_thread(svc.tec.ensure_seeded)
            await asyncio.to_thread(svc.sboe.ensure_seeded)
            svc.bundles = await asyncio.to_thread(seed_bundles, cache, config.ttl, bundles or BUNDLES_DIR)
            yield svc
        finally:
            await election_precincts.aclose()  # before the client closes under a download
            cache.close()
