"""Helpers shared by the bundle tests (test_bundles.py and test_bundle_<source>.py)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from bundles import registry, store
from bundles.entry import Bundle
from bundles.refresh import Outcome, refresh
from pallot.config import Config, Ttls
from pallot.http_cache import RequestSpec

from .conftest import TODAY

NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)  # the cache's clock is the real one


def build_all(tmp_path: Path, names: tuple[str, ...], config: Config | None = None, now: dt.datetime = NOW,
              **kwargs: Any) -> dict[str, Outcome]:
    """Refresh the named bundles into tmp_path/bundles, with no throttle, as of TODAY."""
    outcomes = refresh(names, data_dir=tmp_path / "bundles", config=config or Config(data_dir=tmp_path / "data"),
                       today=lambda: TODAY, now=now, min_interval={}, **kwargs)
    return {outcome.source: outcome for outcome in outcomes}


def build(tmp_path: Path, name: str, **kwargs: Any) -> Outcome:
    return build_all(tmp_path, (name,), **kwargs)[name]


def entry(name: str) -> Bundle:
    return next(e for e in registry.BUNDLES if e.name == name)


def answers(tmp_path: Path, name: str) -> list[dict[str, Any]]:
    return store.load(name, tmp_path / "bundles").answers


def lifetimes(tmp_path: Path, name: str) -> set[float]:
    """The bundle lifetimes its answers are seeded with."""
    return {entry(name).ttl(Ttls(), RequestSpec(**a["request"])) for a in answers(tmp_path, name)}


def notice(client: TestClient, source: str) -> str:
    """The source's notice in Settings."""
    return next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == source)["notice"]
