"""Wisconsin: the Elections Commission's contests and candidates, a CSV saved by hand
(tests/fixtures/state_wi.csv, the state's rows and a few counties'), and its key dates, worked
out from Wisconsin's election law."""

from __future__ import annotations

import datetime as dt
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from bundles import store
from bundles.entry import BundleError
from bundles.manual import import_list
from pallot.states import key_dates as state_key_dates
from pallot.states import wi

from .bundling import build
from .conftest import FIXTURES, TODAY, candidate_names, find_race, get_ballot

D = dt.date
CSV = FIXTURES / "state_wi.csv"
CLOUDFLARE = "<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>challenges.cloudflare.com</body></html>"
HEADER = ("Election,IsReferendum,Candidate,Name On Ballot,CommitteeID,Political Party,Jurisdiction,Contest,District,"
          "Contest Ballot Position,Candidate Ballot Position")


def wi_filings() -> list:
    return wi.parse_rows(CSV.read_text(encoding="utf-8"))


def imported(tmp_path) -> dict:
    outcome = import_list("wi", CSV, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert outcome.status == "updated"
    return outcome.counts


def by_name(filings: list, name: str):
    return next(f for f in filings if f.name == name)


def test_wisconsins_list_has_its_races_parties_and_ballot_order():
    filings = wi_filings()
    assert {f.day for f in filings} == {"2026-11-03"}
    assert Counter(f.reach for f in filings) == {"hd": 197, "sd": 33, "cd": 21, "state": 9, "county": 15,
                                                 "part_county": 3, "city": 2}
    assert [(f.name, f.party) for f in filings if f.office == "Governor / Lieutenant Governor"] == [
        ("Tom Tiffany / David Varnam", "R"), ("David Crowley / Sarah Godlewski", "D")]
    assert [(f.name, f.party) for f in sorted(filings, key=lambda f: f.order) if f.office == "Secretary of State"] == [
        ("Jay Schroeder", "R"), ("JoCasta Zamarripa", "D"), ("Pete Karas", "G")]
    assert (by_name(filings, "Rustin Provance").party, by_name(filings, "Rustin Provance").party_name) == (None, None)
    assert (by_name(filings, "Csaba Keller").party, by_name(filings, "Csaba Keller").party_name) == (None, "Constitution")
    assert by_name(filings, "Kalvin D. Barrett").party == "D" and by_name(filings, "Brandon White").party is None
    pocan = by_name(filings, "Mark Pocan")
    assert (pocan.office, pocan.reach, pocan.district, pocan.group) == ("U.S. Representative District 2", "cd", "2", "federal")
    order = [f.office for f in sorted(filings, key=lambda f: f.order) if f.reach == "state"]
    assert list(dict.fromkeys(order)) == ["Governor / Lieutenant Governor", "Attorney General", "Secretary of State",
                                          "State Treasurer"]


def test_wisconsins_races_reach_the_districts_counties_and_cities_their_rows_name():
    filings = wi_filings()
    chat = by_name(filings, "Nina Chat")
    assert (chat.office, chat.reach, chat.district, chat.group) == ("State Assembly District 76", "hd", "76", "legislature")
    becker = by_name(filings, "Mark Becker")
    assert (becker.office, becker.reach, becker.district) == ("State Senate District 1", "sd", "1")
    sheriff = by_name(filings, "Kalvin D. Barrett")
    assert (sheriff.office, sheriff.reach, sheriff.counties, sheriff.group, sheriff.family) == (
        "Dane County Sheriff", "county", ("DANE",), "county", "SHERIFF")
    judge = by_name(filings, "James Kokalj")
    assert (judge.office, judge.reach, judge.city, judge.counties, judge.group) == (
        "Verona Municipal Judge", "city", "VERONA", ("DANE",), "judicial")
    assert by_name(filings, "Brandon White").city == "JEFFERSON"
    supervisor = by_name(filings, "Preston Scheuermann")
    assert (supervisor.reach, supervisor.counties, supervisor.group) == ("part_county", ("PRICE",), "local")
    marshfield = by_name(filings, "Krista J. James")
    assert (marshfield.reach, marshfield.counties, marshfield.group) == ("part_county", ("WOOD",), "judicial")


def test_wisconsins_referendums_and_contests_no_one_filed_for_are_left_out():
    filings = wi_filings()
    assert not any("Referendum" in f.office or "Coroner" in f.office and "IRON" in f.counties for f in filings)
    rows = [HEADER,
            '2026 General Election,,"Doe, Jane",Jane Doe,,,CITY OF EAU CLAIRE - MULTIPLE COUNTIES,City of Eau Claire '
            'Mayor,City of Eau Claire,300001,1',
            '2026 General Election,,"Roe, Ann",Ann Roe,,,TOWN OF HUDSON - ST. CROIX COUNTY,Town of Hudson Chair,'
            'Town of Hudson,300002,1',
            '2026 General Election,,"Poe, Al",Al Poe,,,CITY OF MADISON - DANE COUNTY,Alder District 4,'
            'Aldermanic District 4,300003,1',
            '2026 Spring Election,,"Moe, Bo",Bo Moe,,,DANE COUNTY,Dane County Executive,Dane County,300004,1']
    found = wi.parse_rows("\n".join(rows))
    assert [(f.name, f.reach, f.counties, f.city) for f in found] == [
        ("Jane Doe", "unplaced", (), None), ("Ann Roe", "part_county", ("ST. CROIX",), None),
        ("Al Poe", "part_city", ("DANE",), "MADISON")]


def test_a_wisconsin_list_it_cant_read_is_refused():
    with pytest.raises(ValueError, match="no Political Party, Contest Ballot Position columns"):
        wi.parse_rows(HEADER.replace("Political Party", "Party").replace("Contest Ballot Position", "Position"))
    with pytest.raises(ValueError, match="no candidates"):
        wi.parse_rows(HEADER + "\n2026 General Election,Referendum,,,,,DANE COUNTY,A Referendum,Dane County,950000,0")
    with pytest.raises(ValueError, match="not a CSV"):
        wi.WiList.parse(b"Election,IsReferendum")


@pytest.mark.parametrize("day", [D(2026, 11, 3), D(2028, 11, 7), D(2030, 11, 5)])
def test_wisconsins_dates_follow_its_election_law(day):
    found = state_key_dates.computed("WI", day)
    assert found.register_by.weekday() == 2 and (day - found.register_by).days == 20  # the third Wednesday before
    assert found.mail_apply_by.weekday() == 3 and (day - found.mail_apply_by).days == 5  # the Thursday before
    assert (day - found.early_start).days == 14
    assert found.early_end.weekday() == 6 and (day - found.early_end).days == 2  # the Sunday before


def test_wisconsins_2026_dates_and_only_its_general_election_has_them():
    found = state_key_dates.computed("WI", D(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        D(2026, 10, 14), D(2026, 10, 29), D(2026, 10, 20), D(2026, 11, 1))
    for day in (D(2026, 8, 11), D(2027, 11, 2), D(2026, 11, 10)):
        assert state_key_dates.computed("WI", day) is None, day


def test_wisconsins_calendar_is_worked_out_without_asking_anyone(client, upstream):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "WI"})
    assert response.headers["content-disposition"] == 'attachment; filename="wisconsin-election-2026-11-03.ics"'
    unfolded = response.text.replace("\r\n ", "")
    assert "UID:wi-2026-11-03-early_start@pallot\r\nDTSTAMP" in unfolded and "DTSTART;VALUE=DATE:20261020" in unfolded
    assert "7 a.m. to 8 p.m." in unfolded and "Texas" not in unfolded
    mail = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "WI", "event": "mail"}).text
    assert "SUMMARY:Absentee ballot request due (Nov 3 election)" in mail and "DTSTART;VALUE=DATE:20261029" in mail
    assert upstream.count("elections.wi.gov") == 0 and upstream.count("myvote.wi.gov") == 0


def test_the_import_bundles_the_parsed_candidates_never_the_csv(tmp_path):
    counts = imported(tmp_path)
    assert counts == {"races": len({f.office_id for f in wi_filings()}), "candidates": 280}
    [answer] = store.load("state_wi", tmp_path / "bundles").answers
    assert answer["request"]["url"] == "manual:state_wi" and set(answer["value"]) == {"filings"}
    assert "CommitteeID" not in str(answer) and "Valiensi Kent, Alexander" not in str(answer)
    assert import_list("wi", CSV, data_dir=tmp_path / "bundles", today=lambda: TODAY).status == "no_changes"


def test_the_import_refuses_cloudflares_page_and_a_file_that_isnt_the_list(tmp_path):
    saved = tmp_path / "saved.csv"
    saved.write_text(CLOUDFLARE, encoding="utf-8")
    with pytest.raises(BundleError, match="the site's bot check, not the list"):
        import_list("wi", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    saved.write_text("Election,Contest\n2026 General Election,GOVERNOR\n", encoding="utf-8")
    with pytest.raises(BundleError, match="isn't a list the Wisconsin Elections Commission's reader understands"):
        import_list("wi", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert not (tmp_path / "bundles" / "state_wi.json").exists()


def test_refreshing_the_bundles_never_fetches_wisconsins_list(tmp_path, upstream):
    outcome = build(tmp_path, "state_wi")
    assert outcome.status == "skipped" and "imported by hand" in outcome.detail
    assert upstream.count("elections.wi.gov") == 0


def test_a_madison_ballot_comes_from_the_imported_list(tmp_path, upstream, make_app, logged_calls):
    imported(tmp_path)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "madison", all_races=True)
        assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "labels": {"hd": "State Assembly"}}
        assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (2, 26, 76)
        names = [race["name"] for race in ballot["races"]]
        assert names[:6] == ["U.S. Representative District 2", "Governor / Lieutenant Governor", "Attorney General",
                             "Secretary of State", "State Treasurer", "State Assembly District 76"]
        for name in ("Dane County Sheriff", "Dane County Clerk of Circuit Court"):
            assert find_race(ballot, name), name
        for name in ("U.S. Representative District 3", "State Assembly District 77", "Verona Municipal Judge",
                     "Wood County Sheriff", "City of Jefferson Municipal Judge"):
            assert find_race(ballot, name) is None and find_race(ballot, name, maybe=True) is None, name
        assert not any(name.startswith("State Senate") for name in names)  # its odd-numbered districts are up
        assert find_race(ballot, "U.S. Representative District 2")["seat"] == "WI-02"
        assert candidate_names(find_race(ballot, "State Assembly District 76")) == [
            "Nina Chat", "Dina Nina Martinez-Rutherford"]
        assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
        assert ballot["key_dates"] == {
            "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-14",
            "mail_apply_by": "2026-10-29", "early_voting_start": "2026-10-20", "early_voting_end": "2026-11-01",
            "source": "Wisconsin Elections Commission", "source_url": "https://elections.wi.gov/",
            "computed": True,
        }
        get_ballot(client, "madison", all_races=True)
        assert logged_calls() == 0
        rows = {row["id"]: row for row in client.get("/api/sources").json()["sources"]}
        assert rows["state_wi"]["notice"].startswith("Imported by hand on ")
    assert upstream.count("elections.wi.gov") == 0 and upstream.count("myvote.wi.gov") == 0


def test_without_an_imported_list_wisconsin_has_the_fecs_races_for_congress(client, upstream):
    ballot = get_ballot(client, "madison")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("doesn't have the Wisconsin Elections Commission's list of candidates" in n for n in ballot["notes"])
    assert find_race(ballot, "U.S. Representative District 2")
    assert upstream.count("elections.wi.gov") == 0
