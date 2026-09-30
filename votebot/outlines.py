"""The district outlines behind the map on Your districts (GET /api/district-outlines).

U.S. House, State Senate and State House come from TIGERweb, one cached request each, and
the State Board of Education district from the PLANE2106 map VoteBot already keeps. They
are asked by the page once the ballot is on screen, so a ballot lookup never waits on them.
A missing outline is a note, never a failed request: the map draws what it has.
"""

from __future__ import annotations

import asyncio
import time
import zipfile

import httpx

from .ballot import Services
from .http_cache import UpstreamError, track_calls
from .models import DistrictOutlines, Meta, Outline
from .sources import osm_tiles, tigerweb
from .sources.tigerweb import Ring

LABELS = {"cd": "U.S. House", "sd": "State Senate", "hd": "State House", "sboe": "State Board of Education"}


async def district_outlines(svc: Services, wanted: dict[str, int | None]) -> DistrictOutlines:
    calls = track_calls()
    started = time.monotonic()
    use_tigerweb = svc.settings.enabled(tigerweb.SOURCE)
    notes: list[str] = []

    async def one(kind: str, number: int) -> tuple[list[Ring] | None, str | None]:
        """The district's rings, or None and why."""
        label = f"{LABELS[kind]} District {number}"
        if kind == "sboe":
            try:
                found = await svc.sboe.outline(number, tigerweb.SIMPLIFY_DEG)
            except (httpx.HTTPError, ValueError, OSError, zipfile.BadZipFile):
                return None, f"Couldn't load the State Board of Education map, so {label} isn't drawn."
        else:
            try:
                found = await svc.tigerweb.outline(kind, number)
            except UpstreamError as exc:
                why = "is paused" if exc.until else "isn't responding"
                return None, f"The US Census's map service {why}, so {label} isn't drawn."
        return found, None if found else f"No outline found for {label}."

    asked = [(kind, number) for kind, number in wanted.items() if number is not None]
    if not use_tigerweb and any(kind in tigerweb.LAYERS for kind, _ in asked):
        notes.append("U.S. House, State Senate and State House outlines are turned off in Settings.")
        asked = [(kind, number) for kind, number in asked if kind not in tigerweb.LAYERS]
    found = await asyncio.gather(*(one(kind, number) for kind, number in asked))
    notes += [note for _, note in found if note]
    return DistrictOutlines(
        outlines=[
            Outline(kind=kind, number=number, rings=rings) for (kind, number), (rings, _) in zip(asked, found) if rings
        ],
        notes=notes,
        street_map=svc.settings.enabled(osm_tiles.SOURCE),
        meta=Meta(
            external_calls=calls.external_calls,
            cache_hits=calls.cache_hits,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        ),
    )
