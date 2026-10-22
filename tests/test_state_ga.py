"""Georgia: each party's nominees from the SOS's results site (tests/fixtures/state_ga_*.json, the
2026 primary, its recount and runoff cut down to a few races), everyone else from its qualifying
list saved by hand (tests/fixtures/state_ga.json, a few counties' and cities' offices, contact
details made up), and its key dates, worked out from Georgia's election law."""

from __future__ import annotations

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from bundles.entry import BundleError
from bundles.manual import import_list
from pallot.states import Filing
from pallot.states import key_dates as state_key_dates
from pallot.states import ga

from .bundling import answers, build
from .conftest import FIXTURES, TODAY, candidate_names, find_race, get_ballot

D = dt.date
QUALIFYING = FIXTURES / "state_ga.json"
DAY = D(2026, 11, 3)
BLOCKED = ("mvp.sos.ga.gov", "www.sos.ga.gov")


def qualified() -> list[Filing]:
    return ga.qualified(QUALIFYING.read_text(encoding="utf-8"))


def counts() -> list[tuple[bool, dict]]:
    elections = json.loads((FIXTURES / "state_ga_elections.json").read_text(encoding="utf-8"))
    return [(runoff, json.loads((FIXTURES / f"state_ga_{election}.json").read_text(encoding="utf-8")))
            for election, runoff in ga.stages(elections, DAY)]


def nominee(filings: list[Filing], office: str, party: str) -> str:
    [found] = [f.name for f in filings if f.office == office and f.party == party]
    return found


def by_name(filings: list[Filing], name: str) -> Filing:
    return next(f for f in filings if f.name == name)


def imported(tmp_path) -> dict:
    outcome = import_list("ga", QUALIFYING, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert outcome.status == "updated"
    return outcome.counts


def never_the_blocked_sites(upstream) -> None:
    assert not [call for call in upstream.calls if any(f" {host}/" in call for host in BLOCKED)]
    assert not [call for call in upstream.calls if call.split()[1].startswith("sos.ga.gov/")]


def contest(name: str, *votes: tuple[str, int]) -> dict:
    return {"name": [{"languageId": "en", "text": name}], "summaryResults": {"ballotOptions": [
        {"name": [{"languageId": "en", "text": who}], "voteCount": n, "isWriteIn": who == "Write-in"}
        for who, n in votes]}}


def test_the_nominees_are_each_partys_primary_or_runoff_winner():
    found = ga.nominees(counts(), DAY.isoformat())
    assert {f.day for f in found} == {"2026-11-03"}
    assert nominee(found, "Governor", "D") == "Keisha Lance Bottoms"  # a majority in May
    assert nominee(found, "Governor", "R") == "Rick Jackson"  # second in May, won the runoff
    assert nominee(found, "State School Superintendent", "R") == "Richard Woods"  # 49.9% in May
    assert nominee(found, "Public Service Commission District 3", "R") == "Fitz Johnson"  # the recount's count
    assert nominee(found, "State House District 58", "D") == "Mathewos Samson"
    ossoff = by_name(found, "Jon Ossoff")
    assert (ossoff.office, ossoff.reach, ossoff.incumbent, ossoff.group) == ("U.S. Senator", "state", True, "federal")
    williams = by_name(found, "Nikema Williams")
    assert (williams.office, williams.reach, williams.district) == ("U.S. Representative District 5", "cd", "5")
    orrock = by_name(found, "Nan Grogan Orrock")
    assert (orrock.office, orrock.reach, orrock.district, orrock.group) == ("State Senate District 36", "sd", "36", "legislature")
    assert by_name(found, "Billy Joe Nelson, Jr.").reach == "unplaced"  # a district attorney's circuit
    assert [f.party for f in found if f.office == "U.S. Senator"] == ["R", "D"]
    assert not [f for f in found if "Senate District 7" in f.office or "Justice" in f.office or "Question" in f.office]


def test_a_contest_no_count_settles_has_no_nominee():
    primary = {"ballotItems": [
        contest("Governor - Rep", ("Ann", 40), ("Bea", 35), ("Cy", 25)),  # no majority, and no runoff
        contest("Attorney General - Dem", ("Dee", 60), ("Write-in", 50)),  # write-ins don't count
        contest("Commissioner of Labor - Rep", ("Eve", 50), ("Flo", 50)),
        contest("Justice - Supreme Court of Georgia (Land)", ("Gus", 100)),
    ]}
    runoff = {"ballotItems": [contest("Commissioner of Labor - Rep", ("Eve", 10), ("Flo", 10))]}
    found = ga.nominees([(False, primary), (True, runoff)], "2026-11-03")
    assert [(f.office, f.name) for f in found] == [("Attorney General", "Dee")]
    with pytest.raises(ValueError, match="ballotItems"):
        ga.contests({"election": {}})


def test_the_counts_are_the_years_primary_its_recounts_and_its_runoff():
    def election(eid: str, date: str, name: str) -> dict:
        return {"publicElectionId": eid, "electionDate": date, "name": [{"languageId": "en", "text": name}]}

    listed = {"elections": [
        election("RUNOFF", "2026-06-16", "June 16th, 2026 General Primary Runoff"),
        election("SPECIAL", "2026-06-09", "June 9th, 2026 Special Election Runoff"),
        election("RECOUNT", "2026-05-19", "RECOUNT - May 19th, 2026 PSC District 3-REP"),
        election("PRIMARY", "2026-05-19", "May 19, 2026 - General Primary"),
        election("PPP", "2026-03-10", "March 10, 2026 Presidential Preference Primary"),
        election("OLD", "2024-05-21", "May 21, 2024 - General Primary"),
    ]}
    assert ga.stages(listed, DAY) == [("PRIMARY", False), ("RECOUNT", False), ("RUNOFF", True)]
    assert ga.stages(listed, D(2028, 11, 7)) == []  # before 2028's primary is listed


def test_the_qualifying_list_keeps_the_qualified_and_their_ballot_names_parties_and_places():
    filings = qualified()
    names = {f.name for f in filings}
    assert {f.day for f in filings} == {"2026-11-03"}
    assert {"Allen Buckley", "Chase Russell Oliver", "Christina Potts", "Dan Hunt"}.isdisjoint(names)  # disqualified, withdrawn
    assert {"Anthony Clayton Woodard", "William Jackson Jones Jr"}.isdisjoint(names)  # withdrew from Telfair's
    assert 'Thomas "Josh" Sappington' in names
    lockhart = by_name(filings, "Travis Terrell Lockhart")
    assert (lockhart.office, lockhart.reach, lockhart.district, lockhart.party) == ("State House District 151", "hd", "151", None)
    soil = by_name(filings, "Jason Ulseth")
    assert (soil.office, soil.reach, soil.counties, soil.group, soil.incumbent) == (
        "Soil and Water District Supervisor", "county", ("FULTON",), "county", True)
    commission = by_name(filings, "Rohit Malhotra")
    assert (commission.reach, commission.counties, commission.party, commission.unexpired) == (
        "part_county", ("FULTON",), "D", True)
    assert by_name(filings, "Carl S. Cansino").office == "State Court Solicitor"  # "(DUPLICATE)" left out
    assert by_name(filings, "Daren Bear Osborn").office == "Sheriff"
    danville = by_name(filings, "Maggie Jackson")
    assert (danville.office, danville.reach, danville.city, danville.counties) == (
        "City Council, City of Danville", "city", "DANVILLE", ("TWIGGS",))
    assert by_name(filings, "Eric Carelock").counties == ("JEFF DAVIS",)
    assert by_name(filings, "Eric Carelock").reach == "part_city"  # a ward
    assert by_name(filings, "Tom Hart").reach == "part_city"  # a district's at-large post
    assert by_name(filings, "Conor Sen").reach == "part_city"
    branch = by_name(filings, "Edward Ray Asbridge")
    assert (branch.office, branch.party, branch.party_name) == ("City Council Member Post 3, City of Flowery Branch", None, None)
    assert by_name(filings, "Patricia Dupree Brooks").party == "R"
    assert by_name(filings, "Laurie Elyse Baio").reach == "unplaced"
    assert by_name(filings, "Timothy Britt Goolsby").office == "Office not named in the list"


def test_a_qualifying_file_it_cant_read_is_refused():
    with pytest.raises(ValueError, match="not JSON"):
        ga.qualified("<!DOCTYPE html><title>Just a moment...</title>")
    with pytest.raises(ValueError, match="no candidates where"):
        ga.qualified(json.dumps({"actions": []}))
    row = {"Name_on_Ballot__c": "ANN LEE", "Declaration__c": "Qualified", "Candidate_Party__c": "Non-Partisan"}
    with pytest.raises(ValueError, match="no qualifying dates"):
        ga.qualified(json.dumps({"actions": [{"returnValue": {"returnValue": {"Countywide": {"FULTON": {"Sheriff": [row]}}}}}]}))
    gone = {**row, "Declaration__c": "Withdrawn", "Date_Qualified__c": "3/5/2026"}
    with pytest.raises(ValueError, match="no qualified candidates"):
        ga.qualified(json.dumps({"actions": [{"returnValue": {"returnValue": {"Countywide": {"FULTON": {"Sheriff": [gone]}}}}}]}))


def test_the_nominees_and_the_qualifying_list_make_one_ballot():
    def filing(office_id: str, name: str, party: str | None) -> Filing:
        return Filing(day="2026-11-03", office_id=office_id, office=office_id.title(), family=office_id, group="state",
                      reach="state", district=None, name=name, party=party)

    nominated = [filing("GOVERNOR", "Rick Jackson", "R"), filing("GOVERNOR", "Keisha Lance Bottoms", "D")]
    listed = [filing("GOVERNOR", "Rick Jackson", "R"), filing("GOVERNOR", "Lee Lib", "L"),
              filing("GOVERNOR", "Ida Indy", None), filing("SHERIFF (TOWNS)", "Ray Rep", "R")]
    assert [f.name for f in ga.merge(nominated, listed)] == [
        "Rick Jackson", "Keisha Lance Bottoms", "Lee Lib", "Ida Indy", "Ray Rep"]


@pytest.mark.parametrize("day", [D(2026, 11, 3), D(2028, 11, 7), D(2030, 11, 5)])
def test_georgias_dates_follow_its_election_law(day):
    found = state_key_dates.computed("GA", day)
    assert found.register_by.weekday() == 0 and (day - found.register_by).days == 29  # the fifth Monday before
    assert (day - found.mail_apply_by).days == 11
    assert found.early_end.weekday() == 4 and (day - found.early_end).days == 4  # the Friday before
    fourth_monday = day - dt.timedelta(days=22)
    holiday = state_key_dates.columbus_day(day.year)
    assert found.early_start == (fourth_monday + dt.timedelta(days=1) if fourth_monday == holiday else fourth_monday)


def test_georgias_2026_dates_and_only_its_general_election_has_them():
    found = state_key_dates.computed("GA", DAY)
    assert (found.register_by, found.mail_apply_by, found.early_start, found.early_end) == (
        D(2026, 10, 5), D(2026, 10, 23), D(2026, 10, 13), D(2026, 10, 30))  # Monday Oct 12 is Columbus Day
    assert state_key_dates.computed("GA", D(2028, 11, 7)).early_start == D(2028, 10, 16)
    for day in (D(2026, 5, 19), D(2027, 11, 2), D(2026, 11, 10)):
        assert state_key_dates.computed("GA", day) is None, day


def test_georgias_calendar_is_worked_out_without_asking_anyone(client, upstream):
    response = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "GA"})
    assert response.headers["content-disposition"] == 'attachment; filename="georgia-election-2026-11-03.ics"'
    unfolded = response.text.replace("\r\n ", "")
    assert "DTSTART;VALUE=DATE:20261013" in unfolded and "7 a.m. to 7 p.m." in unfolded and "Texas" not in unfolded
    mail = client.get("/api/key-dates.ics", params={"date": "2026-11-03", "state": "GA", "event": "mail"}).text
    assert "SUMMARY:Absentee ballot application due (Nov 3 election)" in mail and "DTSTART;VALUE=DATE:20261023" in mail
    assert upstream.calls == []


def test_the_import_bundles_the_parsed_candidates_never_the_contact_details(tmp_path):
    counts = imported(tmp_path)
    assert counts == {"races": 18, "candidates": 38}
    [answer] = answers(tmp_path, "state_ga")
    assert answer["request"]["url"] == "manual:state_ga" and set(answer["value"]) == {"filings"}
    text = (tmp_path / "bundles" / "state_ga.json").read_text(encoding="utf-8")
    assert "example.com" not in text and "555-" not in text and "made up" not in text
    assert import_list("ga", QUALIFYING, data_dir=tmp_path / "bundles", today=lambda: TODAY).status == "no_changes"


def test_the_import_refuses_cloudflares_check_and_a_file_that_isnt_the_list(tmp_path):
    saved = tmp_path / "georgia.json"
    saved.write_text("<!DOCTYPE html><html><head><title>Just a moment...</title></head></html>", encoding="utf-8")
    with pytest.raises(BundleError, match="the site's bot check, not the list"):
        import_list("ga", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    saved.write_text(json.dumps({"actions": [{"returnValue": None}]}), encoding="utf-8")
    with pytest.raises(BundleError, match="isn't a list the Georgia Secretary of State's reader understands"):
        import_list("ga", saved, data_dir=tmp_path / "bundles", today=lambda: TODAY)
    assert not (tmp_path / "bundles" / "state_ga.json").exists()


def test_the_nominees_are_bundled_from_the_results_site_and_the_list_never_fetched(tmp_path, upstream):
    assert build(tmp_path, "state_ga").status == "skipped"
    outcome = build(tmp_path, "state_ga_results")
    assert outcome.status == "updated" and outcome.counts == {"races": 13, "candidates": 25}
    bundled = answers(tmp_path, "state_ga_results")
    assert {a["request"]["url"].rsplit("/", 2)[-2] for a in bundled} == {
        "GeneralPrimary51926", "RECOUNTPSCDistrict3", "06162026GeneralPrimaryRunoff", "jurisdictions"}
    primary = next(a["value"] for a in bundled if "GeneralPrimary51926" in a["request"]["url"])
    assert not [item for item in primary["ballotItems"] if "Justice" in json.dumps(item["name"])]
    assert {call.split()[1].split("/")[0] for call in upstream.calls} == {"results.sos.ga.gov"}
    never_the_blocked_sites(upstream)


def test_an_atlanta_ballot_has_the_nominees_and_the_imported_list(tmp_path, upstream, make_app, logged_calls):
    imported(tmp_path)
    with TestClient(make_app(bundles=tmp_path / "bundles")) as client:
        ballot = get_ballot(client, "atlanta", all_races=True)
        assert ballot["coverage"] == {**ballot["coverage"], "ballot": "list", "districts": ["cd", "sd", "hd"]}
        assert (ballot["districts"]["cd"], ballot["districts"]["sd"], ballot["districts"]["hd"]) == (5, 36, 58)
        for name in ("U.S. Senator", "Governor", "Public Service Commission District 3", "U.S. Representative District 5",
                     "State Senate District 36", "State House District 58", "Soil and Water District Supervisor"):
            assert find_race(ballot, name), name
        for name in ("U.S. Representative District 11", "State House District 151", "Sheriff",
                     "City Council, City of Danville"):
            assert find_race(ballot, name) is None, name
        assert find_race(ballot, "County Commissioner District 4 (Unexpired Term of Mo Ivory, Resigned)", maybe=True)
        senate = find_race(ballot, "U.S. Senator")
        assert candidate_names(senate) == ["Mike Collins", "Jon Ossoff"] and senate["seat"] == "GA-SEN"
        assert [c["party"] for c in senate["candidates"]] == ["R", "D"]
        assert find_race(ballot, "U.S. Representative District 5")["seat"] == "GA-05"
        assert candidate_names(find_race(ballot, "State House District 58")) == ["Torrey Balam", "Mathewos Samson"]
        assert not any(c["unverified"] for race in ballot["races"] for c in race["candidates"])
        assert any("2 District Attorney races" in note for note in ballot["notes"])
        assert ballot["key_dates"] == {
            "election": "General Election", "election_day": "2026-11-03", "register_by": "2026-10-05",
            "mail_apply_by": "2026-10-23", "early_voting_start": "2026-10-13", "early_voting_end": "2026-10-30",
            "source": "Georgia Secretary of State", "source_url": "https://sos.ga.gov/elections", "computed": True,
        }
        get_ballot(client, "atlanta", all_races=True)
        assert logged_calls() == 0
        rows = {row["id"]: row for row in client.get("/api/sources").json()["sources"]}
        assert rows["state_ga"]["notice"].startswith("Imported by hand on ")
    never_the_blocked_sites(upstream)


def test_without_an_imported_list_an_atlanta_ballot_has_the_party_nominees(client, upstream):
    ballot = get_ballot(client, "atlanta")
    assert ballot["coverage"]["ballot"] == "list"
    assert candidate_names(find_race(ballot, "Governor")) == ["Rick Jackson", "Keisha Lance Bottoms"]
    assert find_race(ballot, "Soil and Water District Supervisor") is None
    rows = {row["id"]: row for row in client.get("/api/sources").json()["sources"]}
    assert rows["state_ga"]["notice"] == ("No list imported yet, so ballots here have only the party nominees from "
                                          "its primaries.")
    never_the_blocked_sites(upstream)


def test_without_the_results_site_or_a_kept_copy_georgia_falls_back_to_the_fec(client, upstream):
    upstream.down.add("results.sos.ga.gov")
    ballot = get_ballot(client, "atlanta")
    assert ballot["coverage"]["ballot"] == "fec"
    assert any("Couldn't load the list of candidates from the Georgia Secretary of State" in w for w in ballot["warnings"])
    assert find_race(ballot, "U.S. Representative District 5")
