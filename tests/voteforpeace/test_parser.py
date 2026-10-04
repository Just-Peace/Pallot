from __future__ import annotations

import pytest

from voteforpeace_cache.errors import ParseError
from voteforpeace_cache.parser import parse_page, plain_text

from .conftest import edit


def by_name(page: str) -> dict:
    return {r.name: r for r in parse_page(page).records}


def test_reads_every_candidate_in_page_order(page):
    result = parse_page(page)
    assert len(result.records) == 197 and result.unnamed == []
    assert sum(r.state == "TX" for r in result.records) == 164
    assert [r.state for r in result.records][:2] == ["AL", "AZ"]  # state by state, as the site sorts them


def test_a_candidate_as_the_site_lists_them(page):
    talarico = by_name(page)["James Talarico"]
    assert (talarico.state, talarico.section, talarico.rating, talarico.office_title, talarico.level) == (
        "TX", "Texas", "vote", "U.S. Senator", "federal")
    assert talarico.url == "https://voteforpeace.info/texas/james-talarico"
    assert [e.organization for e in talarico.endorsements] == ["Muslims United PAC", "Asian American Democrats of Texas"]
    assert talarico.election_label == "General: Nov 3, 2026" and talarico.notes.startswith("Candidate's foreign policy")


def test_ratings_other_than_ally(page):
    people = by_name(page)
    assert (people["Jake Auchincloss"].rating, people["Dave Dawson"].rating) == ("reject", "neutral")


def test_notes_are_plain_text_and_names_one_line(page):
    people = by_name(page)
    assert people["Zohaib Qadri"].notes == "Endorsed by Our Revolution."  # "<p>…</p>" on the site
    assert "Damarcus L. Offord" in people  # "Damarcus L.\nOfford" on the site
    assert plain_text("<p>One &amp; two</p><p></p>Three<br/>four") == "One & two\nThree\nfour"


def test_a_misnamed_section_keeps_the_state_and_its_link(page):
    lalama = by_name(page)["Nicolo Lalama"]  # in a section the site calls "Ca"
    assert (lalama.state, lalama.section, lalama.url) == ("CA", "Ca", "https://voteforpeace.info/ca/nicolo-lalama")


def test_a_candidate_without_a_name_is_reported(page):
    result = parse_page(edit(page, '"name":"James Talarico"', '"name":" "'))
    assert len(result.records) == 196 and result.unnamed == ["a896e435-6bf9-4893-b4cd-ffbdaa942f31"]


@pytest.mark.parametrize("broken, message", [
    ("<html><body>Maintenance</body></html>", "no Next.js data"),
    ('<script>self.__next_f.push([1,"0:{}"])</script>', "no candidate sections"),
    ('<script>self.__next_f.push([1,"{\\"sections\\":[{\\"key\\""])</script>', "aren't JSON"),
])
def test_a_page_without_the_list_is_refused(broken, message):
    with pytest.raises(ParseError, match=message):
        parse_page(broken)
