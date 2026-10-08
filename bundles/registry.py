"""BUNDLES, the sources whose answers come with Pallot, and seed(), which puts them in the cache at startup."""

from __future__ import annotations

from pathlib import Path

from pallot.config import Ttls
from pallot.http_cache import HttpCache, RequestSpec

from . import fec, store
from .entry import Bundle

BUNDLES: tuple[Bundle, ...] = (
    Bundle("fec", fec.build, "daily"),
)


def seed(cache: HttpCache, ttl: Ttls, data_dir: Path = store.PACKAGE_DATA_DIR,
         bundles: tuple[Bundle, ...] | None = None) -> dict[str, store.Loaded]:
    """Put each source's bundled answers in the cache, as fetched when they were last checked and
    kept for their bundle lifetime, where the cache has no copy as new (HttpCache.seed). Returns
    the bundles that had answers, by source, for Settings."""
    loaded = {}
    for entry in BUNDLES if bundles is None else bundles:
        bundle = store.load(entry.source, data_dir)
        if bundle.checked_at is None or not bundle.answers:
            continue
        for answer in bundle.answers:
            spec = RequestSpec(**answer["request"])
            cache.seed(entry.source, [(spec, answer["value"])], bundle.checked_at, entry.ttl(ttl, spec))
        loaded[entry.source] = bundle
    return loaded
