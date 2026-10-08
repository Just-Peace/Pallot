"""Vote for Peace's cards: what they show, and how its entries meet the ballot's races (seats.py, which the
endorsement lists share)."""

from __future__ import annotations

import time

import pytest

from pallot.models import Candidate, Match, Race
from pallot.offices import classify
from pallot.sources.seats import entry_seats, party_code
from pallot.sources.voteforpeace import VoteForPeace, card, cards
from pallot.text import snapshot_day

from .conftest import FIXTURES

EXACT = Match(confidence="exact", method="full name, in the same seat")


def entry(name="Jane Doe", rating="vote", office="TX State Representative", district="49", **extra):
    return {"candidate_id": name.lower(), "name": name, "slug": name.lower().replace(" ", "-"), "state": "TX",
            "url": f"https://voteforpeace.info/texas/{name.lower().replace(' ', '-')}", "rating": rating,
            "office_title": office, "district": district, "level": "state_legislature", "jurisdiction": None,
            "party": None, "election_label": "General: Nov 3, 2026", "election_result": "pending",
            "notes": None, "endorsements": [], "articles": [], **extra}


@pytest.fixture
def snapshot(tmp_path) -> VoteForPeace:
    peace = VoteForPeace(tmp_path / "voteforpeace", bundled_dir=FIXTURES / "voteforpeace")
    peace.ensure_seeded()
    return peace


def race(name, *candidates, key="sos:1:1", group="legislature", seat=None):
    return Race(key=key, name=name, group=group, source="sos", seat=seat,
                candidates=[Candidate(key=f"{key}:{i}", name=n, party=p) for i, (n, p) in enumerate(candidates)])


@pytest.mark.parametrize("rating, text, tone, flags", [
    ("vote", "Vote for Peace: Ally", "good", ["ally"]),
    ("reject", "Vote for Peace: Opposed", "warn", ["opposed"]),
    ("neutral", "Vote for Peace: Neutral", "info", ["neutral"]),
    (None, "Vote for Peace: Not rated", "neutral", []),
])
def test_the_rating_is_one_linked_badge_and_a_flag(rating, text, tone, flags):
    result = card(entry(rating=rating), EXACT, "2026-10-04")
    assert [(b.text, b.tone, b.url) for b in result.badges] == [(text, tone, "https://voteforpeace.info/texas/jane-doe")]
    assert result.flags == flags and result.as_of == "2026-10-04" and result.kind == "endorsement"


def test_notes_articles_and_the_sources_it_cites():
    person = entry(
        notes="Running unopposed\nSupports an arms embargo.",
        endorsements=[{"organization": "DSA", "type": "endorsed", "notes": None, "link": "https://dsa.example/endorse"},
                      {"organization": "Track AIPAC", "type": "endorsed", "notes": None, "link": None}],
        articles=[{"title": "Endorsed by", "url": None, "description": "Our Revolution."},
                  {"title": "Interview", "url": "https://news.example/a", "description": None}],
        election_result="won",
    )
    result = card(person, EXACT, None)
    facts = {f.label: f.value for f in result.facts}
    assert facts["Office on Vote for Peace"] == "TX State Representative, District 49"
    assert (facts["Sources it cites"], facts["Result"]) == ("DSA, Track AIPAC", "Won")
    assert result.quotes == ["Running unopposed", "Supports an arms embargo.", "Endorsed by: Our Revolution.",
                             "[Interview](https://news.example/a)"]
    assert [link.label for link in result.links] == ["DSA (cited by Vote for Peace)"]
    assert result.url == "https://voteforpeace.info/texas/jane-doe"


@pytest.mark.parametrize("office, district, level, jurisdiction, seats", [
    ("U.S. Representative", "37", "federal", None, {"TX-37"}),
    ("U.S. Senator", None, "federal", None, {"TX-SEN"}),
    ("TX  State Representative", "135", "state_legislature", None, {"STATEREP:135"}),
    ("TX State Senator", "sd-9", "state_legislature", None, {"STATESEN:9"}),
    ("Lt. Governor", None, "statewide", None, {"LTGOVERNOR"}),
    ("TX Railroad Commissioner", None, "statewide", None, {"RRCOMM"}),
    ("TX Supreme Court Justice", None, "statewide", None, {"JUSTICE_SC:*", "CHIEFJUSTICE_SC"}),
    ("TX State District Appellate Court Judge", None, "county", None, {"JUSTICE_COA:*", "CHIEFJUSTICE_COA:*"}),
    ("Harris District County Court Judge, Harris", "228", "county", "Harris", {"JUDGEDIST:228", "COUNTY:HARRIS"}),
    ("Fort Bend County Treasurer, Missouri City", None, "county", "Missouri City",
     {"COUNTY:MISSOURI CITY", "COUNTY:FORT BEND"}),
    ("TX Board of Education", None, "statewide", None, {"STATEEDU:*"}),
    ("Harris County Treasurer", None, "statewide", None, {"COUNTY:HARRIS"}),  # filed as statewide on the site
    ("U.S. House", "10", "federal", None, {"TX-10"}),  # as an endorsement list may word them
    ("US Senate", None, "federal", None, {"TX-SEN"}),
    ("State House", "49", None, None, {"STATEREP:49"}),
    ("State Senate", "14", None, None, {"STATESEN:14"}),
])
def test_an_entry_names_its_seat_as_the_ballot_does(office, district, level, jurisdiction, seats):
    assert entry_seats(entry(office=office, district=district, level=level, jurisdiction=jurisdiction)) == seats


def test_matches_in_any_race_with_the_seat_to_confirm(snapshot):
    races = [
        race("State Representative District 49", ("Montserrat Garibay", "D"), key="sos:1:49"),
        race("State Representative District 50", ("Montserrat Garibay", "D"), key="sos:1:50"),
        race("U.S. Senator", ("James Talarico", "D"), key="sos:1:2", group="federal", seat="TX-SEN"),
        race("County Commissioner Precinct 4", ("Lesley Briones", None), key="sos:1:3", group="precinct"),
        race("U.S. Representative District 1", ("Jake Auchincloss", "D"), key="sos:1:4", group="federal", seat="TX-01"),
    ]
    scopes = {"sos:1:49": classify("STATE REPRESENTATIVE, DISTRICT 49", "SR", set()),
              "sos:1:50": classify("STATE REPRESENTATIVE, DISTRICT 50", "SR", set())}
    found = cards(snapshot, races, scopes, "Harris").candidates
    assert found["sos:1:49:0"].match.confidence == "exact"
    other_seat = found["sos:1:50:0"].match
    assert (other_seat.confidence, other_seat.note) == (
        "likely", "Vote for Peace lists them for TX State Representative, District 49")
    assert found["sos:1:2:0"].match.confidence == "exact"
    assert found["sos:1:3:0"].match.confidence == "exact"  # a county office, in the voter's county
    assert "sos:1:4:0" not in found  # rated in Massachusetts, never matched in Texas


def test_one_entry_goes_to_one_candidate_in_a_race(snapshot):
    court = race("Justice, Supreme Court, Place 7", ("Kyle Hawkins", "R"), ("Kristen Hawkins", "D"),
                 key="sos:1:7", group="state")
    scopes = {"sos:1:7": classify("JUSTICE, SUPREME COURT, PLACE 7", "SW", set())}
    found = cards(snapshot, [court], scopes, "Travis").candidates
    assert list(found) == ["sos:1:7:1"] and found["sos:1:7:1"].match.confidence == "exact"

    tie = race("A race", ("Kim Hawkins", None), ("Kai Hawkins", None), key="sos:1:8", group="state")
    assert cards(snapshot, [tie], {}, "Travis").candidates == {}  # both are "K Hawkins"


def test_a_last_name_alone_isnt_enough_in_a_county(snapshot):
    court = race("Judge, County Civil Court at Law No. 2", ("Ebony N. Williams", "D"), key="sos:1:9", group="county")
    assert cards(snapshot, [court], {}, "Harris").candidates == {}  # LaShawn Williams is a Harris judge too
    judge = race("District Judge, 248th Judicial District", ("Hilary Unger", "D"), key="sos:1:10", group="judicial")
    scopes = {"sos:1:10": classify("DISTRICT JUDGE, 248TH JUDICIAL DISTRICT", "SR", set())}
    match = cards(snapshot, [judge], scopes, "Harris").candidates["sos:1:10:0"].match  # "Hillary Unger" on the site
    assert (match.confidence, match.method) == ("likely", "first initial and last name, in the same seat")


def test_a_party_that_disagrees_makes_it_likely(snapshot):
    senate = race("U.S. Senator", ("James Talarico", "D"), key="sos:1:2", group="federal", seat="TX-SEN")
    person = next(p for p in snapshot.people("TX") if p["name"] == "James Talarico")
    person["party"] = "Republican"
    match = cards(snapshot, [senate], {}, None).candidates["sos:1:2:0"].match
    assert (match.confidence, match.note) == ("likely", "party differs (Vote for Peace says R)")


def test_a_title_before_the_name_is_left_out(snapshot):
    house = race("State Representative District 26", ("Eliz Markowitz", "D"), key="sos:1:26")
    assert "sos:1:26:0" in cards(snapshot, [house], {}, None).candidates  # "Dr. Eliz Markowitz" on the site
    assert party_code({"party": "Democrat"}) == "D" and party_code({"party": "Nonpartisan"}) is None
    assert party_code({"party": "r"}) == "R"


@pytest.mark.parametrize("city, confidence", [("Austin", "exact"), ("Round Rock", "likely"), (None, "likely")])
def test_a_city_as_the_jurisdiction_is_the_voters_city(snapshot, city, confidence):
    council = race("City Council Member, District 9", ("Zohaib Qadri", None), key="bp:9", group="local")
    match = cards(snapshot, [council], {}, "Travis", city=city).candidates["bp:9:0"].match  # "Austin" on the site
    assert match.confidence == confidence


@pytest.fixture
def in_texas(monkeypatch):
    monkeypatch.setenv("TZ", "America/Chicago")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_the_snapshots_day_is_the_local_day_it_was_taken(in_texas, snapshot):
    # The bundled copy is named 2026-10-04 after the UTC day; it was taken at 9:31 PM on Oct 3 in Texas.
    facts = {f.label: f.value for f in snapshot.details()}
    assert (facts["Snapshot"], facts["Last changed"]) == ("Oct 3, 2026", "Oct 3, 2026, 9:31 PM")
    senate = race("U.S. Senator", ("James Talarico", "D"), key="sos:1:2", group="federal", seat="TX-SEN")
    assert cards(snapshot, [senate], {}, None).candidates["sos:1:2:0"].as_of == "2026-10-03"
    assert snapshot.clear() == "Back to the snapshot that came with Pallot (Oct 3, 2026)."


@pytest.mark.parametrize("name, taken, day", [
    ("2026-10-04", "2026-10-04T02:31:02+00:00", "2026-10-03"),
    ("2026-10-04", "2026-10-04T18:00:00+00:00", "2026-10-04"),
    ("2026-10-04", "2026-09-30T02:31:02+00:00", "2026-10-04"),  # taken another day: its own name stands
    ("2026-10-04", None, "2026-10-04"),
    (None, "2026-10-04T02:31:02+00:00", None),
])
def test_snapshot_day(in_texas, name, taken, day):
    assert snapshot_day(name, taken) == day
