from __future__ import annotations

from pallot.sources import wikidata
from pallot.sources.wikidata import details_from, people_from, photo_url, seat_of

from .conftest import find_race, get_ballot, last_use, load, switch


def person(race, name):
    return next(c for c in race["candidates"] if c["name"] == name)


def card_of(candidate):
    return next((card for card in candidate["cards"] if card["source"] == wikidata.SOURCE), None)


def test_each_office_held_is_read_as_the_seat_the_ballot_spells():
    assert seat_of(wikidata.US_HOUSE, "Texas's 35th congressional district") == "TX-35"
    assert seat_of(wikidata.US_HOUSE, "Texas's 1st congressional district") == "TX-01"
    assert seat_of(wikidata.US_SENATE, "Texas Class 2 senate seat") == "TX-SEN"
    assert seat_of(wikidata.STATE_HOUSE, "Texas State House district 49") == "STATEREP:49"
    assert seat_of(wikidata.STATE_HOUSE, "Harris County") == "STATEREP:*"  # a district Wikidata gives as a county
    assert seat_of(wikidata.STATE_SENATE, "Texas Senate, District 14") == "STATESEN:14"
    assert seat_of(wikidata.STATE_SENATE, None) == "STATESEN:*"
    assert seat_of("Q5589725", None) == "GOVERNOR"
    assert seat_of("Q7444388", None) is None  # Secretary of State: appointed, never on a ballot


def test_the_list_is_folded_into_one_person_each():
    people = {p.name: p for p in people_from(load("wikidata_people.json"))}
    paxton = people["Ken Paxton"]
    assert paxton.qid == "Q6388290" and paxton.party == "R"
    assert {"ATTYGEN", "STATESEN:8", "STATEREP:70"} <= paxton.seats
    assert paxton.held[0].text() == "Texas Attorney General (2015–)"  # the office still held comes first
    assert people["James Talarico"].seats == {"STATEREP:*"}
    details = details_from(load("wikidata_details.json"))
    assert details["Q6388290"].article == "https://en.wikipedia.org/wiki/Ken_Paxton"
    assert details["Q6388290"].photo.startswith("https://commons.wikimedia.org/wiki/Special:FilePath/")
    assert photo_url("http://example.com/a.jpg") is None


def test_an_exact_match_gets_its_photo_and_stable_links(client, upstream):
    ballot = get_ballot(client)
    abbott = person(find_race(ballot, "Governor"), "Greg Abbott")
    card = card_of(abbott)
    assert card["kind"] == "profile" and card["match"]["confidence"] == "exact"
    assert card["url"] == "https://www.wikidata.org/wiki/Q5605224"
    assert abbott["photo_url"] == card["image"] and card["image"].endswith("?width=300")
    links = {link["label"]: link["url"] for link in card["links"]}
    assert links["Wikidata item"] == "https://www.wikidata.org/wiki/Q5605224"
    assert links["Wikipedia article"] == "https://en.wikipedia.org/wiki/Greg_Abbott"
    facts = {fact["label"]: fact["value"] for fact in card["facts"]}
    assert facts["Party"] == "Republican Party" and facts["Texas offices held"].startswith("Governor of Texas (2015–)")
    sources = [c["source"] for c in abbott["cards"]]
    assert sources.index(wikidata.SOURCE) < sources.index("ballotpedia")  # before Ballotpedia on the Profile tab
    assert last_use(client, wikidata.SOURCE)["status"] == "used"


def test_someone_running_for_another_office_is_likely_and_brings_no_photo(client, upstream):
    paxton = person(find_race(get_ballot(client), "U.S. Senator"), "Ken Paxton")
    card = card_of(paxton)
    assert card["match"] == {"confidence": "likely", "method": "full name",
                             "note": "Wikidata lists them for Texas Attorney General (2015–)"}
    assert card["image"] is None and "ballotpedia" in paxton["photo_url"]


def test_a_second_lookup_asks_nothing(client, upstream):
    get_ballot(client)
    assert upstream.count("query.wikidata.org") == 2  # the list, then the matched people's details
    assert get_ballot(client)["meta"]["external_calls"] == 0
    assert upstream.count("query.wikidata.org") == 2


def test_a_source_kept_off_shows_nothing(client, upstream):
    switch(client, wikidata.SOURCE, False)
    ballot = get_ballot(client)
    assert not [c for r in ballot["races"] for c in r["candidates"] if card_of(c)]
    assert upstream.count("query.wikidata.org") == 0
    assert last_use(client, wikidata.SOURCE)["status"] == "off"


def test_a_refusal_pauses_it_and_the_ballot_still_loads(client, upstream):
    upstream.wikidata_status = 429
    ballot = get_ballot(client)
    assert "Couldn't load Wikidata profiles (HTTP 429)." in ballot["warnings"]
    asked = upstream.count("query.wikidata.org")
    again = get_ballot(client)
    assert upstream.count("query.wikidata.org") == asked
    assert any("paused until" in w for w in again["warnings"])
    status = next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == wikidata.SOURCE)
    assert status["notice"].startswith("Paused until") and status["notice_tone"] == "warn"
