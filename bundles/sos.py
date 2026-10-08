"""Texas SOS's bundle: the statewide answers every lookup starts from (elections, reference tables,
each upcoming election's candidate list), each kept for its own bundle lifetime."""

from __future__ import annotations

from pallot.config import Ttls
from pallot.http_cache import RequestSpec
from pallot.sources.sos import CBP, SYSTEM, Sos

from .entry import BundleError, Context

LIFETIMES = {  # endpoint -> the Ttls field of its answers' bundle lifetime
    f"{CBP}/getElectionsByYear/": "sos_elections_bundle",
    f"{SYSTEM}/getAllRegions": "sos_reference_bundle",
    f"{CBP}/getPoliticalParties": "sos_reference_bundle",
    f"{CBP}/getCandidateStatus": "sos_reference_bundle",
    f"{CBP}/getDeclarationStatus": "sos_reference_bundle",
    f"{CBP}/findQualifiedCandidates": "sos_candidates_bundle",
}


def lifetime(ttl: Ttls, spec: RequestSpec) -> float:
    """An answer's bundle lifetime, by its endpoint; an endpoint the bundle doesn't know is an error."""
    for endpoint, field in LIFETIMES.items():
        if spec.url == endpoint or (endpoint.endswith("/") and spec.url.startswith(endpoint)):
            return getattr(ttl, field)
    raise ValueError(f"no bundle lifetime for {spec.url}")


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
