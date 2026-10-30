"""Oregon: ORESTAR's candidate export for the general election, a spreadsheet saved by hand
(tests/fixtures/state_or.xlsx: Governor, Congress, Salem's districts, a few more, the first row of
every other House district and a row of each kind left out), and its key dates, worked out from the
ORS."""

from __future__ import annotations

import datetime as dt
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from bundles import store
from bundles.entry import BundleError
from bundles.manual import import_list
from pallot.states import key_dates as state_key_dates
from pallot.states import or_, ordinal

from .bundling import build
from .conftest import FIXTURES, TODAY, candidate_names, find_race, get_ballot

D = dt.date
XLSX = FIXTURES / "state_or.xlsx"


def or_filings() -> list:
    return or_.OrList.parse(XLSX.read_bytes())


def row(group: str, office: str, name: str, label: str = "Democrat", order: str = "1",
        election: str = "2026 General Election", qualified: str = "Y", withdrawn: str = "") -> list[str]:
    return [election, group, office, "Nominated", label, name, order, qualified, withdrawn]


def rows(*extra: list[str]) -> list[list[str]]:
    """The export's header, a candidate in every U.S. House and State House district, then ``extra``."""
    return [list(or_.COLUMNS),
            *(row("US Representative", f"{ordinal(n)} District", f"Jane Doe{n}") for n in range(1, 7)),
            *(row("State Representative", f"{ordinal(n)} District", f"Rep Roe{n}") for n in range(1, 61)), *extra]


def imported(tmp_path) -> dict:
    outcome = import_list("or", XLSX, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert outcome.status == "updated"
    return outcome.counts


def test_oregons_list_has_governor_congress_and_the_legislature():
    filings = or_filings()
    assert {f.day for f in filings} == {"2026-11-03"}
    assert {f.reach for f in filings} == {"state", "cd", "sd", "hd"}
    assert len({f.district for f in filings if f.reach == "hd"}) == 60
    assert [(f.name, f.party, f.party_name) for f in filings if f.office == "Governor"] == [
        ("Brett Smith", None, "Pacific Green"), ("Tina Kotek", "D", "Democrat / Working Families"),
        ("Christine Drazan", "R", "Republican / Libertarian")]
    assert [f.office for f in filings][:4] == ["U.S. Senator"] * 4
    assert not any(f.group == "judicial" or "Attorney" in f.office for f in filings)


def test_a_candidate_several_parties_nominated_is_on_the_ballot_once_with_each():
    filings = or_filings()
    senate = [(f.name, f.party, f.party_name) for f in filings if f.office == "U.S. Senator"]
    assert senate == [("David Brock Smith", "R", None), ("Jeff Merkley", "D", "Democrat / Working Families"),
                      ("Gary Lyndon Dye", "L", None), ("Chris Henry", None, "Progressive / Pacific Green")]
    [gomberg] = [f for f in filings if f.name == "David Gomberg"]
    assert (gomberg.office, gomberg.party, gomberg.party_name) == (
        "State Representative District 10", "D", "Democrat / Republican / Independent")
    assert Counter(f.name for f in filings).most_common(1)[0][1] == 1


def test_withdrawn_and_unqualified_filings_arent_on_the_ballot():
    filings = or_.parse_rows(rows(row("US Senator", "statewide", "Sam Gone", withdrawn="09/01/2026"),
                                  row("US Senator", "statewide", "Sal Out", label="Republican", qualified="N"),
                                  row("Judge of the Circuit Court", "4th District, Position 2", "Jo Bench",
                                      label="Nonpartisan")))
    assert not any(f.reach == "state" or f.name in ("Sam Gone", "Sal Out", "Jo Bench") for f in filings)


def test_an_oregon_list_it_cant_read_is_refused():
    with pytest.raises(ValueError, match="no Qlf Ind, Witdrw Date columns"):
        or_.parse_rows([list(or_.COLUMNS[:-2]), ["2026 General Election", "Governor", "statewide"]])
    with pytest.raises(ValueError, match="not a general election's list: '2026 Primary Election'"):
        or_.parse_rows(rows(row("Governor", "statewide", "Jane Doe", election="2026 Primary Election")))
    with pytest.raises(ValueError, match="an office it doesn't know: County Commissioner, Position 1"):
        or_.parse_rows(rows(row("County Commissioner", "Position 1", "Jane Doe")))
    with pytest.raises(ValueError, match="two candidates of one party in GOVERNOR: a primary's list"):
        or_.parse_rows(rows(row("Governor", "statewide", "Jane Doe"), row("Governor", "statewide", "Jo Roe")))
    with pytest.raises(ValueError, match="0 U.S. House races, not 6"):
        or_.parse_rows([list(or_.COLUMNS), row("Governor", "statewide", "Jane Doe")])
    with pytest.raises(ValueError, match="no candidates"):
        or_.parse_rows([list(or_.COLUMNS)])
    with pytest.raises(ValueError, match="not a spreadsheet"):
        or_.OrList.parse("Election Txt")


def test_oregons_2026_dates_follow_the_ors():
    found = state_key_dates.computed("OR", D(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        D(2026, 10, 13), None, D(2026, 10, 14), None)
    for day in (D(2026, 5, 19), D(2027, 11, 2)):
        assert state_key_dates.computed("OR", day) is None, day


def test_oregons_calendar_file_says_every_voter_is_mailed_a_ballot(client, upstream):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "OR"})
    assert response.headers["content-disposition"] == 'attachment; filename="oregon-election-2026-11-03.ics"'
    text = response.text.replace("\r\n ", "")
    assert all(day in text for day in ("20261013", "20261014", "20261103"))
    assert "Official drop boxes and your county elections office close at 8 p.m. on Election Day" in text
    info = state_key_dates.GUIDES["OR"].voter_info()
    assert info.poll_hours == "until 8 p.m." and info.late_registration is None
    assert info.mail_eligibility.startswith("Every active voter is mailed a ballot. It goes out 14 to 20 days before")
    assert upstream.count("sos.oregon.gov") == 0 and upstream.count("sos.state.or.us") == 0


def test_the_import_bundles_the_parsed_candidates_never_the_spreadsheet(tmp_path):
    counts = imported(tmp_path)
    assert counts == {"races": len({f.office_id for f in or_filings()}), "candidates": len(or_filings())}
    [answer] = store.load("state_or", tmp_path / "bundles").answers
    assert answer["request"]["url"] == "manual:state_or" and set(answer["value"]) == {"filings"}
    assert "Nominated" not in str(answer) and "Lake County" not in str(answer)
    assert import_list("or", XLSX, data_dir=tmp_path / "bundles", today=lambda: TODAY).status == "no_changes"


def test_the_import_refuses_a_file_that_isnt_the_list(tmp_path):
    saved = tmp_path / "saved.xlsx"
    saved.write_text("<html><body>ORESTAR</body></html>", encoding="utf-8")
    with pytest.raises(BundleError, match="isn't a list the Oregon Secretary of State's reader understands"):
        import_list("or", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert not (tmp_path / "bundles" / "state_or.json").exists()


def test_refreshing_the_bundles_never_fetches_oregons_list(tmp_path, upstream):
    outcome = build(tmp_path, "state_or")
    assert outcome.status == "skipped" and "imported by hand" in outcome.detail
    assert upstream.count("sos.state.or.us") == 0


def test_a_salem_ballot_comes_from_the_imported_list(tmp_path, upstream, make_app, logged_calls):
    imported(tmp_path)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "salem", all_races=True)
        assert ballot["coverage"]["ballot"] == "list"
        assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (6, 11, 21)
        assert {race["name"] for race in ballot["races"]} == {
            "U.S. Senator", "U.S. Representative District 6", "Governor", "State Senator District 11",
            "State Representative District 21"}
        house = find_race(ballot, "U.S. Representative District 6")
        assert house["seat"] == "OR-06" and candidate_names(house) == ["Andrea Salinas", "David Russ"]
        assert candidate_names(find_race(ballot, "State Representative District 21")) == ["Michael Welsh", "Kevin L Mannix"]
        assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
        assert any("district attorneys" in note for note in ballot["notes"])
        assert ballot["key_dates"] == {
            "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-13",
            "mail_apply_by": None, "early_voting_start": "2026-10-14", "early_voting_end": None,
            "source": "Oregon Secretary of State", "source_url": or_.SOS, "computed": True,
        }
        get_ballot(client, "salem", all_races=True)
        assert logged_calls() == 0
        sources = {source["id"]: source for source in client.get("/api/sources").json()["sources"]}
        assert sources["state_or"]["notice"].startswith("Imported by hand on ")
    assert upstream.count("sos.state.or.us") == 0


def test_without_an_imported_list_oregon_has_the_fecs_races_for_congress(client, upstream):
    ballot = get_ballot(client, "salem")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("doesn't have the Oregon Secretary of State's list of candidates" in n for n in ballot["notes"])
    assert upstream.count("sos.state.or.us") == 0
