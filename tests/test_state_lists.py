"""States' official lists of candidates (pallot/states): reading North Carolina's and Michigan's,
and the ballots made from them."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from pallot.config import DAY
from pallot.states import district_key, from_json
from pallot.states.mi import MiList
from pallot.states.nc import NcList

from .bundling import answers, build, came_with, lifetimes
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch


def nc_list() -> str:
    return (FIXTURES / "state_nc.csv").read_text(encoding="utf-8")


def mi_list() -> str:
    return (FIXTURES / "state_mi.html").read_text(encoding="utf-8")


def test_districts_are_spelled_one_way_however_they_are_written():
    assert district_key("038") == district_key(38) == district_key("District 38") == "38"
    assert district_key("3rd Suffolk") == district_key("Third Suffolk") == "3 SUFFOLK"
    assert district_key("12A") == "12A" and district_key("Washington-4") == "WASHINGTON 4"


def test_north_carolinas_list_has_each_candidate_once_with_the_counties_their_race_reaches():
    filings = NcList.parse(nc_list())
    assert {f.day for f in filings} == {"2026-11-03"}  # the primary's rows are left out
    senate = sorted((f for f in filings if f.office_id == "US SENATE"), key=lambda f: f.order)
    assert [f.name for f in senate] == ["Roy Cooper", "Michael Whatley", "Shannon W. Bray", "Michael Dublin"]
    assert [f.party for f in senate] == ["D", "R", "L", "G"]
    assert set(senate[0].counties) == {"WAKE", "DURHAM", "ALAMANCE", "MECKLENBURG"}
    at_large = [f for f in filings if f.office_id == "WAKE COUNTY BOARD OF COMMISSIONERS AT-LARGE"]
    assert {(f.reach, f.seats, f.group) for f in at_large} == {("county", 2, "county")}
    house = next(f for f in filings if f.office_id == "NC HOUSE OF REPRESENTATIVES DISTRICT 038")
    assert (house.reach, house.district, house.office) == ("hd", "38", "NC House of Representatives District 38")
    ward = next(f for f in filings if f.office_id == "CITY OF RALEIGH CITY COUNCIL DISTRICT A")
    assert (ward.reach, ward.city) == ("part_city", "RALEIGH CITY COUNCIL DISTRICT A")


def test_a_list_without_the_columns_it_should_have_is_refused():
    with pytest.raises(ValueError, match="contest_name"):
        NcList.parse("election_dt,county_name\n11/03/2026,WAKE\n")
    with pytest.raises(ValueError):
        MiList.parse("<html><body>Down for maintenance</body></html>")


def test_michigans_list_leaves_out_withdrawn_and_disqualified_candidates():
    filings = MiList.parse(mi_list())
    names = {f.name for f in filings}
    assert "Felix Thibodeau" not in names  # DISQ
    senate = [f.name for f in filings if f.office_id == "U.S. Senate"]
    assert senate[:2] == ["Abdul El-Sayed", "Mike Rogers"]
    justices = [f for f in filings if f.office_id == "Justice of Supreme Court"]
    assert {f.name for f in justices if f.incumbent} == {"Megan Kathleen Cavanagh", "Noah P. Hood"}
    assert all(f.seats == 2 and f.reach == "state" for f in justices)
    probate = next(f for f in filings if f.office_id.startswith("INGHAM Judge of Probate"))
    assert (probate.reach, probate.counties) == ("county", ("INGHAM",))
    assert next(f for f in filings if "Circuit Court" in f.office_id).reach == "unplaced"


def test_the_bundled_copy_is_the_candidates_without_the_raw_file():
    shaped = NcList.shape(nc_list())
    assert set(shaped) == {"filings"} and "street_address" not in json.dumps(shaped)
    assert from_json(json.loads(json.dumps(shaped))) == NcList.parse(nc_list())
    assert NcList.shape(shaped) is shaped


def test_a_bundled_list_is_its_candidates_and_serves_a_lookup_without_asking(tmp_path, upstream, make_app):
    outcome = build(tmp_path, "state_nc")
    assert outcome.status == "updated" and outcome.answers == 1 and outcome.counts["candidates"] > 0
    [answer] = answers(tmp_path, "state_nc")
    assert set(answer["value"]) == {"filings"} and lifetimes(tmp_path, "state_nc") == {2 * DAY}
    asked = upstream.count("s3.amazonaws.com")
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "raleigh")
        said = came_with(client, "state_nc")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "U.S. Senator")
    assert upstream.count("s3.amazonaws.com") == asked and said.startswith("Came with 1 answer, checked ")


def test_a_north_carolina_ballot_comes_from_its_official_list(client, upstream, logged_calls):
    ballot = get_ballot(client, "raleigh")
    assert ballot["coverage"]["ballot"] == "list"
    senate = find_race(ballot, "U.S. Senator")
    assert candidate_names(senate) == ["Roy Cooper", "Michael Whatley", "Shannon W. Bray", "Michael Dublin"]
    assert senate["source"] == "state_nc" and senate["seat"] == "NC-SEN"
    assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
    house = find_race(ballot, "U.S. Representative District 2")
    assert any(card["source"] == "fec" for c in house["candidates"] for card in c["cards"])
    for name in ("NC State Senate District 14", "NC House of Representatives District 38", "Wake County Sheriff",
                 "City of Raleigh Mayor", "NC Supreme Court Associate Justice Seat 1"):
        assert find_race(ballot, name), name
    assert find_race(ballot, "Wake County Board of Commissioners District 1") is None
    assert ballot["left_out"]["races"] > 0 and ballot["maybe"] == []
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (2, 14, 38)
    assert ballot["key_dates"] is None and upstream.count("goelect") == 0 and upstream.count("ballotpedia") == 0
    get_ballot(client, "raleigh")
    assert logged_calls() == 0


def test_races_on_part_of_the_county_show_when_asked_for(client):
    ballot = get_ballot(client, "raleigh", all_races=True)
    [section] = ballot["maybe"]
    assert section["id"] == "unconfirmed"
    names = candidate_names
    assert find_race(ballot, "Wake County Board of Commissioners District 1", maybe=True)
    assert find_race(ballot, "City of Raleigh City Council District A", maybe=True)
    assert names(find_race(ballot, "NC District Court Judge District 10A Seat 1", maybe=True))


def test_a_michigan_ballot_has_its_statewide_races_and_says_what_it_leaves_out(client):
    ballot = get_ballot(client, "lansing")
    for name in ("U.S. Senator", "U.S. Representative District 7", "Governor / Lt. Governor",
                 "State Senator District 21", "State Representative District 77", "Justice of the Supreme Court"):
        assert find_race(ballot, name), name
    assert find_race(ballot, "Justice of the Supreme Court")["seats"] == 2
    assert find_race(ballot, "Ingham County Judge of Probate, incumbent position")
    assert any("court races" in note and "sample ballot" in note for note in ballot["notes"])


def test_a_state_list_turned_off_leaves_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_nc", False)
    ballot = get_ballot(client, "raleigh")
    assert ballot["coverage"]["ballot"] == "fec"
    assert all(c["unverified"] for race in ballot["races"] for c in race["candidates"])
    assert any("turned off" in note for note in ballot["notes"])
    assert upstream.count("s3.amazonaws.com") == 0


@pytest.mark.parametrize("trouble", ["unreadable", "down"])
def test_a_state_list_that_cant_be_had_leaves_the_races_for_congress_from_the_fec(client, upstream, trouble):
    if trouble == "down":
        upstream.down.add("mi-boe.entellitrak.com")
    else:
        upstream.state_lists["mi-boe.entellitrak.com"] = "<html><body>Down for maintenance</body></html>"
    ballot = get_ballot(client, "lansing")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Michigan Bureau of Elections" in w for w in ballot["warnings"])


def test_settings_lists_each_states_election_office(client):
    overview = client.get("/api/sources").json()
    assert any(group["id"] == "states" and group["toggle_all"] for group in overview["groups"])
    rows = {row["id"]: row for row in overview["sources"] if row["group"] == "states"}
    assert set(rows) == {"state_nc", "state_mi"} and rows["state_nc"]["enabled"]
