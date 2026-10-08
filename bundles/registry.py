"""BUNDLES, the answers that come with Pallot, and seed(), which puts them in the cache at startup."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from pallot.config import Ttls
from pallot.http_cache import HttpCache, RequestSpec

from . import fec, sos, store
from .entry import Bundle

BUNDLES: tuple[Bundle, ...] = (
    Bundle("fec", fec.build, "daily"),
    Bundle("sos", sos.build, "daily", lifetime=sos.lifetime, include=sos.statewide),
    Bundle("sos", sos.build_ballot_orders, "daily", lifetime=sos.lifetime, name="sos_ballot_order",
           include=sos.is_ballot_order, keep=sos.published),
)


def seed(cache: HttpCache, ttl: Ttls, data_dir: Path = store.PACKAGE_DATA_DIR,
         bundles: tuple[Bundle, ...] | None = None) -> dict[str, store.Loaded]:
    """Put each bundle's answers in the cache under its source, as fetched when they were last
    checked and kept for their bundle lifetime, where the cache has no copy as new (HttpCache.seed).
    Returns the bundles that had answers, by name, each with its source, for Settings."""
    loaded = {}
    for entry in BUNDLES if bundles is None else bundles:
        bundle = store.load(entry.name, data_dir)
        if bundle.checked_at is None or not bundle.answers:
            continue
        for answer in bundle.answers:
            spec = RequestSpec(**answer["request"])
            cache.seed(entry.source, [(spec, answer["value"])], bundle.checked_at, entry.ttl(ttl, spec))
        loaded[entry.name] = dataclasses.replace(bundle, source=entry.source)
    return loaded
