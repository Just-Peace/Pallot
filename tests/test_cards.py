from __future__ import annotations

from pallot.models import Match
from pallot.sources import trackaipac
from pallot.sources.ballotpedia import BpCandidate, BpRace, card as ballotpedia_card

EXACT = Match(confidence="exact", method="full name, in the same seat")


def listing(category, total=None, **extra):
    return {"category": category, "israel_lobby_total": total, **extra}


def test_trackaipac_list_and_money_share_one_linked_badge():
    person = {"name": "August Pfluger", "seat": "TX-11", "categories": ["congress"],
              "listings": [listing("congress", 219959, seat="TX-11")]}
    [badge] = trackaipac.card(person, EXACT, "2026-09-27").badges
    assert badge.text == "TrackAIPAC: member of Congress $219,959"
    assert badge.url == trackaipac.CATEGORY_PAGES["congress"]
    assert badge.tone == "warn" and "Israel lobby" in badge.hint


def test_trackaipac_badge_per_list_without_money_when_none_is_shown():
    person = {"name": "Greg Casar", "seat": "TX-35", "categories": ["endorsed", "congress"],
              "listings": [listing("endorsed"), listing("congress")]}
    badges = trackaipac.card(person, EXACT, "2026-09-27").badges
    assert [b.text for b in badges] == ["TrackAIPAC endorsed", "TrackAIPAC: member of Congress"]
    assert [b.tone for b in badges] == ["good", "info"]
    assert all(b.url for b in badges) and not any(b.hint for b in badges)


def test_trackaipac_lists_and_money_for_pick_by_rule():
    member = {"name": "August Pfluger", "categories": ["congress"], "listings": [listing("congress", 219959)]}
    assert (trackaipac.card(member, EXACT, None).flags, trackaipac.card(member, EXACT, None).figures) == (
        ["congress"], {"israel_lobby": 219959})
    endorsed = {"name": "Greg Casar", "categories": ["endorsed", "congress"],
                "listings": [listing("endorsed"), listing("congress")]}
    assert (trackaipac.card(endorsed, EXACT, None).flags, trackaipac.card(endorsed, EXACT, None).figures) == (
        ["endorsed", "congress"], {})  # no total shown: no figure, rather than $0
    watched = {"name": "James Talarico", "categories": ["watchlist"], "listings": [listing("watchlist", 0)]}
    assert trackaipac.card(watched, EXACT, None).figures == {"israel_lobby": 0}


def test_trackaipac_notes_link_to_the_site_not_to_pallot():
    person = {"name": "James Talarico", "seat": "TX-SEN", "categories": ["watchlist"], "listings": [listing(
        "watchlist", 0, notes=["[This candidate is pro-israel.](/james-talarico)",
                               "Said so [on X](https://x.com/someone/status/1) and [here](/endorsements)."])]}
    assert trackaipac.card(person, EXACT, "2026-09-27").quotes == [
        "[This candidate is pro-israel.](https://www.trackaipac.com/james-talarico)",
        "Said so [on X](https://x.com/someone/status/1) and [here](https://www.trackaipac.com/endorsements).",
    ]


def test_ballotpedia_profile_badge_links_to_the_profile():
    race = BpRace(1, "U.S. Senate Texas", "State", "Texas", "federal", 1, "https://ballotpedia.org/race", ())
    with_survey = BpCandidate(7, "Ken Paxton", "R", "Republican Party", False, False, "On the Ballot",
                              "https://ballotpedia.org/Ken_Paxton", None, True)
    result = ballotpedia_card(with_survey, race, 0.0, None)
    [badge] = result.badges
    assert (badge.text, badge.url) == ("Ballotpedia profile", "https://ballotpedia.org/Ken_Paxton")
    assert any(f.label == "Candidate survey" for f in result.facts)

    no_profile = BpCandidate(8, "Someone", None, None, False, False, None, None, None, False)
    assert ballotpedia_card(no_profile, race, 0.0, None).badges == []
