"""Whole-ballot scenarios through the API, against recorded responses."""

from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from pallot.ballot import _jp_is_constable
from pallot.sources.sos import still_running

from .conftest import (
    ADDRESSES, TRAVIS_LIST, TRAVIS_QUERY, candidate_names, find_race, get_ballot, last_use, load, travis_rows,
)


def sources_of(candidate):
    return [card["source"] for card in candidate["cards"]]


def card_of(candidate, source):
    return next(card for card in candidate["cards"] if card["source"] == source)


def test_capitol_ballot(client):
    ballot = get_ballot(client)

    assert ballot["election_date"] == "2026-11-03"
    assert [e["name"] for e in ballot["elections"]] == ["2026 November General Election"]  # specials don't apply here
    d = ballot["districts"]
    assert (d["cd"], d["sd"], d["hd"], d["sboe"]) == (10, 14, 49, 5)
    assert (d["jp"], d["constable"], d["commissioner"]) == (5, 5, 2)  # from Travis County's list, by election precinct 300
    assert d["precinct_sources"] == {"commissioner": "county", "jp": "county", "constable": "county"}
    assert d["county_source"] == {"county": "Travis", "method": "table"}
    assert d["city_council"] == "District 9"
    assert d["election_precinct"] == {"name": "300", "code": "0300", "county": 453,
                                      "map_label": "2026 Primary Election Voting Precincts", "primary_map": True}
    assert ballot["location"]["county"] == "Travis" and ballot["location"]["city"] == "Austin"
    assert (ballot["location"]["state"], ballot["location"]["state_name"]) == ("TX", "Texas")

    senate = find_race(ballot, "U.S. Senator")
    assert candidate_names(senate)[:3] == ["Ken Paxton", "James Talarico", "Ted Brown"]
    assert senate["candidates"][0]["party_name"] == "Republican"

    house = [r["name"] for r in ballot["races"] if r["name"].startswith("U.S. Representative")]
    assert house == ["U.S. Representative District 10"]
    assert [r["name"] for r in ballot["races"] if r["name"].startswith("State Representative")] == ["State Representative District 49"]
    assert [r["name"] for r in ballot["races"] if "Board of Education" in r["name"]] == ["Member, State Board of Education, District 5"]
    assert not [r for r in ballot["races"] if r["name"].startswith("State Senator")]
    assert d["not_up"] == ["sd"]  # shown in Your districts, not as a note
    assert not [note for note in ballot["notes"] if "up for election" in note]

    assert find_race(ballot, "Justice of the Peace Precinct 5")
    assert not [r for r in ballot["races"] if "Constable" in r["name"]]  # precinct 4's race isn't ours
    assert find_race(ballot, "County Commissioner Precinct 2") and not find_race(ballot, "County Commissioner Precinct 4")
    assert "precinct" not in [s["id"] for s in ballot["maybe"]]
    assert find_race(ballot, "District Judge, 147th Judicial District")  # whole-county judicial races stay

    assert find_race(ballot, "Austin City Council District 9")["source"] == "ballotpedia"
    special = next(s for s in ballot["maybe"] if s["id"] == "special")
    assert all(r["group"] == "local" for r in special["races"]) and any(r["seats"] > 1 for r in special["races"])

    paxton = senate["candidates"][0]
    assert sources_of(paxton) == ["fec", "sos", "polls", "ballotpedia", "trackaipac"]  # the tabs in Details
    tap = card_of(paxton, "trackaipac")
    assert tap["match"]["confidence"] == "exact"
    watchlist = next(b for b in tap["badges"] if b["text"].startswith("TrackAIPAC watchlist"))
    assert watchlist["text"] == "TrackAIPAC watchlist $0" and watchlist["url"].endswith("/candidates")
    profile = next(b for b in card_of(paxton, "ballotpedia")["badges"] if b["text"] == "Ballotpedia profile")
    assert profile["url"].startswith("https://ballotpedia.org/")
    talarico = senate["candidates"][1]
    assert sources_of(talarico)[-4:] == ["trackaipac", "voteforpeace", "emgage", "examplepac"]  # the endorsement lists last
    vfp = card_of(talarico, "voteforpeace")
    assert (vfp["match"]["confidence"], vfp["flags"]) == ("exact", ["ally"])
    assert vfp["badges"][0]["text"] == "Vote for Peace: Ally" and vfp["url"].endswith("/texas/james-talarico")
    hawkins = {c["name"]: c for c in find_race(ballot, "Justice, Supreme Court, Place 7")["candidates"]}
    assert "voteforpeace" in sources_of(hawkins["Kristen Hawkins"])  # the site names no place: any place counts
    assert "voteforpeace" not in sources_of(hawkins["Kyle Hawkins"])  # "K Hawkins" too, but Kristen's is the full name
    sos_card = card_of(paxton, "sos")
    assert {"Name on ballot", "Filing status", "Occupation"} <= {f["label"] for f in sos_card["facts"]}
    assert paxton["photo_url"]  # from Ballotpedia

    statuses = {s["id"]: (s["last_use"] or {}).get("status") for s in client.get("/api/sources").json()["sources"]}
    assert statuses == {"geocoding": "used", "tigerweb": None, "osm_tiles": None, "suggestions": None, "sos": "used",
                        "key_dates": "used", "ballotpedia": "used", "trackaipac": "used", "voteforpeace": "used", "examplepac": "used", "mupac": "used", "cair": "used", "emgage": "used", "fec": "used",
                        "tec": statuses["tec"], "polls": "used", "election_precincts": "used",
                        "county_precincts": "used"}
    # (suggestions are asked for while typing, the map after)
    assert ballot["warnings"] == [] and not [note for note in ballot["notes"] if "precinct" in note]


def test_federal_races_get_fec_money(client):
    ballot = get_ballot(client)
    senate, house = find_race(ballot, "U.S. Senator"), find_race(ballot, "U.S. Representative District 10")

    comparison, _polls = senate["cards"]
    assert comparison["source"] == "fec" and comparison["url"].endswith("/elections/senate/TX/2026/")
    raised = {p["label"]: p["amount"] for p in comparison["breakdowns"][0]["parts"]}
    assert raised == {"Ken Paxton": 9248698.53, "James Talarico": 68560930.42, "Ted Brown": 7459.52}
    assert [p["candidate_key"] for p in comparison["breakdowns"][0]["parts"]] == [c["key"] for c in senate["candidates"]]
    assert [p["label"] for p in house["cards"][0]["breakdowns"][0]["parts"]] == ["Chris Gober", "Caitlin Rourk"]

    talarico = next(c for c in senate["candidates"] if c["name"] == "James Talarico")
    fec = next(card for card in talarico["cards"] if card["source"] == "fec")
    assert fec["match"]["confidence"] == "exact" and fec["as_of"] == "2026-06-30"
    assert [(b["text"], b["tone"]) for b in fec["badges"]] == [
        ("FEC: raised $68.6M", "neutral"), ("Outside spending for: $4.1M", "info"), ("Outside spending against: $705K", "warn"),
    ]
    assert all("none of it went to the campaign" in b["hint"] for b in fec["badges"][1:])
    assert fec["badges"][0]["url"] == "https://www.fec.gov/data/candidate/S6TX00479/?cycle=2026&election_full=true"
    assert [b["title"] for b in fec["breakdowns"]] == [
        "Where the money came from", "Donations by size", "Where donors live", "Top donors' employers", "Outside spending",
    ]
    sources = fec["breakdowns"][0]
    assert sum(p["amount"] for p in sources["parts"]) == pytest.approx(sources["total"], abs=1)
    assert any("Senate" in link["label"] for link in fec["links"])  # personal financial disclosures
    assert set(fec["figures"]) == {"raised", "spent", "cash", "outside_for", "small_share", "self_share"}  # what Pick by rule tests
    assert (fec["figures"]["small_share"], fec["figures"]["self_share"]) == (53.6, 0.0)  # percents of raised
    assert fec["figures"]["raised"] == 68560930.42 and fec["figures"]["outside_for"] == pytest.approx(4.1e6, rel=0.05)

    paxton = next(card for card in senate["candidates"][0]["cards"] if card["source"] == "fec")
    assert paxton["match"]["confidence"] == "likely" and "Warren Kenneth Paxton" in paxton["match"]["note"]
    assert paxton["breakdowns"] == []  # only Talarico's breakdown calls were recorded
    assert not [card for race in ballot["races"] if not race["seat"] for card in race["cards"] if card["source"] == "fec"]


def test_federal_race_comparison(client):
    senate = find_race(get_ballot(client), "U.S. Senator")
    paxton, talarico, brown = keys = [c["key"] for c in senate["candidates"]]
    comparison = senate["cards"][0]["comparison"]
    assert comparison["candidates"] == keys and comparison["as_of"][talarico] == "2026-06-30"
    sections = {s["title"]: s for s in comparison["sections"]}
    assert list(sections) == ["Totals", "Where the money came from", "Donations by size", "Where donors live",
                              "Top donors' employers", "Outside spending"]

    totals = {r["label"]: [v["amount"] for v in r["values"]] for r in sections["Totals"]["rows"]}
    assert totals["Raised"] == [9248698.53, 68560930.42, 7459.52]
    assert totals["Outside spending for them"][1] == pytest.approx(4.1e6, rel=0.05)
    assert totals["Outside spending against them"][1] == pytest.approx(705e3, rel=0.01)

    where = sections["Where the money came from"]
    assert [v["amount"] for v in where["rows"][0]["values"]][::2] == [None, None]  # only Talarico's details were recorded
    assert where["totals"] == {talarico: 68560930.42}
    home = sections["Where donors live"]
    assert [r["label"] for r in home["rows"]] == ["Texas", "Other states"]
    assert sum(r["values"][1]["amount"] for r in home["rows"]) == pytest.approx(home["totals"][talarico])
    assert all(r["values"][1]["count"] for r in home["rows"])
    assert list(sections["Top donors' employers"]["columns"]) == [talarico]
    outside = sections["Outside spending"]["columns"][talarico]
    assert {(e["tag"], e["tone"]) for e in outside} == {("for", "info"), ("against", "warn")}
    assert not any(e["note"] for e in outside) and "None of this went to the campaigns" in sections["Outside spending"]["note"]


def test_repeat_lookups_make_no_external_calls_even_after_a_restart(make_app, upstream):
    with TestClient(make_app()) as client:
        first = get_ballot(client)
        calls_after_first = len(upstream.calls)
        again = get_ballot(client)
    assert first["meta"]["external_calls"] > 0
    assert again["meta"]["external_calls"] == 0 and len(upstream.calls) == calls_after_first

    with TestClient(make_app()) as client:  # same data dir
        after_restart = get_ballot(client)
    assert after_restart["meta"]["external_calls"] == 0
    assert len(upstream.calls) == calls_after_first


def test_harris_county_gets_exactly_one_sboe_race(client):
    client.put("/api/sources/ballotpedia", json={"enabled": False})
    ballot = get_ballot(client, "harris")
    assert ballot["districts"]["sboe"] == 4 and ballot["location"]["county"] == "Harris"
    sboe = [r["name"] for r in ballot["races"] if "Board of Education" in r["name"]]
    assert sboe == ["Member, State Board of Education, District 4"]
    assert find_race(ballot, "Member, State Board of Education, District 4")["unexpired"] is True


def test_special_election_comes_from_the_statewide_list_when_the_county_has_no_ballot_order(client):
    ballot = get_ballot(client, "hd93")
    race = find_race(ballot, "State Representative District 93")
    assert race is not None and race["unexpired"] and race["election_id"] == 66734
    assert race["candidates"]
    assert "2026 Special Election House District 93" in [e["name"] for e in ballot["elections"]]
    assert not find_race(ballot, "State Representative District 49")  # the Capitol's own district is filtered out


def test_the_statewide_list_leaves_out_races_it_cant_place(client, upstream):
    """It names no county for a district judge, so one elsewhere in Texas mustn't reach this ballot."""
    judge = {**load("sos_candidates_66734.json")[0], "idOffice": 999999, "idCandidate": 999999,
             "txOfficeName": "DISTRICT JUDGE, 999TH JUDICIAL DISTRICT - UNEXPIRED TERM", "txFullNameBallot": "PAT ELSEWHERE"}
    upstream.extra_candidates[66734] = [judge]
    ballot = get_ballot(client, "hd93")
    everyone = [c["name"] for r in ballot["races"] + [r for s in ballot["maybe"] for r in s["races"]] for c in r["candidates"]]
    assert everyone and not [name for name in everyone if "ELSEWHERE" in name.upper()]
    assert find_race(ballot, "State Representative District 93")  # district races still come through
    assert any("doesn't say which counties judicial" in note for note in ballot["notes"])


def _write_in(office_id, candidate_id, name, **changes):
    """A declared write-in row of the statewide list, shaped like a real one."""
    return {**load("sos_candidates_53815.json")[0], "idOffice": office_id, "idCandidate": candidate_id, "cdParty": "W",
            "cdCandType": "WRTIN", "cdDeclarationStatus": "A", "txFullNameBallot": name, "txCountyName": None, **changes}


def test_a_deceased_status_drops_a_declared_write_in_but_not_a_printed_name():
    assert not still_running({"cdParty": "W", "cdDeclarationStatus": "D"})
    assert still_running({"cdParty": "R", "cdDeclarationStatus": "D"})
    assert still_running({"cdParty": "W", "cdDeclarationStatus": "A"})


def test_declared_write_ins_follow_the_printed_candidates(client, upstream):
    senate_rows = [r for r in load("sos_ballot_53815_227.json") if r["txOfficeName"].strip() == "U. S. SENATOR"]
    senate_office = senate_rows[0]["idOffice"]
    upstream.extra_candidates[53815] = [
        _write_in(senate_office, 900001, "PAT FILED"),
        _write_in(senate_office, 900002, "LEE WITHDREW", cdDeclarationStatus="R"),
        _write_in(senate_office, 900006, "DEE CEASED", cdDeclarationStatus="D"),
        _write_in(351, 900003, "SAM ELSEWHERE", cdOfficeType="CW", txCountyName="HARRIS"),  # Travis's county clerk office id
        _write_in(351, 900004, "KIM CLERK", cdOfficeType="CW", txCountyName="TRAVIS"),
        _write_in(999999, 900005, "NO SUCH RACE", cdOfficeType="SR", txOfficeName="DISTRICT JUDGE, 999TH JUDICIAL DISTRICT"),
    ]
    ballot = get_ballot(client)
    senate = find_race(ballot, "U.S. Senator")
    assert len(senate["candidates"]) == len(senate_rows) + 1 and senate["candidates"][-1]["name"] == "Pat Filed"
    filed = senate["candidates"][-1]
    assert filed["write_in"] and filed["party"] is None and filed["party_name"] is None
    assert "sos" in sources_of(filed)
    assert not any(c["write_in"] for c in senate["candidates"][:-1])
    assert candidate_names(find_race(ballot, "County Clerk"))[-1] == "Kim Clerk"
    everyone = [c["name"] for r in ballot["races"] + [r for s in ballot["maybe"] for r in s["races"]] for c in r["candidates"]]
    assert not {"Lee Withdrew", "Sam Elsewhere", "No Such Race"} & set(everyone)


def test_a_race_with_only_write_ins_is_shown_where_it_can_be_placed(client, upstream):
    upstream.extra_candidates[53815] = [
        _write_in(990001, 900001, "SAL SURVEYOR", cdOfficeType="CW", txCountyName="TRAVIS",
                  txOfficeName="TRAVIS - COUNTY SURVEYOR", nbSortOrder=13, nbSecondarySortOrder=1),
        _write_in(990002, 900002, "CAL FIVE", cdOfficeType="CR", txCountyName="TRAVIS",
                  txOfficeName="TRAVIS - COUNTY CONSTABLE PRECINCT 5", nbSortOrder=17, nbSecondarySortOrder=5),
        _write_in(990003, 900003, "CAL ONE", cdOfficeType="CR", txCountyName="TRAVIS",
                  txOfficeName="TRAVIS - COUNTY CONSTABLE PRECINCT 1", nbSortOrder=17, nbSecondarySortOrder=1),
        _write_in(990004, 900004, "HAL HARRIS", cdOfficeType="CW", txCountyName="HARRIS",
                  txOfficeName="HARRIS - COUNTY SURVEYOR", nbSortOrder=13, nbSecondarySortOrder=1),
        _write_in(990005, 900005, "JUDGE ELSEWHERE", cdOfficeType="SR",
                  txOfficeName="DISTRICT JUDGE, 276TH JUDICIAL DISTRICT", nbSortOrder=70, nbSecondarySortOrder=276),
        _write_in(990006, 900006, "REP ELSEWHERE", cdOfficeType="SR",
                  txOfficeName="STATE REPRESENTATIVE DISTRICT 93", nbSortOrder=51, nbSecondarySortOrder=93),
    ]
    ballot = get_ballot(client)
    surveyor = find_race(ballot, "County Surveyor")
    assert candidate_names(surveyor) == ["Sal Surveyor"] and surveyor["candidates"][0]["write_in"]
    county = [r["name"] for r in ballot["races"] if r["group"] == "county"]
    assert county[county.index("County Treasurer") + 1] == "County Surveyor"
    assert candidate_names(find_race(ballot, "County Constable Precinct 5")) == ["Cal Five"]
    everyone = [c["name"] for r in ballot["races"] + [r for s in ballot["maybe"] for r in s["races"]] for c in r["candidates"]]
    assert not {"Cal One", "Hal Harris", "Judge Elsewhere", "Rep Elsewhere"} & set(everyone)


def test_a_write_in_only_district_race_isnt_guessed(client, upstream):
    """Without the voter's district, the statewide list's races for every district in Texas
    would otherwise all land under "Couldn't confirm"."""
    client.put("/api/sources/election_precincts", json={"enabled": False})
    upstream.down.add("data.capitol.texas.gov")
    upstream.extra_candidates[53815] = [
        _write_in(990001, 900001, "SID ELSEWHERE", cdOfficeType="SR",
                  txOfficeName="MEMBER, STATE BOARD OF EDUCATION, DISTRICT 3", nbSortOrder=49, nbSecondarySortOrder=3),
    ]
    ballot = get_ballot(client)
    assert ballot["districts"]["sboe"] is None
    unconfirmed = next(s for s in ballot["maybe"] if s["id"] == "unconfirmed")
    assert [r["name"] for r in unconfirmed["races"]] == ["Member, State Board of Education, District 5"]


def test_a_failed_write_in_list_keeps_the_printed_ballot(client, upstream):
    upstream.candidates_down.add(53815)
    ballot = get_ballot(client)
    senate = find_race(ballot, "U.S. Senator")
    assert senate["candidates"] and not any(c["write_in"] for c in senate["candidates"])
    assert any("declared write-in candidates" in note for note in ballot["notes"])


def test_ballotpedia_off(client):
    client.put("/api/sources/ballotpedia", json={"enabled": False})
    ballot = get_ballot(client)
    assert not [r for r in ballot["races"] if r["source"] == "ballotpedia"]
    maybe = {s["id"]: [r["name"] for r in s["races"]] for s in ballot["maybe"]}
    assert find_race(ballot, "Justice of the Peace Precinct 5")  # the county's list still places it
    assert "precinct" not in maybe and "special" not in maybe
    assert last_use(client, "ballotpedia")["status"] == "off"
    senate = find_race(ballot, "U.S. Senator")
    assert sources_of(senate["candidates"][0]) == ["fec", "sos", "polls", "trackaipac"]


def test_state_source_off_uses_ballotpedia_for_everything(client, upstream):
    client.put("/api/sources/sos", json={"enabled": False})
    ballot = get_ballot(client)
    assert upstream.count("goelect") == 0
    assert ballot["elections"][0]["name"] == "Ballotpedia sample ballot"
    assert ballot["districts"]["sboe"] == 5  # from the SBOE map, which doesn't need Texas SOS
    senate = find_race(ballot, "U.S. Senate Texas")
    assert senate["seat"] == "TX-SEN"
    assert any(c["write_in"] for c in senate["candidates"])
    assert "trackaipac" in sources_of(next(c for c in senate["candidates"] if c["name"] == "Ken Paxton"))
    assert find_race(ballot, "Travis County Justice of the Peace Precinct 5")["group"] == "precinct"


def _bp_districts(payload):
    return payload["data"]["elections"][0]["districts"]


def test_ballotpedias_notes_show_under_the_race(client):
    house = find_race(get_ballot(client), "U.S. Representative District 10")
    assert house["notes"] == [{
        "text": "Texas redrew its U.S. House district map ahead of the 2026 elections. Your district may have changed.",
        "url": "https://ballotpedia.org/Redistricting_in_Texas_ahead_of_the_2026_elections",
        "source": "Ballotpedia",
    }]


def test_a_race_only_ballotpedia_lists_is_added(client, upstream):
    def add_appraisal_district(payload):
        county = next(d for d in _bp_districts(payload) if d["type"] == "County")
        race = copy.deepcopy(next(r for r in county["races"] if r["office"]["name"] == "Travis County Clerk"))
        race["id"] = 999001
        race["office"] = {"name": "Travis Central Appraisal District, Place 1", "type": "Appraisal", "level": "Local"}
        race["candidates"][0].update(id=999002, person={"name": "Pat Appraiser"})
        county["races"].append(race)

    upstream.ballotpedia_edit = add_appraisal_district
    ballot = get_ballot(client)
    appraisal = find_race(ballot, "Travis Central Appraisal District, Place 1")
    assert (appraisal["group"], appraisal["source"], candidate_names(appraisal)) == ("county", "ballotpedia", ["Pat Appraiser"])
    assert not find_race(ballot, "Travis County Clerk")  # the state lists its candidate, so it isn't added again
    assert not find_race(ballot, "Texas 147th District Court")


def test_a_precinct_ballotpedia_names_without_its_kind(client, upstream):
    def generic_name(payload):
        next(d for d in _bp_districts(payload) if d["type"] == "County subdivision")["name"] = "Travis County Precinct 5"

    upstream.ballotpedia_edit = generic_name
    client.put("/api/sources/county_precincts", json={"enabled": False})
    d = get_ballot(client)["districts"]
    assert (d["jp"], d["constable"]) == (5, 5)
    assert d["precinct_sources"] == {"jp": "ballotpedia", "constable": "ballotpedia"}


def test_ballotpedia_can_say_who_holds_the_seat(client, upstream):
    def incumbents(payload):
        for district in _bp_districts(payload):
            for race in district["races"]:
                for candidate in race["candidates"]:
                    if candidate["person"]["name"] in ("James Talarico", "Donald Huffines"):
                        candidate["is_incumbent"] = True

    upstream.ballotpedia_edit = incumbents
    ballot = get_ballot(client)
    talarico = next(c for c in find_race(ballot, "U.S. Senator")["candidates"] if c["name"] == "James Talarico")
    assert talarico["incumbent"] and card_of(talarico, "ballotpedia")["match"]["confidence"] == "exact"
    huffines = next(c for c in find_race(ballot, "Comptroller of Public Accounts")["candidates"] if c["name"] == "Don Huffines")
    assert not huffines["incumbent"]  # Don and Donald: only a likely match


def test_no_ballot_source_is_an_error(client):
    client.put("/api/sources/sos", json={"enabled": False})
    client.put("/api/sources/ballotpedia", json={"enabled": False})
    response = client.post("/api/ballot", json={"address": ADDRESSES["capitol"]})
    assert response.status_code == 400 and "Settings" in response.json()["detail"]


def test_entered_precincts_override_the_countys(client):
    ballot = get_ballot(client, precincts={"commissioner": 4})
    assert find_race(ballot, "County Commissioner Precinct 4")
    assert not find_race(ballot, "County Commissioner Precinct 2")
    d = ballot["districts"]
    assert d["precinct_sources"] == {"commissioner": "you", "jp": "county", "constable": "county"}
    assert d["county_source"] == {"county": "Travis", "method": "table"}  # for the card's small print
    assert "precinct" not in [s["id"] for s in ballot["maybe"]]


def test_an_emptied_precinct_overrides_the_county_and_ballotpedia(client):
    ballot = get_ballot(client, precincts={"commissioner": None, "jp": None})
    d = ballot["districts"]
    assert (d["jp"], d["constable"], d["commissioner"]) == (None, None, None)
    assert set(d["precinct_sources"].values()) == {"you"}
    assert find_race(ballot, "Justice of the Peace Precinct 5", maybe=True)
    assert not find_race(ballot, "Justice of the Peace Precinct 5")
    assert not [note for note in ballot["notes"] if "precinct" in note]


def test_no_precincts_sent_brings_the_countys_numbers_back(client):
    d = get_ballot(client, precincts=None)["districts"]
    assert (d["commissioner"], d["jp"]) == (2, 5) and set(d["precinct_sources"].values()) == {"county"}


def test_without_the_countys_list_ballotpedia_gives_the_precincts(client, upstream):
    client.put("/api/sources/county_precincts", json={"enabled": False})
    ballot = get_ballot(client)
    d = ballot["districts"]
    assert (d["jp"], d["constable"], d["commissioner"]) == (5, 5, None)
    assert d["precinct_sources"] == {"jp": "ballotpedia", "constable": "ballotpedia"} and d["county_source"] is None
    assert {r["name"] for r in ballot["maybe"][0]["races"]} == {"County Commissioner Precinct 2", "County Commissioner Precinct 4"}
    assert upstream.count("traviscountytx") == 0 and last_use(client, "county_precincts")["status"] == "off"


def test_a_note_when_the_county_and_ballotpedia_differ(client, upstream):
    upstream.arcgis["taxmaps.traviscountytx.gov"][TRAVIS_QUERY] = travis_rows({**TRAVIS_LIST, "300": (2, 3)})
    ballot = get_ballot(client)
    assert ballot["districts"]["jp"] == 3 and ballot["districts"]["precinct_sources"]["jp"] == "county"
    assert find_race(ballot, "Justice of the Peace Precinct 5", maybe=False) is None
    assert ("Ballotpedia puts this address in justice of the peace precinct 5, but Travis County's records say 3, which "
            "this ballot uses. Your voter registration certificate says which.") in ballot["notes"]


def test_one_number_for_jp_and_constable(client):
    d = get_ballot(client, precincts={"jp": 3})["districts"]
    assert (d["jp"], d["constable"]) == (3, 3)
    assert d["precinct_sources"] == {"commissioner": "county", "jp": "you", "constable": "you"}
    assert _jp_is_constable({"constable": 4}) == {"constable": 4, "jp": 4}
    assert _jp_is_constable({"jp": None}) == {"jp": None, "constable": None}
    assert _jp_is_constable({"jp": 2, "constable": None}) == {"jp": 2, "constable": None}


def test_commissioner_precincts_run_one_to_four(client):
    response = client.post("/api/ballot", json={"address": ADDRESSES["capitol"], "precincts": {"commissioner": 5}})
    assert response.status_code == 422


def test_entered_districts_win_over_the_addresss(client):
    ballot = get_ballot(client, districts={"cd": 37})
    d = ballot["districts"]
    assert (d["cd"], d["sd"], d["entered"]) == (37, 14, ["cd"])
    assert find_race(ballot, "U.S. Representative District 37") and not find_race(ballot, "U.S. Representative District 10")
    assert get_ballot(client)["districts"]["entered"] == []
    response = client.post("/api/ballot", json={"address": ADDRESSES["capitol"], "districts": {"cd": 39}})
    assert response.status_code == 422


def test_nominatim_fallback_is_marked_approximate(client):
    client.put("/api/sources/ballotpedia", json={"enabled": False})
    ballot = get_ballot(client, "mopac")
    assert ballot["location"]["geocoder"] == "nominatim" and ballot["location"]["approximate"]
    assert any("approximately" in w for w in ballot["warnings"])
    assert ballot["location"]["county"] == "Travis"


def source_row(client: TestClient, source_id: str) -> dict:
    return next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == source_id)


def test_a_census_refusal_pauses_it_and_addresses_already_looked_up_still_work(client, upstream):
    get_ballot(client)
    upstream.refusing["geocoding.geo.census.gov"] = 429
    first = client.post("/api/ballot", json={"address": ADDRESSES["ut"]})
    assert first.status_code == 502 and "isn't responding" in first.json()["detail"]
    again = client.post("/api/ballot", json={"address": ADDRESSES["harris"]})
    assert again.status_code == 502 and again.json()["detail"].startswith("The address lookup is paused until ")
    assert upstream.count("geocoding.geo.census.gov") == 2  # the Capitol, then the refusal; not asked again
    assert get_ballot(client)["location"]["geocoder"] == "census"
    row = source_row(client, "geocoding")
    assert row["notice_tone"] == "warn" and row["notice"].startswith("Paused until ")
    assert row["notice"].endswith(" after the address lookup refused a request; addresses already looked up still work.")


def test_a_nominatim_refusal_pauses_it(client, upstream):
    upstream.refusing["nominatim.openstreetmap.org"] = 403
    assert client.post("/api/ballot", json={"address": ADDRESSES["mopac"]}).status_code == 502
    again = client.post("/api/ballot", json={"address": "1 Nowhere Lane, Austin, TX 78701"})
    assert again.status_code == 502 and "is paused until" in again.json()["detail"]
    assert upstream.count("nominatim.openstreetmap.org") == 1


def test_a_texas_sos_refusal_pauses_it_and_the_ballot_comes_from_ballotpedia(client, upstream):
    upstream.refusing["goelect.txelections.civixapps.com"] = 403
    ballot = get_ballot(client)
    assert ballot["races"] and any("Ballotpedia only" in w for w in ballot["warnings"])
    asked = upstream.count("goelect.txelections.civixapps.com")
    get_ballot(client)
    assert upstream.count("goelect.txelections.civixapps.com") == asked  # paused: not asked again
    nothing = client.post("/api/ballot", json={"address": ADDRESSES["ut"]})  # Ballotpedia has no races there
    assert nothing.status_code == 502 and nothing.json()["detail"].startswith("Texas SOS is paused until ")
    row = source_row(client, "sos")
    assert row["notice_tone"] == "warn"
    assert row["notice"].endswith(" after Texas SOS refused a request; ballots it already sent still show.")


def test_outside_texas_is_refused(client):
    response = client.post("/api/ballot", json={"address": ADDRESSES["dc"]})
    assert response.status_code == 422 and "Texas" in response.json()["detail"]


def test_unknown_address(client):
    response = client.post("/api/ballot", json={"address": "Nowhere Street 123"})
    assert response.status_code == 422


def test_ballotpedia_refusal_degrades_gracefully(client, upstream):
    upstream.ballotpedia_status = 403
    ballot = get_ballot(client)
    assert find_race(ballot, "U.S. Senator")
    assert not find_race(ballot, "Austin City Council District 9")
    assert last_use(client, "ballotpedia")["status"] == "error"
    assert any("Ballotpedia" in w for w in ballot["warnings"])


def test_state_site_down_with_nothing_cached(client, upstream):
    client.put("/api/sources/ballotpedia", json={"enabled": False})
    upstream.down.add("goelect.txelections.civixapps.com")
    response = client.post("/api/ballot", json={"address": ADDRESSES["capitol"]})
    assert response.status_code == 502


def test_state_site_down_later_serves_the_cached_copy(make_app, upstream, tmp_path):
    config_dir = tmp_path / "data"
    with TestClient(make_app(config_dir)) as client:
        get_ballot(client)
    # expire everything, then take the state site down
    import sqlite3

    with sqlite3.connect(config_dir / "cache.sqlite3") as db:
        db.execute("UPDATE responses SET expires_at = 0")
    upstream.down.add("goelect.txelections.civixapps.com")
    with TestClient(make_app(config_dir)) as client:
        ballot = get_ballot(client)
        asked = upstream.count("goelect")
        get_ballot(client)  # the failed requests aren't retried yet: their old copies serve again
        assert upstream.count("goelect") == asked
        sos = last_use(client, "sos")
    assert find_race(ballot, "U.S. Senator")
    assert sos["status"] == "stale" and sos["calls"] == 0


def test_a_ballot_reads_each_state_list_once(client, monkeypatch):
    cache = client.app.state.svc.cache
    asked: list[str] = []
    original = cache.get_json

    async def counting(source, spec, **kwargs):
        asked.append(spec.url)
        return await original(source, spec, **kwargs)

    monkeypatch.setattr(cache, "get_json", counting)
    get_ballot(client)
    for suffix in ("getAllRegions", "getPoliticalParties", "getCandidateStatus", "getDeclarationStatus"):
        assert sum(url.endswith(suffix) for url in asked) == 1, suffix
