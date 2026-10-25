"""States' official lists of candidates (pallot/states): reading North Carolina's, Michigan's,
Pennsylvania's, Florida's, Virginia's and California's, and the ballots made from them."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from pallot.config import DAY
from pallot.http_cache import RequestSpec
from pallot.sources import ca_key_dates
from pallot.sources.key_dates import Deadlines
from pallot.states import ca, district_key, fl, from_json, pdf_lines
from pallot.states.ca import CaList
from pallot.states.fl import FlList
from pallot.states.mi import MiList
from pallot.states.nc import NcList
from pallot.states.pa import PaList
from pallot.states.va import VaList

from .bundling import answers, build, came_with, lifetimes
from .conftest import FIXTURES, candidate_names, find_race, get_ballot, switch


def nc_list() -> str:
    return (FIXTURES / "state_nc.csv").read_text(encoding="utf-8")


def mi_list() -> str:
    return (FIXTURES / "state_mi.html").read_text(encoding="utf-8")


def recorded(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


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
    assert ballot["key_dates"] is None and upstream.count("goelect") == 0
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
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-19",
        "mail_apply_by": "2026-10-30", "early_voting_start": "2026-10-24", "early_voting_end": "2026-11-01",
        "source": "Michigan Department of State", "source_url": "https://www.michigan.gov/sos/elections/voting",
        "computed": True,
    }


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
    assert ballot["key_dates"]["register_by"] == "2026-10-19"


def test_pennsylvanias_list_keeps_the_nominees_and_leaves_out_the_primarys_party_offices():
    filings = PaList.parse(recorded("state_pa.html"))
    assert {f.day for f in filings} == {"2026-11-03"}
    names = {f.name for f in filings}
    assert "Justin Douglas" not in names  # lost the primary
    assert "Anthony James Dastra" not in names  # withdrew
    assert not any("COMMITTEE" in f.office_id for f in filings)
    governor = sorted((f for f in filings if f.office == "Governor"), key=lambda f: f.order)
    assert [(f.name, f.party) for f in governor] == [
        ("Joshua D Shapiro", "D"), ("Stacy Lorraine Garrity", "R"), ("Kenneth V Krawchuk", "L")]
    assert [f.name for f in filings if f.office == "Lieutenant Governor"].count("Jason L Richey") == 1  # filed twice
    house = next(f for f in filings if f.name == "Cynthia P Ward")  # nominated by write-ins in the primary
    assert (house.reach, house.district, house.office) == ("hd", "103", "State Representative District 103")


def test_floridas_list_keeps_only_the_qualified_candidates():
    filings = FlList.parse(recorded("state_fl.tsv"))
    names = {f.name for f in filings}
    assert {"Jay Collins", "Jerry Demings", "Neal Dunn", "Tiffany Baker"}.isdisjoint(names)  # lost, withdrew, didn't qualify, unopposed
    senate = sorted((f for f in filings if f.office == "U.S. Senator"), key=lambda f: f.order)
    assert [(f.name, f.party) for f in senate] == [("Ashley Moody", "R"), ("Angie Nixon", "D"), ("Neil J. Gillespie", None)]
    governor = [f for f in filings if f.office == "Governor"]
    assert {f.name for f in governor if f.write_in} == {"Kathy Anderson", "Erik Morris"}
    appeals = next(f for f in filings if f.office_id.startswith("DCA 1 "))
    assert appeals.reach == "counties" and "LEON" in appeals.counties and appeals.office.startswith("Retain 1st District")
    assert not any(f.family.startswith("LOXAHATCHEE") for f in filings)  # a special district: not placed


def test_floridas_list_is_asked_for_with_its_download_form():
    asked = RequestSpec("POST", fl.URL, form=fl.form(dt.date(2026, 11, 3)), as_text=True)
    assert asked.form["elecID"] == "20261103-GEN"
    assert RequestSpec.loads(asked.dumps()) == asked
    assert asked.key != RequestSpec("POST", fl.URL, form=fl.form(dt.date(2028, 11, 7)), as_text=True).key


def test_virginias_list_has_its_races_for_congress_and_their_incumbents():
    filings = VaList.parse(recorded("state_va.html"))
    assert {f.day for f in filings} == {"2026-11-03"} and {f.group for f in filings} == {"federal"}
    fourth = sorted((f for f in filings if f.district == "4"), key=lambda f: f.order)
    assert [(f.name, f.party, f.party_name, f.incumbent) for f in fourth] == [
        ("Jennifer L. McClellan", "D", None, True), ('Robert P. "Family Man" Murray, Jr.', "R", None, False),
        ('Joan E. "Andrews" Bell', None, "Independent", False)]
    with pytest.raises(ValueError):
        VaList.parse("<html><body><h1>Page not found</h1></body></html>")


@pytest.mark.parametrize("source, host, address", [
    ("state_pa", "www.pavoterservices.pa.gov", "harrisburg"),
    ("state_fl", "dos.elections.myflorida.com", "tallahassee"),
    ("state_va", "www.elections.virginia.gov", "richmond"),
    ("state_ca", "elections.cdn.sos.ca.gov", "losangeles"),
])
def test_each_states_bundled_list_serves_a_lookup_without_asking(tmp_path, upstream, make_app, source, host, address):
    outcome = build(tmp_path, source)
    assert outcome.status == "updated" and outcome.answers == 1 and outcome.counts["candidates"] > 0
    asked = upstream.count(host)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, address)
    assert ballot["coverage"]["ballot"] == "list" and upstream.count(host) == asked


def test_a_pennsylvania_ballot_comes_from_its_official_list(client, logged_calls):
    ballot = get_ballot(client, "harrisburg")
    assert ballot["coverage"]["ballot"] == "list"
    assert [race["name"] for race in ballot["races"]] == [
        "U.S. Representative District 10", "Governor", "Lieutenant Governor", "State Representative District 103"]
    house = find_race(ballot, "U.S. Representative District 10")
    assert candidate_names(house) == ["Janelle Stelson", "Scott Perry"] and house["seat"] == "PA-10"
    assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
    get_ballot(client, "harrisburg")
    assert logged_calls() == 0


def test_a_florida_ballot_has_its_courts_retention_for_the_voters_county(client, upstream, logged_calls):
    ballot = get_ballot(client, "tallahassee")
    assert ballot["coverage"]["ballot"] == "list"
    assert candidate_names(find_race(ballot, "U.S. Senator")) == ["Ashley Moody", "Angie Nixon", "Neil J. Gillespie"]
    for name in ("U.S. Representative District 2", "Governor", "Commissioner of Agriculture",
                 "State Representative District 9", "Retain Supreme Court Justice Carlos G. Muniz",
                 "Retain 1st District Court of Appeal Judge Tim Osterhaus"):
        assert find_race(ballot, name), name
    assert not any("2nd District Court of Appeal" in race["name"] for race in ballot["races"])
    governor = find_race(ballot, "Governor")
    assert [c["name"] for c in governor["candidates"] if c["write_in"]] == ["Kathy Anderson", "Erik Morris"]
    assert "POST dos.elections.myflorida.com/candidates/extractCanList.asp" in upstream.calls
    get_ballot(client, "tallahassee")
    assert logged_calls() == 0


def test_a_virginia_ballot_has_its_races_for_congress_from_its_list(client, logged_calls):
    ballot = get_ballot(client, "richmond")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd"]}
    assert [race["name"] for race in ballot["races"]] == ["U.S. Senator", "U.S. Representative District 4"]
    house = find_race(ballot, "U.S. Representative District 4")
    assert [c["incumbent"] for c in house["candidates"]] == [True, False, False]
    get_ballot(client, "richmond")
    assert logged_calls() == 0


def test_settings_lists_each_states_election_office(client):
    overview = client.get("/api/sources").json()
    assert any(group["id"] == "states" and group["toggle_all"] for group in overview["groups"])
    rows = {row["id"]: row for row in overview["sources"] if row["group"] == "states"}
    assert set(rows) == {"state_nc", "state_mi", "state_pa", "state_fl", "state_va", "state_ca", "key_dates_ca", "state_az",
                         "state_nv", "state_ga", "state_wi", "state_oh", "state_ia", "state_nj"}
    assert rows["state_nc"]["enabled"] and rows["key_dates_ca"]["enabled"]


def ca_list() -> bytes:
    return (FIXTURES / "state_ca.pdf").read_bytes()


def test_californias_list_has_its_races_parties_incumbents_and_courts():
    filings = CaList.parse(ca_list())
    reaches = Counter(reach for reach, _ in {(f.reach, f.office_id) for f in filings})
    assert (reaches["cd"], reaches["state"], reaches["unplaced"]) == (52, 8 + 2, 4)  # two Supreme Court justices statewide
    assert {"26"} <= {f.district for f in filings if f.reach == "sd"} and {"54"} <= {f.district for f in filings if f.reach == "hd"}
    governor = sorted((f for f in filings if f.office == "Governor"), key=lambda f: f.order)
    assert [(f.name, f.party, f.group) for f in governor] == [("Xavier Becerra", "D", "state"), ("Steve Hilton", "R", "state")]
    kiley = next(f for f in filings if f.name == "Kevin Kiley")
    assert (kiley.party, kiley.party_name, kiley.office, kiley.district) == (None, None, "U.S. Representative District 6", "6")
    assert {(f.party, f.party_name) for f in filings if f.office == "Superintendent of Public Instruction"} == {(None, None)}
    assert next(f for f in filings if f.name == "Shirley N. Weber").incumbent
    assert not next(f for f in filings if f.name == "Donald P. (Don) Wagner").incumbent
    assert next(f for f in filings if f.office == "State Assembly Member District 54").group == "legislature"
    evans = next(f for f in filings if f.name == "Kelli M. Evans")
    assert (evans.office, evans.reach, evans.group, evans.incumbent) == (
        "Retain Kelli M. Evans, Associate Justice of the Supreme Court", "state", "judicial", True)
    kim = next(f for f in filings if f.name == "Michelle C. Kim")
    assert (kim.reach, kim.district, kim.counties) == ("counties", "2", ("LOS ANGELES", "SAN LUIS OBISPO", "SANTA BARBARA", "VENTURA"))
    assert "SOLANO" in next(f for f in filings if f.name == "Charles A. Smiley").counties


def test_californias_court_pages_are_read_through_their_spacing_wraps_and_order():
    plain = [
        "Court of Appeal – Third Appellate District",
        "Alpine, Amador, Butte, Calaveras, Colusa, El Dorado, Glenn, Lassen, Modoc, Mono,",
        "Nevada, Placer, Plumas, Sacramento, San Joaquin, Sh  asta, Sierra, Siskiyou, Sutter,",
        "Page 37 of 41",
        "• For Associate Justice, Court of Appeal, Third District",
        "Shall DAVID B. SAPP be elected to the office for the term provided by law?",
        "• For Associate Justice, Court of Appeal, Fourth District, Division One",
        "Shall San Diego County Superior Court Judge LISA RODRIGUEZ be elected to",
        "the office for the term provided by law?",
        "Court of Appeal – Fourth Appellate District",
        "Imperial, Inyo, Orange, Riverside, San Bern ardino, San Diego",
        "• For Associate Justice of the Supreme Court",
        "Shall Associate Justice of the Supreme Court KENNETH R. YEGAN be elected to the",
        "office for the term provided by law?",
    ]
    courts = [f for f in ca.parse_lines(pdf_lines(ca_list()), plain) if f.group == "judicial"]
    assert [f.name for f in courts] == ["Kenneth R. Yegan", "David B. Sapp", "Lisa Rodriguez"]  # the ballot's order
    yegan, sapp, rodriguez = courts
    assert (yegan.reach, yegan.incumbent) == ("state", True)
    assert sapp.office == "Elect David B. Sapp, Associate Justice, Court of Appeal, Third District" and not sapp.incumbent
    assert {"SHASTA", "SAN JOAQUIN", "SUTTER"} <= set(sapp.counties) and "SAN DIEGO" not in sapp.counties
    assert (rodriguez.district, rodriguez.office.split(",")[0]) == ("4", "Elect Lisa Rodriguez")
    assert "SAN BERNARDINO" in rodriguez.counties


def test_a_california_list_without_every_house_race_or_that_isnt_a_pdf_is_refused():
    layout = pdf_lines(ca_list())
    cut = layout[:next(i for i, line in enumerate(layout) if line.strip() == "United States Representative District 30")]
    with pytest.raises(ValueError, match="29 U.S. House races"):
        ca.parse_lines(cut, [])
    with pytest.raises(ValueError, match="not a PDF"):
        CaList.parse(b"<html><body>Service Unavailable</body></html>")


def test_a_california_ballot_comes_from_its_pdf_kept_only_as_its_candidates(client, upstream, logged_calls, tmp_path):
    ballot = get_ballot(client, "losangeles")
    assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "labels": {"hd": "State Assembly"}}
    for name in ("U.S. Representative District 34", "Governor", "Superintendent of Public Instruction",
                 "State Senate District 26", "State Assembly Member District 54",
                 "Retain Kelli M. Evans, Associate Justice of the Supreme Court",
                 "Retain Michelle C. Kim, Associate Justice, Court of Appeal, Second District, Division One"):
        assert find_race(ballot, name), name
    assert find_race(ballot, "U.S. Representative District 34")["seat"] == "CA-34"
    assert not any("First District" in race["name"] or "Equalization" in race["name"] for race in ballot["races"])
    assert any("4 Board of Equalization races" in note for note in ballot["notes"])
    evans = find_race(ballot, "Retain Kelli M. Evans, Associate Justice of the Supreme Court")
    assert [(c["name"], c["party"], c["incumbent"]) for c in evans["candidates"]] == [("Kelli M. Evans", None, True)]
    data = tmp_path / "data"
    assert upstream.count("elections.cdn.sos.ca.gov") == 1 and not list(data.glob(".*.part"))
    with sqlite3.connect(data / "cache.sqlite3") as db:
        [(value,)] = db.execute("SELECT value FROM responses WHERE source = 'state_ca'").fetchall()
    assert set(json.loads(value)) == {"filings"}
    get_ballot(client, "losangeles")
    assert logged_calls() == 0


def test_a_california_list_it_cant_read_keeps_the_last_good_copy(make_app, upstream):
    with TestClient(make_app()) as client:
        get_ballot(client, "losangeles")
    upstream.state_lists["elections.cdn.sos.ca.gov"] = "<html><body>Down for maintenance</body></html>"
    status, said = make_app.cache_command("hard-refresh", "state_ca")
    assert status != 0 and "failed and kept their old copy" in said and "not a PDF" in said
    with TestClient(make_app()) as client:
        ballot = get_ballot(client, "losangeles")
    assert ballot["coverage"]["ballot"] == "list" and find_race(ballot, "State Assembly Member District 54")


def test_californias_key_dates_come_from_its_secretary_of_states_page():
    [found] = ca_key_dates.parse(recorded("key_dates_ca.html"))
    assert found == Deadlines(dt.date(2026, 11, 3), "General Election", register_by=dt.date(2026, 10, 19),
                              mail_apply_by=dt.date(2026, 10, 27), state="CA")
    assert ca_key_dates.no_elections(recorded("key_dates_ca.html")) is None
    assert ca_key_dates.no_elections("<html><body><h1>Site maintenance</h1></body></html>")


def test_a_california_ballot_has_its_key_dates_and_their_calendar(client, upstream, logged_calls):
    ballot = get_ballot(client, "losangeles")
    assert ballot["key_dates"] == {
        "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-19",
        "mail_apply_by": "2026-10-27", "early_voting_start": None, "early_voting_end": None,
        "source": "California Secretary of State", "source_url": ca_key_dates.URL, "computed": False,
    }
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "CA"})
    assert response.status_code == 200 and "california-election-2026-11-03.ics" in response.headers["content-disposition"]
    assert "SUMMARY:Last day to register to vote" in response.text.replace("\r\n ", "")
    mail = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "CA", "event": "mail"})
    assert "SUMMARY:Ask for a replacement mail ballot" in mail.text.replace("\r\n ", "")
    assert upstream.count("www.sos.ca.gov") == 1
    get_ballot(client, "losangeles")
    assert logged_calls() == 0


def test_californias_key_dates_off_or_unreadable_leave_the_ballot(client, upstream):
    switch(client, "key_dates_ca", False)
    ballot = get_ballot(client, "losangeles")
    assert ballot["key_dates"] is None and upstream.count("www.sos.ca.gov") == 0
    switch(client, "key_dates_ca", True)
    upstream.ca_key_dates = "<html><body><h1>Site maintenance</h1></body></html>"
    ballot = get_ballot(client, "losangeles")
    assert ballot["key_dates"] is None and ballot["coverage"]["ballot"] == "list"
    assert any("key dates" in note and "California Secretary of State" in note for note in ballot["notes"])


def test_with_californias_list_off_or_unreadable_its_ballot_has_the_races_for_congress_from_the_fec(client, upstream):
    switch(client, "state_ca", False)
    ballot = get_ballot(client, "losangeles")
    assert ballot["coverage"]["ballot"] == "fec" and find_race(ballot, "U.S. Representative District 34")
    assert upstream.count("elections.cdn.sos.ca.gov") == 0
    switch(client, "state_ca", True)
    upstream.state_lists["elections.cdn.sos.ca.gov"] = "%PDF-1.7 cut short"
    ballot = get_ballot(client, "losangeles")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the California Secretary of State" in w for w in ballot["warnings"])
