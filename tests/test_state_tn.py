"""Tennessee: the Secretary of State's five candidate spreadsheets, saved by hand into one folder
(tests/fixtures/state_tn: their office, name and party columns, Governor and Congress whole and a
few districts of the Legislature), and its key dates, worked out from Tennessee's election law."""

from __future__ import annotations

import datetime as dt
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from bundles import store
from bundles.entry import BundleError
from bundles.manual import import_list
from pallot.states import tn
from pallot.states import key_dates as state_key_dates

from .bundling import build
from .conftest import FIXTURES, TODAY, candidate_names, find_race, get_ballot

D = dt.date
FOLDER = FIXTURES / "state_tn"


def books() -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in FOLDER.iterdir()}


def tn_filings() -> list:
    return tn.parse_books(books())


def imported(tmp_path) -> dict:
    outcome = import_list("tn", FOLDER, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert outcome.status == "updated"
    return outcome.counts


def test_tennessees_lists_have_governor_congress_and_its_legislature():
    filings = tn_filings()
    assert {f.day for f in filings} == {"2026-11-03"}
    assert Counter(f.reach for f in filings) == {"state": 25, "cd": 46, "sd": 3, "hd": 1}
    order = list(dict.fromkeys(f.office for f in filings))
    assert order == ["Governor", "U.S. Senator", *(f"U.S. Representative District {n}" for n in range(1, 10)),
                     "State Senator District 29", "State Senator District 31", "State Representative District 86"]
    assert [(f.name, f.party) for f in filings if f.office == "Governor"][:3] == [
        ("Marsha Blackburn", "R"), ("Jerri Green", "D"), ("Misam Abidi", None)]
    hagerty = next(f for f in filings if f.name == "Bill Hagerty")
    assert (hagerty.office, hagerty.reach, hagerty.group) == ("U.S. Senator", "state", "federal")
    pearson = [(f.office, f.reach, f.district) for f in filings if f.name == "Justin J. Pearson"]
    assert pearson == [("U.S. Representative District 9", "cd", "9"), ("State Representative District 86", "hd", "86")]
    assert next(f for f in filings if f.name == "Dennis Clark").party_name == "Independent"
    assert not any("Qualified" in f.name or f.district == "93" for f in filings)


def test_a_tennessee_folder_it_cant_read_is_refused():
    found = books()
    with pytest.raises(ValueError, match="no Tennessee|no State House list"):
        tn.parse_books({name: raw for name, raw in found.items() if not name.startswith("TNHouse")})
    with pytest.raises(ValueError, match="not one November's lists"):
        tn.parse_books({**found, "Governor_Nov2024.xlsx": found["Governor_Nov2026.xlsx"]})
    with pytest.raises(ValueError, match="two candidates of one party in GOVERNOR"):
        tn.parse_books({**found, "Governor2_Nov2026.xlsx": found["Governor_Nov2026.xlsx"]})
    with pytest.raises(ValueError, match="not a folder"):
        tn.TnList.parse(b"Office")


def test_tennessees_2026_dates_follow_its_election_law():
    found = state_key_dates.computed("TN", D(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        D(2026, 10, 5), D(2026, 10, 24), D(2026, 10, 14), D(2026, 10, 29))
    assert state_key_dates.GUIDES["TN"].voter_info().poll_hours == "until 7 p.m. Central, 8 p.m. Eastern"


def test_tennessees_calendar_is_worked_out_without_asking_anyone(client, upstream):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "TN"})
    assert response.headers["content-disposition"] == 'attachment; filename="tennessee-election-2026-11-03.ics"'
    unfolded = response.text.replace("\r\n ", "")
    assert "DTSTART;VALUE=DATE:20261014" in unfolded and "Polls close at 7 p.m. Central time\\, 8 p.m. Eastern time" in unfolded
    mail = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "TN", "event": "mail"}).text
    assert "SUMMARY:Absentee application due (Nov 3 election)" in mail and "DTSTART;VALUE=DATE:20261024" in mail
    assert upstream.count("tn.gov") == 0


def test_the_import_bundles_the_parsed_candidates_never_the_spreadsheets(tmp_path):
    counts = imported(tmp_path)
    assert counts == {"races": len({f.office_id for f in tn_filings()}), "candidates": len(tn_filings())}
    [answer] = store.load("state_tn", tmp_path / "bundles").answers
    assert answer["request"]["url"] == "manual:state_tn" and set(answer["value"]) == {"filings"}
    assert "Brentwood" not in str(answer) and "Party Name" not in str(answer)
    assert import_list("tn", FOLDER, data_dir=tmp_path / "bundles", today=lambda: TODAY).status == "no_changes"


def test_the_import_refuses_a_file_for_a_folder(tmp_path):
    with pytest.raises(BundleError, match="isn't a folder"):
        import_list("tn", FOLDER / "Governor_Nov2026.xlsx", data_dir=tmp_path / "bundles", today=lambda: TODAY)
    with pytest.raises(BundleError, match="isn't a file"):
        import_list("ar", FOLDER, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert not (tmp_path / "bundles" / "state_tn.json").exists()


def test_refreshing_the_bundles_never_fetches_tennessees_list(tmp_path, upstream):
    outcome = build(tmp_path, "state_tn")
    assert outcome.status == "skipped" and "imported by hand" in outcome.detail
    assert upstream.count("tn.gov") == 0


def test_a_memphis_ballot_comes_from_the_imported_list(tmp_path, upstream, make_app, logged_calls):
    imported(tmp_path)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "memphis", all_races=True)
        assert ballot["coverage"]["ballot"] == "list"
        assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (5, 29, 86)
        names = [race["name"] for race in ballot["races"]]
        assert names == ["U.S. Senator", "U.S. Representative District 5", "Governor", "State Senator District 29",
                         "State Representative District 86"]
        assert candidate_names(find_race(ballot, "State Senator District 29")) == ["Raumesh Akbari"]
        assert find_race(ballot, "U.S. Representative District 5")["seat"] == "TN-05"
        assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
        assert any("county election commission" in note for note in ballot["notes"])
        assert ballot["key_dates"] == {
            "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-05",
            "mail_apply_by": "2026-10-24", "early_voting_start": "2026-10-14", "early_voting_end": "2026-10-29",
            "source": "Tennessee Secretary of State", "source_url": "https://sos.tn.gov/elections",
            "computed": True,
        }
        get_ballot(client, "memphis", all_races=True)
        assert logged_calls() == 0
        rows = {row["id"]: row for row in client.get("/api/sources").json()["sources"]}
        assert rows["state_tn"]["notice"].startswith("Imported by hand on ")
    assert upstream.count("tn.gov") == 0


def test_without_an_imported_list_tennessee_has_the_fecs_races_for_congress(client, upstream):
    ballot = get_ballot(client, "memphis")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("doesn't have the Tennessee Secretary of State's list of candidates" in n for n in ballot["notes"])
    assert upstream.count("tn.gov") == 0
