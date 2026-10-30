"""Massachusetts: the Secretary of the Commonwealth's page of the state election's candidates, saved
by hand (tests/fixtures/state_ma.html: its headings and candidates, each street and town made "1
Main St., Town"), and its key dates, worked out from Massachusetts's election law."""

from __future__ import annotations

import datetime as dt
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from bundles import store
from bundles.entry import BundleError
from bundles.manual import import_list
from pallot.states import ma
from pallot.states import key_dates as state_key_dates

from .bundling import build
from .conftest import FIXTURES, TODAY, candidate_names, find_race, get_ballot

D = dt.date
PAGE = FIXTURES / "state_ma.html"
TITLE = "<html><head><title>2026 State Election Candidates</title></head><body><article>"


def ma_filings() -> list:
    return ma.parse_page(PAGE.read_text(encoding="utf-8"))


def by_name(filings: list, name: str):
    return next(f for f in filings if f.name == name)


def imported(tmp_path) -> dict:
    outcome = import_list("ma", PAGE, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert outcome.status == "updated"
    return outcome.counts


def test_massachusettss_page_has_congress_its_statewide_offices_and_its_legislature():
    filings = ma_filings()
    assert {f.day for f in filings} == {"2026-11-03"}
    assert Counter(f.reach for f in filings) == {"state": 15, "cd": 17, "sd": 51, "hd": 210}
    assert len({f.district for f in filings if f.reach == "sd"}) == 40
    assert len({f.district for f in filings if f.reach == "hd"}) == 160
    order = list(dict.fromkeys(f.office for f in filings))
    assert order[:7] == ["U.S. Senator", "Governor and Lieutenant Governor", "Attorney General", "Secretary of State",
                         "Treasurer", "Auditor", "U.S. Representative District 1"]
    assert [(f.name, f.party, f.party_name) for f in filings if f.office_id == "GOVERNOR"] == [
        ("Healey and Driscoll", "D", None), ("Minogue and Oliver", "R", None), ("James and Kittredge", None, "Independent")]
    assert by_name(filings, "Joe Tache").party_name == "Socialism and Liberation"
    assert by_name(filings, "John Francis Moran").party == "D"  # the page's "Demo"
    neal = by_name(filings, "Richard E. Neal")
    assert (neal.office, neal.district, neal.party, neal.party_name) == ("U.S. Representative District 1", "1", None, None)
    barrett = by_name(filings, "John Barrett, III")
    assert (barrett.office, barrett.reach, barrett.district) == (
        "State Representative, First Berkshire District", "hd", "1st Berkshire")
    assert not any(f.name in ("Tara J. Jacobs", "Kevin R. Hayden", "Lori M. Streeter", "Left out") or
                   f.name.upper() == "NO NOMINATIONS" for f in filings)


def test_districts_are_spelt_as_the_census_spells_them():
    filings = ma_filings()
    districts = {f.office: f.district for f in filings if f.reach in ("sd", "hd")}
    assert districts["State Senator, Berkshire, Hampden, Franklin & Hampshire District"] == (
        "Berkshire-Hampden-Franklin-Hampshire")
    assert districts["State Senator, Cape & Islands District"] == "Cape and Islands"
    assert districts["State Senator, First Essex & Middlesex District"] == "First Essex and Middlesex"
    assert districts["State Senator, Third Suffolk District"] == "Third Suffolk"
    assert districts["State Representative, Twenty-First Middlesex District"] == "21st Middlesex"
    assert districts["State Representative, Thirtieth Middlesex District"] == "30th Middlesex"
    assert districts["State Representative, Barnstable, Dukes & Nantucket District"] == "Barnstable-Dukes-Nantucket"
    assert districts["State Representative, Third Suffolk District"] == "3rd Suffolk"
    with pytest.raises(ValueError, match="a district it doesn't know"):
        ma.census_name("hd", "Third Gotham District")
    with pytest.raises(ValueError, match="a district it doesn't know"):
        ma.census_name("sd", "Third Suffolk")


def test_a_massachusetts_page_it_cant_read_is_refused():
    with pytest.raises(ValueError, match="not the state election's candidates page"):
        ma.parse_page("<html><body><article><h2>Senator in Congress</h2></article></body></html>")
    with pytest.raises(ValueError, match="an office it doesn't know: Mayor"):
        ma.parse_page(f"{TITLE}<h2>Mayor</h2><p>Jane Doe, Democratic</p></article>")
    with pytest.raises(ValueError, match="two candidates of one party in US SENATE"):
        ma.parse_page(f"{TITLE}<h2>Senator in Congress</h2><p>Jane Doe, 1 Main St., Town, Democratic</p>"
                      f"<p>John Roe, 1 Main St., Town, Democratic</p></article>")
    with pytest.raises(ValueError, match="0 U.S. House races, not 9"):
        ma.parse_page(f"{TITLE}<h2>Senator in Congress</h2><p>Jane Doe, 1 Main St., Town, Democratic</p></article>")
    with pytest.raises(ValueError, match="no candidates"):
        ma.parse_page(f"{TITLE}</article>")
    with pytest.raises(ValueError, match="not a web page"):
        ma.MaList.parse(b"<html>")


def test_massachusettss_2026_dates_follow_its_election_law():
    found = state_key_dates.computed("MA", D(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        D(2026, 10, 24), D(2026, 10, 27), D(2026, 10, 17), D(2026, 10, 30))
    for day in (D(2026, 9, 1), D(2027, 11, 2)):
        assert state_key_dates.computed("MA", day) is None, day
    info = state_key_dates.GUIDES["MA"].voter_info()
    assert info.poll_hours == "7 a.m. – 8 p.m." and info.late_registration is None


def test_massachusettss_calendar_is_worked_out_without_asking_anyone(client, upstream):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "MA"})
    assert response.headers["content-disposition"] == 'attachment; filename="massachusetts-election-2026-11-03.ics"'
    unfolded = response.text.replace("\r\n ", "")
    assert "DTSTART;VALUE=DATE:20261017" in unfolded and "Polls are open 7 a.m. to 8 p.m." in unfolded
    mail = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "MA", "event": "mail"}).text
    assert "SUMMARY:Vote-by-mail application due (Nov 3 election)" in mail and "DTSTART;VALUE=DATE:20261027" in mail
    assert upstream.count("sec.state.ma.us") == 0


def test_the_import_bundles_the_parsed_candidates_never_the_page(tmp_path):
    counts = imported(tmp_path)
    assert counts == {"races": len({f.office_id for f in ma_filings()}), "candidates": len(ma_filings())}
    [answer] = store.load("state_ma", tmp_path / "bundles").answers
    assert answer["request"]["url"] == "manual:state_ma" and set(answer["value"]) == {"filings"}
    assert "Main St" not in str(answer) and "<p>" not in str(answer)
    assert import_list("ma", PAGE, data_dir=tmp_path / "bundles", today=lambda: TODAY).status == "no_changes"


def test_the_import_refuses_the_sites_bot_check(tmp_path):
    saved = tmp_path / "saved.html"
    saved.write_text("<html><body>Request unsuccessful. Incapsula incident ID: 1-2</body></html>", encoding="utf-8")
    with pytest.raises(BundleError, match="is the site's bot check"):
        import_list("ma", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert not (tmp_path / "bundles" / "state_ma.json").exists()


def test_refreshing_the_bundles_never_fetches_massachusettss_page(tmp_path, upstream):
    outcome = build(tmp_path, "state_ma")
    assert outcome.status == "skipped" and "imported by hand" in outcome.detail
    assert upstream.count("sec.state.ma.us") == 0


def test_a_boston_ballot_comes_from_the_imported_page(tmp_path, upstream, make_app, logged_calls):
    imported(tmp_path)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "boston", all_races=True)
        assert ballot["coverage"]["ballot"] == "list"
        assert ballot["districts"]["cd"] == 8
        names = [race["name"] for race in ballot["races"]]
        assert names[:2] == ["U.S. Senator", "U.S. Representative District 8"]
        assert set(names) == {"U.S. Senator", "U.S. Representative District 8", "Governor and Lieutenant Governor",
                              "Attorney General", "Secretary of State", "Treasurer", "Auditor",
                              "State Senator, Third Suffolk District", "State Representative, Third Suffolk District"}
        assert candidate_names(find_race(ballot, "State Senator, Third Suffolk District")) == ["Lydia Marie Edwards"]
        assert candidate_names(find_race(ballot, "State Representative, Third Suffolk District")) == ["Aaron Michlewitz"]
        assert find_race(ballot, "U.S. Representative District 8")["seat"] == "MA-08"
        assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
        assert any("Governor's Council" in note for note in ballot["notes"])
        assert ballot["key_dates"] == {
            "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-24",
            "mail_apply_by": "2026-10-27", "early_voting_start": "2026-10-17", "early_voting_end": "2026-10-30",
            "source": "Massachusetts Secretary of the Commonwealth", "source_url": ma.GUIDE.url, "computed": True,
        }
        get_ballot(client, "boston", all_races=True)
        assert logged_calls() == 0
        rows = {row["id"]: row for row in client.get("/api/sources").json()["sources"]}
        assert rows["state_ma"]["notice"].startswith("Imported by hand on ")
    assert upstream.count("sec.state.ma.us") == 0


def test_without_an_imported_page_massachusetts_has_the_fecs_races_for_congress(client, upstream):
    ballot = get_ballot(client, "boston")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("doesn't have the Massachusetts Secretary of the Commonwealth's list of candidates" in n
               for n in ballot["notes"])
    assert upstream.count("sec.state.ma.us") == 0
