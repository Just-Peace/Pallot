"""TIGERweb's bundle: the service index and every Texas U.S. House, State Senate and State House
district's outline, asked exactly as a lookup asks (Tigerweb.outline), so the cache keys match. The
SBOE's outlines come from the SBOE map Pallot keeps, not from TIGERweb."""

from __future__ import annotations

from typing import Any

from pallot.sources.tigerweb import Tigerweb

from .entry import BundleError, Context

DISTRICTS = {"cd": 38, "sd": 31, "hd": 150}  # Texas's districts of each kind TIGERweb draws


def drawn(value: Any) -> bool:
    """A district TIGERweb has no shape for isn't bundled, so a lookup asks for it live."""
    return not isinstance(value, dict) or "layers" in value or bool(value.get("features"))


async def build(ctx: Context) -> dict[str, int]:
    """Every district's outline, one request after another at TIGERweb's pace; counts those found
    of each kind and those TIGERweb had no shape for."""
    svc = Tigerweb(ctx.cache, ctx.config.ttl)
    counts = {kind: 0 for kind in DISTRICTS}
    try:
        for kind, highest in DISTRICTS.items():
            for number in range(1, highest + 1):
                counts[kind] += await svc.outline(kind, number) is not None
    except Exception as exc:
        raise BundleError(f"couldn't load TIGERweb's district outlines: {exc}") from exc
    if not all(counts.values()):
        raise BundleError("TIGERweb has no layer or no outline for a kind of Texas district")
    return {**counts, "missing": sum(DISTRICTS.values()) - sum(counts.values())}
