"""The live endorsement feeds: each organization's adapter, the cards they give like a frozen
list's, the copy kept a week (a second lookup asks no one), a refusal's pause, and the row in
Settings with Refresh and Clear (tests/fixtures/endorsement_feeds holds each recorded list), and
a token read from the list's page, sent and never kept."""

from __future__ import annotations

import datetime as dt
import sqlite3

import pytest
from fastapi.testclient import TestClient

from pallot.admin import SOURCES
from pallot.http_cache import Unreadable
from pallot.models import Candidate, Race
from pallot.sources.endorsement_feeds import FEEDS, cair_action, emgage, meta_token, muslims_united
from pallot.sources.endorsements import ENDORSEMENTS_DIR, FLAG, EndorsementList, read_entry

from .conftest import FEED_TOKEN, fixture_bytes, get_ballot, last_use, load, switch

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
    assert (casar["label"], casar["kind"], casar["as_of"], casar["match"]["confidence"], casar["flags"]) == (
        "Muslims United PAC", "endorsement", today.isoformat(), "exact", [FLAG])
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


def test_its_settings_row_and_pallot_cache_refreshes_and_rebuilds_it(client, make_app, upstream):
    get_ballot(client, "ut")
    found = row(client)
    assert (found["label"], found["toggleable"], found["enabled"], found["frozen"], found["bundled"],
            found["cache"]["entries"]) == ("Muslims United PAC endorsements", True, True, False, False, 1)
    assert found["notice"].startswith("Fetched from [Muslims United PAC's website](https://muslimsunitedpac.com/endorsements) on ")
    assert found["notice"].endswith("; a lookup fetches it again once it's 7 days old.")
    assert [(f["label"], f["value"]) for f in found["details"]] == [
        ("Texas candidates", "3"), ("All candidates", "26 in 18 states")]

    refreshed = make_app.cache_command("hard-refresh", MUPAC)
    assert refreshed == (0, "Muslims United PAC endorsements: Refreshed 1 saved response. 3 of its 26 candidates are in Texas.")
    assert upstream.count(FEED_HOST) == 2

    rebuilt = make_app.cache_command("rebuild", MUPAC)[1]
    assert rebuilt.startswith("Deleted 1 saved response, and what Muslims United PAC endorsements kept in files.")
    assert upstream.count(FEED_HOST) == 3
    assert "Greg Casar" in cards_from(get_ballot(client, "ut")) and upstream.count(FEED_HOST) == 3


def test_hard_refresh_fetches_a_list_never_fetched(make_app, upstream):
    assert make_app.cache_command("refresh", MUPAC) == (0, "Muslims United PAC endorsements: nothing past its lifetime.")
    assert upstream.count(FEED_HOST) == 0
    message = make_app.cache_command("hard-refresh", MUPAC)[1]
    assert message == "Muslims United PAC endorsements: Refreshed 0 saved responses. 3 of its 26 candidates are in Texas."
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
        switch(client, MUPAC, False)
        ballot = get_ballot(client, "ut")
        assert not cards_from(ballot) and upstream.count(FEED_HOST) == 0
        assert row(client)["enabled"] is False and last_use(client, MUPAC)["status"] == "off"
        assert next(f for f in client.get("/api/endorsements").json() if f["source"] == MUPAC)["enabled"] is False


# -- Emgage PAC: its list wants a token its page hands out ---------------------------------------

EMGAGE = "emgage"
EMGAGE_PAGE = "candidates.emgagepac.org/page/SupportOurCandidates"
EMGAGE_API = "candidates.emgagepac.org/api/v2/donation-page/SupportOurCandidates"


def test_emgage_entries():
    found = {entry["name"]: entry for entry in emgage(load(f"endorsement_feeds/{EMGAGE}.json"))}
    assert len(found) == 39
    assert found["Greg Casar"] == {"name": "Greg Casar", "state": "TX", "office": "U.S. House", "district": "35",
                                   "party": "Democratic", "note": None}
    assert (found["Marquette Greene-Scott"]["district"], found["Debbie Dingell"]["district"]) == ("22", "6")  # "D-MI-06"
    assert found["James Talarico"] == {"name": "James Talarico", "state": "TX", "office": "U.S. Senate", "district": None,
                                       "party": None, "note": None}  # its district is empty
    assert (found["Bernie Sanders"]["district"], found["Bernie Sanders"]["party"]) == (None, "Independent")  # "I-VT"
    assert "Dr. Adam Hamawy" in found
    assert [read_entry(raw, n, EMGAGE)["name"] for n, raw in enumerate(found.values())] == list(found)


def test_emgage_leaves_out_what_isnt_a_candidate():
    with pytest.raises(ValueError):
        emgage({"recipients": None})
    answer = {"recipients": [
        {"recipientType": "Organization", "displayName": "Emgage PAC", "office": None, "district": "", "state": "MI"},
        {"recipientType": "FederalCandidate", "displayName": "Greg Casar", "office": "U.S. House", "district": "d-tx-35",
         "state": "TX", "politicalParty": None, "profileTeaser": "<span><img src='x'></span>",
         "description": "<p>Chair&nbsp;of the <b>CPC</b>.</p><p>Since 2023.</p>"},
        "not a candidate",
    ]}
    assert emgage(answer) == [{"name": "Greg Casar", "state": "TX", "office": "U.S. House", "district": "35",
                               "party": "Democratic", "note": "Chair of the CPC. Since 2023."}]


def test_meta_token_reads_the_page():
    read = meta_token("RequestVerificationToken", "RequestVerificationToken")
    assert read(fixture_bytes(f"endorsement_feeds/{EMGAGE}.html").decode()) == {"RequestVerificationToken": FEED_TOKEN}
    assert read('<META content="abc" NAME="requestverificationtoken">') == {"RequestVerificationToken": "abc"}
    with pytest.raises(Unreadable, match="^its page has no RequestVerificationToken to send$"):
        read('<meta name="RequestVerificationToken" content=""><meta name="other" content="abc">')


def test_emgage_matches_texas_seats():
    entries = [read_entry(raw, n, EMGAGE) for n, raw in enumerate(emgage(load(f"endorsement_feeds/{EMGAGE}.json")))]
    found = EndorsementList(source=EMGAGE, label="Emgage PAC", organization="Emgage PAC", url=FEEDS[1].url,
                            captured="2026-10-04", description="", entries=entries, live=True)
    races = [race("U.S. Representative District 22", ("Marquette Greene-Scott", "D"), ("Troy Nehls", "R"),
                  key="sos:1:22", seat="TX-22"),
             race("U.S. Representative District 37", ("Greg Casar", "D"), key="sos:1:37", seat="TX-37"),
             race("U.S. Senator", ("James Talarico", "D"), ("Ken Paxton", "R"), key="sos:1:sen", seat="TX-SEN")]
    cards = found.cards(races, {}, "Fort Bend").candidates
    assert {key: card.match.confidence for key, card in cards.items()} == {
        "sos:1:22:0": "exact", "sos:1:37:0": "likely", "sos:1:sen:0": "exact"}
    # Emgage still lists Greg Casar for the 35th, his seat before Texas redrew its districts.
    assert cards["sos:1:37:0"].match.note == "Emgage PAC lists them for U.S. House, District 35"
    assert cards["sos:1:22:0"].url == FEEDS[1].url  # no page of its own: the list's


def test_emgage_sends_the_token_and_keeps_it_nowhere(client, upstream, tmp_path):
    ballot = get_ballot(client, "ut")
    casar = cards_from(ballot, EMGAGE)["Greg Casar"]
    assert (casar["label"], casar["match"]["confidence"], [b["text"] for b in casar["badges"]]) == (
        "Emgage PAC", "likely", ["Endorsed by Emgage PAC"])
    assert cards_from(ballot, EMGAGE)["James Talarico"]["match"]["confidence"] == "exact"
    assert (upstream.count(EMGAGE_PAGE), upstream.count(EMGAGE_API), upstream.feed_tokens) == (1, 1, [FEED_TOKEN])
    assert last_use(client, EMGAGE)["calls"] == 2

    again = get_ballot(client, "ut")
    assert again["meta"]["external_calls"] == 0 and upstream.count(EMGAGE_PAGE) == 1  # no page for a token either

    with sqlite3.connect(tmp_path / "data" / "cache.sqlite3") as db:
        rows = db.execute("SELECT key, request, value FROM responses WHERE source = ?", (EMGAGE,)).fetchall()
        flags = db.execute("SELECT name FROM flags").fetchall()
    assert len(rows) == 1 and "/api/v2/donation-page/" in rows[0][1]  # the list; its page isn't kept
    assert FEED_TOKEN not in repr((rows, flags))
    assert not [p for p in (tmp_path / "data").glob("cache.sqlite3*") if FEED_TOKEN.encode() in p.read_bytes()]


def test_emgage_refresh_asks_for_a_new_token(client, make_app, upstream):
    get_ballot(client, "ut")
    message = make_app.cache_command("hard-refresh", EMGAGE)[1]
    assert message == "Emgage PAC endorsements: Refreshed 1 saved response. 3 of its 39 candidates are in Texas."
    assert (upstream.count(EMGAGE_PAGE), upstream.count(EMGAGE_API), upstream.feed_tokens) == (2, 2, [FEED_TOKEN] * 2)


def test_emgage_page_without_a_token(client, upstream):
    upstream.feed_pages[EMGAGE] = "<html><head><title>Maintenance</title></head></html>"
    ballot = get_ballot(client, "ut")
    assert not cards_from(ballot, EMGAGE)
    assert "Couldn't load Emgage PAC's endorsements (its page has no RequestVerificationToken to send)." in ballot["warnings"]
    assert upstream.count(EMGAGE_API) == 0 and last_use(client, EMGAGE)["status"] == "error"


@pytest.mark.parametrize("step", ["page", "list"])
def test_emgage_a_refusal_on_either_step_pauses_it(client, upstream, step):
    if step == "page":
        upstream.feed_page_status = 403
    else:
        upstream.feed_status = 429
    ballot = get_ballot(client, "ut")
    assert not cards_from(ballot, EMGAGE)
    assert [w for w in ballot["warnings"] if w.startswith("Couldn't load Emgage PAC's endorsements (HTTP 4")]
    asked = upstream.count("candidates.emgagepac.org")
    assert asked == (1 if step == "page" else 2)

    again = get_ballot(client, "ut")
    assert upstream.count("candidates.emgagepac.org") == asked  # paused: neither step is asked again
    assert any("paused until" in w and "Emgage PAC's website refused a request" in w for w in again["warnings"])
    assert row(client, EMGAGE)["notice"].startswith("Paused until ")
