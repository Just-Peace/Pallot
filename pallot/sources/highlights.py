"""The Funding chips on a candidate's row: a few facts worked out from a money source's
figures ("Mostly small donors"), by one set of rules for the FEC and the TEC, so the
thresholds match. They're facts, not endorsements, and say nothing under a $10,000 campaign.
"""

from __future__ import annotations

from ..models import Badge
from ..text import money_short

FLOOR = 10_000  # raised below this, a campaign isn't "mostly" anything
MOSTLY = 50  # a share above this percent is "mostly"


def _pct(value: float) -> str:
    """A share for a hint, with a decimal where rounding would make it read as half."""
    return f"{value:.0f}%" if value >= MOSTLY + 0.5 else f"{value:.1f}%"


def highlights(figures: dict[str, float], *, state: str, credit: str) -> list[Badge]:
    """The chips ``figures`` earn. ``state`` names the ballot's state ("Texas"), and ``credit``
    the source and period each hint ends with ("FEC, 2021–26")."""
    raised = figures.get("raised") or 0
    if raised < FLOOR:
        return []

    def share(name: str) -> float | None:
        value = figures.get(name)
        return value if value is not None and value > MOSTLY else None

    chips = []
    if (small := share("small_share")) is not None:
        chips.append(Badge(text="Mostly small donors",
                           hint=f"{_pct(small)} of the {money_short(raised)} raised came from donations of $200 or less ({credit})"))
    if (home := share("in_state_share")) is not None:
        chips.append(Badge(text=f"Mostly {state} donors",
                           hint=f"{_pct(home)} of itemized donations from individuals with an address came from {state} ({credit})"))
    if (own := share("self_share")) is not None:
        chips.append(Badge(text="Mostly self-funded",
                           hint=f"{_pct(own)} of the {money_short(raised)} raised was the candidate's own gifts and loans ({credit})"))
    return chips
