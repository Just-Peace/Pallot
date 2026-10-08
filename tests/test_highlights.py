from __future__ import annotations

import pytest

from pallot.sources import fec
from pallot.sources.highlights import FLOOR, highlights


def chips(**figures):
    return [(b.text, b.tone) for b in highlights({"raised": 100_000.0, **figures}, state="Texas", credit="FEC, 2025–26")]


@pytest.mark.parametrize("share, small, home", [
    (90.0, ("Overwhelmingly small donors", "good"), ("Overwhelmingly Texas donors", "good")),
    (75.1, ("Overwhelmingly small donors", "good"), ("Overwhelmingly Texas donors", "good")),
    (75.0, ("Mostly small donors", "good"), ("Mostly Texas donors", "good")),
    (50.1, ("Mostly small donors", "good"), ("Mostly Texas donors", "good")),
    (50.0, None, None),
    (49.9, ("Mostly large donations", "warn"), ("Mostly out-of-state donors", "warn")),
    (25.0, ("Mostly large donations", "warn"), ("Mostly out-of-state donors", "warn")),
    (24.9, ("Overwhelmingly large donations", "warn"), ("Overwhelmingly out-of-state donors", "warn")),
])
def test_a_share_reads_both_ways_by_degree(share, small, home):
    assert chips(small_share=share) == ([small] if small else [])
    assert chips(in_state_share=share) == ([home] if home else [])


@pytest.mark.parametrize("share, chip", [(90.0, ("Overwhelmingly self-funded", "warn")), (60.0, ("Mostly self-funded", "warn")),
                                         (50.0, None), (10.0, None)])
def test_self_funding_shows_only_above_half(share, chip):
    assert chips(self_share=share) == ([chip] if chip else [])


@pytest.mark.parametrize("raised, shown", [(FLOOR - 0.01, False), (FLOOR, True), (FLOOR + 1, True), (None, False)])
def test_a_small_campaign_gets_none(raised, shown):
    figures = {"small_share": 80.0, "in_state_share": 80.0, "self_share": 80.0}
    if raised is not None:
        figures["raised"] = raised
    assert bool(highlights(figures, state="Texas", credit="TEC")) is shown


def test_the_hints_give_the_figure():
    small, home, own = highlights({"raised": 1_200_000.0, "small_share": 50.4, "in_state_share": 62.0, "self_share": 75.2},
                                  state="Texas", credit="FEC, 2025–26")
    assert small.hint == "50.4% of the $1.2M raised came from donations under $500 (FEC, 2025–26)"
    assert home.hint == "62% of itemized donations from individuals with an address came from Texas (FEC, 2025–26)"
    assert own.hint == "75% of the $1.2M raised was the candidate's own gifts and loans (FEC, 2025–26)"
    [large] = highlights({"raised": 1_200_000.0, "small_share": 20.0}, state="Texas", credit="FEC, 2025–26")
    assert large.hint == "20% of the $1.2M raised came from donations under $500 (FEC, 2025–26)"


def test_fec_in_state_share_leaves_out_donors_without_a_state():
    rows = [{"state": "TX", "total": 600.0}, {"state": "CA", "total": 400.0}, {"state": None, "total": 5000.0}]
    assert fec._in_state(rows, "TX") == 60.0
    assert fec._in_state([], "TX") is None and fec._in_state(None, "TX") is None
