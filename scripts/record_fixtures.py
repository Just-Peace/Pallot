"""Record the live API responses that Pallot's tests replay, into tests/fixtures/.

    python scripts/record_fixtures.py              # everything
    python scripts/record_fixtures.py --only fec   # just the FEC responses (or ballots, suggest, nationwide, state_lists, polls, key_dates, officeholders, wikidata, tigerweb, election_precincts, county_precincts, endorsement_feeds, tec, trackaipac, voteforpeace)

The ballots take about 30 requests (Census geocoder, Nominatim, Texas SOS, Ballotpedia), and
the address suggestions two (Google's Places Autocomplete, with PALLOT_GOOGLE_API_KEY), the polls three (FiftyPlusOne, one per kind of race),
the key dates one (the Texas SOS's Important Election Dates page, kept as served), the seat
holders two (Congress's current members, cut down to Texas's and a few others, and Open States'
Texas legislators, cut down to the columns Pallot reads), Wikidata two (its Texas officeholders,
cut down to the recorded ballots' candidates and three others, and their details), the
district outlines four (TIGERweb's layer list, and the Capitol's three districts), and the
election precincts one (the Texas Legislative Council portal's list of precinct maps; the
tests make up the map itself), and the county precincts four (Travis's and Harris's lists of their
map services, and the service each county's list of election precincts is in; the tests make up
the lists themselves, from the made-up map), and the endorsement feeds one each (an organization's
whole public list, as served), two for a feed with a token (its page first, kept as only its meta
tags, the token's value replaced by TOKEN).
The 2.6 MB statewide candidate list is cut down to the candidates on the recorded ballots.
The FEC responses cover the Capitol ballot's federal races, plus the full breakdown for
the candidates in FEC_DETAILS (only the first with the shared DEMO_KEY, whose few requests
an hour fit one; set PALLOT_FEC_API_KEY, in the environment or .env, for the rest). These
requests skip Pallot's cache, and with DEMO_KEY they use up the same per-IP allowance as
a running Pallot. The ballots outside Texas (nationwide) take two Census answers, the FEC's
lists of this cycle's elections (six pages) and five seats' filers, and add those states'
members of Congress to the seat holders. The states with an official list (state_lists) take an
address each, North Carolina's list (cut down to four counties and the columns read) and
Michigan's report, their seats' FEC filers, and their legislators. The TrackAIPAC, Vote for Peace and Texas Ethics
Commission fixtures are subsets of the bundled snapshots (no request).
The tests pin "today" to 2026-09-27; after the Nov 3, 2026 election, re-recording means
updating ELECTIONS below and the tests' expectations.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pallot.config import DEMO_KEY, load_config  # noqa: E402
from pallot.offices import classify  # noqa: E402
from pallot.sources import (  # noqa: E402
    ballotpedia, census, county_precincts, election_precincts, fec, google, key_dates, nominatim, officeholders, polls,
    sos, suggestions, tigerweb, wikidata,
)
from pallot.matching import full_key  # noqa: E402
from pallot.sources.endorsement_feeds import FEEDS  # noqa: E402
from pallot.text import display_person  # noqa: E402
from pallot.sources.tec import _seats, tec_seat  # noqa: E402
from pallot.states import mi, nc  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
ADDRESSES = {
    "capitol": "1100 Congress Ave, Austin, TX 78701",
    "ut": "110 Inner Campus Dr, Austin, TX 78712",
    "harris": "1001 Preston St, Houston, TX 77002",
    "mopac": "13500 N Mopac Expy, Austin, TX 78728",  # the Census can't match this one
    "dc": "1600 Pennsylvania Ave NW, Washington, DC 20500",
}
ELECTIONS = {53815: 2026, 66734: 2026, 66618: 2026}  # Nov 3, 2026: general + two specials
COUNTIES = {227: "travis", 101: "harris"}
TOKEN = "recorded-token"  # in place of the token an endorsement feed's page hands out
BALLOTPEDIA_AT = ("capitol",)
TRACKAIPAC_PEOPLE = (
    "tx-ken-paxton", "tx-james-talarico", "tx-august-pfluger", "tx-greg-casar", "tx-lloyd-doggett",
    "tx-michael-cloud", "tx-tanya-lloyd", "tx-ted-cruz", "tx-michael-mccaul", "tx-christian-menefee",
)
# Vote for Peace's Texas candidates, plus these from other states, to show the ballot keeps to Texas.
VOTEFORPEACE_ELSEWHERE = ("juan-ciscomani", "shirley-weber")
FEC_CYCLE = 2026
FEC_RACES = ("TX-SEN", "TX-10")  # the Capitol ballot's federal races
FEC_DETAILS = ("S6TX00479", "S6TX00388")  # James Talarico, Ken Paxton
# Outside Texas: a state with a Senate race, one with a single, at-large seat, and DC's delegate.
NATIONWIDE = {"atlanta": "55 Trinity Ave SW, Atlanta, GA 30303", "cheyenne": "200 W 24th St, Cheyenne, WY 82001"}
NATIONWIDE_RACES = ("GA-SEN", "GA-05", "WY-SEN", "WY-00", "DC-00")
# States with an official list (pallot/states): an address in each, and NC's counties kept in its cut-down list.
STATE_ADDRESSES = {"raleigh": "1 E Edenton St, Raleigh, NC 27601", "lansing": "100 N Capitol Ave, Lansing, MI 48933"}
NC_COUNTIES = ("WAKE", "DURHAM", "ALAMANCE", "MECKLENBURG")
# What a voter might have typed so far: a street that's in Austin, Houston and elsewhere, and
# a street that's only in Austin.
SUGGEST = {"congress": "1100 congress ave", "duval": "4512 duval st"}
OUTLINES = {"cd": 10, "sd": 14, "hd": 49}  # the Capitol's districts
PRECINCT_COUNTIES = {"travis": 453, "harris": 201}  # the fixture addresses' counties, by FIPS code


def save(name: str, data: object) -> None:
    path = FIXTURES / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{name}: {path.stat().st_size:,} bytes")


def record_ballots(client: httpx.Client) -> None:
    def get(url: str, **kwargs: object) -> object:
        response = client.get(url, **kwargs)
        response.raise_for_status()
        return response.json()

    def post(url: str, body: dict) -> list:
        response = client.post(url, json=body)
        response.raise_for_status()
        return response.json()

    points = {}
    for name, address in ADDRESSES.items():
        data = get(f"{census.BASE}/onelineaddress", params={"address": census.normalize_address(address), **census.PARAMS})
        save(f"census_{name}.json", data)
        matches = data["result"]["addressMatches"]
        if matches:
            points[name] = (matches[0]["coordinates"]["y"], matches[0]["coordinates"]["x"])

    hits = get(nominatim.URL, params={"q": census.normalize_address(ADDRESSES["mopac"]), "format": "jsonv2",
                                      "countrycodes": "us", "limit": "1"})
    save("nominatim_mopac.json", hits)
    lat, lon = float(hits[0]["lat"]), float(hits[0]["lon"])
    save("census_coords_mopac.json",
         get(f"{census.BASE}/coordinates", params={"x": f"{lon:.6f}", "y": f"{lat:.6f}", **census.PARAMS}))

    for year in (2026, 2027):
        save(f"sos_elections_{year}.json", get(f"{sos.CBP}/getElectionsByYear/{year}"))
    save("sos_regions.json", get(f"{sos.SYSTEM}/getAllRegions"))
    save("sos_parties.json", get(f"{sos.CBP}/getPoliticalParties"))
    save("sos_statuses.json", get(f"{sos.CBP}/getCandidateStatus"))
    save("sos_declarations.json", get(f"{sos.CBP}/getDeclarationStatus"))

    on_ballot: set[int] = set()
    for election, year in ELECTIONS.items():
        for county_id in COUNTIES:
            rows = post(f"{sos.CBP}/getCandidateBallotOrder",
                        {"electionYear": year, "electionId": election, "countyId": county_id, "source": "TX"})
            save(f"sos_ballot_{election}_{county_id}.json", rows)
            on_ballot |= {row["idCandidate"] for row in rows}
    for election, year in ELECTIONS.items():
        rows = post(f"{sos.CBP}/findQualifiedCandidates", {"electionYear": year, "electionId": election})
        if len(rows) > 200:
            rows = [row for row in rows if row["idCandidate"] in on_ballot]
        save(f"sos_candidates_{election}.json", rows)

    for name in BALLOTPEDIA_AT:
        lat, lon = points[name]
        save(f"ballotpedia_{name}.json",
             get(ballotpedia.URL, params={"long": f"{lon:.5f}", "lat": f"{lat:.5f}", "include_volunteer": "true"},
                 headers={"Origin": ballotpedia.ORIGIN, "Accept": "application/json"}))


def record_suggest(client: httpx.Client, key: str) -> None:
    """Google's address suggestions for SUGGEST, without the place ids (only the text is read)."""
    if not key:
        print("No PALLOT_GOOGLE_API_KEY: the suggestions were not recorded.")
        return
    for name, text in SUGGEST.items():
        spec = suggestions.request(suggestions.normalize(text))
        response = client.post(spec.url, json=spec.json, headers={google.KEY_HEADER: key})
        response.raise_for_status()
        kept = [{"placePrediction": {"text": {"text": s["placePrediction"]["text"]["text"]}}}
                for s in response.json().get("suggestions") or [] if "placePrediction" in s]
        save(f"suggestions_{name}.json", {"suggestions": kept})


def record_fec(client: httpx.Client, key: str) -> None:
    def get(path: str, params: dict[str, str]) -> dict:
        response = client.get(f"{fec.API}{path}", params=params, headers={"X-Api-Key": key})
        response.raise_for_status()
        print(f"  FEC requests left this hour: {response.headers.get('x-ratelimit-remaining', '?')}")
        return response.json()

    rows: dict[str, dict] = {}
    for seat in FEC_RACES:
        state, _, district = seat.partition("-")
        params = {"state": state, "cycle": str(FEC_CYCLE), "election_full": "true", "per_page": "100", "sort": "-total_receipts"}
        if district == "SEN":
            params["office"], name = "senate", "fec_elections_senate.json"
        else:
            params.update(office="house", district=f"{int(district):02d}")
            name = f"fec_elections_house_{int(district):02d}.json"
        data = get("/elections/", params)
        save(name, data)
        rows.update({row["candidate_id"]: row for row in data.get("results") or []})

    whole = {"cycle": str(FEC_CYCLE), "election_full": "true"}
    try:
        for candidate_id in FEC_DETAILS if key != DEMO_KEY else FEC_DETAILS[:1]:
            ranked = {**whole, "candidate_id": candidate_id, "per_page": "100", "sort": "-total"}
            save(f"fec_totals_{candidate_id}.json", get(f"/candidate/{candidate_id}/totals/", whole))
            save(f"fec_by_size_{candidate_id}.json",
                 get("/schedules/schedule_a/by_size/by_candidate/", {**whole, "candidate_id": candidate_id}))
            save(f"fec_by_state_{candidate_id}.json", get("/schedules/schedule_a/by_state/by_candidate/", ranked))
            save(f"fec_outside_{candidate_id}.json", get("/schedules/schedule_e/by_candidate/", ranked))
            committee = rows.get(candidate_id, {}).get("candidate_pcc_id")
            if committee:
                save(f"fec_by_employer_{committee}.json",
                     get("/schedules/schedule_a/by_employer/",
                         {"committee_id": committee, "cycle": str(FEC_CYCLE), "per_page": "40", "sort": "-total"}))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 429:
            raise
        print("The FEC's hourly limit ran out; the rest of the FEC fixtures were not recorded. "
              "Set PALLOT_FEC_API_KEY, or run --only fec again in an hour.")


def record_nationwide(client: httpx.Client, key: str) -> None:
    """The ballots outside Texas: NATIONWIDE's Census answers, the FEC's lists of this cycle's
    elections (every page) and NATIONWIDE_RACES' filers, named by state, and those states'
    members of Congress added to officeholders_congress.json."""
    def get(url: str, params: dict[str, str], headers: dict[str, str] | None = None) -> dict:
        response = client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()

    for name, address in NATIONWIDE.items():
        save(f"census_{name}.json",
             get(f"{census.BASE}/onelineaddress", {"address": census.normalize_address(address), **census.PARAMS}))
    fec_headers = {"X-Api-Key": key}
    try:
        for office in ("senate", "house"):
            page, pages = 1, 1
            while page <= pages:
                data = get(f"{fec.API}/elections/search/",
                           {"cycle": str(FEC_CYCLE), "office": office, "per_page": "100", "page": str(page)}, fec_headers)
                pages = int(data["pagination"]["pages"])
                save(f"fec_elections_search_{office}_{page}.json", data)
                page += 1
        for seat in NATIONWIDE_RACES:
            state, _, district = seat.partition("-")
            params = {"state": state, "cycle": str(FEC_CYCLE), "election_full": "true", "per_page": "100", "sort": "-total_receipts"}
            if district == "SEN":
                params["office"], name = "senate", f"fec_elections_{state.lower()}_senate.json"
            else:
                params.update(office="house", district=f"{int(district):02d}")
                name = f"fec_elections_{state.lower()}_house_{int(district):02d}.json"
            save(name, get(f"{fec.API}/elections/", params, fec_headers))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 429:
            raise
        print("The FEC's hourly limit ran out; the rest of the nationwide fixtures were not recorded. "
              "Set PALLOT_FEC_API_KEY, or run --only nationwide again in an hour.")
    states = {seat.partition("-")[0] for seat in NATIONWIDE_RACES}
    members = get(officeholders.CONGRESS, {})
    path = FIXTURES / "officeholders_congress.json"
    kept = [m for m in json.loads(path.read_text(encoding="utf-8")) if m["terms"][-1].get("state") not in states]
    save(path.name, kept + [m for m in members if m["terms"][-1].get("state") in states])


def record_state_lists(client: httpx.Client, key: str) -> None:
    """The states with an official list: STATE_ADDRESSES' Census answers; North Carolina's list cut
    down to NC_COUNTIES and to the columns states/nc.py reads (no addresses, phones or emails);
    Michigan's report without its inline styles; the FEC's filers for each address's seats; their
    Open States legislators (the columns officeholders.py reads), and their members of Congress
    added to officeholders_congress.json."""
    seats = []
    for name, address in STATE_ADDRESSES.items():
        response = client.get(f"{census.BASE}/onelineaddress", params={"address": census.normalize_address(address), **census.PARAMS})
        response.raise_for_status()
        save(f"census_{name}.json", response.json())
        match = response.json()["result"]["addressMatches"][0]
        place = census.parse_geographies(match["geographies"], match["coordinates"]["y"], match["coordinates"]["x"], None)
        seats += [f"{place.state}-SEN", f"{place.state}-{place.cd:02d}"]

    response = client.get(nc.URL.format(year=FEC_CYCLE))
    response.raise_for_status()
    rows = [row for row in csv.DictReader(io.StringIO(response.text)) if row["county_name"].upper() in NC_COUNTIES]
    out = io.StringIO()
    writer = csv.DictWriter(out, nc.COLUMNS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    (FIXTURES / "state_nc.csv").write_text(out.getvalue(), encoding="utf-8", newline="")
    print(f"state_nc.csv: {len(rows):,} rows")
    response = client.get(mi.URL, params={"page": "page.miboePublicReport", "electionType": "GEN", "electionYear": str(FEC_CYCLE)})
    response.raise_for_status()
    (FIXTURES / "state_mi.html").write_text(re.sub(r'\s(?:style|class)="[^"]*"', "", response.text), encoding="utf-8", newline="")
    print(f"state_mi.html: {(FIXTURES / 'state_mi.html').stat().st_size:,} bytes")

    try:
        for seat in seats:
            state, _, district = seat.partition("-")
            params = {"state": state, "cycle": str(FEC_CYCLE), "election_full": "true", "per_page": "100", "sort": "-total_receipts"}
            if district == "SEN":
                params["office"], name = "senate", f"fec_elections_{state.lower()}_senate.json"
            else:
                params.update(office="house", district=district)
                name = f"fec_elections_{state.lower()}_house_{district}.json"
            response = client.get(f"{fec.API}/elections/", params=params, headers={"X-Api-Key": key})
            response.raise_for_status()
            save(name, response.json())
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 429:
            raise
        print("The FEC's hourly limit ran out; its state-list fixtures were not all recorded.")

    states = {seat.partition("-")[0] for seat in seats}
    columns = ("id", "name", "current_party", "current_district", "current_chamber", "given_name", "family_name")
    for state in states:
        response = client.get(officeholders.LEGISLATURE.format(state=state.lower()))
        response.raise_for_status()
        out = io.StringIO()
        writer = csv.DictWriter(out, columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv.DictReader(io.StringIO(response.text)))
        (FIXTURES / f"officeholders_{state.lower()}.csv").write_text(out.getvalue(), encoding="utf-8", newline="")
    response = client.get(officeholders.CONGRESS)
    response.raise_for_status()
    path = FIXTURES / "officeholders_congress.json"
    kept = [m for m in json.loads(path.read_text(encoding="utf-8")) if m["terms"][-1].get("state") not in states]
    save(path.name, kept + [m for m in response.json() if m["terms"][-1].get("state") in states])


def record_polls(client: httpx.Client) -> None:
    """FiftyPlusOne's Senate, House and Governor lists (all their pages), cut down to the Texas
    polls plus a few from other states."""
    for kind in polls.KINDS:
        rows, offset = [], 0
        while True:
            response = client.get(polls.API, headers=polls.HEADERS, params={
                "offset": str(offset), "limit": str(polls.PAGE), "filterValue": kind, "sortBy": "created_at", "dir": "DESC"})
            response.raise_for_status()
            page = response.json().get("data") or []
            rows += page
            if len(page) < polls.PAGE:
                break
            offset += polls.PAGE
        texas = [row for row in rows if row.get("state") == polls.STATE]
        others = [row for row in rows if row.get("state") != polls.STATE][:3]
        save(f"polls_{kind}.json", {"success": True, "count": len(texas + others), "data": texas + others})


def record_key_dates(client: httpx.Client) -> None:
    """The Important Election Dates page, byte for byte: the tests parse the real thing,
    earlier years' commented-out tables included."""
    response = client.get(key_dates.URL)
    response.raise_for_status()
    path = FIXTURES / "sos_key_dates.html"
    path.write_bytes(response.content)
    print(f"{path.name}: {path.stat().st_size:,} bytes ({response.headers.get('content-type')})")


def record_officeholders(client: httpx.Client) -> None:
    """Who holds each seat: Congress's members from Texas plus three others, and Texas's
    legislators with only the columns officeholders.py reads."""
    response = client.get(officeholders.CONGRESS)
    response.raise_for_status()
    members = response.json()
    texas = [m for m in members if m["terms"][-1].get("state") == officeholders.STATE]
    others = [m for m in members if m["terms"][-1].get("state") != officeholders.STATE][:3]
    nationwide = {seat.partition("-")[0] for seat in NATIONWIDE_RACES} | {"NC", "MI"}  # and STATE_ADDRESSES' states
    others += [m for m in members if m["terms"][-1].get("state") in nationwide and m not in others]
    save("officeholders_congress.json", texas + others)
    response = client.get(officeholders.LEGISLATURE.format(state="tx"))
    response.raise_for_status()
    columns = ("id", "name", "current_party", "current_district", "current_chamber", "given_name", "family_name")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    out = io.StringIO()
    writer = csv.DictWriter(out, columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path = FIXTURES / "officeholders_tx.csv"
    path.write_text(out.getvalue(), encoding="utf-8", newline="")
    print(f"{path.name}: {path.stat().st_size:,} bytes")


def record_wikidata(client: httpx.Client) -> None:
    """Wikidata's Texas officeholders, cut down to the recorded ballots' candidates and a few others, and
    their details, as Pallot asks for them."""

    def get(spec) -> dict:
        response = client.get(spec.url, params=spec.params, headers=spec.headers)
        response.raise_for_status()
        return response.json()

    names = {full_key(display_person(row.get("txFullNameBallot") or ""))
             for path in FIXTURES.glob("sos_ballot_*.json") for row in json.loads(path.read_text(encoding="utf-8"))}
    answer = get(wikidata.people_spec())
    rows = answer["results"]["bindings"]
    ids = {row["p"]["value"] for row in rows if full_key(row["label"]["value"]) in names}
    ids |= set(sorted({row["p"]["value"] for row in rows} - ids)[:3])
    save("wikidata_people.json", {**answer, "results": {"bindings": [row for row in rows if row["p"]["value"] in ids]}})
    save("wikidata_details.json", get(wikidata.details_spec(sorted(i.rsplit("/", 1)[1] for i in ids))))


def record_tigerweb(client: httpx.Client) -> None:
    """TIGERweb's layer list, then the Capitol's districts, sent as Pallot sends them."""

    def get(spec) -> dict:
        response = client.get(spec.url, params=spec.params)
        response.raise_for_status()
        return response.json()

    index = get(tigerweb.index_spec())
    save("tigerweb_layers.json", index)
    for kind, number in OUTLINES.items():
        save(f"tigerweb_{tigerweb.geoid(kind, number)}.json",
             get(tigerweb.outline_spec(tigerweb.layer_id(index, kind), kind, number)))


def record_election_precincts(client: httpx.Client) -> None:
    """The portal's index of precinct maps, as Pallot asks for it (never the 45 MB map)."""
    spec = election_precincts.index_spec()
    response = client.get(spec.url, params=spec.params)
    response.raise_for_status()
    save("election_precincts_index.json", response.json())


def record_county_precincts(client: httpx.Client) -> None:
    """The fixture addresses' counties' lists of their map services, cut down to the services named
    like the one Pallot reads, and that service's layers, as Pallot asks for them."""

    def get(url: str) -> dict:
        response = client.get(url, params={"f": "json"})
        response.raise_for_status()
        return response.json()

    for name, fips in PRECINCT_COUNTIES.items():
        layer = county_precincts.COUNTIES[fips].table.layer
        listing = get(layer.folder)
        services = [s for s in listing["services"] if re.fullmatch(layer.service, s["name"], re.IGNORECASE)]
        save(f"county_precincts_{name}_services.json", {**listing, "services": services})
        service = county_precincts.pick(services, layer.service, server=layer.server)
        save(f"county_precincts_{name}_service.json",
             get(f"{county_precincts.services_root(layer.folder)}/{service['name']}/{layer.server}"))


def record_endorsement_feeds(client: httpx.Client) -> None:
    """Each live endorsement feed's whole list, as Pallot asks for it, into endorsement_feeds/<source>.json."""
    for feed in FEEDS:
        headers = dict(feed.headers or {})
        if feed.token:
            page = client.get(feed.url)
            page.raise_for_status()
            token = feed.token(page.text)
            headers.update(token)
            kept = "".join(re.findall(r"<meta\b[^>]*>", page.text, re.IGNORECASE))
            for value in token.values():
                kept = kept.replace(value, TOKEN)
            path = FIXTURES / f"endorsement_feeds/{feed.source}.html"
            path.write_text(f"<!DOCTYPE html>\n<html><head>{kept}</head><body></body></html>\n", encoding="utf-8", newline="\n")
            print(f"endorsement_feeds/{feed.source}.html: {path.stat().st_size:,} bytes")
        response = client.get(feed.api, headers=headers)
        response.raise_for_status()
        save(f"endorsement_feeds/{feed.source}.json", response.json())


def record_tec() -> None:
    """The bundled TEC snapshot's filers and outside spending for the Travis ballot's state races."""
    bundled = ROOT / "tec_cache" / "data"
    current = json.loads((bundled / "current.json").read_text(encoding="utf-8"))
    counties = {row["txName"].upper() for row in json.loads((FIXTURES / "sos_regions.json").read_text(encoding="utf-8"))}
    seats = set()
    for row in json.loads((FIXTURES / "sos_ballot_53815_227.json").read_text(encoding="utf-8")):
        seat = tec_seat(classify(row.get("txOfficeName") or "", row.get("cdOfficeType"), counties), "TRAVIS")
        if seat:
            seats.add(seat)
    subset = {
        **current,
        "filers": [f for f in current["filers"] if _seats(f) & seats],
        "outside": [o for o in current["outside"] if _seats(o) & seats],
    }
    save("tec/current.json", subset)
    save("tec/meta.json", json.loads((bundled / "meta.json").read_text(encoding="utf-8")))


def record_trackaipac() -> None:
    bundled = ROOT / "trackaipac_cache" / "data"
    current = json.loads((bundled / "current.json").read_text(encoding="utf-8"))
    people = [p for p in current["candidates"] if p["candidate_id"] in TRACKAIPAC_PEOPLE]
    save("trackaipac/current.json", {"snapshot": current["snapshot"], "candidates": people})
    save("trackaipac/meta.json", json.loads((bundled / "meta.json").read_text(encoding="utf-8")))


def record_voteforpeace() -> None:
    bundled = ROOT / "voteforpeace_cache" / "data"
    current = json.loads((bundled / "current.json").read_text(encoding="utf-8"))
    people = [p for p in current["candidates"] if p["state"] == "TX" or p["slug"] in VOTEFORPEACE_ELSEWHERE]
    save("voteforpeace/current.json", {"snapshot": current["snapshot"], "candidates": people})
    save("voteforpeace/meta.json", json.loads((bundled / "meta.json").read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record the responses Pallot's tests replay.")
    parser.add_argument("--only", choices=("ballots", "suggest", "fec", "nationwide", "state_lists", "polls", "key_dates", "officeholders", "wikidata", "tigerweb", "election_precincts",
                                           "county_precincts", "endorsement_feeds", "tec", "trackaipac", "voteforpeace"),
                        help="record just this part")
    only = parser.parse_args(argv).only
    config = load_config()
    with httpx.Client(timeout=90, headers={"User-Agent": config.user_agent}, follow_redirects=True) as client:
        if only in (None, "ballots"):
            record_ballots(client)
        if only in (None, "suggest"):
            record_suggest(client, config.google_api_key)
        if only in (None, "fec"):
            record_fec(client, config.fec_api_key)
        if only in (None, "nationwide"):
            record_nationwide(client, config.fec_api_key)
        if only in (None, "state_lists"):
            record_state_lists(client, config.fec_api_key)
        if only in (None, "polls"):
            record_polls(client)
        if only in (None, "key_dates"):
            record_key_dates(client)
        if only in (None, "officeholders"):
            record_officeholders(client)
        if only in (None, "wikidata"):
            record_wikidata(client)
        if only in (None, "tigerweb"):
            record_tigerweb(client)
        if only in (None, "election_precincts"):
            record_election_precincts(client)
        if only in (None, "county_precincts"):
            record_county_precincts(client)
        if only in (None, "endorsement_feeds"):
            record_endorsement_feeds(client)
    if only in (None, "tec"):
        record_tec()
    if only in (None, "trackaipac"):
        record_trackaipac()
    if only in (None, "voteforpeace"):
        record_voteforpeace()
    return 0


if __name__ == "__main__":
    sys.exit(main())
