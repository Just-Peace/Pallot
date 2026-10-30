"""Utah: the Lieutenant Governor's General Election Certification, a scanned PDF whose text is saved
by hand (tests/fixtures/state_ut.txt: its text up to the constitutional amendments, misreadings
and all), and its key dates, worked out from the Utah Code."""

from __future__ import annotations

import datetime as dt
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from bundles import store
from bundles.entry import BundleError
from bundles.manual import import_list
from pallot.states import key_dates as state_key_dates
from pallot.states import ut

from .bundling import build
from .conftest import FIXTURES, TODAY, candidate_names, find_race, get_ballot, load

D = dt.date
TEXT = FIXTURES / "state_ut.txt"
TITLE = "***AMENDED*** 2026 GENERAL ELECTION CERTIFICATION"


def ut_filings() -> list:
    return ut.UtList.parse(TEXT.read_text(encoding="utf-8"))


def race(heading: str, *lines: str) -> list[str]:
    return [f"{heading}. {heading} consists of a portion of Salt Lake County.", "Candidate Party", *lines]


def certification(*extra: str) -> str:
    """A title, a candidate in every U.S. House and State House district, then ``extra``."""
    lines = [TITLE, "FEDERAL OFFICE"]
    for n in range(1, 5):
        lines += race(f"U.S. House of Representatives District {n}", f"JANE DOE{n} Democratic")
    lines.append("STATE REPRESENTATIVE")
    for n in range(1, 76):
        lines += race(f"Utah House of Representatives District {n}", f"REP ROE{n} Republican")
    return "\n".join([*lines, *extra])


def imported(tmp_path) -> dict:
    outcome = import_list("ut", TEXT, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert outcome.status == "updated"
    return outcome.counts


def test_utahs_certification_has_congress_the_legislature_and_the_judges():
    filings = ut_filings()
    assert {f.day for f in filings} == {"2026-11-03"}
    assert Counter(f.reach for f in filings) == {"hd": 155, "sd": 35, "counties": 25, "cd": 19, "state": 7}
    assert len({f.district for f in filings if f.reach == "hd"}) == 75
    assert len({f.district for f in filings if f.reach == "sd"}) == 15
    assert [(f.name, f.party, f.party_name) for f in filings if f.office == "U.S. Representative District 2"] == [
        ("Peter Crosby", "D", None), ("Daniel Cottam", "L", None), ("Robert M. Moesinger", None, None),
        ("Blake D. Moore", "R", None), ("Carlton E. Bowen", None, "Independent American Party")]
    assert not any(f.office.startswith(("State Board", "Board of Education")) or "Justice Court" in f.office
                   for f in filings)


def test_the_scans_misreadings_are_put_right():
    names = {f.name for f in ut_filings()}
    assert {"Chris Reid", "Barbara J. Haggerty", "Scott H Chew", "Glenn D Webb", "Jess Birtcher", "Adonis Hooslyn",
            "Richard S Robillard", "Karli Black", '"CJ" Christina Hernandez'} <= names
    assert not {"Chrjs Reid", "Scotthchew", "Karl! Black"} & names


def test_judges_stand_for_retention_statewide_or_in_their_districts_counties():
    filings = ut_filings()
    [pohlman] = [f for f in filings if f.name == "Jill M. Pohlman"]
    assert (pohlman.office, pohlman.reach, pohlman.retention, pohlman.incumbent, pohlman.party) == (
        "Retain Supreme Court Justice Jill M. Pohlman", "state", True, True, None)
    [nelson] = [f for f in filings if f.name == "Jason Craig Nelson"]
    assert (nelson.office, nelson.reach, nelson.counties) == (
        "Retain Second District Court Judge Jason Craig Nelson", "counties", ("DAVIS", "MORGAN", "WEBER"))
    [morgan] = [f for f in filings if f.name == "Kirk Max Morgan"]
    assert morgan.office == "Retain First District Juvenile Court Judge Kirk Max Morgan"
    assert not any(f.name in ("Lisa A. Garner", "Clay W. Stucki") for f in filings)  # justice courts


def test_a_utah_certification_it_cant_read_is_refused():
    with pytest.raises(ValueError, match="no year in its title"):
        ut.candidates(certification().replace(TITLE, "CERTIFICATION"))
    with pytest.raises(ValueError, match="a line it can't read: 'JO ROE Democratlc'"):
        ut.candidates(certification(*race("Utah Senate District 9", "JO ROE Democratlc")))
    with pytest.raises(ValueError, match="two candidates of one party in STATE SENATE 9: a primary's list"):
        ut.candidates(certification(*race("Utah Senate District 9", "JO ROE Democratic", "SAM POE Democratic")))
    with pytest.raises(ValueError, match="an office it doesn't know"):
        ut.candidates(certification("NON-PARTISAN JUDICIAL RETENTION ELECTIONS",
                                    "First Judicial District. The First Judicial District consists of Cache County.",
                                    "Shall JO ROE be retained in the office of Clerk of the First Circuit?"))
    with pytest.raises(ValueError, match="0 U.S. House races, not 4"):
        ut.candidates("\n".join([TITLE, "STATE SENATOR", *race("Utah Senate District 9", "JO ROE Democratic")]))
    with pytest.raises(ValueError, match="no candidates"):
        ut.candidates(TITLE)
    with pytest.raises(ValueError, match="not a text file"):
        ut.UtList.parse(b"%PDF-1.7")


def test_two_unaffiliated_candidates_in_one_race_are_no_primarys_list():
    filings = ut.candidates(certification(*race("Utah Senate District 9", "JO ROE Unaffiliated", "SAM POE Unaffiliated")))
    assert [f.name for f in filings if f.office == "State Senator District 9"] == ["Jo Roe", "Sam Poe"]


def test_utahs_2026_dates_follow_the_utah_code():
    found = state_key_dates.computed("UT", D(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        D(2026, 10, 23), None, D(2026, 10, 20), D(2026, 10, 30))
    for day in (D(2026, 6, 23), D(2027, 11, 2)):
        assert state_key_dates.computed("UT", day) is None, day


def test_utahs_calendar_file_says_every_voter_is_mailed_a_ballot(client, upstream):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "UT"})
    assert response.headers["content-disposition"] == 'attachment; filename="utah-election-2026-11-03.ics"'
    text = response.text.replace("\r\n ", "")
    assert all(day in text for day in ("20261023", "20261020", "20261103"))
    info = state_key_dates.GUIDES["UT"].voter_info()
    assert info.poll_hours == "7 a.m. – 8 p.m." and info.late_registration
    assert info.mail_eligibility.startswith("Every active voter is mailed a ballot. It goes out 7 to 21 days before")
    assert upstream.count("vote.utah.gov") == 0


def test_the_import_bundles_the_parsed_candidates_never_the_text(tmp_path):
    counts = imported(tmp_path)
    assert counts == {"races": len({f.office_id for f in ut_filings()}), "candidates": len(ut_filings())}
    [answer] = store.load("state_ut", tmp_path / "bundles").answers
    assert answer["request"]["url"] == "manual:state_ut" and set(answer["value"]) == {"filings"}
    assert "consists of" not in str(answer) and "CHRJS" not in str(answer)
    assert import_list("ut", TEXT, data_dir=tmp_path / "bundles", today=lambda: TODAY).status == "no_changes"


def test_the_import_refuses_a_file_that_isnt_the_list(tmp_path):
    saved = tmp_path / "saved.txt"
    saved.write_text("<html><body>vote.utah.gov</body></html>", encoding="utf-8")
    with pytest.raises(BundleError, match="isn't a list the Utah Lieutenant Governor's Office's reader understands"):
        import_list("ut", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert not (tmp_path / "bundles" / "state_ut.json").exists()


def test_refreshing_the_bundles_never_fetches_utahs_list(tmp_path, upstream):
    outcome = build(tmp_path, "state_ut")
    assert outcome.status == "skipped" and "imported by hand" in outcome.detail
    assert upstream.count("vote.utah.gov") == 0


def test_a_salt_lake_city_ballot_comes_from_the_imported_list(tmp_path, upstream, make_app, logged_calls):
    census = load("census_saltlakecity.json")["result"]["addressMatches"][0]["geographies"]
    assert census["120th Congressional Districts"][0]["BASENAME"] == "1"  # Map 1A, the court's map of 2026
    imported(tmp_path)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "saltlakecity", all_races=True)
        assert ballot["coverage"]["ballot"] == "list"
        assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (1, 9, 22)
        names = [race["name"] for race in ballot["races"]]
        assert names[:3] == ["U.S. Representative District 1", "State Senator District 9",
                             "State Representative District 22"]
        assert len(names) == 3 + 7 + 7  # the Supreme Court and Court of Appeals, and the Third District's judges
        assert "Retain Third District Court Judge Coral Sanchez" in names
        house = find_race(ballot, "U.S. Representative District 1")
        assert house["seat"] == "UT-01" and candidate_names(house) == [
            "Jesse West", "Ben McAdams", "Elias Henry Montgomery", "Riley Owen"]
        assert candidate_names(find_race(ballot, "State Representative District 22")) == ["Jen Dailey-Provost",
                                                                                          "Char Varga"]
        assert find_race(ballot, "Retain Supreme Court Justice Jill M. Pohlman")["retention"]
        assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
        assert any("State Board of Education" in note for note in ballot["notes"])
        assert ballot["key_dates"] == {
            "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-23",
            "mail_apply_by": None, "early_voting_start": "2026-10-20", "early_voting_end": "2026-10-30",
            "source": "Utah Lieutenant Governor's Office", "source_url": ut.SITE, "computed": True,
        }
        get_ballot(client, "saltlakecity", all_races=True)
        assert logged_calls() == 0
        sources = {source["id"]: source for source in client.get("/api/sources").json()["sources"]}
        assert sources["state_ut"]["notice"].startswith("Imported by hand on ")
    assert upstream.count("vote.utah.gov") == 0
