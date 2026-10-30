"""West Virginia: the Secretary of State's candidate listing, a CSV saved by hand (tests/fixtures/state_wv.csv:
Congress, a few districts' whole races and every other district's first row), and its key dates, worked
out from West Virginia's election law."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from bundles import store
from bundles.entry import BundleError
from bundles.manual import import_list
from pallot.states import key_dates as state_key_dates
from pallot.states import wv

from .bundling import build
from .conftest import FIXTURES, TODAY, candidate_names, find_race, get_ballot

D = dt.date
CSV = FIXTURES / "state_wv.csv"
HEADER = '"Name","Party","Race","Filing Date"'


def wv_filings() -> list:
    return wv.parse_rows(CSV.read_text(encoding="utf-8"))


def by_name(filings: list, name: str):
    return next(f for f in filings if f.name == name)


def imported(tmp_path) -> dict:
    outcome = import_list("wv", CSV, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert outcome.status == "updated"
    return outcome.counts


def districts(races: int, office: str, start: int = 1) -> str:
    """One Republican's row for each of ``races`` districts of ``office``, to pass MINIMUM."""
    return "\n".join(f'"JANE DOE {n}","REPUBLICAN","{office} - DISTRICT {n}","01/12/2026"' for n in range(start, races + 1))


def test_west_virginias_list_has_congress_and_its_legislature():
    filings = wv_filings()
    assert {f.day for f in filings} == {"2026-11-03"}
    assert {f.reach for f in filings} == {"state", "cd", "sd", "hd"}
    assert len({f.district for f in filings if f.reach == "hd"}) == 100
    assert len({f.district for f in filings if f.reach == "sd" and not f.unexpired}) == 17
    assert [(f.name, f.party, f.party_name) for f in filings if f.office == "U.S. Senator"] == [
        ("Rachel Fetty Anderson", "D", None), ("Shelley Moore Capito", "R", None), ("S. Marshall Wilson", None, "Constitution")]
    miller = by_name(filings, "Carol Miller")
    assert (miller.office, miller.reach, miller.district, miller.group) == ("U.S. Representative District 1", "cd", "1",
                                                                          "federal")
    pushkin = by_name(filings, "Mike Pushkin")
    assert (pushkin.office, pushkin.reach, pushkin.district) == ("House of Delegates District 54", "hd", "54")
    wheeler = by_name(filings, "Lance Wheeler")
    assert (wheeler.office, wheeler.reach, wheeler.district, wheeler.group) == ("State Senator District 8", "sd", "8",
                                                                              "legislature")
    assert by_name(filings, "Paige Reiring").party_name == "Mountain"
    assert (by_name(filings, "Tara Martinez").party, by_name(filings, "Tara Martinez").party_name) == (None, "Independent")
    assert by_name(filings, "Joshua Lee Haskiell").party_name is None
    assert not any("Judge" in f.office or f.name in ("Kris Raynes", "Eleni Kontos-Miller") for f in filings)
    order = list(dict.fromkeys(f.reach for f in filings))
    assert order == ["state", "cd", "sd", "hd"]


def test_names_in_capitals_are_put_in_mixed_case():
    names = {f.name for f in wv_filings()}
    for name in ("Shelley Moore Capito", "Belinda Fox-Spencer", "D.R. Buck Jennings", "Colin Savage"):
        assert name in names, name


def test_the_senates_unexpired_terms_are_races_of_their_own():
    filings = [f for f in wv_filings() if f.reach == "sd" and f.district in ("3", "17")]
    assert [(f.office_id, f.name, f.unexpired) for f in filings if f.unexpired] == [
        ("STATE SENATE 3 UNEXPIRED", "Trenton Carl Barnhart", True),
        ("STATE SENATE 3 UNEXPIRED", "Ronnie Green", True),
        ("STATE SENATE 17 UNEXPIRED", "Richie Robb", True),
        ("STATE SENATE 17 UNEXPIRED", "Anne B. Charnock", True)]
    assert [f.name for f in filings if f.district == "3" and not f.unexpired] == ["Caci Petrehn", "Mike Azinger"]


def test_a_west_virginia_list_it_cant_read_is_refused():
    with pytest.raises(ValueError, match="no Race, Filing Date columns"):
        wv.parse_rows('"Name","Party"\n"JANE DOE","REPUBLICAN"')
    with pytest.raises(ValueError, match="an office it doesn't know: MAYOR"):
        wv.parse_rows(f'{HEADER}\n"JANE DOE","REPUBLICAN","MAYOR","01/12/2026"')
    with pytest.raises(ValueError, match="a filing date it can't read"):
        wv.parse_rows(f'{HEADER}\n"JANE DOE","REPUBLICAN","U.S. SENATE","2026-01-12"')
    with pytest.raises(ValueError, match="0 U.S. House races, not 2"):
        wv.parse_rows(f'{HEADER}\n"JANE DOE","REPUBLICAN","U.S. SENATE","01/12/2026"')
    with pytest.raises(ValueError, match="no candidates"):
        wv.parse_rows(HEADER)
    with pytest.raises(ValueError, match="not a CSV"):
        wv.WvList.parse(b"Name")


def test_a_primarys_list_is_refused():
    rows = "\n".join((HEADER, districts(2, "U.S. HOUSE OF REPRESENTATIVES"), districts(17, "STATE SENATE"),
                      districts(100, "HOUSE OF DELEGATES")))
    assert len(wv.parse_rows(rows)) == 119
    with pytest.raises(ValueError, match="two candidates of one party in STATE HOUSE 7: a primary's list"):
        wv.parse_rows(f'{rows}\n"JOHN ROE","REPUBLICAN","HOUSE OF DELEGATES - DISTRICT 7","01/13/2026"')
    two_independents = f'{rows}\n' + "\n".join(f'"{n}","INDEPENDENT","HOUSE OF DELEGATES - DISTRICT 7","07/30/2026"'
                                               for n in ("JOHN ROE", "RICHARD ROE"))
    assert len(wv.parse_rows(two_independents)) == 121


def test_west_virginias_2026_dates_follow_its_election_law():
    found = state_key_dates.computed("WV", D(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        D(2026, 10, 13), D(2026, 10, 28), D(2026, 10, 21), D(2026, 10, 31))
    for day in (D(2026, 5, 12), D(2026, 12, 1)):
        assert state_key_dates.computed("WV", day) is None, day


def test_west_virginias_calendar_is_worked_out_without_asking_anyone(client, upstream):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "WV"})
    assert response.headers["content-disposition"] == 'attachment; filename="west-virginia-election-2026-11-03.ics"'
    unfolded = response.text.replace("\r\n ", "")
    assert "DTSTART;VALUE=DATE:20261021" in unfolded and "6:30 a.m. to 7:30 p.m." in unfolded
    mail = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "WV", "event": "mail"}).text
    assert "SUMMARY:Absentee application due (Nov 3 election)" in mail and "DTSTART;VALUE=DATE:20261028" in mail
    assert upstream.count("wvsos.gov") == 0 and upstream.count("sos.wv.gov") == 0


def test_the_import_bundles_the_parsed_candidates_never_the_csv(tmp_path):
    counts = imported(tmp_path)
    assert counts == {"races": len({f.office_id for f in wv_filings()}), "candidates": len(wv_filings())}
    [answer] = store.load("state_wv", tmp_path / "bundles").answers
    assert answer["request"]["url"] == "manual:state_wv" and set(answer["value"]) == {"filings"}
    assert "Filing Date" not in str(answer) and "01/20/2026" not in str(answer) and "SHELLEY" not in str(answer)
    assert import_list("wv", CSV, data_dir=tmp_path / "bundles", today=lambda: TODAY).status == "no_changes"


def test_the_import_refuses_a_file_that_isnt_the_list(tmp_path):
    saved = tmp_path / "saved.csv"
    saved.write_text("<html><body>403 Forbidden</body></html>", encoding="utf-8")
    with pytest.raises(BundleError, match="isn't a list the West Virginia Secretary of State's reader understands"):
        import_list("wv", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert not (tmp_path / "bundles" / "state_wv.json").exists()


def test_refreshing_the_bundles_never_fetches_west_virginias_list(tmp_path, upstream):
    outcome = build(tmp_path, "state_wv")
    assert outcome.status == "skipped" and "imported by hand" in outcome.detail
    assert upstream.count("wvsos.gov") == 0


def test_a_charleston_ballot_comes_from_the_imported_list(tmp_path, upstream, make_app, logged_calls):
    imported(tmp_path)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "charleston", all_races=True)
        assert ballot["coverage"]["ballot"] == "list"
        assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (1, 8, 54)
        names = [race["name"] for race in ballot["races"]]
        assert names == ["U.S. Senator", "U.S. Representative District 1", "State Senator District 8",
                         "House of Delegates District 54"]
        assert candidate_names(find_race(ballot, "House of Delegates District 54")) == ["Mike Pushkin", "Tara Martinez"]
        assert find_race(ballot, "U.S. Representative District 1")["seat"] == "WV-01"
        assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
        assert any("circuit and family court judges" in note for note in ballot["notes"])
        assert ballot["key_dates"] == {
            "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-13",
            "mail_apply_by": "2026-10-28", "early_voting_start": "2026-10-21", "early_voting_end": "2026-10-31",
            "source": "West Virginia Secretary of State", "source_url": "https://sos.wv.gov/elections",
            "computed": True,
        }
        get_ballot(client, "charleston", all_races=True)
        assert logged_calls() == 0
        rows = {row["id"]: row for row in client.get("/api/sources").json()["sources"]}
        assert rows["state_wv"]["notice"].startswith("Imported by hand on ")
    assert upstream.count("wvsos.gov") == 0


def test_without_an_imported_list_west_virginia_has_the_fecs_races_for_congress(client, upstream):
    ballot = get_ballot(client, "charleston")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("doesn't have the West Virginia Secretary of State's list of candidates" in n for n in ballot["notes"])
    assert upstream.count("wvsos.gov") == 0
