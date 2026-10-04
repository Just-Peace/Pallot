from __future__ import annotations

import dataclasses

import pytest

from voteforpeace_cache.errors import ValidationError
from voteforpeace_cache.guard import validate
from voteforpeace_cache.parser import ParseResult, parse_page


@pytest.fixture
def parsed(page) -> ParseResult:
    return parse_page(page)


def problems(result: ParseResult) -> str:
    with pytest.raises(ValidationError) as caught:
        validate(result)
    return "\n".join(caught.value.problems)


def test_the_page_passes_with_nothing_to_note(parsed):
    assert validate(parsed) == []


def test_too_few_candidates(parsed):
    assert "parsed 99 candidates, expected at least 100" in problems(ParseResult(parsed.records[:99]))


def test_unknown_rating_and_missing_fields(parsed):
    records = [dataclasses.replace(r, rating="endorse", office_title=None) for r in parsed.records]
    found = problems(ParseResult(records))
    assert "unknown ratings: endorse" in found and "have office_title" in found


def test_the_same_candidate_twice(parsed):
    assert "listed more than once" in problems(ParseResult(parsed.records + parsed.records[:1]))


def test_an_unrated_candidate_is_kept_with_a_note(parsed):
    records = [dataclasses.replace(parsed.records[0], rating=None), *parsed.records[1:]]
    assert validate(ParseResult(records)) == ["'Robert Hunter' (AL) has no rating; stored as shown"]
