"""Iowa: the Secretary of State's candidate list, a PDF saved by hand (tests/fixtures/state_ia.txt,
a few of its text lines as pdf_lines reads them, every candidate's contact details made up, with
the rest of the State House made up here), and its key dates, worked out from the Iowa Code."""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from bundles import store
from bundles.entry import BundleError
from bundles.manual import import_list
from pallot.states import from_json, ia
from pallot.states import key_dates as state_key_dates

from .bundling import build
from .conftest import FIXTURES, TODAY, candidate_names, find_race, get_ballot

D = dt.date
LINES = FIXTURES / "state_ia.txt"
CLOUDFLARE = "<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>challenges.cloudflare.com</body></html>"
TITLE = "                                         November 3, 2026 General Election"
FOOTER = ("Filing period for federal and state offices for NPPO and petition candidates:  February 23 - June 2 at 5:00 "
          "p.m.                     Last Updated")
MADE_UP = "Pat Doe"


def row(office: str, party: str, name: str, date: str = "3/2/2026") -> str:
    return (f"{office:<52}{party:<16}{name:<35}PO Box 1, Des Moines, IA 50301          515-555-0100      "
            f"candidate@example.com          {date}")


def ia_lines(house: int = ia.MIN_STATE_HOUSE) -> list[str]:
    """The fixture's lines, and a made-up candidate for each State House district up to ``house`` it leaves out."""
    lines = LINES.read_text(encoding="utf-8").splitlines()
    have = {line.split("District ")[1].split()[0] for line in lines if line.startswith("State Representative")}
    return lines + [FOOTER] + [row(f"State Representative District {n}", "Republican", MADE_UP)
                               for n in range(1, house + 1) if str(n) not in have]


def ia_filings() -> list:
    return [f for f in ia.parse_lines(ia_lines()) if f.name != MADE_UP]


@pytest.fixture
def saved(tmp_path, monkeypatch):
    """The list as a saved PDF: its bytes are made up, and reading it gives ia_lines()."""
    path = tmp_path / "candidate-list.pdf"
    path.write_bytes(b"%PDF-1.7 the saved list")
    monkeypatch.setattr(ia, "pdf_lines", lambda raw: ia_lines() if raw == path.read_bytes() else [])
    return path


def imported(tmp_path, saved) -> dict:
    outcome = import_list("ia", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert outcome.status == "updated"
    return outcome.counts


def by_name(filings: list, name: str):
    return next(f for f in filings if f.name == name)


def test_iowas_list_has_its_races_parties_and_ballot_names():
    filings = ia_filings()
    assert {f.day for f in filings} == {"2026-11-03"}
    assert Counter(f.reach for f in filings) == {"cd": 11, "state": 17, "sd": 5, "hd": 3}
    assert Counter(f.party for f in filings) == {"R": 15, "D": 17, "L": 2, None: 2}
    assert [(f.name, f.party) for f in filings if f.office == "U.S. Senator"] == [
        ("Ashley Hinson", "R"), ("Josh Turek", "D"), ("Thomas Laehn", "L")]
    bridgford = by_name(filings, "Michael Bridgford")
    assert (bridgford.office, bridgford.reach, bridgford.district, bridgford.party, bridgford.party_name) == (
        "U.S. Representative District 1", "cd", "1", None, None)
    assert [f.office for f in filings if f.reach == "state" and f.party == "D"] == [
        "U.S. Senator", "Governor", "Lieutenant Governor", "Secretary of State", "Auditor of State",
        "Treasurer of State", "Secretary of Agriculture", "Attorney General"]
    assert (by_name(filings, "Rob Sand").family, by_name(filings, "Dave Muhlbauer").family) == (
        "GOVERNOR", "LIEUTENANT GOVERNOR")
    assert by_name(filings, "Paul D. Pate").group == "state"


def test_iowas_legislative_races_reach_their_districts_and_a_party_without_a_candidate_is_left_out():
    filings = ia_filings()
    langston = by_name(filings, "Ronald Langston")
    assert (langston.office, langston.reach, langston.district, langston.group, langston.family) == (
        "State Senator District 17", "sd", "17", "legislature", "STATE SENATE")
    muhammad = by_name(filings, "Ivette Muhammad")
    assert (muhammad.office, muhammad.reach, muhammad.district, muhammad.family) == (
        "State Representative District 33", "hd", "33", "STATE HOUSE")
    assert [(f.name, f.party) for f in filings if f.office == "State Senator District 15"] == [("Tony Bisignano", "D")]
    assert [f.name for f in filings if f.office == "State Representative District 34"] == ["Rob Johnson"]
    assert not any("--" in f.name or "@" in f.name for f in filings)


def test_an_iowa_list_it_cant_read_or_that_isnt_all_of_it_is_refused():
    with pytest.raises(ValueError, match="title"):
        ia.parse_lines([row("Governor", "Republican", "Zach Lahn")])
    with pytest.raises(ValueError, match="an office it doesn't know: County Sheriff"):
        ia.parse_lines([TITLE, row("County Sheriff", "Republican", "Pat Roe")])
    with pytest.raises(ValueError, match="can't split"):
        ia.parse_lines([TITLE, "                                                    Republican      Pat Roe"])
    with pytest.raises(ValueError, match="can't split"):
        ia.parse_lines([TITLE, row("Governor", "Republican", "Pat Roe").rsplit(" ", 1)[0]])
    with pytest.raises(ValueError, match="only 99 State House races"):
        ia.parse_lines(ia_lines(house=99))
    lines = [line for line in ia_lines() if "United States Representative District 4" not in line]
    with pytest.raises(ValueError, match="only 3 U.S. House races"):
        ia.parse_lines(lines)
    with pytest.raises(ValueError, match="not a PDF"):
        ia.IaList.parse(CLOUDFLARE)


def test_the_bundled_list_has_every_race_and_no_candidates_contact_details():
    [answer] = store.load("state_ia", store.PACKAGE_DATA_DIR).answers
    assert answer["request"]["url"] == "manual:state_ia" and set(answer["value"]) == {"filings"}
    filings = from_json(answer["value"])
    assert len({f.office_id for f in filings}) == 137 and len(filings) == 245
    assert Counter(f.reach for f in filings) == {"hd": 173, "sd": 44, "state": 17, "cd": 11}
    assert len({f.office_id for f in filings if f.reach == "sd"}) == 25
    assert {int(f.district) for f in filings if f.reach == "sd"} == set(range(1, 50, 2))
    assert {int(f.district) for f in filings if f.reach == "hd"} == set(range(1, 101))
    assert Counter(f.party for f in filings) == {"D": 124, "R": 111, None: 8, "L": 2}
    text = json.dumps(answer)
    assert "@" not in text and "PO Box" not in text and ", IA 5" not in text and "515-" not in text


@pytest.mark.parametrize("day", [D(2026, 11, 3), D(2028, 11, 7), D(2030, 11, 5)])
def test_iowas_dates_follow_the_iowa_code(day):
    found = state_key_dates.computed("IA", day)
    assert (day - found.register_by).days == 15 and found.mail_apply_by == found.register_by
    assert (day - found.early_start).days == 20 and (day - found.early_end).days == 1


def test_iowas_2026_dates_and_only_its_general_election_has_them():
    found = state_key_dates.computed("IA", D(2026, 11, 3))
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        D(2026, 10, 19), D(2026, 10, 19), D(2026, 10, 14), D(2026, 11, 2))
    for day in (D(2026, 6, 2), D(2027, 11, 2), D(2026, 11, 10)):
        assert state_key_dates.computed("IA", day) is None, day


def test_iowas_calendar_is_worked_out_without_asking_anyone(client, upstream):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "IA"})
    assert response.headers["content-disposition"] == 'attachment; filename="iowa-election-2026-11-03.ics"'
    unfolded = response.text.replace("\r\n ", "")
    assert "UID:ia-2026-11-03-early_start@pallot\r\nDTSTAMP" in unfolded and "DTSTART;VALUE=DATE:20261014" in unfolded
    assert "7 a.m. to 8 p.m." in unfolded and "Texas" not in unfolded
    mail = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "IA", "event": "mail"}).text
    assert "SUMMARY:Absentee ballot request due (Nov 3 election)" in mail and "DTSTART;VALUE=DATE:20261019" in mail
    assert upstream.count("sos.iowa.gov") == 0


def test_the_import_bundles_the_parsed_candidates_never_the_pdf(tmp_path, saved):
    counts = imported(tmp_path, saved)
    assert counts == {"races": 17 + 98, "candidates": 36 + 98}
    [answer] = store.load("state_ia", tmp_path / "bundles").answers
    assert answer["request"]["url"] == "manual:state_ia" and set(answer["value"]) == {"filings"}
    text = (tmp_path / "bundles" / "state_ia.json").read_text(encoding="utf-8")
    assert "candidate@example.com" not in text and "515-555-0100" not in text and "PO Box" not in text
    assert import_list("ia", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY).status == "no_changes"


def test_the_import_refuses_cloudflares_page_and_a_file_that_isnt_the_list(tmp_path, saved):
    page = tmp_path / "saved.pdf"
    page.write_text(CLOUDFLARE, encoding="utf-8")
    with pytest.raises(BundleError, match="the site's bot check, not the list"):
        import_list("ia", page, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    page.write_bytes(b"%PDF-1.7 cut short")
    with pytest.raises(BundleError, match="isn't a list the Iowa Secretary of State's reader understands"):
        import_list("ia", page, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert not (tmp_path / "bundles" / "state_ia.json").exists()


def test_refreshing_the_bundles_never_fetches_iowas_list(tmp_path, upstream):
    for due in (False, True):
        outcome = build(tmp_path, "state_ia", due=due)
        assert outcome.status == "skipped" and "imported by hand" in outcome.detail
    assert upstream.count("sos.iowa.gov") == 0


def test_a_des_moines_ballot_comes_from_the_imported_list(tmp_path, saved, upstream, make_app, logged_calls):
    imported(tmp_path, saved)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "desmoines", all_races=True)
        assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "labels": {}}
        assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (3, 17, 33)
        names = [race["name"] for race in ballot["races"]]
        for name in ("U.S. Senator", "U.S. Representative District 3", "Governor", "Lieutenant Governor",
                     "Secretary of State", "Auditor of State", "Treasurer of State", "Secretary of Agriculture",
                     "Attorney General", "State Senator District 17", "State Representative District 33"):
            assert name in names, name
        for name in ("U.S. Representative District 1", "State Senator District 15", "State Senator District 19",
                     "State Representative District 34"):
            assert find_race(ballot, name) is None and find_race(ballot, name, maybe=True) is None, name
        senate = find_race(ballot, "U.S. Senator")
        assert senate["source"] == "state_ia" and senate["seat"] == "IA-SEN"
        house = find_race(ballot, "U.S. Representative District 3")
        assert house["seat"] == "IA-03" and candidate_names(house) == ["Zach Nunn", "Sarah Trone Garriott"]
        assert any(card["source"] == "fec" for c in house["candidates"] + senate["candidates"] for card in c["cards"])
        assert candidate_names(find_race(ballot, "State Senator District 17")) == ["Ronald Langston", "Samy El-Baroudi"]
        assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
        assert ballot["key_dates"] == {
            "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-19",
            "mail_apply_by": "2026-10-19", "early_voting_start": "2026-10-14", "early_voting_end": "2026-11-02",
            "source": "Iowa Secretary of State", "source_url": "https://sos.iowa.gov/general-election",
            "computed": True,
        }
        get_ballot(client, "desmoines", all_races=True)
        assert logged_calls() == 0
        rows = {row["id"]: row for row in client.get("/api/sources").json()["sources"]}
        assert rows["state_ia"]["notice"].startswith("Imported by hand on ")
    assert upstream.count("sos.iowa.gov") == 0


def test_without_an_imported_list_iowa_has_the_fecs_races_for_congress(client, upstream):
    ballot = get_ballot(client, "desmoines")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("doesn't have the Iowa Secretary of State's list of candidates" in n for n in ballot["notes"])
    assert find_race(ballot, "U.S. Representative District 3")
    assert upstream.count("sos.iowa.gov") == 0
