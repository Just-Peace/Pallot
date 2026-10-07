from __future__ import annotations

import pytest

from pallot.sources import fec
from pallot.sources.highlights import FLOOR, highlights


def chips(**figures):
    return [b.text for b in highlights({"raised": 100_000.0, **figures}, state="Texas", credit="FEC, 2025–26")]


@pytest.mark.parametrize("share, shown", [(49.9, False), (50.0, False), (50.1, True), (90.0, True)])
def test_each_chip_needs_more_than_half(share, shown):
    assert chips(small_share=share) == (["Mostly small donors"] if shown else [])
    assert chips(in_state_share=share) == (["Mostly Texas donors"] if shown else [])
    assert chips(self_share=share) == (["Mostly self-funded"] if shown else [])


@pytest.mark.parametrize("raised, shown", [(FLOOR - 0.01, False), (FLOOR, True), (FLOOR + 1, True), (None, False)])
def test_a_small_campaign_gets_none(raised, shown):
    figures = {"small_share": 80.0, "in_state_share": 80.0, "self_share": 80.0}
    if raised is not None:
        figures["raised"] = raised
    assert bool(highlights(figures, state="Texas", credit="TEC")) is shown


def test_the_hints_give_the_figure():
    small, home, own = highlights({"raised": 1_200_000.0, "small_share": 50.4, "in_state_share": 62.0, "self_share": 75.2},
                                  state="Texas", credit="FEC, 2025–26")
    assert small.hint == "50.4% of the $1.2M raised came from donations of $200 or less (FEC, 2025–26)"
    assert home.hint == "62% of itemized donations from individuals with an address came from Texas (FEC, 2025–26)"
    assert own.hint == "75% of the $1.2M raised was the candidate's own gifts and loans (FEC, 2025–26)"
    assert {small.tone, home.tone, own.tone} == {"neutral"}


def test_fec_in_state_share_leaves_out_donors_without_a_state():
    rows = [{"state": "TX", "total": 600.0}, {"state": "CA", "total": 400.0}, {"state": None, "total": 5000.0}]
    assert fec._in_state(rows, "TX") == 60.0
    assert fec._in_state([], "TX") is None and fec._in_state(None, "TX") is None
