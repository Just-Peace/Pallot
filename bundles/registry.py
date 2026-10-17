"""BUNDLES, the answers that come with Pallot, and seed(), which puts them in the cache at startup."""

from __future__ import annotations

from pathlib import Path

from pallot.config import Ttls
from pallot.http_cache import HttpCache, RequestSpec

from . import county_precincts, endorsement_feeds, fec, officeholders, polls, sos, states, store, tigerweb, wikidata
from .entry import Bundle

BUNDLES: tuple[Bundle, ...] = (
    Bundle("fec", fec.build, "daily", include=lambda spec: not fec.is_race_list(spec)),
    Bundle("fec", fec.build_races, "daily", name="fec_races", include=fec.is_race_list),
    Bundle("sos", sos.build, "daily", lifetime=sos.lifetime, include=sos.statewide),
    Bundle("sos", sos.build_ballot_orders, "daily", lifetime=sos.lifetime, name="sos_ballot_order",
           include=sos.is_ballot_order, keep=sos.published),
    Bundle("officeholders", officeholders.build, "weekly"),
    Bundle("wikidata", wikidata.build, "weekly"),
    Bundle("tigerweb", tigerweb.build, "weekly", keep=tigerweb.drawn),
    Bundle("county_precincts", county_precincts.build, "weekly"),
    Bundle("polls", polls.build, "daily"),
    *endorsement_feeds.BUNDLES,
    *states.BUNDLES,
)


def seed(cache: HttpCache, ttl: Ttls, data_dir: Path = store.PACKAGE_DATA_DIR,
         bundles: tuple[Bundle, ...] | None = None) -> dict[str, store.Seeded]:
    """Put each bundle's answers in the cache under its source, as fetched when they were last
    checked and kept for their bundle lifetime, where the cache has no copy as new (HttpCache.seed).
    Returns the bundles that had answers, by name, each with its source and count, for Settings:
    the answers themselves aren't kept in memory once they're in the cache."""
    loaded = {}
    for entry in BUNDLES if bundles is None else bundles:
        bundle = store.load(entry.name, data_dir)
        if bundle.checked_at is None or not bundle.answers:
            continue
        for answer in bundle.answers:
            spec = RequestSpec(**answer["request"])
            cache.seed(entry.source, [(spec, answer["value"])], bundle.checked_at, entry.ttl(ttl, spec))
        loaded[entry.name] = store.Seeded(entry.source, bundle.checked_at, len(bundle.answers))
    return loaded
