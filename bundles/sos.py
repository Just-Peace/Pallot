"""Texas SOS's bundles: the statewide answers every lookup starts from (elections, reference tables,
each upcoming election's candidate list), and, in a bundle of their own, every county's ballot order
for each upcoming election; each answer kept for its own bundle lifetime."""

from __future__ import annotations

from typing import Any

from pallot.config import Ttls
from pallot.http_cache import RequestSpec, UpstreamError, value_is_empty
from pallot.sources.sos import CBP, SYSTEM, Sos

from .entry import BundleError, Context

BALLOT_ORDER = f"{CBP}/getCandidateBallotOrder"
MAX_SERVER_ERRORS = 10  # ballot orders a build may leave out after an HTTP 5xx before it gives up
LIFETIMES = {  # endpoint -> the Ttls field of its answers' bundle lifetime
    f"{CBP}/getElectionsByYear/": "sos_elections_bundle",
    f"{SYSTEM}/getAllRegions": "sos_reference_bundle",
    f"{CBP}/getPoliticalParties": "sos_reference_bundle",
    f"{CBP}/getCandidateStatus": "sos_reference_bundle",
    f"{CBP}/getDeclarationStatus": "sos_reference_bundle",
    f"{CBP}/findQualifiedCandidates": "sos_candidates_bundle",
    BALLOT_ORDER: "sos_ballot_order_bundle",
}


def lifetime(ttl: Ttls, spec: RequestSpec) -> float:
    """An answer's bundle lifetime, by its endpoint; an endpoint the bundle doesn't know is an error."""
    for endpoint, field in LIFETIMES.items():
        if spec.url == endpoint or (endpoint.endswith("/") and spec.url.startswith(endpoint)):
            return getattr(ttl, field)
    raise ValueError(f"no bundle lifetime for {spec.url}")


def is_ballot_order(spec: RequestSpec) -> bool:
    return spec.url == BALLOT_ORDER


def statewide(spec: RequestSpec) -> bool:
    return not is_ballot_order(spec)


def published(value: Any) -> bool:
    """An empty ballot order (not out yet, or a special the county isn't in) is asked live, kept briefly (sos_empty)."""
    return not value_is_empty(value)


async def build(ctx: Context) -> dict[str, int]:
    """This year's and next year's elections, the reference tables, and each upcoming election's
    statewide candidate list; counts the upcoming elections and their candidates."""
    sos = Sos(ctx.cache, ctx.config.ttl, ctx.today)
    try:
        elections = [e for day in (await sos.upcoming()).values() for e in day]
        await sos.counties()
        await sos.lookups()
        lists = [(await sos.candidates(e)).value or [] for e in elections]
    except Exception as exc:
        raise BundleError(f"couldn't load Texas SOS's statewide data: {exc}") from exc
    if not elections:
        raise BundleError("Texas SOS lists no upcoming election")
    return {"elections": len(elections), "candidates": sum(len(rows) for rows in lists)}


async def build_ballot_orders(ctx: Context) -> dict[str, int]:
    """Every county's ballot order for each upcoming election, one request after another (at the
    build's pace for Texas SOS, refresh.BUILD_INTERVAL). It stops at the first refusal (which pauses
    Texas SOS) or other failure, except a server error: Texas SOS answers HTTP 500 now and then for
    one county, which is then left out and asked live, up to MAX_SERVER_ERRORS of them. Counts the
    elections, the published ballot orders and the ones left out."""
    sos = Sos(ctx.cache, ctx.config.ttl, ctx.today)
    count = errors = 0
    try:
        elections = [e for day in (await sos.upcoming()).values() for e in day]
        counties = sorted((await sos.counties()).values())
        for election in elections:
            for county_id in counties:
                try:
                    count += published((await sos.ballot_order(election, county_id)).value)
                except UpstreamError as exc:
                    if (exc.status or 0) < 500 or exc.until is not None or errors >= MAX_SERVER_ERRORS:
                        raise
                    errors += 1
    except Exception as exc:
        raise BundleError(f"couldn't load Texas SOS's ballot orders: {exc}") from exc
    if not elections or not counties:
        raise BundleError("Texas SOS lists no upcoming election or no county")
    return {"elections": len(elections), "ballot_orders": count, "server_errors": errors}
