"""The live endorsement feeds: each organization's adapter, the cards they give like a frozen
list's, the copy kept a week (a second lookup asks no one), a refusal's pause, and the row in
Settings with Refresh and Clear (tests/fixtures/endorsement_feeds holds each recorded list)."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from pallot.admin import SOURCES
from pallot.models import Candidate, Race
from pallot.sources.endorsement_feeds import FEEDS, cair_action, muslims_united
from pallot.sources.endorsements import ENDORSEMENTS_DIR, FLAG, EndorsementList, read_entry

from .conftest import get_ballot, last_use, load

MUPAC = "mupac"
FEED_HOST = "muslimsunitedpac.com"
CAIR = "cair"
CAIR_HOST = "cairactionguide.org"
CAIR_TX = "https://cairactionguide.org/explore#state-tx"
ENDORSED = "Endorsed: strong alignment, integrity, and clear community benefit."


def row(client: TestClient, source: str = MUPAC) -> dict:
    return next(s for s in client.get("/api/sources").json()["sources"] if s["id"] == source)


def cards_from(ballot: dict, source: str = MUPAC) -> dict[str, dict]:
    return {p["name"]: c for r in ballot["races"] for p in r["candidates"] for c in p["cards"] if c["source"] == source}


def test_feed_ids_are_their_own():
    ids = [feed.source for feed in FEEDS]
    files = {path.stem for path in ENDORSEMENTS_DIR.glob("*.json")}
    assert len(set(ids)) == len(ids) and not set(ids) & ({info.id for info in SOURCES} | files)


def test_muslims_united_entries():
    found = {entry["name"]: entry for entry in muslims_united(load(f"endorsement_feeds/{MUPAC}.json"))}
    assert len(found) == 26  # incumbents and challengers; "total" is a count, skipped
    assert found["Al Green"] == {
        "name": "Al Green", "state": "TX", "office": "U.S. House", "district": "18", "party": "Democratic", "note": None,
        "url": "https://muslimsunitedpac.com/endorsements/al-green-tx"}
    assert found["Rashida Tlaib"]["note"].startswith("The only Palestinian-American in Congress")  # its "ourTake"
    assert (found["Bernie Sanders"]["office"], found["Bernie Sanders"]["district"]) == ("U.S. Senate", None)
    assert found["Ruwa Romman"]["office"] == "Governor of Georgia"  # its officeName, which names a seat too
    assert found["Zohran Mamdani"]["office"] == "Mayor of New York City"
    assert [read_entry(raw, n, MUPAC)["name"] for n, raw in enumerate(found.values())] == list(found)


def test_muslims_united_leaves_out_what_it_cant_read():
    with pytest.raises(ValueError):
        muslims_united([])
    answer = {"incumbents": [
        {"id": "1", "name": "Al Green", "officeType": "US House", "state": "TX", "district": "18", "slug": "../x"},
        {"id": "1", "name": "Al Green", "officeType": "US House", "state": "TX", "district": "18"},
        "not a candidate",
    ], "total": 2}
    assert muslims_united(answer) == [{"name": "Al Green", "state": "TX", "office": "U.S. House", "district": "18",
                                       "party": None, "note": None, "url": None}]


def test_cair_action_entries():
    entries = cair_action(load(f"endorsement_feeds/{CAIR}.json"))
    assert len(entries) == 591  # 594 endorsements: three candidates are there for a primary and its runoff
    assert [read_entry(raw, n, CAIR)["name"] for n, raw in enumerate(entries)] == [e["name"] for e in entries]
    texas = {e["name"]: (e["office"], e["district"], e["jurisdiction"]) for e in entries if e["state"] == "TX"}
    assert texas == {
        "Al Green": ("U.S. Representative", "18", None),  # congressional "TX-18"
        "Zeeshan Hafeez": ("U.S. Representative", "33", None),
        "Greg Casar": ("U.S. Representative", "37", None),
        "Staci Childs": ("State Representative", "131", None),  # state_lower "State House District 131"
        "Ron Reynolds": ("State Representative", "27", None),
        "Montserrat Garibay": ("State Representative", "49", None),
        "Jeremy Hendricks": ("State Representative", "50", None),  # lost the primary: kept, as CAIR keeps it
        "Brittany Black": ("State Representative", "61", None),
        "Stephanie Limon Bazan": ("State Board of Education", "5", None),  # special_district
        "Allison Bush": ("State Board of Education", "5", None),
        "Tiffany Perkinz": ("State Board of Education", "7", None),
        "Brittanye Morris": ("Fort Bend County Commissioner", "4", "Fort Bend"),  # "… Commissioner Pct 4"
        "Susanna Ledesma Woody": ("Travis County Commissioner", "4", "Travis"),  # "…, Precinct 4"
        "Dexter McCoy": ("Fort Bend County Judge", None, "Fort Bend"),
        "Letitia Plummer": ("Harris County Judge", None, "Harris"),
        "Audrie Lawton-Evans": ("Harris County Attorney", None, "Harris"),
        "Joe Panzarella": ("Houston City Council District C", None, None),  # municipal: its name, no county
    }
    casar = next(e for e in entries if e["name"] == "Greg Casar")
    assert (casar["party"], casar["note"], casar["url"]) == ("Democrat", ENDORSED, CAIR_TX)
    others = {(e["state"], e["name"]): e for e in entries}
    haney = others[("CA", "Matt Haney")]  # a "State Assembly Member" names no seat; its kind's office does
    assert (haney["office"], haney["district"], haney["url"]) == (
        "State Representative", "17", "https://cairactionguide.org/explore#state-ca")
    gee = others[("CA", "Natalie Gee")]  # a county office whose name starts with no county: its name
    assert (gee["office"], gee["district"], gee["jurisdiction"]) == (
        "San Francisco Board of Supervisors, District 4", None, None)
    preferred = next(e for e in entries if e["note"].startswith("Preferred"))
    assert preferred["note"] == "Preferred: supportive overall and open to stronger partnership."


def test_cair_action_keeps_one_entry_a_candidate_and_only_endorsements():
    with pytest.raises(ValueError):
        cair_action({"endorsements": []})

    def endorsement(level="Endorsed", date="2026-03-03", kind="primary", **extra):
        return {"candidateId": 7, "candidateName": "Greg Casar", "party": None, "status": "published",
                "endorsementLevel": level, "notes": None, "electionResult": None,
                "jurisdiction": {"kind": "congressional", "name": "TX-37", "state": "TX"},
                "office": {"level": "federal", "title": "U.S. Representative"},
                "election": {"type": kind, "electionDate": date}, **extra}

    found = cair_action([
        endorsement("Preferred"),
        endorsement("Endorsed", "2026-05-26", "runoff", notes="Runoff pick.", electionResult="Lost"),
        endorsement("Endorsed", "2026-11-03", "general", candidateId=8,
                    jurisdiction={"kind": "state_lower", "name": "State House District 49", "state": "TX"},
                    office={"title": "State Representative"}),
        endorsement("Oppose", candidateId=9), endorsement("No Recommendation", candidateId=10),
        endorsement(status="pending", candidateId=11), endorsement(candidateName=" ", candidateId=12),
        "not an endorsement",
    ])
    assert found == [
        {"name": "Greg Casar", "state": "TX", "office": "U.S. Representative", "district": "37", "jurisdiction": None,
         "party": None, "note": f"{ENDORSED} Runoff pick.", "url": CAIR_TX},  # the runoff's, the latest; lost, still kept
        {"name": "Greg Casar", "state": "TX", "office": "State Representative", "district": "49", "jurisdiction": None,
         "party": None, "note": ENDORSED, "url": CAIR_TX},  # another candidate id: another entry
    ]


def test_cair_action_reads_every_kind_of_seat():
    def seat(kind, name, title, state="TX"):
        entry = cair_action([{"candidateName": "A B", "endorsementLevel": "Endorsed",
                              "jurisdiction": {"kind": kind, "name": name, "state": state}, "office": {"title": title}}])[0]
        return entry["office"], entry["district"], entry["jurisdiction"]

    assert seat("congressional", "TX-18", "U.S. Representative") == ("U.S. Representative", "18", None)
    assert seat("state_lower", "State House District 131", "State Representative") == ("State Representative", "131", None)
    assert seat("state_upper", "State Senate District 14", "State Senator") == ("State Senator", "14", None)
    assert seat("state", "Texas", "U.S. Senator") == ("U.S. Senator", None, None)
    assert seat("state", "Texas", "Attorney General") == ("Attorney General", None, None)
    assert seat("special_district", "State Board of Education District 5", "State Board of Education") == (
        "State Board of Education", "5", None)
    assert seat("county", "Fort Bend County Commissioner Pct 4", "County Commissioner") == (
        "Fort Bend County Commissioner", "4", "Fort Bend")
    assert seat("county", "Harris County Attorney", "County Attorney") == ("Harris County Attorney", None, "Harris")
    assert seat("county", "Fort Bend County Judge", "County Judge") == ("Fort Bend County Judge", None, "Fort Bend")
    assert seat("county", "Travis County Sheriff", "Travis County Sheriff") == ("Travis County Sheriff", None, "Travis")
    assert seat("municipal", "Houston City Council District C", "City Council Member") == (
        "Houston City Council District C", None, None)
    assert seat("school_district", "Austin ISD Board, District 2", "School Board Member") == (
        "Austin ISD Board, District 2", None, None)
    assert seat("judicial_district", "Alameda County Superior Court Judge, Seat 19", "Superior Court Judge", "CA") == (
        "Alameda County Superior Court Judge", None, "Alameda")
    assert seat("state_lower", "Washington House LD 10, Pos. 1", "Washington House LD 10, Pos. 1", "WA") == (
        "State Representative", "10", None)
    assert seat("a kind it doesn't know", "Somewhere", "Dogcatcher") == ("Dogcatcher", None, None)


def race(name, *candidates, key, seat):
    return Race(key=key, name=name, group="federal", source="sos", seat=seat,
                candidates=[Candidate(key=f"{key}:{i}", name=n, party=p) for i, (n, p) in enumerate(candidates)])


def test_entries_match_as_a_frozen_lists_do():
    entries = [read_entry(raw, n, MUPAC) for n, raw in enumerate(muslims_united(load(f"endorsement_feeds/{MUPAC}.json")))]
    found = EndorsementList(source=MUPAC, label="Muslims United PAC", organization="Muslims United PAC",
                            url="https://muslimsunitedpac.com/endorsements", captured="2026-10-04",
                            description="", entries=entries, live=True)
    races = [race("U.S. Representative District 18", ("Al Green", "D"), ("Ronald Whitfield", "R"), key="sos:1:18", seat="TX-18"),
             race("U.S. Representative District 9", ("Al Green", "D"), key="sos:1:9", seat="TX-09"),
             race("U.S. Representative District 12", ("Rashida Tlaib", "D"), key="sos:1:12", seat="TX-12")]
    cards = found.cards(races, {}, "Harris").candidates
    assert {key: card.match.confidence for key, card in cards.items()} == {"sos:1:18:0": "exact", "sos:1:9:0": "likely"}
    # Rashida Tlaib is on the list for Michigan's 12th, never Texas's.
    green = cards["sos:1:18:0"]
    assert {f.label: f.value for f in green.facts}["List fetched"] == "Oct 4, 2026"
    assert green.url == "https://muslimsunitedpac.com/endorsements/al-green-tx" and green.flags == [FLAG]


def test_the_ballot_fetches_it_once_and_keeps_it(client, upstream):
    assert row(client)["notice"].startswith("Not fetched yet: the first lookup with it on fetches")
    ballot = get_ballot(client, "ut")
    casar = cards_from(ballot)["Greg Casar"]
    today = dt.date.today()
    assert (casar["label"], casar["as_of"], casar["match"]["confidence"], casar["flags"]) == (
        "Muslims United PAC", today.isoformat(), "exact", [FLAG])
    assert [(b["text"], b["url"]) for b in casar["badges"]] == [
        ("Endorsed by Muslims United PAC", "https://muslimsunitedpac.com/endorsements/greg-casar-tx")]
    assert {f["label"]: f["value"] for f in casar["facts"]}["Office on the list"] == "U.S. House, District 37"
    assert casar["quotes"][0].startswith("As Chair of the Congressional Progressive Caucus")
    assert upstream.count(FEED_HOST) == 1
    assert last_use(client, MUPAC)["status"] == "used" and last_use(client, MUPAC)["calls"] == 1

    again = get_ballot(client, "ut")
    assert again["meta"]["external_calls"] == 0 and upstream.count(FEED_HOST) == 1
    get_ballot(client)  # another address, another state's ballot races: the same copy
    assert upstream.count(FEED_HOST) == 1

    endorsements = {found["source"]: found for found in client.get("/api/endorsements").json()}
    assert endorsements[MUPAC] == {
        "source": MUPAC, "label": "Muslims United PAC", "organization": "Muslims United PAC",
        "url": "https://muslimsunitedpac.com/endorsements", "captured": today.isoformat(),
        "description": FEEDS[0].description, "live": True, "enabled": True}


def test_cair_matches_texas_candidates(client, upstream):
    ballot = get_ballot(client, "ut")
    casar = cards_from(ballot, CAIR)["Greg Casar"]
    assert (casar["label"], casar["match"]["confidence"], casar["flags"], casar["quotes"]) == (
        "CAIR Action", "exact", [FLAG], [ENDORSED])
    assert [(b["text"], b["url"]) for b in casar["badges"]] == [("Endorsed by CAIR Action", CAIR_TX)]
    assert {f["label"]: f["value"] for f in casar["facts"]}["Office on the list"] == "U.S. Representative, District 37"
    assert cards_from(ballot, CAIR)["Montserrat Garibay"]["match"]["confidence"] == "exact"  # State House District 49
    assert upstream.count(CAIR_HOST) == 1

    plummer = cards_from(get_ballot(client, "harris"), CAIR)["Letitia Plummer"]  # a county office, by its county
    assert plummer["match"]["confidence"] == "exact"
    assert {f["label"]: f["value"] for f in plummer["facts"]}["Office on the list"] == "Harris County Judge"
    assert get_ballot(client, "ut")["meta"]["external_calls"] == 0 and upstream.count(CAIR_HOST) == 1
    assert [(f["label"], f["value"]) for f in row(client, CAIR)["details"]] == [
        ("Texas candidates", "17"), ("All candidates", "591 in 27 states")]


def test_its_settings_row_refreshes_and_clears(client, upstream):
    get_ballot(client, "ut")
    found = row(client)
    assert (found["label"], found["toggleable"], found["enabled"], found["frozen"], found["refreshable"],
            found["resettable"], found["cache"]["entries"]) == (
        "Muslims United PAC endorsements", True, True, False, True, False, 1)
    assert found["notice"].startswith("Fetched from [Muslims United PAC's website](https://muslimsunitedpac.com/endorsements) on ")
    assert found["notice"].endswith("; a lookup fetches it again once it's 7 days old.")
    assert [(f["label"], f["value"]) for f in found["details"]] == [
        ("Texas candidates", "3"), ("All candidates", "26 in 18 states")]
    assert found["clear_confirm"] == "Clear everything cached from Muslims United PAC endorsements? The next lookup will fetch it again."

    refreshed = client.post(f"/api/sources/{MUPAC}/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["message"] == "Refreshed 1 cached response. 3 of its 26 candidates are in Texas."
    assert upstream.count(FEED_HOST) == 2

    cleared = client.post(f"/api/sources/{MUPAC}/clear").json()["message"]
    assert cleared == "Cleared 1 cached response. The next lookup fetches the list again."
    assert row(client)["details"] == []
    assert "Greg Casar" in cards_from(get_ballot(client, "ut")) and upstream.count(FEED_HOST) == 3


def test_refresh_fetches_a_list_never_fetched(client, upstream):
    message = client.post(f"/api/sources/{MUPAC}/refresh").json()["message"]
    assert message == "Refreshed 0 cached responses. 3 of its 26 candidates are in Texas."
    assert upstream.count(FEED_HOST) == 1


def test_a_refusal_pauses_it_and_the_ballot_goes_on(client, upstream):
    upstream.feed_status = 429
    ballot = get_ballot(client, "ut")
    assert not cards_from(ballot) and ballot["races"]
    assert [w for w in ballot["warnings"] if w.startswith("Couldn't load Muslims United PAC's endorsements (")]
    assert last_use(client, MUPAC)["status"] == "error"
    assert upstream.count(FEED_HOST) == 1

    again = get_ballot(client, "ut")
    assert upstream.count(FEED_HOST) == 1  # paused: not asked again
    assert any("paused until" in w and "Muslims United PAC's website refused a request" in w for w in again["warnings"])
    notice = row(client)["notice"]
    assert notice.startswith("Paused until ") and notice.endswith(
        "after Muslims United PAC's website refused a request; the list already fetched still shows.")
    assert row(client)["notice_tone"] == "warn"


def test_an_answer_it_cant_read_is_refused(client, upstream):
    upstream.feed_answers[MUPAC] = {"incumbents": [{"title": "renamed fields"}], "total": 1}
    ballot = get_ballot(client, "ut")
    assert not cards_from(ballot)
    assert "Couldn't load Muslims United PAC's endorsements (a list with no candidate Pallot can read)." in ballot["warnings"]
    assert row(client)["details"] == []


def test_turned_off_it_isnt_asked(make_app, upstream):
    with TestClient(make_app()) as client:
        assert client.put(f"/api/sources/{MUPAC}", json={"enabled": False}).status_code == 200
        ballot = get_ballot(client, "ut")
        assert not cards_from(ballot) and upstream.count(FEED_HOST) == 0
        assert row(client)["enabled"] is False and last_use(client, MUPAC)["status"] == "off"
    with TestClient(make_app()) as client:  # the switch is kept
        assert next(f for f in client.get("/api/endorsements").json() if f["source"] == MUPAC)["enabled"] is False
