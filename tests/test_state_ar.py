"""Arkansas: the Secretary of State's candidate search, a CSV saved by hand (tests/fixtures/state_ar.csv:
Congress, the statewide offices and a few districts' rows), and its key dates, worked out from
Arkansas's election law."""

from __future__ import annotations

import datetime as dt
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from bundles import store
from bundles.entry import BundleError
from bundles.manual import import_list
from pallot.states import ar
from pallot.states import key_dates as state_key_dates

from .bundling import build
from .conftest import FIXTURES, TODAY, candidate_names, find_race, get_ballot

D = dt.date
CSV = FIXTURES / "state_ar.csv"
HEADER = '"","Candidate Name","Position/Office","Party Affiliation","Filing Date"'


def ar_filings() -> list:
    return ar.parse_rows(CSV.read_text(encoding="utf-8"))


def by_name(filings: list, name: str):
    return next(f for f in filings if f.name == name)


def imported(tmp_path) -> dict:
    outcome = import_list("ar", CSV, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert outcome.status == "updated"
    return outcome.counts


def test_arkansass_list_has_congress_its_statewide_offices_and_its_legislature():
    filings = ar_filings()
    assert {f.day for f in filings} == {"2026-11-03"}
    assert Counter(f.reach for f in filings) == {"state": 16, "cd": 10, "hd": 6, "sd": 2}
    assert [(f.name, f.party) for f in filings if f.office == "U.S. Senator"] == [
        ("Hallie Shoffner", "D"), ("Tom Cotton", "R"), ("Jeff Wadlin", "L")]
    order = list(dict.fromkeys(f.office for f in filings if f.reach == "state"))
    assert order == ["U.S. Senator", *ar.STATEWIDE]
    hill = by_name(filings, "French Hill")
    assert (hill.office, hill.reach, hill.district, hill.group) == ("U.S. Representative District 2", "cd", "2", "federal")
    tucker = by_name(filings, "Clarke Tucker")
    assert (tucker.office, tucker.reach, tucker.district, tucker.group) == ("State Senator District 14", "sd", "14",
                                                                           "legislature")
    assert (by_name(filings, "Laura Marsh").party, by_name(filings, "Laura Marsh").party_name) == (None, "Independent")
    assert not any("Circuit" in f.office or f.name in ("Kristin Pawlik", "Wendy Howerton") for f in filings)


def test_the_titles_candidates_filed_under_are_dropped_from_their_names():
    names = {f.name for f in ar_filings()}
    for name in ("Tom Cotton", "Sarah Huckabee Sanders", "Leslie Rutledge", "Cole Jester", "Kim Hammer", "Fred Love",
                 "Tim Griffin", "Dennis Milligan", "John Thurston", "French Hill", "Tippi McCullough", "Brian Armas",
                 "Kendra Moore", 'James "Rus" Russell, III'):
        assert name in names, name
    assert not any(name.split()[0] in ("Senator", "Congressman", "Representative", "Justice", "State") for name in names)


def test_house_district_8s_special_election_is_a_race_of_its_own():
    filings = [f for f in ar_filings() if f.district == "8"]
    assert [(f.office_id, f.name, f.party, f.unexpired) for f in filings] == [
        ("STATE HOUSE 8", "Brian Armas", "R", False),
        ("STATE HOUSE 8 UNEXPIRED", "Parker John Stohlton", "D", True),
        ("STATE HOUSE 8 UNEXPIRED", "Kara Armas", "R", True)]


def test_an_arkansas_list_it_cant_read_is_refused():
    with pytest.raises(ValueError, match="no Party Affiliation, Filing Date columns"):
        ar.parse_rows('"","Candidate Name","Position/Office"\n"","Jane Doe","Governor"')
    with pytest.raises(ValueError, match="an office it doesn't know: Mayor"):
        ar.parse_rows(f'{HEADER}\n"","Jane Doe","Mayor","Republican","2025-11-03"')
    with pytest.raises(ValueError, match="0 U.S. House races, not 4"):
        ar.parse_rows(f'{HEADER}\n"","Jane Doe","Governor","Republican","2025-11-03"')
    with pytest.raises(ValueError, match="no candidates"):
        ar.parse_rows(HEADER)
    with pytest.raises(ValueError, match="not a CSV"):
        ar.ArList.parse(b"Candidate Name")


def test_arkansass_2026_dates_follow_its_election_law():
    found = state_key_dates.computed("AR", D(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        D(2026, 10, 5), D(2026, 10, 27), D(2026, 10, 19), D(2026, 11, 2))
    for day in (D(2026, 3, 3), D(2026, 12, 1)):
        assert state_key_dates.computed("AR", day) is None, day


def test_arkansass_calendar_is_worked_out_without_asking_anyone(client, upstream):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "AR"})
    assert response.headers["content-disposition"] == 'attachment; filename="arkansas-election-2026-11-03.ics"'
    unfolded = response.text.replace("\r\n ", "")
    assert "DTSTART;VALUE=DATE:20261019" in unfolded and "7:30 a.m. to 7:30 p.m." in unfolded
    mail = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "AR", "event": "mail"}).text
    assert "SUMMARY:Absentee application due (Nov 3 election)" in mail and "DTSTART;VALUE=DATE:20261027" in mail
    assert upstream.count("arkansas.gov") == 0


def test_the_import_bundles_the_parsed_candidates_never_the_csv(tmp_path):
    counts = imported(tmp_path)
    assert counts == {"races": len({f.office_id for f in ar_filings()}), "candidates": len(ar_filings())}
    [answer] = store.load("state_ar", tmp_path / "bundles").answers
    assert answer["request"]["url"] == "manual:state_ar" and set(answer["value"]) == {"filings"}
    assert "Filing Date" not in str(answer) and "2025-11-03" not in str(answer) and "Congressman" not in str(answer)
    assert import_list("ar", CSV, data_dir=tmp_path / "bundles", today=lambda: TODAY).status == "no_changes"


def test_the_import_refuses_a_file_that_isnt_the_list(tmp_path):
    saved = tmp_path / "saved.csv"
    saved.write_text("<html><body>Candidate Search</body></html>", encoding="utf-8")
    with pytest.raises(BundleError, match="isn't a list the Arkansas Secretary of State's reader understands"):
        import_list("ar", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert not (tmp_path / "bundles" / "state_ar.json").exists()


def test_refreshing_the_bundles_never_fetches_arkansass_list(tmp_path, upstream):
    outcome = build(tmp_path, "state_ar")
    assert outcome.status == "skipped" and "imported by hand" in outcome.detail
    assert upstream.count("arkansas.gov") == 0


def test_a_little_rock_ballot_comes_from_the_imported_list(tmp_path, upstream, make_app, logged_calls):
    imported(tmp_path)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "littlerock", all_races=True)
        assert ballot["coverage"]["ballot"] == "list"
        assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (2, 14, 74)
        names = [race["name"] for race in ballot["races"]]
        assert names == ["U.S. Senator", "U.S. Representative District 2", *ar.STATEWIDE, "State Senator District 14",
                         "State Representative District 74"]
        assert candidate_names(find_race(ballot, "State Senator District 14")) == ["Clarke Tucker", "Mark S. Foster"]
        assert find_race(ballot, "U.S. Representative District 2")["seat"] == "AR-02"
        assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
        assert any("circuit judge" in note for note in ballot["notes"])
        assert ballot["key_dates"] == {
            "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-05",
            "mail_apply_by": "2026-10-27", "early_voting_start": "2026-10-19", "early_voting_end": "2026-11-02",
            "source": "Arkansas Secretary of State", "source_url": "https://www.sos.arkansas.gov/elections",
            "computed": True,
        }
        get_ballot(client, "littlerock", all_races=True)
        assert logged_calls() == 0
        rows = {row["id"]: row for row in client.get("/api/sources").json()["sources"]}
        assert rows["state_ar"]["notice"].startswith("Imported by hand on ")
    assert upstream.count("arkansas.gov") == 0


def test_without_an_imported_list_arkansas_has_the_fecs_races_for_congress(client, upstream):
    ballot = get_ballot(client, "littlerock")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("doesn't have the Arkansas Secretary of State's list of candidates" in n for n in ballot["notes"])
    assert find_race(ballot, "U.S. Representative District 2")
    assert upstream.count("arkansas.gov") == 0
