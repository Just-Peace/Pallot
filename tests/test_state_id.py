"""Idaho: the Secretary of State's candidate search export for the general election, a spreadsheet
saved by hand (tests/fixtures/state_id.xlsx: Congress, the statewide offices, Boise's district, a
few more, the first rows of every other district and a row of each office left out), and its key
dates, worked out from the Idaho Code."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from bundles import store
from bundles.entry import BundleError
from bundles.manual import import_list
from pallot.states import id_
from pallot.states import key_dates as state_key_dates

from .bundling import build
from .conftest import FIXTURES, TODAY, candidate_names, find_race, get_ballot

D = dt.date
XLSX = FIXTURES / "state_id.xlsx"
GENERAL = "November 03, 2026 - 2026 General"


def id_filings() -> list:
    return id_.IdList.parse(XLSX.read_bytes())


def by_name(filings: list, name: str):
    return next(f for f in filings if f.name == name)


def row(kind: str, office: str, name: str, district: str = "", seat: str = "", label: str = "Republican",
        election: str = GENERAL, write_in: str = "", withdrawn: str = "") -> list[str]:
    return [name, election, kind, office, district, seat, label, write_in, withdrawn]


def rows(*extra: list[str]) -> list[list[str]]:
    """The export's header, a Republican in every U.S. House and legislative district, then ``extra``."""
    return [list(id_.COLUMNS),
            *(row("Federal", "United States Representative", f"Jane Doe{n}", str(n)) for n in (1, 2)),
            *(row("State Legislature", "State Senator", f"Sen Roe{n}", str(n)) for n in range(1, 36)),
            *(row("State Legislature", "State Representative", f"Rep Roe{n}", str(n), "A") for n in range(1, 36)),
            *extra]


def imported(tmp_path) -> dict:
    outcome = import_list("id", XLSX, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert outcome.status == "updated"
    return outcome.counts


def test_idahos_list_has_congress_its_statewide_offices_and_its_legislature():
    filings = id_filings()
    assert {f.day for f in filings} == {"2026-11-03"}
    assert {f.reach for f in filings} == {"state", "cd", "sd", "hd"}
    assert len({f.district for f in filings if f.reach == "sd"}) == 35
    assert len({f.district for f in filings if f.reach == "hd"}) == 35
    assert [(f.name, f.party, f.party_name) for f in filings if f.office == "U.S. Senator"] == [
        ("Jim Risch", "R", None), ("Matt Loesby", "L", None), ("Natalie M Fleming", None, "Independent"),
        ("Todd Achilles", None, "Independent")]
    simpson = by_name(filings, "Mike Simpson")
    assert (simpson.office, simpson.reach, simpson.district, simpson.group) == ("U.S. Representative District 2", "cd",
                                                                              "2", "federal")
    offices = list(dict.fromkeys(f.office for f in filings if f.group == "state"))
    assert offices == ["Governor", "Lieutenant Governor", "Secretary of State", "State Controller", "State Treasurer",
                       "Attorney General", "Superintendent of Public Instruction"]
    assert by_name(filings, "Pro-Life").party_name == "Constitution"
    assert not any(f.write_in for f in filings if f.name != "Jacob Burnett")
    assert [f.name for f in filings if f.office == "Governor"][-1] == "Jacob Burnett" and by_name(filings, "Jacob Burnett").write_in
    assert not any("Judge" in f.office or "County" in f.office or f.party_name == "Non-Partisan" for f in filings)
    assert list(dict.fromkeys(f.group for f in filings)) == ["federal", "state", "legislature"]


def test_each_house_seat_is_a_race_of_its_own_after_its_districts_senator():
    filings = [f for f in id_filings() if f.district == "19" and f.group == "legislature"]
    assert [(f.office_id, f.office, f.name, f.party) for f in filings] == [
        ("STATE SENATE 19", "State Senator District 19", "Melissa Wintrow", "D"),
        ("STATE SENATE 19", "State Senator District 19", "Melissa J. Christian", "R"),
        ("STATE HOUSE 19 SEAT A", "State Representative District 19 Seat A", "Monica C. Church", "D"),
        ("STATE HOUSE 19 SEAT A", "State Representative District 19 Seat A", "Bryan Hopkins", "R"),
        ("STATE HOUSE 19 SEAT B", "State Representative District 19 Seat B", "Chris Mathias", "D"),
        ("STATE HOUSE 19 SEAT B", "State Representative District 19 Seat B", "Stanley Roach", "R")]
    assert {(f.reach, f.district) for f in filings} == {("sd", "19"), ("hd", "19")}


def test_an_idaho_list_it_cant_read_is_refused():
    with pytest.raises(ValueError, match="no Seat/Zone, Party Affiliation, Write-In, Withdrawal Date columns"):
        id_.parse_rows([["Ballot Name", "Election Date - Name", "District Type", "Office", "District"]])
    with pytest.raises(ValueError, match="not a general election's list: 'May 19, 2026 - 2026 Primary'"):
        id_.parse_rows(rows(row("Statewide", "Governor", "Jane Roe", election="May 19, 2026 - 2026 Primary")))
    with pytest.raises(ValueError, match="an office it doesn't know: Statewide, State Mine Inspector"):
        id_.parse_rows(rows(row("Statewide", "State Mine Inspector", "Jane Roe")))
    with pytest.raises(ValueError, match="an office it doesn't know: State Legislature, State Representative 4 C"):
        id_.parse_rows(rows(row("State Legislature", "State Representative", "Jane Roe", "4", "C")))
    with pytest.raises(ValueError, match="more than one election"):
        id_.parse_rows(rows(row("Statewide", "Governor", "Jane Roe", election="November 08, 2028 - 2028 General")))
    with pytest.raises(ValueError, match="34 State Senate races, not 35"):
        id_.parse_rows([r for r in rows() if r[0] != "Sen Roe35"])
    with pytest.raises(ValueError, match="no candidates"):
        id_.parse_rows([list(id_.COLUMNS)])
    with pytest.raises(ValueError, match="not a spreadsheet"):
        id_.IdList.parse("Ballot Name")


def test_a_primarys_list_is_refused_and_a_withdrawn_candidate_dropped():
    assert len(id_.parse_rows(rows())) == 72
    with pytest.raises(ValueError, match="two candidates of one party in STATE HOUSE 7 SEAT A: a primary's list"):
        id_.parse_rows(rows(row("State Legislature", "State Representative", "John Roe", "7", "A")))
    assert len(id_.parse_rows(rows(row("State Legislature", "State Representative", "John Roe", "7", "B")))) == 73
    withdrawn = id_.parse_rows(rows(row("State Legislature", "State Representative", "John Roe", "7", "A",
                                        withdrawn="08/28/2026")))
    assert "John Roe" not in {f.name for f in withdrawn}
    two_independents = rows(*(row("Federal", "United States Senator", n, label="Independent") for n in ("A Roe", "B Roe")))
    assert len(id_.parse_rows(two_independents)) == 74
    county = id_.parse_rows(rows(row("County", "County Commissioner", "Jane Roe", "Ada", "1"),
                                 row("Judicial", "District Judge", "Joe Roe", "4", "Ada A", "Non-Partisan")))
    assert len(county) == 72


def test_idahos_2026_dates_follow_its_election_law():
    found = state_key_dates.computed("ID", D(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        D(2026, 10, 23), D(2026, 10, 23), D(2026, 10, 13), D(2026, 10, 30))  # early voting opens after Columbus Day
    for day in (D(2026, 5, 19), D(2026, 12, 1), D(2027, 11, 2)):
        assert state_key_dates.computed("ID", day) is None, day
    info = state_key_dates.GUIDES["ID"].voter_info()
    assert info.poll_hours == "8 a.m. – 8 p.m. local time"
    assert info.late_registration and "on Election Day" in info.late_registration.label


def test_idahos_calendar_is_worked_out_without_asking_anyone(client, upstream):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "ID"})
    assert response.headers["content-disposition"] == 'attachment; filename="idaho-election-2026-11-03.ics"'
    unfolded = response.text.replace("\r\n ", "")
    assert "DTSTART;VALUE=DATE:20261013" in unfolded and "8 a.m. to 8 p.m. local time" in unfolded
    mail = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "ID", "event": "mail"}).text
    assert "SUMMARY:Absentee request due (Nov 3 election)" in mail and "DTSTART;VALUE=DATE:20261023" in mail
    assert upstream.count("voteidaho.gov") == 0


def test_the_import_bundles_the_parsed_candidates_never_the_spreadsheet(tmp_path):
    counts = imported(tmp_path)
    assert counts == {"races": len({f.office_id for f in id_filings()}), "candidates": len(id_filings())}
    [answer] = store.load("state_id", tmp_path / "bundles").answers
    assert answer["request"]["url"] == "manual:state_id" and set(answer["value"]) == {"filings"}
    assert "Mailing" not in str(answer) and "Election Date" not in str(answer)
    assert import_list("id", XLSX, data_dir=tmp_path / "bundles", today=lambda: TODAY).status == "no_changes"


def test_the_import_refuses_a_file_that_isnt_the_list(tmp_path):
    saved = tmp_path / "saved.xlsx"
    saved.write_bytes(b"<html><body>Just a moment...</body></html>")
    with pytest.raises(BundleError, match="isn't a list the Idaho Secretary of State's reader understands"):
        import_list("id", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert not (tmp_path / "bundles" / "state_id.json").exists()


def test_refreshing_the_bundles_never_fetches_idahos_list(tmp_path, upstream):
    outcome = build(tmp_path, "state_id")
    assert outcome.status == "skipped" and "imported by hand" in outcome.detail
    assert upstream.count("voteidaho.gov") == 0


def test_a_boise_ballot_comes_from_the_imported_list(tmp_path, upstream, make_app, logged_calls):
    imported(tmp_path)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "boise", all_races=True)
        assert ballot["coverage"]["ballot"] == "list"
        assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (2, 19, 19)
        names = [race["name"] for race in ballot["races"]]
        assert names == ["U.S. Senator", "U.S. Representative District 2", "Governor", "Lieutenant Governor",
                         "Secretary of State", "State Controller", "State Treasurer", "Attorney General",
                         "Superintendent of Public Instruction", "State Senator District 19",
                         "State Representative District 19 Seat A", "State Representative District 19 Seat B"]
        assert candidate_names(find_race(ballot, "State Representative District 19 Seat B")) == ["Chris Mathias",
                                                                                                 "Stanley Roach"]
        assert find_race(ballot, "U.S. Representative District 2")["seat"] == "ID-02"
        assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
        assert any("county and local races" in note for note in ballot["notes"])
        assert ballot["key_dates"] == {
            "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-23",
            "mail_apply_by": "2026-10-23", "early_voting_start": "2026-10-13", "early_voting_end": "2026-10-30",
            "source": "Idaho Secretary of State", "source_url": "https://voteidaho.gov/", "computed": True,
        }
        get_ballot(client, "boise", all_races=True)
        assert logged_calls() == 0
        rows = {row["id"]: row for row in client.get("/api/sources").json()["sources"]}
        assert rows["state_id"]["notice"].startswith("Imported by hand on ")
    assert upstream.count("voteidaho.gov") == 0


def test_without_an_imported_list_idaho_has_the_fecs_races_for_congress(client, upstream):
    ballot = get_ballot(client, "boise")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("doesn't have the Idaho Secretary of State's list of candidates" in n for n in ballot["notes"])
    assert upstream.count("voteidaho.gov") == 0
