"""The Compare dialog's pivots: each candidate's breakdowns turned into rows of bars side by
side, and name lists into columns with names more than one candidate has flagged."""

from __future__ import annotations

from votebot.models import Breakdown, Share
from votebot.sources import compare


def breakdown(*parts, total=None):
    return Breakdown(title="t", parts=[Share(label=label, amount=amount, count=count) for label, amount, count in parts],
                     total=total)


def test_bars_keep_the_categories_in_order_and_tell_nothing_from_no_figure():
    section = compare.bars("Where the money came from", {
        "a": breakdown(("Small", 10.0, None), ("PACs", 30.0, 2), total=40.0),
        "b": breakdown(("Small", 5.0, None), ("Individuals", 50.0, 7), ("PACs", 5.0, 1), total=60.0),
        "c": None,  # the source has the candidate, not this breakdown
    })
    assert [r.label for r in section.rows] == ["Small", "Individuals", "PACs"]
    individuals = section.rows[1]
    assert [(v.candidate_key, v.amount, v.count) for v in individuals.values] == [("a", 0.0, None), ("b", 50.0, 7), ("c", None, None)]
    assert section.totals == {"a": 40.0, "b": 60.0}


def test_bars_need_someone_with_the_breakdown():
    assert compare.bars("t", {"a": None, "b": breakdown()}) is None


def test_figures_leave_out_rows_nobody_has():
    section = compare.figures("Totals", [
        compare.row("Raised", {"a": 100.0, "b": 50.0}),
        compare.row("Loans", {"a": 0.0, "b": None}),
        compare.row("Itemized donations", {"a": 80.0, "b": 0.0}, {"a": 12, "b": 0}),
    ])
    assert [r.label for r in section.rows] == ["Raised", "Itemized donations"]
    assert [(v.amount, v.count) for v in section.rows[1].values] == [(80.0, 12), (0.0, 0)]
    assert not section.totals  # totals aren't shares of anything
    assert compare.figures("Totals", [compare.row("Loans", {"a": None})]) is None


def test_columns_flag_names_in_more_than_one_column():
    section = compare.columns("Largest donors", {
        "a": compare.named(breakdown(("Texans for Lawsuit Reform PAC", 500.0, 1), ("Pat Smith", 100.0, 1))),
        "b": compare.named(breakdown(("TEXANS FOR LAWSUIT REFORM PAC", 50.0, 1))),
        "c": compare.named(breakdown(("Texans for Lawsuit Reform PAC", 5.0, 1))),
        "d": [],
    })
    tlr, pat = section.columns["a"]
    assert tlr.shared_with == ["b", "c"] and pat.shared_with == []
    assert section.columns["b"][0].shared_with == ["a", "c"]
    assert "d" not in section.columns  # nothing to list


def test_columns_match_on_the_key_given():
    pat = Share(label="Pat Smith", amount=100.0)
    section = compare.columns("Largest donors", {"a": [(pat, "PAT SMITH|TX")], "b": [(pat, "PAT SMITH|CA")]})
    assert section.columns["a"][0].shared_with == []  # a different Pat Smith
