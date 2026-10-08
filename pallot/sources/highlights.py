"""The Funding chips on a candidate's row: a few facts worked out from a money source's
figures ("Mostly small donors"), by one set of rules for the FEC and the TEC, so the
thresholds match. Each share reads both ways: small donors and Texas donors are green, large
donations, out-of-state donors and self-funding amber. Above OVERWHELMING percent a chip says
"Overwhelmingly", above MOSTLY "Mostly", and it says nothing under a $10,000 campaign.
"""

from __future__ import annotations

from ..models import Badge
from ..text import money_short

FLOOR = 10_000  # raised below this, a campaign isn't "mostly" anything
MOSTLY = 50  # a share above this percent is "mostly"
OVERWHELMING = 75  # and above this, "overwhelmingly"


def _pct(value: float) -> str:
    """A share for a hint, with a decimal where rounding would make it read as half."""
    return f"{value:.1f}%" if abs(value - MOSTLY) < 0.5 else f"{value:.0f}%"


def _degree(value: float) -> str | None:
    """"Overwhelmingly" or "Mostly" for a share, or None at half or under."""
    if value > OVERWHELMING:
        return "Overwhelmingly"
    return "Mostly" if value > MOSTLY else None


def _sides(value: float, good: str, bad: str, hint: str, credit: str) -> Badge | None:
    """The chip a share earns: ``good`` (green) above half, ``bad`` (amber) below it, with the
    share of each side in the hint."""
    for share, words, tone in ((value, good, "good"), (100 - value, bad, "warn")):
        if degree := _degree(share):
            return Badge(text=f"{degree} {words}", tone=tone, hint=f"{hint.format(_pct(value))} ({credit})")
    return None


def highlights(figures: dict[str, float], *, state: str, credit: str) -> list[Badge]:
    """The chips ``figures`` earn. ``state`` names the ballot's state ("Texas"), and ``credit``
    the source and period each hint ends with ("FEC, 2021–26")."""
    raised = figures.get("raised") or 0
    if raised < FLOOR:
        return []
    chips: list[Badge | None] = []
    if (small := figures.get("small_share")) is not None:
        chips.append(_sides(small, "small donors", "large donations",
                            f"{{}} of the {money_short(raised)} raised came from donations of $200 or less", credit))
    if (home := figures.get("in_state_share")) is not None:
        chips.append(_sides(home, f"{state} donors", "out-of-state donors",
                            f"{{}} of itemized donations from individuals with an address came from {state}", credit))
    if (own := figures.get("self_share")) is not None and (degree := _degree(own)):
        chips.append(Badge(text=f"{degree} self-funded", tone="warn",
                           hint=f"{_pct(own)} of the {money_short(raised)} raised was the candidate's own gifts and loans ({credit})"))
    return [chip for chip in chips if chip]
