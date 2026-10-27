"""The district outlines behind the map on Your districts (GET /api/district-outlines).

U.S. House, State Senate and State House come from TIGERweb, one cached request each, in any
state; in Texas, the State Board of Education district from the PLANE2106 map Pallot already
keeps, and the election precinct from the precinct map the ballot lookup downloaded (never
downloaded here).
They are asked by the page once the ballot is on screen, so a ballot lookup never waits on them.
A missing outline is a note, never a failed request: the map draws what it has.
"""

from __future__ import annotations

import asyncio
import zipfile

from . import coverage
from .ballot import Services
from .http_cache import UpstreamError, track_calls
from .models import DistrictOutlines, Outline
from .settings import Sources
from .sources import election_precincts, osm_tiles, tigerweb
from .sources.sboe import Ring

LABELS = {"cd": "U.S. House", "sd": "State Senate", "hd": "State House", "sboe": "State Board of Education"}


async def district_outlines(
    svc: Services, wanted: dict[str, int | str | None], precinct: tuple[int, str] | None = None,
    sources: Sources | None = None, state: str = "TX",
) -> DistrictOutlines:
    """The districts in ``wanted`` (kind -> number, or name) in ``state``, then the election
    precinct (county FIPS, the map's code for it), with the sources the voter has on (by default,
    Pallot's defaults)."""
    calls = track_calls()
    sources = sources or svc.sources
    use_tigerweb = sources.enabled(tigerweb.SOURCE)
    labels = {**LABELS, **coverage.of(state).labels}
    notes: list[str] = []

    async def one(kind: str, number: int | str) -> tuple[list[Ring] | None, str | None]:
        """The district's rings, or None and why."""
        label = f"{labels[kind]} (at large)" if kind == "cd" and number == 0 else f"{labels[kind]} District {number}"
        if kind == "sboe":
            try:
                found = await svc.sboe.outline(number, tigerweb.SIMPLIFY_DEG)
            except UpstreamError as exc:
                why = "is paused" if exc.until else "isn't responding"
                return None, f"The Texas Legislative Council's portal {why}, so {label} isn't drawn."
            except (ValueError, OSError, zipfile.BadZipFile):
                return None, f"Couldn't load the State Board of Education map, so {label} isn't drawn."
        else:
            try:
                found = await svc.tigerweb.outline(kind, number, state)
            except UpstreamError as exc:
                why = "is paused" if exc.until else "isn't responding"
                return None, f"The US Census's map service {why}, so {label} isn't drawn."
        return found, None if found else f"No outline found for {label}."

    async def election_precinct(county: int, code: str) -> tuple[list[Ring] | None, str | None]:
        """The precinct's rings from the map kept, or None and why."""
        label = f"Election precinct {election_precincts.display_name(code)}"
        if not sources.enabled(election_precincts.SOURCE):
            return None, "Election precinct outlines are turned off in Settings."
        if svc.election_precincts.stored() is None:
            return None, f"The election precinct map hasn't downloaded yet, so {label} isn't drawn."
        try:
            found = await svc.election_precincts.outline(county, code)
        except (OSError, ValueError):
            return None, f"Couldn't read the election precinct map, so {label} isn't drawn."
        return found, None if found else f"No outline found for {label}."

    asked = [(kind, number) for kind, number in wanted.items() if number is not None]
    if not use_tigerweb and any(kind in tigerweb.LAYERS for kind, _ in asked):
        notes.append("U.S. House, State Senate and State House outlines are turned off in Settings.")
        asked = [(kind, number) for kind, number in asked if kind not in tigerweb.LAYERS]
    drawn: list[tuple[tuple[str, int | str], tuple[list[Ring] | None, str | None]]] = list(
        zip(asked, await asyncio.gather(*(one(kind, number) for kind, number in asked)))
    )
    if precinct:
        county, code = precinct
        drawn.append((("election_precinct", election_precincts.display_name(code)), await election_precinct(county, code)))
    notes += [note for _, (_, note) in drawn if note]
    outlines = DistrictOutlines(
        outlines=[Outline(kind=kind, number=number, rings=rings) for (kind, number), (rings, _) in drawn if rings],
        notes=notes,
        street_map=sources.enabled(osm_tiles.SOURCE),
    )
    calls.log("district outlines")
    return outlines
