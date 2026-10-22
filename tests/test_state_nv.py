"""Nevada: the Secretary of State's certified list, a PDF saved by hand (tests/fixtures/state_nv.pdf,
its first six pages: the column headings, the statewide races and Clark County's), and its key
dates, worked out from Nevada's election law."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from bundles import store
from bundles.entry import BundleError
from bundles.manual import import_list
from pallot.states import key_dates as state_key_dates
from pallot.states import nv, pdf_lines

from .bundling import build
from .conftest import FIXTURES, TODAY, candidate_names, find_race, get_ballot

D = dt.date
PDF = FIXTURES / "state_nv.pdf"
BOT_CHECK = ("<html><head><META NAME=\"robots\" CONTENT=\"noindex,nofollow\"></head><body>Request unsuccessful. "
             "Incapsula incident ID: 1234-5678</body></html>")
HEADINGS = ("  Name on Ballot          Candidate Name          Party or Nonpartisan Office          Office Sought"
            "          Filing Office          Filed Date          Note")


def nv_lines() -> list[str]:
    return pdf_lines(PDF.read_bytes())


def imported(tmp_path) -> dict:
    outcome = import_list("nv", PDF, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert outcome.status == "updated"
    return outcome.counts


def by_name(filings: list, name: str):
    return next(f for f in filings if f.name == name)


def test_nevadas_list_has_its_races_parties_and_ballot_names():
    filings = nv.parse_lines(nv_lines())
    assert {f.day for f in filings} == {"2026-11-03"}
    horsford = by_name(filings, "Steven A. Horsford")
    assert (horsford.office, horsford.reach, horsford.district, horsford.party) == (
        "U.S. Representative District 4", "cd", "4", "D")
    assert [f.name for f in filings if f.office == "Governor"] == ["Aaron D. Ford", "Danielle Ford", "Joseph Lombardo"]
    assert [(f.party, f.party_name) for f in filings if f.office == "Secretary of State"] == [
        ("D", None), (None, "Independent American Party"), ("L", None), ("R", None)]
    assert (by_name(filings, "William Johnson").party, by_name(filings, "Kristina Pickering").party) == (None, None)
    assert {"Gregory T. Hafen II", 'Francisco "Cisco" Aguilar', 'Kimberly A. ("Kim") Wanker', '"Tick" Segerblom',
            "Joe Hardy Jr.", "Stacey Giomi"} <= {f.name for f in filings}


def test_nevadas_races_reach_the_districts_counties_and_cities_their_office_names():
    filings = nv.parse_lines(nv_lines())
    flores = by_name(filings, "Edgar Flores")
    assert (flores.office, flores.reach, flores.district, flores.group) == ("State Senate District 2", "sd", "2", "legislature")
    moore = by_name(filings, "Cinthia Moore")
    assert (moore.office, moore.reach, moore.district) == ("State Assembly District 11", "hd", "11")
    assert by_name(filings, "Kristina Pickering").office == "Justice of the Supreme Court, Seat B"
    assert {f.reach for f in filings if f.group == "state"} == {"state", "unplaced", "part_county"}  # the Regents
    yeager = by_name(filings, "Bita \"Marie\" Yeager")
    assert (yeager.reach, yeager.district, yeager.counties, yeager.family) == ("counties", "8", ("CLARK",), "DISTRICT COURT JUDGE")
    assert by_name(filings, "Shea M. Backus").reach == "hd"
    wanker = by_name(filings, 'Kimberly A. ("Kim") Wanker')
    assert (wanker.district, wanker.counties) == ("5", ("ESMERALDA", "NYE"))
    assessor = by_name(filings, "Judy Joe")
    assert (assessor.office, assessor.reach, assessor.group, assessor.counties) == ("County Assessor", "county", "county", ("CLARK",))
    assert by_name(filings, "Manny Kess").reach == "part_county"  # County Commissioner, District E
    assert by_name(filings, "Aaron Dalley").reach == "part_county"  # a water district
    assert by_name(filings, "Michael Allmon").reach == "part_county"  # Justice of the Peace, Henderson
    mayor = by_name(filings, "Hollie Chadwick")
    assert (mayor.reach, mayor.city, mayor.counties, mayor.office) == ("city", "HENDERSON", ("CLARK",), "Mayor, City of Henderson")
    ward = by_name(filings, "Shannon Nordstrom")
    assert (ward.reach, ward.city) == ("part_city", "LAS VEGAS")
    judge = by_name(filings, "Matt Walker")
    assert (judge.reach, judge.city, judge.group) == ("city", "LAS VEGAS", "judicial")
    assert by_name(filings, "Brent Foutz").city == "BOULDER CITY"
    furlong = by_name(filings, "Kenneth T. Furlong")
    assert (furlong.office, furlong.reach, furlong.counties) == ("Sheriff", "county", ("CARSON CITY",))


def test_nevadas_list_leaves_out_who_withdrew_died_or_was_successfully_challenged():
    filings = nv.parse_lines(nv_lines())
    assert "Amber Candelaria" not in {f.name for f in filings}
    assert by_name(filings, 'Michele "Shell" Mercer').office.endswith("Family Division, Dept. Z")
    lines = ["2026 General Election", HEADINGS] + [
        f"  {name}          {name}          Nonpartisan          Sheriff          Lyon County          3/2/2026{note}"
        for name, note in (("Pope, Brad", ""), ("White, Lance", "          Deceased"),
                           ("Doe, Jane", "          Withdrawn"), ("Roe, Ann", "          Successfully Challenged"))]
    assert [f.name for f in nv.parse_lines(lines)] == ["Brad Pope"]


def test_a_nevada_list_it_cant_read_is_refused():
    with pytest.raises(ValueError, match="column headings"):
        nv.parse_lines(["2026 General Election", "Name on Ballot   Office Sought"])
    with pytest.raises(ValueError, match="title"):
        nv.parse_lines([HEADINGS])
    row = "  Pope,  Brad  Brad Pope          Nonpartisan  Sheriff          Lyon County          3/2/2026"
    with pytest.raises(ValueError, match="can't split"):
        nv.parse_lines(["2026 General Election", HEADINGS, row])
    with pytest.raises(ValueError, match="not a PDF"):
        pdf_lines(b"<html><body>Request unsuccessful. Incapsula incident ID</body></html>")


@pytest.mark.parametrize("day", [D(2026, 11, 3), D(2028, 11, 7), D(2030, 11, 5)])
def test_nevadas_dates_follow_its_election_law(day):
    found = state_key_dates.computed("NV", day)
    assert found.register_by.weekday() == 1 and (day - found.register_by).days == 28  # the fourth Tuesday before
    assert (day - found.mail_apply_by).days == 14
    assert found.early_start.weekday() == 5 and found.early_start == day - dt.timedelta(days=17)  # the third Saturday before
    assert found.early_end.weekday() == 4 and found.early_end == day - dt.timedelta(days=4)  # the Friday before


def test_nevadas_2026_dates_and_only_its_general_election_has_them():
    found = state_key_dates.computed("NV", D(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        D(2026, 10, 6), D(2026, 10, 20), D(2026, 10, 17), D(2026, 10, 30))
    for day in (D(2026, 6, 9), D(2027, 11, 2), D(2026, 11, 10)):
        assert state_key_dates.computed("NV", day) is None, day


def test_nevadas_calendar_is_worked_out_without_asking_anyone(client, upstream):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "NV"})
    assert response.headers["content-disposition"] == 'attachment; filename="nevada-election-2026-11-03.ics"'
    unfolded = response.text.replace("\r\n ", "")
    assert "UID:nv-2026-11-03-early_start@pallot\r\nDTSTAMP" in unfolded and "DTSTART;VALUE=DATE:20261017" in unfolded
    assert "7 a.m. to 7 p.m." in unfolded and "Texas" not in unfolded
    mail = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "NV", "event": "mail"}).text
    assert "SUMMARY:Last day to register and still be mailed a ballot (Nov 3 election)" in mail
    assert "DTSTART;VALUE=DATE:20261020" in mail
    assert upstream.count("sos.state.tx.us") == 0 and upstream.count("nvsos.gov") == 0


def test_the_import_bundles_the_parsed_candidates_never_the_pdf(tmp_path):
    counts = imported(tmp_path)
    assert counts["races"] > 100 and counts["candidates"] > 250
    [answer] = store.load("state_nv", tmp_path / "bundles").answers
    assert answer["request"]["url"] == "manual:state_nv" and set(answer["value"]) == {"filings"}
    assert import_list("nv", PDF, data_dir=tmp_path / "bundles", today=lambda: TODAY).status == "no_changes"


def test_the_import_refuses_the_bot_check_and_a_file_that_isnt_the_list(tmp_path):
    saved = tmp_path / "saved.pdf"
    saved.write_text(BOT_CHECK, encoding="utf-8")
    with pytest.raises(BundleError, match="the site's bot check, not the list"):
        import_list("nv", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    saved.write_bytes(b"%PDF-1.7 cut short")
    with pytest.raises(BundleError, match="isn't a list the Nevada Secretary of State's reader understands"):
        import_list("nv", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert not (tmp_path / "bundles" / "state_nv.json").exists()


def test_refreshing_the_bundles_never_fetches_nevadas_list(tmp_path, upstream):
    outcome = build(tmp_path, "state_nv")
    assert outcome.status == "skipped" and "imported by hand" in outcome.detail
    assert upstream.count("nvsos") == 0


def test_a_las_vegas_ballot_comes_from_the_imported_list(tmp_path, upstream, make_app, logged_calls):
    imported(tmp_path)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "lasvegas", all_races=True)
        assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "labels": {"hd": "State Assembly"}}
        assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (4, 2, 11)
        for name in ("U.S. Representative District 4", "Governor", "Attorney General", "State Senate District 2",
                     "State Assembly District 11", "Justice of the Supreme Court, Seat B",
                     "District Court Judge, Eighth Judicial District, Department 1", "County Assessor",
                     "Municipal Court Judge, Dept. 1, City of Las Vegas"):
            assert find_race(ballot, name), name
        for name in ("U.S. Representative District 1", "State Assembly District 12", "Mayor, City of Henderson",
                     "District Court Judge, Ninth Judicial District, Department 1", "Board of Regents, District 8"):
            assert find_race(ballot, name) is None, name
        for name in ("City of Las Vegas, Councilman Ward 2", "County Commissioner, District E",
                     "Board of Regents, District 2"):
            assert find_race(ballot, name, maybe=True), name
        assert find_race(ballot, "U.S. Representative District 4")["seat"] == "NV-04"
        assert candidate_names(find_race(ballot, "State Senate District 2")) == ["Edgar Flores"]
        assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
        assert any("1 Board of Regents race" in note for note in ballot["notes"])
        assert ballot["key_dates"] == {
            "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-06",
            "mail_apply_by": "2026-10-20", "early_voting_start": "2026-10-17", "early_voting_end": "2026-10-30",
            "source": "Nevada Secretary of State", "source_url": "https://www.nvsos.gov/sos/elections",
            "computed": True,
        }
        get_ballot(client, "lasvegas", all_races=True)
        assert logged_calls() == 0
        rows = {row["id"]: row for row in client.get("/api/sources").json()["sources"]}
        assert rows["state_nv"]["notice"].startswith("Imported by hand on ")
    assert upstream.count("nvsos") == 0


def test_without_an_imported_list_nevada_has_the_fecs_races_for_congress(client, upstream):
    ballot = get_ballot(client, "lasvegas")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("doesn't have the Nevada Secretary of State's list of candidates" in n for n in ballot["notes"])
    assert find_race(ballot, "U.S. Representative District 4")
    assert upstream.count("nvsos") == 0