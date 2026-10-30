"""Louisiana: the Secretary of State's candidate inquiry, a CSV saved by hand (tests/fixtures/state_la.csv:
Congress, the Legislature and a few of each kind of office left out), and its key dates, worked out
from Louisiana's election code."""

from __future__ import annotations

import datetime as dt
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from bundles import store
from bundles.entry import BundleError
from bundles.manual import import_list
from pallot.states import key_dates as state_key_dates
from pallot.states import la

from .bundling import build
from .conftest import FIXTURES, TODAY, candidate_names, find_race, get_ballot

D = dt.date
CSV = FIXTURES / "state_la.csv"
HEADER = ('"Election","OfficeTitle","OfficeTitleDescription","NumberToBeElected","BallotFirstName","BallotLastName",'
          '"BallotSuffix","Party","Outcome"')


def la_filings() -> list:
    return la.parse_rows(CSV.read_text(encoding="utf-8"))


def row(office: str, district: str, first: str, last: str, party: str = "Republican", outcome: str = "") -> str:
    return f'"11/03/2026","{office}","{district}","1","{first}","{last}","","{party}","{outcome}"'


def imported(tmp_path) -> dict:
    outcome = import_list("la", CSV, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert outcome.status == "updated"
    return outcome.counts


def test_louisianas_list_has_congress_and_the_legislatures_special_election():
    filings = la_filings()
    assert {f.day for f in filings} == {"2026-11-03"}
    assert Counter(f.reach for f in filings) == {"state": 2, "cd": 39, "hd": 3}
    assert [(f.name, f.party) for f in filings if f.office == "U.S. Senator"] == [("Jamie Davis", "D"), ("Julia Letlow", "R")]
    assert [f.district for f in filings if f.reach == "cd"] == sorted((f.district for f in filings if f.reach == "cd"), key=int)
    second = [(f.name, f.party) for f in filings if f.office == "U.S. Representative District 2"]
    assert second == [("Lisa Ballay", "L"), ('Walter "Rocky" Beach', None), ("Troy A. Carter Sr.", "D"),
                      ('Renada "Honey" Collins', None), ("Peter Williams", "R")]
    house = [f for f in filings if f.reach == "hd"]
    assert {(f.office, f.office_id, f.district, f.unexpired) for f in house} == {
        ("State Representative District 92", "STATE HOUSE 92 UNEXPIRED", "92", True)}
    assert [f.name for f in house] == ["Gregory Carroll", "Alex Perdomo", 'Michael "Mike" Sigur']
    assert not any(f.group == "judicial" or f.name in ("Connie Norris", "Angela Hershey", "Alan Seabaugh") for f in filings)


def test_two_candidates_of_one_party_in_an_open_primary_are_usual():
    fifth = Counter(f.party for f in la_filings() if f.district == "5" and f.reach == "cd")
    assert fifth == {"R": 6, "D": 3}


def test_nicknames_and_suffixes_are_kept_as_the_ballot_prints_them():
    names = {f.name for f in la_filings()}
    for name in ("Jamie Davis", "Mike Johnson", "Clay Higgins", 'E. "Liddy" Glass', 'Caleb "With a C" Walker',
                 "Larry Davis III", "Stewart Cathey Jr."):
        assert name in names, name
    assert not any("'" in name for name in names)


def test_unopposed_withdrawn_and_disqualified_candidates_arent_on_the_ballot():
    text = "\n".join([HEADER, *(row("U. S. Representative", f"{n}th Congressional District", "Jane", f"Doe{n}")
                                for n in range(1, 7)),
                      row("State Representative", "92nd Representative District", "John", "Smith", outcome="Unopposed"),
                      row("U. S. Representative", "4th Congressional District", "Sam", "Gone", outcome="Withdrew"),
                      row("U. S. Representative", "4th Congressional District", "Sal", "Out", outcome="Other/Disq")])
    assert [f.name for f in la.parse_rows(text)] == [f"Jane Doe{n}" for n in range(1, 7)]


def test_a_louisiana_list_it_cant_read_is_refused():
    six = [row("U. S. Representative", f"{n}th Congressional District", "Jane", f"Doe{n}") for n in range(1, 7)]
    with pytest.raises(ValueError, match="no NumberToBeElected, BallotFirstName"):
        la.parse_rows('"Election","OfficeTitle","OfficeTitleDescription"\n"11/03/2026","Mayor",""')
    with pytest.raises(ValueError, match="an office it doesn't know: Coroner"):
        la.parse_rows("\n".join([HEADER, *six, row("Coroner", "Parish of Orleans", "Jane", "Doe")]))
    with pytest.raises(ValueError, match="an outcome it doesn't know: Elected"):
        la.parse_rows("\n".join([HEADER, *six, row("U. S. Senator", "", "Jane", "Doe", outcome="Elected")]))
    with pytest.raises(ValueError, match="two U.S. Senate candidates of one party"):
        la.parse_rows("\n".join([HEADER, *six, row("U. S. Senator", "", "Jane", "Doe"), row("U. S. Senator", "", "Jo", "Roe")]))
    with pytest.raises(ValueError, match="0 U.S. House races, not 6"):
        la.parse_rows("\n".join([HEADER, row("U. S. Senator", "", "Jane", "Doe")]))
    with pytest.raises(ValueError, match="no candidates"):
        la.parse_rows(HEADER)
    with pytest.raises(ValueError, match="not a CSV"):
        la.LaList.parse(b"Election")


def test_louisianas_2026_dates_follow_its_election_code():
    found = state_key_dates.computed("LA", D(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        D(2026, 10, 13), D(2026, 10, 30), D(2026, 10, 20), D(2026, 10, 27))
    for day in (D(2026, 5, 16), D(2026, 12, 12)):
        assert state_key_dates.computed("LA", day) is None, day


def test_louisianas_calendar_is_worked_out_without_asking_anyone(client, upstream):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "LA"})
    assert response.headers["content-disposition"] == 'attachment; filename="louisiana-election-2026-11-03.ics"'
    unfolded = response.text.replace("\r\n ", "")
    assert "DTSTART;VALUE=DATE:20261020" in unfolded and "6 a.m. to 8 p.m." in unfolded
    mail = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "LA", "event": "mail"}).text
    assert "SUMMARY:Mail ballot request due (Nov 3 election)" in mail and "DTSTART;VALUE=DATE:20261030" in mail
    assert upstream.count("sos.la.gov") == 0


def test_the_import_bundles_the_parsed_candidates_never_the_csv(tmp_path):
    counts = imported(tmp_path)
    assert counts == {"races": len({f.office_id for f in la_filings()}), "candidates": len(la_filings())}
    [answer] = store.load("state_la", tmp_path / "bundles").answers
    assert answer["request"]["url"] == "manual:state_la" and set(answer["value"]) == {"filings"}
    assert "Unopposed" not in str(answer) and "'Jamie'" not in str(answer) and "Seabaugh" not in str(answer)
    assert import_list("la", CSV, data_dir=tmp_path / "bundles", today=lambda: TODAY).status == "no_changes"


def test_the_import_refuses_a_file_that_isnt_the_list(tmp_path):
    saved = tmp_path / "saved.csv"
    saved.write_text("<html><body>Candidate Inquiry</body></html>", encoding="utf-8")
    with pytest.raises(BundleError, match="isn't a list the Louisiana Secretary of State's reader understands"):
        import_list("la", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert not (tmp_path / "bundles" / "state_la.json").exists()


def test_refreshing_the_bundles_never_fetches_louisianas_list(tmp_path, upstream):
    outcome = build(tmp_path, "state_la")
    assert outcome.status == "skipped" and "imported by hand" in outcome.detail
    assert upstream.count("sos.la.gov") == 0


def test_a_baton_rouge_ballot_comes_from_the_imported_list(tmp_path, upstream, make_app, logged_calls):
    imported(tmp_path)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "batonrouge", all_races=True)
        assert ballot["coverage"]["ballot"] == "list"
        assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (2, 14, 67)
        assert [race["name"] for race in ballot["races"]] == ["U.S. Senator", "U.S. Representative District 2"]
        house = find_race(ballot, "U.S. Representative District 2")
        assert house["seat"] == "LA-02" and candidate_names(house)[0] == "Lisa Ballay"
        assert house["election_name"] == "Open Primary"
        assert [note["text"] for note in house["notes"]] == [la.OPEN_PRIMARY[1]]
        senate = find_race(ballot, "U.S. Senator")
        assert senate["election_name"] is None and not any(note["source"] == la.LaList.label for note in senate["notes"])
        assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
        assert any("Public Service Commission" in note for note in ballot["notes"])
        assert ballot["key_dates"] == {
            "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-13",
            "mail_apply_by": "2026-10-30", "early_voting_start": "2026-10-20", "early_voting_end": "2026-10-27",
            "source": "Louisiana Secretary of State", "source_url": "https://www.sos.la.gov/elections-voting",
            "computed": True,
        }
        get_ballot(client, "batonrouge", all_races=True)
        assert logged_calls() == 0
        rows = {row["id"]: row for row in client.get("/api/sources").json()["sources"]}
        assert rows["state_la"]["notice"].startswith("Imported by hand on ")
    assert upstream.count("sos.la.gov") == 0


def test_without_an_imported_list_louisiana_has_the_fecs_races_for_congress(client, upstream):
    ballot = get_ballot(client, "batonrouge")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("doesn't have the Louisiana Secretary of State's list of candidates" in n for n in ballot["notes"])
    assert upstream.count("sos.la.gov") == 0
