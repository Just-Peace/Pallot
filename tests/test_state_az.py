"""Arizona's list (states/az.py), saved by hand and imported (bundles/manual.py): reading it,
importing it, and the ballots made from it, without ever asking Arizona's sites.
tests/fixtures/state_az.html is the real page cut down to a few offices."""

from __future__ import annotations

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from bundles import store
from bundles.__main__ import main as bundle_main
from bundles.entry import BundleError
from bundles.manual import import_list
from pallot.states.az import AzList

from .bundling import build
from .conftest import FIXTURES, TODAY, candidate_names, find_race, get_ballot

PAGE = FIXTURES / "state_az.html"
CHALLENGE = "<html><head><title>Just a moment...</title></head><body>Checking your browser</body></html>"


def imported(tmp_path) -> dict:
    outcome = import_list("az", PAGE, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert outcome.status == "updated"
    return outcome.counts


def test_arizonas_list_has_congress_statewide_the_legislature_and_the_judges():
    filings = AzList.parse(PAGE.read_text(encoding="utf-8"))
    assert {f.day for f in filings} == {"2026-11-03"}
    third = [f for f in filings if f.office_id == "US HOUSE 3"]
    assert [(f.name, f.party, f.party_name, f.write_in) for f in third] == [
        ("Yassamin Ansari", "D", None, False), ("David Redkey", "G", None, False),
        ("Alan Aversa", None, "No Labels Party", False), ("Jacob Parkman", "R", None, True)]
    assert (third[0].office, third[0].reach, third[0].district) == ("U.S. Representative District 3", "cd", "3")
    assert next(f for f in filings if f.office_id == "US HOUSE 1").name == 'Thomas "Jay" Feely IV'
    house = [f for f in filings if f.office_id == "STATE HOUSE 11"]
    assert {(f.reach, f.district, f.seats, f.office) for f in house} == {
        ("hd", "11", 2, "State Representative, Legislative District 11")}
    assert [f.name for f in house] == ["Cesar Aleman", "Joseph Charles Dailey", "Junelle Cavero", "Oscar De Los Santos"]
    senate = [f for f in filings if f.office_id == "STATE SENATE 11"]
    assert {(f.reach, f.seats) for f in senate} == {("sd", 1)}
    assert {f.seats for f in filings if f.office_id == "CORPORATION COMMISSIONER"} == {2}  # two nominees a party
    justice = next(f for f in filings if f.name == "John Lopez IV")
    assert (justice.office, justice.reach, justice.group) == ("Retain Supreme Court Justice John Lopez IV", "state",
                                                             "judicial")
    appeals = next(f for f in filings if f.name == "Lacey Stover Gard")
    assert appeals.office == "Retain Court of Appeals Division Two Judge Lacey Stover Gard"
    assert (appeals.reach, "PIMA" in appeals.counties, "MARICOPA" in appeals.counties) == ("counties", True, False)
    assert not any("Proposition" in f.office or "Copyright" in f.name for f in filings)
    assert len(filings) == 44


GENERAL = '<html><body><h2>2026 General Election</h2><span>Tuesday, November 03, 2026</span>{}</body></html>'


@pytest.mark.parametrize("page", [
    CHALLENGE, "", "<html><body><h2>2026 General Election</h2></body></html>",
    GENERAL.format("<h3>Governor</h3><h4>HOBBS, KATIE (DEM)</h4>"),
    GENERAL.format("<h3>U.S. Representative in Congress - District No. 3</h3><h4>ANSARI, YASSAMIN</h4>"),
])
def test_a_page_that_isnt_the_list_is_refused(page):
    with pytest.raises(ValueError):
        AzList.parse(page)


def test_the_import_bundles_the_parsed_candidates_without_their_contact_details(tmp_path):
    counts = imported(tmp_path)
    assert counts == {"races": 22, "candidates": 44}
    [answer] = store.load("state_az", tmp_path / "bundles").answers
    assert answer["request"]["url"] == "manual:state_az" and set(answer["value"]) == {"filings"}
    assert "602-555-0100" in PAGE.read_text(encoding="utf-8") and "555-0100" not in json.dumps(answer)
    again = import_list("az", PAGE, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert again.status == "no_changes"
    assert store.read_meta(tmp_path / "bundles")["state_az"]["candidates"] == 44


def test_the_import_refuses_the_bot_check_and_writes_nothing(tmp_path, capsys):
    saved = tmp_path / "saved.html"
    saved.write_text(CHALLENGE, encoding="utf-8")
    with pytest.raises(BundleError, match="the site's bot check, not the list"):
        import_list("az", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert bundle_main(["import-list", "az", str(saved), "--data-dir", str(tmp_path / "bundles")]) == 2
    assert "Not imported" in capsys.readouterr().err
    assert not (tmp_path / "bundles" / "state_az.json").exists()
    with pytest.raises(BundleError, match="no candidates for the general election on 2028-11-07"):
        import_list("az", PAGE, data_dir=tmp_path / "bundles", today=lambda: dt.date(2027, 1, 1))
    with pytest.raises(BundleError, match="no list imported by hand"):
        import_list("tx", PAGE, data_dir=tmp_path / "bundles")


def test_refreshing_the_bundles_never_fetches_arizonas_list(tmp_path, upstream):
    outcome = build(tmp_path, "state_az")
    assert outcome.status == "skipped" and "imported by hand" in outcome.detail
    assert upstream.count("arizona") == 0 and upstream.count("azsos") == 0


def test_an_arizona_ballot_comes_from_the_imported_list(tmp_path, upstream, make_app, logged_calls):
    imported(tmp_path)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "phoenix")
        assert ballot["coverage"]["ballot"] == "list"
        names = [race["name"] for race in ballot["races"]]
        assert names[:6] == [
            "U.S. Representative District 3", "Governor", "Corporation Commissioner",
            "State Senator, Legislative District 11", "State Representative, Legislative District 11",
            "Retain Supreme Court Justice John Lopez IV"]
        assert sum(name.startswith("Retain Court of Appeals Division One") for name in names) == 8
        assert not any("Division Two" in name or "District 12" in name for name in names)
        house = find_race(ballot, "U.S. Representative District 3")
        assert candidate_names(house) == ["Yassamin Ansari", "David Redkey", "Alan Aversa", "Jacob Parkman"]
        assert [c["write_in"] for c in house["candidates"]] == [False, False, False, True]
        assert find_race(ballot, "State Representative, Legislative District 11")["seats"] == 2
        assert find_race(ballot, "Corporation Commissioner")["seats"] == 2
        assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
        assert ballot["key_dates"] == {
            "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-05",
            "mail_apply_by": None, "early_voting_start": "2026-10-07", "early_voting_end": "2026-10-30",
            "source": "Arizona Secretary of State", "source_url": "https://azsos.gov/elections", "computed": True,
        }
        get_ballot(client, "phoenix")
        assert logged_calls() == 0
        rows = {row["id"]: row for row in client.get("/api/sources").json()["sources"]}
        assert rows["state_az"]["notice"].startswith("Imported by hand on ")
    assert upstream.count("arizona") == 0 and upstream.count("azsos") == 0


def test_without_an_imported_list_arizona_has_the_fecs_races_for_congress(client, upstream):
    ballot = get_ballot(client, "phoenix")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("doesn't have the Arizona Secretary of State's list of candidates" in n for n in ballot["notes"])
    assert all(c["unverified"] for race in ballot["races"] for c in race["candidates"])
    assert find_race(ballot, "U.S. Representative District 3")
    rows = {row["id"]: row for row in client.get("/api/sources").json()["sources"]}
    assert rows["state_az"]["notice"].startswith("No list imported yet")
    assert upstream.count("arizona") == 0 and upstream.count("azsos") == 0


def test_pallot_cache_never_refreshes_the_imported_list_and_a_rebuild_keeps_it(tmp_path, upstream, make_app):
    imported(tmp_path)
    with TestClient(make_app(bundles=tmp_path / "bundles")):
        pass
    checked = make_app.cache_command("check", "state_az", bundles=tmp_path / "bundles")[1]
    assert "never fetched or refreshed" in checked and "Imported by hand on " in checked
    assert "Arizona" not in make_app.cache_command("refresh", "state_az", bundles=tmp_path / "bundles")[1]
    make_app.cache_command("rebuild", bundles=tmp_path / "bundles")
    with TestClient(make_app(bundles=tmp_path / "no-bundles")) as client:
        assert get_ballot(client, "phoenix")["coverage"]["ballot"] == "list"
    assert upstream.count("arizona") == 0 and upstream.count("azsos") == 0


def test_arizonas_calendar_file_has_its_dates(client):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "AZ"})
    assert response.status_code == 200 and "arizona-election-2026-11-03.ics" in response.headers["content-disposition"]
    assert "Polls are open 6 a.m. to 7 p.m." in response.text.replace("\r\n ", "")
