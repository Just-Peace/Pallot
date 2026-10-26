"""New York: the State Board of Elections' certification of candidates, a PDF saved by hand
(tests/fixtures/state_ny.txt, the text lines of its statewide races and a few others), and its key
dates, worked out from New York's Election Law."""

from __future__ import annotations

import datetime as dt
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from bundles import store
from bundles.entry import BundleError
from bundles.manual import import_list
from pallot.states import key_dates as state_key_dates
from pallot.states import ny, require

from .bundling import build
from .conftest import FIXTURES, TODAY, candidate_names, find_race, get_ballot

D = dt.date
LINES = (FIXTURES / "state_ny.txt").read_text(encoding="utf-8").split("\n")
CLOUDFLARE = "<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>challenges.cloudflare.com</body></html>"


def block(office: str, district: int, rows: list[tuple[str, str]]) -> list[str]:
    lines = [f"Office:        {office}", f"District:     {district}", "Counties:   Part of Erie", "Vote For:   1", "",
             " Party                            Candidate Name", ""]
    for label, name in rows:
        lines += [f" {label:<28}{name}".rstrip(), "", ""]
    return lines


def whole_list() -> list[str]:
    """The fixture's lines, with a made-up race for each Congress and Assembly district it leaves out."""
    found = ny.parse_lines(LINES)
    lines = list(LINES)
    for office, reach, count in (("Representative in Congress", "cd", 26), ("Member of Assembly", "hd", 150)):
        have = {int(f.district) for f in found if f.reach == reach}
        for number in sorted(set(range(1, count + 1)) - have):
            lines += block(office, number, [("Democratic", f"Dana {reach.upper()}{number} Doe"), ("Working Families", "")])
    return lines


@pytest.fixture
def pdf(tmp_path, monkeypatch):
    """A saved certification, read as the whole list's text lines."""
    monkeypatch.setattr(ny, "pdf_lines", lambda raw: whole_list())
    path = tmp_path / "certification.pdf"
    path.write_bytes(b"%PDF-1.7 the certification")
    return path


def imported(tmp_path, path) -> dict:
    outcome = import_list("ny", path, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert outcome.status == "updated"
    return outcome.counts


def by_name(filings: list, name: str):
    return next(f for f in filings if f.name == name)


def test_new_yorks_certification_has_its_races_and_seats():
    filings = ny.parse_lines(LINES)
    assert {f.day for f in filings} == {"2026-11-03"}
    races = {f.office_id: f for f in filings}
    assert Counter(f.reach for f in races.values()) == {"state": 3, "cd": 4, "sd": 4, "hd": 8, "counties": 4}
    assert [f.office for f in races.values() if f.reach == "state"] == [
        "Governor and Lieutenant Governor", "Comptroller", "Attorney General"]
    lander = by_name(filings, "Brad Lander")
    assert (lander.office, lander.reach, lander.district, lander.group) == ("U.S. Representative District 10", "cd", "10", "federal")
    lee = by_name(filings, "Grace Lee")
    assert (lee.office, lee.reach, lee.district, lee.group) == ("State Senate District 27", "sd", "27", "legislature")
    assembly = [f for f in filings if f.office == "State Assembly District 97"]  # its block reads "SteOffice:"
    assert assembly and {(f.reach, f.district, f.family) for f in assembly} == {("hd", "97", "STATE ASSEMBLY")}
    assert any(f.office == "State Senate District 54" for f in filings)  # "Counties" without its colon
    first = [f for f in filings if f.office == "Supreme Court Justice, 1st Judicial District"]
    assert {(f.reach, f.district, f.counties, f.seats, f.group, f.family) for f in first} == {
        ("counties", "1", ("NEW YORK",), 6, "judicial", "SUPREME COURT JUSTICE")}
    third = by_name(filings, "Amy E. Joyce")
    assert (third.counties, third.seats) == (("ALBANY", "COLUMBIA", "GREENE", "RENSSELAER", "SCHOHARIE", "SULLIVAN", "ULSTER"), 2)
    assert ny._counties("Clinton, Saint Lawrence & Washington") == (("CLINTON", "ST. LAWRENCE", "WASHINGTON"), False)
    assert ny._counties("Part of Nassau & Part of Suffolk") == (("NASSAU", "SUFFOLK"), True)


def test_a_candidate_on_several_party_lines_is_one_candidate_with_every_line():
    filings = ny.parse_lines(LINES)
    assert [(f.name, f.party, f.party_name) for f in filings if f.office == "U.S. Representative District 10"] == [
        ("Brad Lander", "D", "Democratic / Working Families"), ("Jennifer E. Moore", "R", "Republican / Conservative")]
    assert [(f.name, f.party, f.party_name) for f in filings if f.office == "U.S. Representative District 21"] == [
        ("Blake Gendebien", "D", None), ("Anthony Constantino", "R", "Republican / Taxpayer Rights")]
    brooklyn = [f for f in filings if f.office == "Supreme Court Justice, 2nd Judicial District"]  # over a page break
    assert [(f.name, f.party, f.party_name) for f in brooklyn] == [
        ("Betsey Jean Jacques", "D", "Democratic / Republican / Conservative"), ("Hemalee J. Patel", "D", "Democratic / Republican"),
        ("Sherveal Mimes", "D", "Democratic / Republican / Conservative"),
        ("Lola Waterman", "D", "Democratic / Republican / Conservative"), ("William D. Spain Jr", None, "Conservative")]
    assert (by_name(filings, "Karen M. Wilutis").party_name, by_name(filings, "Anthony R. Portesy").party_name) == (
        "Republican / Conservative", "Conservative")  # "Karen M.Wilutis" on her Republican line
    assert [f.name for f in filings if f.office == "Supreme Court Justice, 1st Judicial District"][5:7] == [
        "Christopher Chin", "Amy S. Taylor"]
    assert by_name(filings, "Amy S. Taylor").party_name == "Working Families"
    assert (by_name(filings, "Heather L. Micha").party, by_name(filings, "Heather L. Micha").party_name) == (None, "Coalition")


def test_wrapped_names_and_party_lines_are_read_whole_and_empty_lines_skipped():
    filings = ny.parse_lines(LINES)
    assert [(f.name, f.party, f.party_name) for f in filings if f.office == "Governor and Lieutenant Governor"] == [
        ("Kathy C. Hochul and Adrienne E. Adams", "D", "Democratic / Working Families"),
        ("Bruce A. Blakeman and Todd Hood", "R", "Republican / Conservative / Vote Affordable")]
    assert [(f.name, f.party) for f in filings if f.office == "State Senate District 12"] == [
        ("Aber Kawas", "D"), ("Han-Khon To", "R")]
    assert by_name(filings, "Veronica I. Gonzalez").party_name == "Republican / Conservative"
    assert by_name(filings, "Cristina Fontanelli").party_name == "Republican / Save NYC"
    assert by_name(filings, "Mercedes Vazquez-Simmons").party_name == "Mercedes Simmons Cares"
    assert by_name(filings, "Casey Marie O’Connor-Manasia").party == "R"  # "O’Connor -Manasia"
    assert all(f.name for f in filings) and not any("Working Families" in f.name for f in filings)


def test_a_new_york_certification_it_cant_read_is_refused():
    with pytest.raises(ValueError, match="4 U.S. House races, not 26"):
        require(ny.parse_lines(LINES), ny.MINIMUM)
    with pytest.raises(ValueError, match="no general election's title"):
        ny.parse_lines(["Office: Comptroller"])
    with pytest.raises(ValueError, match="no races"):
        ny.parse_lines(LINES[:1])
    with pytest.raises(ValueError, match="a race without its Vote For: Comptroller"):
        ny.parse_lines([LINES[0], "Office:  Comptroller", "District:  Statewide", "Counties:  All"])
    with pytest.raises(ValueError, match="not a PDF"):
        ny.NyList.parse("Office: Comptroller")


@pytest.mark.parametrize("day", [D(2026, 11, 3), D(2027, 11, 2), D(2028, 11, 7)])
def test_new_yorks_dates_follow_its_election_law(day):
    found = state_key_dates.computed("NY", day)
    assert (day - found.register_by).days == (day - found.mail_apply_by).days == (day - found.early_start).days == 10
    assert (day - found.early_end).days == 2


def test_new_yorks_2026_dates_and_only_its_general_election_has_them():
    found = state_key_dates.computed("NY", D(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        D(2026, 10, 24), D(2026, 10, 24), D(2026, 10, 24), D(2026, 11, 1))
    for day in (D(2026, 6, 23), D(2026, 11, 10)):
        assert state_key_dates.computed("NY", day) is None, day


def test_new_yorks_calendar_is_worked_out_without_asking_anyone(client, upstream):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "NY"})
    assert response.headers["content-disposition"] == 'attachment; filename="new-york-election-2026-11-03.ics"'
    unfolded = response.text.replace("\r\n ", "")
    assert "UID:ny-2026-11-03-early_start@pallot\r\nDTSTAMP" in unfolded and "DTSTART;VALUE=DATE:20261024" in unfolded
    assert "6 a.m. to 9 p.m." in unfolded and "Texas" not in unfolded
    assert upstream.count("elections.ny.gov") == 0


def test_the_import_bundles_the_parsed_candidates_never_the_pdf(tmp_path, pdf):
    counts = imported(tmp_path, pdf)
    assert counts == {"races": 3 + 26 + 4 + 150 + 4, "candidates": len(ny.parse_lines(whole_list()))}
    [answer] = store.load("state_ny", tmp_path / "bundles").answers
    assert answer["request"]["url"] == "manual:state_ny" and set(answer["value"]) == {"filings"}
    assert import_list("ny", pdf, data_dir=tmp_path / "bundles", today=lambda: TODAY).status == "no_changes"


def test_the_import_refuses_cloudflares_page_and_a_partial_certification(tmp_path, monkeypatch):
    saved = tmp_path / "saved.pdf"
    saved.write_text(CLOUDFLARE, encoding="utf-8")
    with pytest.raises(BundleError, match="the site's bot check, not the list"):
        import_list("ny", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    monkeypatch.setattr(ny, "pdf_lines", lambda raw: LINES)
    saved.write_bytes(b"%PDF-1.7 part of it")
    with pytest.raises(BundleError, match="reader understands: 4 U.S. House races, not 26"):
        import_list("ny", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert not (tmp_path / "bundles" / "state_ny.json").exists()


def test_the_bundled_certification_has_every_race():
    [answer] = store.load("state_ny").answers
    filings = answer["value"]["filings"]
    races = {f["office_id"]: f for f in filings}
    assert Counter(f["reach"] for f in races.values()) == {"hd": 150, "sd": 63, "cd": 26, "counties": 11, "state": 3}
    assert len(filings) == 502
    assert sorted(int(f["district"]) for f in races.values() if f["family"] == "SUPREME COURT JUSTICE") == [
        1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 13]


def test_refreshing_the_bundles_never_fetches_new_yorks_certification(tmp_path, upstream):
    outcome = build(tmp_path, "state_ny")
    assert outcome.status == "skipped" and "imported by hand" in outcome.detail
    assert upstream.count("elections.ny.gov") == 0


def test_a_manhattan_ballot_comes_from_the_imported_certification(tmp_path, pdf, upstream, make_app, logged_calls):
    imported(tmp_path, pdf)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "manhattan", all_races=True)
        assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "labels": {"hd": "State Assembly"}}
        assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (10, 27, 65)
        assert [race["name"] for race in ballot["races"]] == [
            "U.S. Representative District 10", "Governor and Lieutenant Governor", "Comptroller", "Attorney General",
            "State Senate District 27", "State Assembly District 65", "Supreme Court Justice, 1st Judicial District"]
        house = find_race(ballot, "U.S. Representative District 10")
        assert house["seat"] == "NY-10" and candidate_names(house) == ["Brad Lander", "Jennifer E. Moore"]
        assert any(card["source"] == "fec" for c in house["candidates"] for card in c["cards"])
        court = find_race(ballot, "Supreme Court Justice, 1st Judicial District")
        assert court["seats"] == 6 and len(court["candidates"]) == 11
        for name in ("Supreme Court Justice, 2nd Judicial District", "Supreme Court Justice, 3rd Judicial District",
                     "State Senate District 46"):
            assert find_race(ballot, name) is None and find_race(ballot, name, maybe=True) is None, name
        assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
        assert ballot["key_dates"] == {
            "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-24",
            "mail_apply_by": "2026-10-24", "early_voting_start": "2026-10-24", "early_voting_end": "2026-11-01",
            "source": "New York State Board of Elections", "source_url": "https://elections.ny.gov/",
            "computed": True,
        }
        get_ballot(client, "manhattan", all_races=True)
        assert logged_calls() == 0
        rows = {row["id"]: row for row in client.get("/api/sources").json()["sources"]}
        assert rows["state_ny"]["notice"].startswith("Imported by hand on ")
    assert upstream.count("elections.ny.gov") == 0


def test_an_albany_ballot_has_its_districts_and_its_judicial_districts_race(tmp_path, pdf, upstream, make_app):
    imported(tmp_path, pdf)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "albany", all_races=True)
    assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (20, 46, 109)
    names = [race["name"] for race in ballot["races"]]
    assert names[:4] == ["U.S. Representative District 20", "Governor and Lieutenant Governor", "Comptroller",
                         "Attorney General"]
    assert {"State Senate District 46", "State Assembly District 109"} <= set(names)
    court = find_race(ballot, "Supreme Court Justice, 3rd Judicial District")
    assert court["seats"] == 2 and candidate_names(court) == ["Amy E. Joyce", "Jennifer G. Sober"]
    assert find_race(ballot, "Supreme Court Justice, 1st Judicial District") is None
    house = find_race(ballot, "U.S. Representative District 20")
    assert candidate_names(house) == ["Paul D. Tonko", "Ralph F. Ambrosio"]
    assert any(card["source"] == "fec" for c in house["candidates"] for card in c["cards"])
    assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
    assert upstream.count("elections.ny.gov") == 0


def test_without_an_imported_certification_new_york_has_the_fecs_races_for_congress(client, upstream):
    ballot = get_ballot(client, "manhattan")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("doesn't have the New York State Board of Elections' certification of the candidates" in n for n in ballot["notes"])
    assert find_race(ballot, "U.S. Representative District 10")
    assert upstream.count("elections.ny.gov") == 0
