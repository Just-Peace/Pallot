"""The counties' bundle: each of the seven counties' list of its election precincts, or its maps of
its commissioner and JP precincts, asked exactly as a lookup asks (CountyPrecincts.records): the
service index, the service's layers and every page of the layer, so the cache keys match.

A county refusing a request (403, 429) pauses all seven, so the build stops there. A county whose
server is down, or whose records can't be read, is left out and counted, so a lookup there asks it
live; the build fails when most are."""

from __future__ import annotations

import logging

from pallot.http_cache import RequestSpec, UpstreamError
from pallot.sources import arcgis_error
from pallot.sources import county_precincts as cp
from pallot.sources.election_precincts import ElectionPrecincts

from .entry import BundleError, Context


async def build(ctx: Context) -> dict[str, int]:
    """Every county's records, one request after another at the counties' pace; counts the
    counties bundled and those left out."""
    counties = cp.COUNTIES
    precincts = ElectionPrecincts(ctx.cache, ctx.config.ttl, ctx.config.election_precincts_dir, tidy=False)
    svc = cp.CountyPrecincts(ctx.cache, ctx.config.ttl, precincts, counties)
    left_out: list[str] = []
    for county in counties.values():
        try:
            await svc.records(county)
        except UpstreamError as exc:
            if exc.status in cp.REFUSALS or exc.until:
                raise BundleError(f"{exc}; every county's server is paused, so the others weren't asked") from exc
            left_out.append(f"{county.name} ({exc})")
        except (ValueError, OSError) as exc:
            left_out.append(f"{county.name} ({exc})")
        for saved in ctx.cache.saved(cp.SOURCE):
            kept = ctx.cache.peek(RequestSpec.loads(saved.request))
            if kept is not None and (why := arcgis_error(kept.value)):
                raise BundleError(f"{county.name} County's map server answered an ArcGIS error: {why}")
    if len(left_out) * 2 > len(counties):
        raise BundleError(f"most counties couldn't be asked: {'; '.join(left_out)}")
    for why in left_out:
        logging.getLogger(__name__).warning("county_precincts: left out %s", why)
    return {"counties": len(counties) - len(left_out), "missing": len(left_out)}
