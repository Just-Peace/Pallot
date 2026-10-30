"""New Hampshire: the Secretary of State's candidate list, a CSV transcribed by hand from its PDF
(tests/fixtures/state_nh.csv: its name, office, district and party columns, Governor, Congress, the
Legislature, the Executive Council and the sheriffs), and its key dates, worked out from New
Hampshire's election law."""

from __future__ import annotations

import datetime as dt
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from bundles import store
from bundles.entry import BundleError
from bundles.manual import import_list
from pallot.states import nh
from pallot.states import key_dates as state_key_dates

from .bundling import build
from .conftest import FIXTURES, TODAY, candidate_names, find_race, get_ballot

D = dt.date
CSV = FIXTURES / "state_nh.csv"
HEADER = "Office / Section,District / County,Candidate Name,Party"


def nh_filings() -> list:
    return nh.parse_rows(CSV.read_text(encoding="utf-8"))


def by_name(filings: list, name: str):
    return next(f for f in filings if f.name == name)


def imported(tmp_path) -> dict:
    outcome = import_list("nh", CSV, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert outcome.status == "updated"
    return outcome.counts


def test_new_hampshires_list_has_governor_congress_and_its_legislature():
    filings = nh_filings()
    assert {f.day for f in filings} == {"2026-11-03"}
    assert Counter(f.reach for f in filings)["cd"] == 5
    assert len({f.district for f in filings if f.reach == "sd"}) == 24
    assert len({f.office_id for f in filings if f.reach == "hd"}) == 203
    assert sum(next(f.seats for f in filings if f.office_id == race) for race in
               {f.office_id for f in filings if f.reach == "hd"}) == 400
    assert [(f.office, f.name, f.party) for f in filings[:6]] == [
        ("Governor", "Cinde Warmington", "D"), ("Governor", "Kelly Ayotte", "R"), ("Governor", "Stephen Villee", "L"),
        ("U.S. Senator", "Chris Pappas", "D"), ("U.S. Senator", "John E. Sununu", "R"),
        ("U.S. Senator", "Edmond Laplante", None)]
    assert by_name(filings, "Edmond Laplante").party_name == "Constitution"
    goodlander = by_name(filings, "Maggie Goodlander")
    assert (goodlander.office, goodlander.reach, goodlander.district) == ("U.S. Representative District 2", "cd", "2")
    assert not any(f.name in ("Luz Bay", "Joseph D. Kenney") or "Sheriff" in f.office for f in filings)


def test_house_districts_are_the_censuss_with_their_seats_and_floterials_placed_by_their_base_districts():
    filings = nh_filings()
    base = by_name(filings, "Kyle Haines")
    assert (base.office, base.district, base.seats, base.party_name) == (
        "State Representative, Hillsborough District 12", "Hillsborough 12", 8, "Independent")
    floterial = next(f for f in filings if f.office_id == "STATE HOUSE MERRIMACK 29")
    assert (floterial.office, floterial.district, floterial.seats) == (
        "State Representative, Merrimack District 29", "Merrimack 29,Merrimack 18,Merrimack 23,Merrimack 24", 1)
    assert set(nh.FLOTERIALS) | {f"{county} {n}" for county, seats in nh.SEATS.items()
                                 for n in range(1, len(seats) + 1)} == {f.district.split(",")[0] for f in filings
                                                                        if f.reach == "hd"}


def test_a_candidate_nominated_by_two_parties_is_kept_once_with_both():
    major = [f for f in nh_filings() if f.name == "Kevin M. Major"]
    assert [(f.party, f.party_name) for f in major] == [("D", "Democratic / Republican")]


def test_a_new_hampshire_list_it_cant_read_is_refused():
    with pytest.raises(ValueError, match="no District / County, Party columns"):
        nh.parse_rows("Office / Section,Candidate Name\nGovernor,Jane Doe")
    with pytest.raises(ValueError, match="an office it doesn't know: Mayor"):
        nh.parse_rows(f"{HEADER}\nMayor,,Jane Doe,REP")
    with pytest.raises(ValueError, match="a State House district it doesn't know"):
        nh.parse_rows(f"{HEADER}\nState Representative,HILLSBOROUGH District 46,Jane Doe,REP")
    with pytest.raises(ValueError, match="a row that isn't a candidate: Domicile, Governor"):
        nh.parse_rows(f"{HEADER}\nGovernor,,Domicile,DEM")
    with pytest.raises(ValueError, match="0 U.S. House races, not 2"):
        nh.parse_rows(f"{HEADER}\nGovernor,,Jane Doe,REP")
    with pytest.raises(ValueError, match="no candidates"):
        nh.parse_rows(HEADER)
    with pytest.raises(ValueError, match="not a CSV"):
        nh.NhList.parse(b"Candidate Name")


def test_new_hampshires_2026_dates_follow_its_election_law():
    found = state_key_dates.computed("NH", D(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        None, D(2026, 11, 2), None, None)
    for day in (D(2026, 9, 8), D(2027, 11, 2)):
        assert state_key_dates.computed("NH", day) is None, day
    info = state_key_dates.GUIDES["NH"].voter_info()
    assert info.poll_hours == "until 7 p.m. or later" and "polling place on Election Day" in info.late_registration.label


def test_new_hampshires_calendar_is_worked_out_without_asking_anyone(client, upstream):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "NH"})
    assert response.headers["content-disposition"] == 'attachment; filename="new-hampshire-election-2026-11-03.ics"'
    unfolded = response.text.replace("\r\n ", "")
    assert "Polls open by 11 a.m. and close at 7 p.m. or later" in unfolded
    mail = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "NH", "event": "mail"}).text
    assert "SUMMARY:Last day to vote absentee in person (Nov 3 election)" in mail and "DTSTART;VALUE=DATE:20261102" in mail
    assert upstream.count("nh.gov") == 0


def test_the_import_bundles_the_parsed_candidates_never_the_csv(tmp_path):
    counts = imported(tmp_path)
    assert counts == {"races": len({f.office_id for f in nh_filings()}), "candidates": len(nh_filings())}
    [answer] = store.load("state_nh", tmp_path / "bundles").answers
    assert answer["request"]["url"] == "manual:state_nh" and set(answer["value"]) == {"filings"}
    assert "Office / Section" not in str(answer) and "Luz Bay" not in str(answer)
    assert import_list("nh", CSV, data_dir=tmp_path / "bundles", today=lambda: TODAY).status == "no_changes"


def test_the_import_refuses_a_file_that_isnt_the_list(tmp_path):
    saved = tmp_path / "saved.csv"
    saved.write_text("<html><body>Access Denied</body></html>", encoding="utf-8")
    with pytest.raises(BundleError, match="isn't a list the New Hampshire Secretary of State's reader understands"):
        import_list("nh", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert not (tmp_path / "bundles" / "state_nh.json").exists()


def test_refreshing_the_bundles_never_fetches_new_hampshires_list(tmp_path, upstream):
    outcome = build(tmp_path, "state_nh")
    assert outcome.status == "skipped" and "imported by hand" in outcome.detail
    assert upstream.count("nh.gov") == 0


def test_a_concord_ballot_has_its_base_and_floterial_house_races(tmp_path, upstream, make_app, logged_calls):
    imported(tmp_path)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "concord", all_races=True)
        assert ballot["coverage"]["ballot"] == "list"
        assert (ballot["districts"]["cd"], ballot["districts"]["sd"]) == (2, 15)
        names = [race["name"] for race in ballot["races"]]
        assert names == ["U.S. Senator", "U.S. Representative District 2", "Governor", "State Senator District 15",
                         "State Representative, Merrimack District 18", "State Representative, Merrimack District 29"]
        senate = find_race(ballot, "State Senator District 15")
        assert candidate_names(senate) == [f.name for f in nh_filings() if f.office == "State Senator District 15"]
        assert find_race(ballot, "U.S. Representative District 2")["seat"] == "NH-02"
        assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
        assert any("Executive Council" in note for note in ballot["notes"])
        assert ballot["key_dates"] == {
            "election": "General Election", "election_day": "2026-11-03", "register_by": None,
            "mail_apply_by": "2026-11-02", "early_voting_start": None, "early_voting_end": None,
            "source": "New Hampshire Secretary of State", "source_url": "https://www.sos.nh.gov/elections",
            "computed": True,
        }
        get_ballot(client, "concord", all_races=True)
        assert logged_calls() == 0
        rows = {row["id"]: row for row in client.get("/api/sources").json()["sources"]}
        assert rows["state_nh"]["notice"].startswith("Imported by hand on ")
    assert upstream.count("nh.gov") == 0


def test_without_an_imported_list_new_hampshire_has_the_fecs_races_for_congress(client, upstream):
    ballot = get_ballot(client, "concord")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("doesn't have the New Hampshire Secretary of State's list of candidates" in n for n in ballot["notes"])
    assert upstream.count("nh.gov") == 0
