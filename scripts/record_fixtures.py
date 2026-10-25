"""Record the live API responses that Pallot's tests replay, into tests/fixtures/.

    python scripts/record_fixtures.py              # everything
    python scripts/record_fixtures.py --only fec   # just the FEC responses (or ballots, suggest, nationwide, state_lists, state_ca, state_nv, state_ga, state_wi, state_oh, state_ia, state_nj, state_ny, state_co, state_il, polls, key_dates, officeholders, wikidata, tigerweb, election_precincts, county_precincts, endorsement_feeds, tec, trackaipac, voteforpeace)

The ballots take about 30 requests (Census geocoder, Nominatim, Texas SOS), and
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
address each, North Carolina's list (cut down to four counties and the columns read),
Michigan's report, Pennsylvania's and Florida's lists (cut down to the address's races and the
fields read) and Virginia's federal list (without its contact columns), their seats' FEC
filers, and their legislators. California's (state_ca) takes a Los Angeles address and its
certified list, a 14 MB PDF (--pdf a copy you downloaded), cut down to a small PDF of the pages
that address needs, and the table of its SOS's election dates page. Nevada's (state_nv) takes a
Las Vegas address and the certified list saved by hand in manual/state_nv (--pdf another copy),
never downloaded, cut down the same way. Georgia's (state_ga) takes the qualifying list saved by
hand in manual/state_ga (--json another copy), never downloaded, cut down to a few counties and
cities with its contact details made up, and the results site's list of elections and the
year's primary, recount and runoff, cut down to a few races. Wisconsin's (state_wi) takes a
Madison address and the contests and candidates saved by hand in manual/state_wi (--csv another
copy), never downloaded, cut down to the state's rows and a few counties'. Ohio's (state_oh) takes
a Columbus address and the statewide list transcribed by hand into manual/state_oh (--json another
copy), never downloaded, with the address's House seat's FEC filers. Iowa's (state_ia) takes a Des
Moines address and the candidate list saved by hand in manual/state_ia (--pdf another copy), never
downloaded, as a few of its text lines with every candidate's contact details made up. New Jersey's (state_nj) takes a
Trenton address, the Division of Elections' page cut down to its links, and the U.S. Senate and House
lists it links, rewritten as small text PDFs without the candidates' addresses. New York's (state_ny) takes a
Manhattan and an Albany address and the certification saved by hand in manual/state_ny (--pdf
another copy), never downloaded, cut down to some races' text lines. Colorado's (state_co) takes a
Denver address and the SOS's candidate spreadsheet as served (it has no contact details). Illinois's
(state_il) takes a Chicago address, the State Board's list of elections cut down to its table, the
election's download page cut down to its form, and the candidate data file it posts back for, with
its contact columns emptied. The TrackAIPAC, Vote for Peace and Texas Ethics
Commission fixtures are subsets of the bundled snapshots (no request).
The tests pin "today" to 2026-09-27; after the Nov 3, 2026 election, re-recording means
updating ELECTIONS below and the tests' expectations.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
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
    ca_key_dates, census, county_precincts, election_precincts, fec, google, key_dates, nominatim, officeholders, polls,
    sos, suggestions, tigerweb, wikidata,
)
from pallot.matching import full_key  # noqa: E402
from pallot.sources.endorsement_feeds import FEEDS  # noqa: E402
from pallot.text import display_person  # noqa: E402
from pallot.sources.tec import _seats, tec_seat  # noqa: E402
from pallot.sources.fec import general_day  # noqa: E402
from pallot.states import _ORDINALS, Rows, ca, co, fl, ga, ia, il, mi, nc, nj, ordinal, pa, pdf_lines, va  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

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
STATE_ADDRESSES = {
    "raleigh": "1 E Edenton St, Raleigh, NC 27601", "lansing": "100 N Capitol Ave, Lansing, MI 48933",
    "harrisburg": "501 N 3rd St, Harrisburg, PA 17120", "tallahassee": "400 S Monroe St, Tallahassee, FL 32399",
    "richmond": "1000 Bank St, Richmond, VA 23219", "phoenix": "1700 W Washington St, Phoenix, AZ 85007",
}
NC_COUNTIES = ("WAKE", "DURHAM", "ALAMANCE", "MECKLENBURG")
CA_ADDRESS = ("losangeles", "200 N Spring St, Los Angeles, CA 90012")  # City Hall: an even State Senate district, up in 2026
NV_ADDRESS = ("lasvegas", "495 S Main St, Las Vegas, NV 89101")  # City Hall
WI_ADDRESS = ("madison", "2 E Main St, Madison, WI 53703")  # the State Capitol
WI_JURISDICTIONS = ("DANE COUNTY", "WOOD COUNTY", "PRICE COUNTY", "IRON COUNTY", "JEFFERSON COUNTY", "WALWORTH COUNTY",
                    "MULTIPLE COUNTIES")
OH_ADDRESS = ("columbus", "90 W Broad St, Columbus, OH 43215")  # City Hall
NY_ADDRESSES ={"manhattan": "260 Broadway, New York, NY 10007", "albany": "100 State St, Albany, NY 12207"}
# New York's races kept besides the statewide ones and the addresses' districts: wrapped names and
# counties, a "Counties" without its colon, "SteOffice:", one-off party lines, and the Supreme Court
# districts of the two addresses, Brooklyn's (split over a page) and Long Island's.
NY_RACES = (("REPRESENTATIVE IN CONGRESS", "1"), ("REPRESENTATIVE IN CONGRESS", "21"), ("STATE SENATOR", "12"),
            ("STATE SENATOR", "54"), ("MEMBER OF ASSEMBLY", "61"), ("MEMBER OF ASSEMBLY", "74"),
            ("MEMBER OF ASSEMBLY", "75"), ("MEMBER OF ASSEMBLY", "97"), ("MEMBER OF ASSEMBLY", "123"),
            ("MEMBER OF ASSEMBLY", "137"), ("SUPREME COURT JUSTICE", "1"), ("SUPREME COURT JUSTICE", "2"),
            ("SUPREME COURT JUSTICE", "3"), ("SUPREME COURT JUSTICE", "10"))
IA_ADDRESS = ("desmoines", "400 Robert D Ray Dr, Des Moines, IA 50309")  # City Hall: an odd State Senate district, up in 2026
IA_CONTACT = "PO Box 1, Des Moines, IA 50301          515-555-0100      candidate@example.com"  # made up
NJ_ADDRESS = ("trenton", "125 W State St, Trenton, NJ 08608")  # the State House: NJ-12, an open seat in 2026
CO_ADDRESS = ("denver", "1437 Bannock St, Denver, CO 80202")  # the City and County Building: CO-1
IL_ADDRESS = ("chicago", "121 N LaSalle St, Chicago, IL 60602")  # City Hall: Cook County
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

    for name, address in ADDRESSES.items():
        save(f"census_{name}.json",
             get(f"{census.BASE}/onelineaddress", params={"address": census.normalize_address(address), **census.PARAMS}))

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


def record_pa(client: httpx.Client, place: census.Place) -> None:
    """Pennsylvania's page cut down to its election and the candidates statewide, in the address's
    districts and on its county's party committees, with only the fields states/pa.py reads."""
    response = client.get(pa.URL)
    response.raise_for_status()
    election = re.search(r'<option selected="selected" value="\d+">[^<]+</option>', response.text)
    rows = json.loads(html.unescape(re.search(r"id='dataJson' type='hidden' value='([^']*)'", response.text).group(1)))
    mine = {f"{ordinal(place.cd)} Congressional District", f"{ordinal(place.sd)} Senatorial District",
            f"{ordinal(place.hd)} Legislative District", "Statewide"}
    kept = [{c: row[c] for c in pa.COLUMNS} for row in rows
            if " ".join(row["DistrictName"].split()) in mine or row["DistrictName"].startswith(place.county)]
    data = html.escape(json.dumps(kept, ensure_ascii=False), quote=True)
    (FIXTURES / "state_pa.html").write_text(
        f"<html><body><select>{election.group(0)}</select>\n<input id='dataJson' type='hidden' value='{data}' />\n</body></html>\n",
        encoding="utf-8", newline="")
    print(f"state_pa.html: {len(kept):,} candidates")


def record_fl(client: httpx.Client, place: census.Place) -> None:
    """Florida's extract cut down to the columns states/fl.py reads, and to the candidates for
    statewide offices, appeals courts, special districts and the address's districts and circuit."""
    response = client.post(fl.URL, data=fl.form(general_day(dt.date(FEC_CYCLE, 1, 1))))
    response.raise_for_status()
    mine = {"USR": place.cd, "STS": place.sd, "STR": place.hd, "CTJ": 2}  # Leon County is in the Second Circuit
    rows = [row for row in csv.DictReader(io.StringIO(response.text), delimiter="\t")
            if row["OfficeCode"] not in mine or row["Juris1num"].strip().lstrip("0") == str(mine[row["OfficeCode"]])]
    out = io.StringIO()
    writer = csv.DictWriter(out, fl.COLUMNS, extrasaction="ignore", delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    (FIXTURES / "state_fl.tsv").write_text(out.getvalue(), encoding="utf-8", newline="")
    print(f"state_fl.tsv: {len(rows):,} rows")


def record_va(client: httpx.Client) -> None:
    """Virginia's federal list, as a page with only its title and the table's first columns
    (no candidates' emails, phones or addresses)."""
    day = general_day(dt.date(FEC_CYCLE, 1, 1))
    response = client.get(va.URL.format(day=day.day, year=day.year))
    response.raise_for_status()
    reader = Rows()
    reader.feed(response.text)
    heading = re.search(r"<h1>[^<]+</h1>", response.text).group(0)
    rows = "\n".join("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row[:len(va.COLUMNS)]) + "</tr>"
                     for row in reader.rows if len(row) >= len(va.COLUMNS))
    (FIXTURES / "state_va.html").write_text(f"<html><body>{heading}\n<table>\n{rows}\n</table></body></html>\n",
                                            encoding="utf-8", newline="")
    print(f"state_va.html: {len(reader.rows):,} rows")


def record_state_lists(client: httpx.Client, key: str) -> None:
    """The states with an official list: STATE_ADDRESSES' Census answers; North Carolina's list cut
    down to NC_COUNTIES and to the columns states/nc.py reads (no addresses, phones or emails);
    Michigan's report without its inline styles; the FEC's filers for each address's seats; their
    Open States legislators (the columns officeholders.py reads), and their members of Congress
    added to officeholders_congress.json."""
    seats, places = [], {}
    for name, address in STATE_ADDRESSES.items():
        response = client.get(f"{census.BASE}/onelineaddress", params={"address": census.normalize_address(address), **census.PARAMS})
        response.raise_for_status()
        save(f"census_{name}.json", response.json())
        match = response.json()["result"]["addressMatches"][0]
        place = census.parse_geographies(match["geographies"], match["coordinates"]["y"], match["coordinates"]["x"], None)
        places[place.state] = place
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
    record_pa(client, places["PA"])
    record_fl(client, places["FL"])
    record_va(client)

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


def record_ca(client: httpx.Client, key: str, pdf: Path | None) -> None:
    """California: CA_ADDRESS's Census answer; the SOS's certified list (or ``pdf``, a copy of it)
    cut down to the pages for it: the statewide races, every U.S. House page (a list without all
    52 races is refused), the address's Senate and Assembly races, and the courts' pages for the
    Supreme Court and the address's appellate district; the SOS's election dates page, cut down to
    its table of deadlines; its seat's FEC filers, its legislators
    (the columns officeholders.py reads), and its senators and representative added to officeholders_congress.json."""
    name, address = CA_ADDRESS
    response = client.get(f"{census.BASE}/onelineaddress", params={"address": census.normalize_address(address), **census.PARAMS})
    response.raise_for_status()
    save(f"census_{name}.json", response.json())
    match = response.json()["result"]["addressMatches"][0]
    place = census.parse_geographies(match["geographies"], match["coordinates"]["y"], match["coordinates"]["x"], None)
    if pdf is None:
        response = client.get(ca.URL.format(year=FEC_CYCLE))
        response.raise_for_status()
        raw = response.content
    else:
        raw = pdf.read_bytes()
    county = (place.county or "").upper()
    appeal = next(f.district for f in ca.CaList.parse(raw) if f.family == "COURT OF APPEAL" and county in f.counties)
    word = next(w for w, n in _ORDINALS.items() if str(n) == appeal).capitalize()
    reader = PdfReader(io.BytesIO(raw))
    headings = {*ca.STATEWIDE, f"State Senate District {place.sd}", f"State Assembly Member District {place.hd}"}
    kept = []
    for index, page in enumerate(reader.pages):
        lines = {" ".join(line.split()) for line in page.extract_text(extraction_mode="layout").splitlines()}
        plain = page.extract_text()
        if (lines & headings or any(line.startswith("United States Representative District") for line in lines)
                or "Supreme Court" in plain and "For all" in plain or f"{word} District" in plain
                or f"{word} Appellate District" in plain):
            kept.append(index)
    writer = PdfWriter()
    for index in kept:
        writer.add_page(reader.pages[index])
    writer.compress_identical_objects()
    with (FIXTURES / "state_ca.pdf").open("wb") as fh:
        writer.write(fh)
    print(f"state_ca.pdf: pages {kept}, {(FIXTURES / 'state_ca.pdf').stat().st_size:,} bytes")

    response = client.get(ca_key_dates.URL)
    response.raise_for_status()
    table = re.search(r"<table>.*?</table>", response.text, re.S).group(0)
    (FIXTURES / "key_dates_ca.html").write_text(f"<html><body><h1>Election Dates and Resources</h1>\n{table}\n</body></html>\n",
                                                encoding="utf-8", newline="")
    print(f"key_dates_ca.html: {len(ca_key_dates.parse(table)):,} elections")

    response = client.get(f"{fec.API}/elections/", headers={"X-Api-Key": key}, params={
        "state": "CA", "cycle": str(FEC_CYCLE), "election_full": "true", "per_page": "100", "sort": "-total_receipts",
        "office": "house", "district": f"{place.cd:02d}"})
    response.raise_for_status()
    save(f"fec_elections_ca_house_{place.cd:02d}.json", response.json())
    response = client.get(officeholders.LEGISLATURE.format(state="ca"))
    response.raise_for_status()
    columns = ("id", "name", "current_party", "current_district", "current_chamber", "given_name", "family_name")
    out = io.StringIO()
    writer_csv = csv.DictWriter(out, columns, extrasaction="ignore", lineterminator="\n")
    writer_csv.writeheader()
    writer_csv.writerows(csv.DictReader(io.StringIO(response.text)))
    (FIXTURES / "officeholders_ca.csv").write_text(out.getvalue(), encoding="utf-8", newline="")
    response = client.get(officeholders.CONGRESS)
    response.raise_for_status()
    path = FIXTURES / "officeholders_congress.json"
    others = [m for m in json.loads(path.read_text(encoding="utf-8")) if m["terms"][-1].get("state") != "CA"]
    save(path.name, others + [m for m in response.json() if m["terms"][-1].get("state") == "CA"
                              and m["terms"][-1].get("district") in (None, place.cd)])


def record_nv(client: httpx.Client, key: str, pdf: Path | None) -> None:
    """Nevada: NV_ADDRESS's Census answer; the SOS's certified list, never downloaded (its site
    blocks scripts): ``pdf``, or the copy saved in manual/state_nv, cut down to the first page (the
    column headings and the statewide races) and the pages with the address's county or city; its
    seat's FEC filers, its legislators, and its representative added to officeholders_congress.json."""
    name, address = NV_ADDRESS
    response = client.get(f"{census.BASE}/onelineaddress", params={"address": census.normalize_address(address), **census.PARAMS})
    response.raise_for_status()
    save(f"census_{name}.json", response.json())
    match = response.json()["result"]["addressMatches"][0]
    place = census.parse_geographies(match["geographies"], match["coordinates"]["y"], match["coordinates"]["x"], None)
    saved = pdf or next(iter(sorted((ROOT / "manual" / "state_nv").glob("*.pdf"))), None)
    if saved is None:
        raise SystemExit("state_nv: save Nevada's certified list in manual/state_nv (see its README), or pass --pdf")
    reader = PdfReader(io.BytesIO(saved.read_bytes()))
    places = {f"{place.county} County".upper(), f"City Of {place.city}".upper()}
    kept = [index for index, page in enumerate(reader.pages)
            if index == 0 or places & {" ".join(cell.upper().split())
                                       for line in page.extract_text(extraction_mode="layout").splitlines()
                                       for cell in re.split(r"\s{3,}", line.strip())}]
    writer = PdfWriter()
    for index in kept:
        writer.add_page(reader.pages[index])
    writer.compress_identical_objects()
    with (FIXTURES / "state_nv.pdf").open("wb") as fh:
        writer.write(fh)
    print(f"state_nv.pdf: pages {kept}, {(FIXTURES / 'state_nv.pdf').stat().st_size:,} bytes")

    response = client.get(f"{fec.API}/elections/", headers={"X-Api-Key": key}, params={
        "state": "NV", "cycle": str(FEC_CYCLE), "election_full": "true", "per_page": "100", "sort": "-total_receipts",
        "office": "house", "district": f"{place.cd:02d}"})
    response.raise_for_status()
    save(f"fec_elections_nv_house_{place.cd:02d}.json", response.json())
    response = client.get(officeholders.LEGISLATURE.format(state="nv"))
    response.raise_for_status()
    columns = ("id", "name", "current_party", "current_district", "current_chamber", "given_name", "family_name")
    out = io.StringIO()
    writer_csv = csv.DictWriter(out, columns, extrasaction="ignore", lineterminator="\n")
    writer_csv.writeheader()
    writer_csv.writerows(csv.DictReader(io.StringIO(response.text)))
    (FIXTURES / "officeholders_nv.csv").write_text(out.getvalue(), encoding="utf-8", newline="")
    response = client.get(officeholders.CONGRESS)
    response.raise_for_status()
    path = FIXTURES / "officeholders_congress.json"
    others = [m for m in json.loads(path.read_text(encoding="utf-8")) if m["terms"][-1].get("state") != "NV"]
    save(path.name, others + [m for m in response.json() if m["terms"][-1].get("state") == "NV"
                              and m["terms"][-1].get("district") in (None, place.cd)])


def record_oh(client: httpx.Client, key: str, saved: Path | None) -> None:
    """Ohio: OH_ADDRESS's Census answer; the statewide list transcribed by hand into
    manual/state_oh (``saved`` another copy), never downloaded (its site blocks scripts), copied as
    it is (it holds only offices, names and parties); its House seat's FEC filers, its legislators,
    and its members of Congress added to officeholders_congress.json."""
    name, address = OH_ADDRESS
    response = client.get(f"{census.BASE}/onelineaddress", params={"address": census.normalize_address(address), **census.PARAMS})
    response.raise_for_status()
    save(f"census_{name}.json", response.json())
    match = response.json()["result"]["addressMatches"][0]
    place = census.parse_geographies(match["geographies"], match["coordinates"]["y"], match["coordinates"]["x"], None)
    saved = saved or ROOT / "manual" / "state_oh" / "ohio.json"
    if not saved.exists():
        raise SystemExit("state_oh: save Ohio's list as manual/state_oh/ohio.json (see its README), or pass --json")
    save("state_oh.json", json.loads(saved.read_text(encoding="utf-8")))
    response = client.get(f"{fec.API}/elections/", headers={"X-Api-Key": key}, params={
        "state": "OH", "cycle": str(FEC_CYCLE), "election_full": "true", "per_page": "100", "sort": "-total_receipts",
        "office": "house", "district": f"{place.cd:02d}"})
    response.raise_for_status()
    save(f"fec_elections_oh_house_{place.cd:02d}.json", response.json())
    response = client.get(officeholders.LEGISLATURE.format(state="oh"))
    response.raise_for_status()
    columns = ("id", "name", "current_party", "current_district", "current_chamber", "given_name", "family_name")
    out = io.StringIO()
    writer_csv = csv.DictWriter(out, columns, extrasaction="ignore", lineterminator="\n")
    writer_csv.writeheader()
    writer_csv.writerows(csv.DictReader(io.StringIO(response.text)))
    (FIXTURES / "officeholders_oh.csv").write_text(out.getvalue(), encoding="utf-8", newline="")
    response = client.get(officeholders.CONGRESS)
    response.raise_for_status()
    path = FIXTURES / "officeholders_congress.json"
    others = [m for m in json.loads(path.read_text(encoding="utf-8")) if m["terms"][-1].get("state") != "OH"]
    save(path.name, others + [m for m in response.json() if m["terms"][-1].get("state") == "OH"
                              and m["terms"][-1].get("district") in (None, place.cd)])


def record_ia(client: httpx.Client, key: str, pdf: Path | None) -> None:
    """Iowa: IA_ADDRESS's Census answer; the candidate list saved by hand in manual/state_ia
    (``pdf`` another copy), never downloaded (its site blocks scripts), as its text lines cut down
    to Congress, the statewide offices, the address's and the next districts' races and one with
    a party's "--", with every candidate's address, phone and email made up (IA_CONTACT); its
    seats' FEC filers, its legislators, and its members of Congress added to officeholders_congress.json."""
    name, address = IA_ADDRESS
    response = client.get(f"{census.BASE}/onelineaddress", params={"address": census.normalize_address(address), **census.PARAMS})
    response.raise_for_status()
    save(f"census_{name}.json", response.json())
    match = response.json()["result"]["addressMatches"][0]
    place = census.parse_geographies(match["geographies"], match["coordinates"]["y"], match["coordinates"]["x"], None)
    path = pdf or next(iter(sorted((ROOT / "manual" / "state_ia").glob("*.pdf"))), None)
    if path is None:
        raise SystemExit("state_ia: save Iowa's candidate list in manual/state_ia (see its README), or pass --pdf")
    keep = {f"STATE SENATOR DISTRICT {place.sd}", f"STATE SENATOR DISTRICT {place.sd + 2}", "STATE SENATOR DISTRICT 15",
            f"STATE REPRESENTATIVE DISTRICT {place.hd}", f"STATE REPRESENTATIVE DISTRICT {place.hd + 1}"}
    lines, office = [], None
    for line in pdf_lines(path.read_bytes()):
        if not line.strip() or ia._NOISE.match(line):
            if office is None and line.strip():
                lines.append(line)
            continue
        cells = re.split(r"\s{3,}", line.strip())
        shown = "" if line[0].isspace() else cells.pop(0)
        office = shown or office
        if office.upper().startswith("STATE ") and office.upper() not in keep:
            continue
        lines.append(f"{shown:<52}{cells[0]:<16}--" if cells[1] == "--" else
                     f"{shown:<52}{cells[0]:<16}{cells[1]:<35}{IA_CONTACT}          {cells[-1]}")
    (FIXTURES / "state_ia.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    print(f"state_ia.txt: {(FIXTURES / 'state_ia.txt').stat().st_size:,} bytes")
    for office, district in (("senate", None), ("house", f"{place.cd:02d}")):
        response = client.get(f"{fec.API}/elections/", headers={"X-Api-Key": key}, params={
            "state": "IA", "cycle": str(FEC_CYCLE), "election_full": "true", "per_page": "100", "sort": "-total_receipts",
            "office": office, **({"district": district} if district else {})})
        response.raise_for_status()
        save(f"fec_elections_ia_{office}.json" if district is None else f"fec_elections_ia_house_{district}.json",
             response.json())
    response = client.get(officeholders.LEGISLATURE.format(state="ia"))
    response.raise_for_status()
    columns = ("id", "name", "current_party", "current_district", "current_chamber", "given_name", "family_name")
    out = io.StringIO()
    writer_csv = csv.DictWriter(out, columns, extrasaction="ignore", lineterminator="\n")
    writer_csv.writeheader()
    writer_csv.writerows(csv.DictReader(io.StringIO(response.text)))
    (FIXTURES / "officeholders_ia.csv").write_text(out.getvalue(), encoding="utf-8", newline="")
    response = client.get(officeholders.CONGRESS)
    response.raise_for_status()
    members = FIXTURES / "officeholders_congress.json"
    others = [m for m in json.loads(members.read_text(encoding="utf-8")) if m["terms"][-1].get("state") != "IA"]
    save(members.name, others + [m for m in response.json() if m["terms"][-1].get("state") == "IA"
                                 and m["terms"][-1].get("district") in (None, place.cd)])


def text_pdf(pages: list[list[str]]) -> bytes:
    """A PDF of ``pages`` of lines in Courier, each laid out as written, for a fixture that
    stands in for a list whose real file carries what Pallot never keeps."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "", "<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"]
    kids = []
    for lines in pages:
        escaped = [re.sub(r"([\\()])", r"\\\1", line) for line in lines]
        stream = "\n".join(f"BT /F1 5 Tf 20 {770 - 9 * i} Td ({line}) Tj ET" for i, line in enumerate(escaped))
        objects.append(f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
                       f"/Contents {len(objects)} 0 R >>")
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def without_addresses(raw: bytes) -> list[list[str]]:
    """New Jersey's list, page by page, without its candidates' addresses: a candidate's first
    line keeps its name and party where they were, the address lines under it are left out."""
    pages: list[list[str]] = []
    for line in pdf_lines(raw):
        if re.match(r"\d{2}/\d{2}/\d{4}\s.*Official List", line):
            pages.append([])
        if not line.strip() or not pages:
            continue
        indent = len(line) - len(line.lstrip())
        if indent and indent < 50 and not re.search(r"Candidates for|GENERAL ELECTION", line):
            continue
        cells = re.split(r"\s{2,}", line.strip())
        if (not indent and len(cells) >= 3 and not re.match(r"Name\s{2,}Address|\d{2}/\d{2}/\d{4}", line)
                and "Congressional District" not in line):
            line = cells[0].ljust(line.rindex(cells[-1])) + cells[-1]
        pages[-1].append(line)
    return pages


def record_nj(client: httpx.Client, key: str) -> None:
    """New Jersey: NJ_ADDRESS's Census answer; the Division of Elections' election information
    page, cut down to its title and its links to the general election's lists; the U.S. Senate and
    House lists it links, rewritten without the candidates' addresses; the address's FEC filers for
    U.S. Senate and House, its legislators, and its members of Congress added to officeholders_congress.json."""
    name, address = NJ_ADDRESS
    response = client.get(f"{census.BASE}/onelineaddress", params={"address": census.normalize_address(address), **census.PARAMS})
    response.raise_for_status()
    save(f"census_{name}.json", response.json())
    match = response.json()["result"]["addressMatches"][0]
    place = census.parse_geographies(match["geographies"], match["coordinates"]["y"], match["coordinates"]["x"], None)
    response = client.get(nj.URL.format(year=FEC_CYCLE))
    response.raise_for_status()
    title = " ".join(re.search(r"<title>[^<]*</title>", response.text).group(0).split())
    anchors = [" ".join(a.split()) for a in re.findall(r"<a [^>]*href=\"[^\"]*\.pdf\".*?</a>", response.text, re.S)
               if "-general-candidates-" in a or re.search(r"-general-results-us-(senate|house)\.pdf", a)]
    (FIXTURES / "state_nj.html").write_text(
        f"<html><head>{title}</head><body>\n" + "\n".join(f"<p>{a}</p>" for a in anchors) + "\n</body></html>\n",
        encoding="utf-8", newline="")
    for kind, url in nj.links(response.text)["links"].items():
        response = client.get(url)
        response.raise_for_status()
        (FIXTURES / f"state_nj_{kind}.pdf").write_bytes(text_pdf(without_addresses(response.content)))
        print(f"state_nj_{kind}.pdf: {len(nj.NjList.parse((FIXTURES / f'state_nj_{kind}.pdf').read_bytes()))} candidates")
    for office, district in (("senate", None), ("house", place.cd)):
        response = client.get(f"{fec.API}/elections/", headers={"X-Api-Key": key}, params={
            "state": "NJ", "cycle": str(FEC_CYCLE), "election_full": "true", "per_page": "100", "sort": "-total_receipts",
            "office": office, **({"district": f"{district:02d}"} if district else {})})
        response.raise_for_status()
        save(f"fec_elections_nj_{office}{f'_{district:02d}' if district else ''}.json", response.json())
    response = client.get(officeholders.LEGISLATURE.format(state="nj"))
    response.raise_for_status()
    columns = ("id", "name", "current_party", "current_district", "current_chamber", "given_name", "family_name")
    out = io.StringIO()
    writer_csv = csv.DictWriter(out, columns, extrasaction="ignore", lineterminator="\n")
    writer_csv.writeheader()
    writer_csv.writerows(csv.DictReader(io.StringIO(response.text)))
    (FIXTURES / "officeholders_nj.csv").write_text(out.getvalue(), encoding="utf-8", newline="")
    response = client.get(officeholders.CONGRESS)
    response.raise_for_status()
    path = FIXTURES / "officeholders_congress.json"
    others = [m for m in json.loads(path.read_text(encoding="utf-8")) if m["terms"][-1].get("state") != "NJ"]
    save(path.name, others + [m for m in response.json() if m["terms"][-1].get("state") == "NJ"
                              and m["terms"][-1].get("district") in (None, place.cd)])

def record_co(client: httpx.Client, key: str) -> None:
    """Colorado: CO_ADDRESS's Census answer; the SOS's candidate spreadsheet, kept as served (it has
    no contact details); the address's FEC filers for U.S. Senate and House, its legislators, and
    its members of Congress added to officeholders_congress.json."""
    name, address = CO_ADDRESS
    response = client.get(f"{census.BASE}/onelineaddress", params={"address": census.normalize_address(address), **census.PARAMS})
    response.raise_for_status()
    save(f"census_{name}.json", response.json())
    match = response.json()["result"]["addressMatches"][0]
    place = census.parse_geographies(match["geographies"], match["coordinates"]["y"], match["coordinates"]["x"], None)
    response = client.get(co.URL.format(year=FEC_CYCLE))
    response.raise_for_status()
    (FIXTURES / "state_co.xlsx").write_bytes(response.content)
    print(f"state_co.xlsx: {len(co.CoList.parse(response.content))} candidates")
    for office, district in (("senate", None), ("house", place.cd)):
        response = client.get(f"{fec.API}/elections/", headers={"X-Api-Key": key}, params={
            "state": "CO", "cycle": str(FEC_CYCLE), "election_full": "true", "per_page": "100", "sort": "-total_receipts",
            "office": office, **({"district": f"{district:02d}"} if district else {})})
        response.raise_for_status()
        save(f"fec_elections_co_{office}{f'_{district:02d}' if district else ''}.json", response.json())
    response = client.get(officeholders.LEGISLATURE.format(state="co"))
    response.raise_for_status()
    columns = ("id", "name", "current_party", "current_district", "current_chamber", "given_name", "family_name")
    out = io.StringIO()
    writer_csv = csv.DictWriter(out, columns, extrasaction="ignore", lineterminator="\n")
    writer_csv.writeheader()
    writer_csv.writerows(csv.DictReader(io.StringIO(response.text)))
    (FIXTURES / "officeholders_co.csv").write_text(out.getvalue(), encoding="utf-8", newline="")
    response = client.get(officeholders.CONGRESS)
    response.raise_for_status()
    path = FIXTURES / "officeholders_congress.json"
    others = [m for m in json.loads(path.read_text(encoding="utf-8")) if m["terms"][-1].get("state") != "CO"]
    save(path.name, others + [m for m in response.json() if m["terms"][-1].get("state") == "CO"
                              and m["terms"][-1].get("district") in (None, place.cd)])


def record_il(client: httpx.Client, key: str) -> None:
    """Illinois: IL_ADDRESS's Census answer; the State Board's list of elections, cut down to its
    table; the election's download page, cut down to its form with its hidden fields' values made
    up; the candidate data file it posts back for, with every contact column emptied; the address's
    FEC filers for U.S. Senate and House, its legislators, and its members of Congress added to
    officeholders_congress.json."""
    name, address = IL_ADDRESS
    response = client.get(f"{census.BASE}/onelineaddress", params={"address": census.normalize_address(address), **census.PARAMS})
    response.raise_for_status()
    save(f"census_{name}.json", response.json())
    match = response.json()["result"]["addressMatches"][0]
    place = census.parse_geographies(match["geographies"], match["coordinates"]["y"], match["coordinates"]["x"], None)
    response = client.get(il.INDEX)
    response.raise_for_status()
    table = re.search(r"<table[^>]*id=\"ContentPlaceHolder1_gvElections\".*?</table>", response.text, re.S).group(0)
    (FIXTURES / "state_il.html").write_text(f"<html><body>\n{table}\n</body></html>\n", encoding="utf-8", newline="")
    url = il.DOWNLOAD.format(id=il.elections(response.text)["elections"][general_day(dt.date.today()).isoformat()])
    response = client.get(url)
    response.raise_for_status()
    fields = il.hidden_fields(response.text)
    inputs = "\n".join(f'<input type="hidden" name="{field}" id="{field}" value="{field.strip("_")}-recorded" />'
                       for field in fields)
    (FIXTURES / "state_il_download.html").write_text(
        f'<html><body><form method="post" action="./DownloadCandidates.aspx" id="form1">\n{inputs}\n</form></body></html>\n',
        encoding="utf-8", newline="")
    response = client.post(url, data={**fields, **il.FORM})
    response.raise_for_status()
    lines = response.content.decode("utf-8").splitlines()
    header = lines[0].split("\t")
    contact = {header.index(c) for c in ("Address1", "Address2", "City", "State", "Zip", "WebSiteAddress", "EmailAddress")}
    text = "".join("\t".join("" if i in contact else cell for i, cell in enumerate(line.split("\t"))) + "\r\n"
                   for line in lines[:1] + [line for line in lines[1:] if line.strip()])
    (FIXTURES / "state_il.tsv").write_text(text, encoding="utf-8", newline="")
    print(f"state_il.tsv: {len(il.parse(text))} active candidates")
    for office, district in (("senate", None), ("house", place.cd)):
        response = client.get(f"{fec.API}/elections/", headers={"X-Api-Key": key}, params={
            "state": "IL", "cycle": str(FEC_CYCLE), "election_full": "true", "per_page": "100", "sort": "-total_receipts",
            "office": office, **({"district": f"{district:02d}"} if district else {})})
        response.raise_for_status()
        save(f"fec_elections_il_{office}{f'_{district:02d}' if district else ''}.json", response.json())
    response = client.get(officeholders.LEGISLATURE.format(state="il"))
    response.raise_for_status()
    columns = ("id", "name", "current_party", "current_district", "current_chamber", "given_name", "family_name")
    out = io.StringIO()
    writer_csv = csv.DictWriter(out, columns, extrasaction="ignore", lineterminator="\n")
    writer_csv.writeheader()
    writer_csv.writerows(csv.DictReader(io.StringIO(response.text)))
    (FIXTURES / "officeholders_il.csv").write_text(out.getvalue(), encoding="utf-8", newline="")
    response = client.get(officeholders.CONGRESS)
    response.raise_for_status()
    path = FIXTURES / "officeholders_congress.json"
    others = [m for m in json.loads(path.read_text(encoding="utf-8")) if m["terms"][-1].get("state") != "IL"]
    save(path.name, others + [m for m in response.json() if m["terms"][-1].get("state") == "IL"
                              and m["terms"][-1].get("district") in (None, place.cd)])


GA_PLACES = {
    ("Federal", ""), ("State Race", ""), ("Statewide", ""), ("Countywide", "FULTON"), ("County Level", "FULTON"),
    ("Countywide", "TOWNS"), ("Countywide", "LAMAR"), ("Countywide", "WASHINGTON"), ("Countywide", "FORSYTH"),
    ("Countywide", "POLK"), ("County Level", "TELFAIR"), ("County Level", "SPALDING"),
    ("Municipalwide", "DANVILLE_TWIGGS"), ("Municipalwide", "GORDON"), ("Municipalwide", "FLOWERY_BRANCH"),
    ("Municipalwide", "PINE_LAKE"), ("Municipalwide", "DORAVILLE"), ("Municipal Level", "BROOKHAVEN"),
    ("Municipal Level", "HAZLEHURST"),
}  # the qualifying list's offices kept: Atlanta's county, and one of each kind of race and declaration
GA_KEPT = {"Name_on_Ballot__c", "Candidate_Party__c", "Declaration__c", "Incumbent__c", "County__c", "Date_Qualified__c",
           "Elected_Office__r", "vr_Political_Bodies__c"}
GA_RACES = {"US SENATE", "GOVERNOR", "LIEUTENANT GOVERNOR", "STATE SCHOOL SUPERINTENDENT", "COMMISSIONER OF INSURANCE",
            "PUBLIC SERVICE COMMISSION 3", "PUBLIC SERVICE COMMISSION 5", "US HOUSE 5", "US HOUSE 11", "STATE SENATE 36",
            "STATE HOUSE 58", "STATE HOUSE 151", "DISTRICT ATTORNEY ATLANTIC"}
GA_SKIPPED = ("Justice - Supreme Court of Georgia (Land)", "Party Question 1 - Rep",
              "Special State Senate - District 7/ Especial Senador Estatal del Distrito 7")


def _made_up(row: dict, n: int) -> dict:
    """A qualifying row with everything but what Pallot reads made up: no real email, phone or address."""
    out = {}
    for key, value in row.items():
        if key in GA_KEPT:
            out[key] = value
        elif isinstance(value, bool) or value is None:
            out[key] = value
        elif isinstance(value, (int, float)):
            out[key] = 0
        elif "Email" in key:
            out[key] = f"candidate{n}@example.com"
        elif "Phone" in key:
            out[key] = f"555-01{n % 100:02d}"
        elif "Website" in key and "Street" not in key:
            out[key] = "https://example.com"
        elif key == "Id" or key.endswith("_c") and key.startswith("Elected_Office"):
            out[key] = f"a0n{n:015d}"
        else:
            out[key] = f"made up {n}"
    return out


def record_ga(client: httpx.Client, saved: Path | None) -> None:
    """Georgia: the qualifying list saved by hand in manual/state_ga (``saved`` another copy), never
    downloaded (its site blocks scripts), cut down to GA_PLACES with every contact detail made up;
    the results site's list of elections (this year's and last), and the year's primary, recount and
    runoff, each cut down to GA_RACES' contests and GA_SKIPPED's, with only what Pallot reads; and
    Georgia's legislators. The Atlanta address and its FEC filers are nationwide's."""
    path = saved or next(iter(sorted((ROOT / "manual" / "state_ga").glob("*.json"))), None)
    if path is None:
        raise SystemExit("state_ga: save Georgia's qualifying list in manual/state_ga (see its README), or pass --json")
    groups = json.loads(path.read_text(encoding="utf-8"))["actions"][0]["returnValue"]["returnValue"]
    n = 0
    kept: dict = {}
    for kind, places in groups.items():
        for place, offices in places.items():
            if (kind, place.strip()) not in GA_PLACES:
                continue
            for office, rows in offices.items():
                for row in rows:
                    n += 1
                    kept.setdefault(kind, {}).setdefault(place, {}).setdefault(office, []).append(_made_up(row, n))
    save("state_ga.json", {"actions": [{"returnValue": {"returnValue": kept, "cacheable": True}}]})

    response = client.get(ga.ELECTIONS)
    response.raise_for_status()
    elections = ga.trim(response.json())
    elections["elections"] = [e for e in elections["elections"] if str(e["electionDate"]) >= "2025"]
    save("state_ga_elections.json", elections)
    for election, _ in ga.stages(elections, general_day(dt.date(2026, 9, 27))):
        response = client.get(ga.ELECTION.format(id=election))
        response.raise_for_status()
        data = response.json()
        items = []
        for item in data["ballotItems"]:
            contest = ga._CONTEST.fullmatch(ga._text(item["name"]))
            office = ga.state_office(contest.group("office")) if contest else None
            if (office and office.race in GA_RACES) or ga._text(item["name"]) in GA_SKIPPED:
                items.append({"name": item["name"], "summaryResults": {"ballotOptions": [
                    {key: option.get(key) for key in ("name", "voteCount", "isWriteIn", "party")}
                    for option in item["summaryResults"]["ballotOptions"]]}})
        save(f"state_ga_{election}.json", {"election": {key: data["election"].get(key) for key in ("name", "electionDate")},
                                           "ballotItems": items})
    response = client.get(officeholders.LEGISLATURE.format(state="ga"))
    response.raise_for_status()
    columns = ("id", "name", "current_party", "current_district", "current_chamber", "given_name", "family_name")
    out = io.StringIO()
    writer_csv = csv.DictWriter(out, columns, extrasaction="ignore", lineterminator="\n")
    writer_csv.writeheader()
    writer_csv.writerows(csv.DictReader(io.StringIO(response.text)))
    (FIXTURES / "officeholders_ga.csv").write_text(out.getvalue(), encoding="utf-8", newline="")


def record_wi(client: httpx.Client, key: str, saved: Path | None) -> None:
    """Wisconsin: WI_ADDRESS's Census answer; the Elections Commission's contests and candidates,
    never downloaded (its site blocks scripts): ``saved``, or the copy in manual/state_wi, cut down
    to the state's rows and WI_JURISDICTIONS'; its seat's FEC filers, its legislators, and its
    representative added to officeholders_congress.json."""
    name, address = WI_ADDRESS
    response = client.get(f"{census.BASE}/onelineaddress", params={"address": census.normalize_address(address), **census.PARAMS})
    response.raise_for_status()
    save(f"census_{name}.json", response.json())
    match = response.json()["result"]["addressMatches"][0]
    place = census.parse_geographies(match["geographies"], match["coordinates"]["y"], match["coordinates"]["x"], None)
    path = saved or next(iter(sorted((ROOT / "manual" / "state_wi").glob("*.csv"))), None)
    if path is None:
        raise SystemExit("state_wi: save Wisconsin's contests and candidates in manual/state_wi (see its README), or pass --csv")
    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    out = io.StringIO()
    writer = csv.DictWriter(out, reader.fieldnames or (), lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(row for row in reader if row["Jurisdiction"] == "STATE OF WISCONSIN"
                     or any(row["Jurisdiction"] == j or row["Jurisdiction"].endswith(f" - {j}") for j in WI_JURISDICTIONS))
    (FIXTURES / "state_wi.csv").write_text("﻿" + out.getvalue(), encoding="utf-8", newline="")
    print(f"state_wi.csv: {(FIXTURES / 'state_wi.csv').stat().st_size:,} bytes")

    response = client.get(f"{fec.API}/elections/", headers={"X-Api-Key": key}, params={
        "state": "WI", "cycle": str(FEC_CYCLE), "election_full": "true", "per_page": "100", "sort": "-total_receipts",
        "office": "house", "district": f"{place.cd:02d}"})
    response.raise_for_status()
    save(f"fec_elections_wi_house_{place.cd:02d}.json", response.json())
    response = client.get(officeholders.LEGISLATURE.format(state="wi"))
    response.raise_for_status()
    columns = ("id", "name", "current_party", "current_district", "current_chamber", "given_name", "family_name")
    legislators = io.StringIO()
    writer_csv = csv.DictWriter(legislators, columns, extrasaction="ignore", lineterminator="\n")
    writer_csv.writeheader()
    writer_csv.writerows(csv.DictReader(io.StringIO(response.text)))
    (FIXTURES / "officeholders_wi.csv").write_text(legislators.getvalue(), encoding="utf-8", newline="")
    response = client.get(officeholders.CONGRESS)
    response.raise_for_status()
    members = FIXTURES / "officeholders_congress.json"
    others = [m for m in json.loads(members.read_text(encoding="utf-8")) if m["terms"][-1].get("state") != "WI"]
    save(members.name, others + [m for m in response.json() if m["terms"][-1].get("state") == "WI"
                                 and m["terms"][-1].get("district") in (None, place.cd)])


def record_ny(client: httpx.Client, key: str, saved: Path | None) -> None:
    """New York: NY_ADDRESSES' Census answers; the State Board's certification, never downloaded (its
    site blocks scripts): ``saved``, or the PDF in manual/state_ny, cut down to its title and the
    races in NY_RACES and the addresses' districts, as text lines; their seats' FEC filers, the
    state's legislators, and their representatives added to officeholders_congress.json."""
    path = saved or next(iter(sorted((ROOT / "manual" / "state_ny").glob("*.pdf"))), None)
    if path is None:
        raise SystemExit("state_ny: save New York's certification in manual/state_ny (see its README), or pass --pdf")
    races, seats = set(NY_RACES), set()
    for name, address in NY_ADDRESSES.items():
        response = client.get(f"{census.BASE}/onelineaddress", params={"address": census.normalize_address(address), **census.PARAMS})
        response.raise_for_status()
        save(f"census_{name}.json", response.json())
        match = response.json()["result"]["addressMatches"][0]
        place = census.parse_geographies(match["geographies"], match["coordinates"]["y"], match["coordinates"]["x"], None)
        races |= {("REPRESENTATIVE IN CONGRESS", str(place.cd)), ("STATE SENATOR", str(place.sd)),
                  ("MEMBER OF ASSEMBLY", str(place.hd))}
        seats.add(place.cd)
    lines = pdf_lines(path.read_bytes())
    starts = [i for i, line in enumerate(lines) if "Office:" in line] + [len(lines)]
    kept = lines[:1]
    for start, end in zip(starts, starts[1:]):
        office = " ".join(lines[start].split("Office:", 1)[1].upper().split())
        district = next((line.split(":", 1)[1].strip() for line in lines[start:end] if line.startswith("District:")), "")
        if office in ("GOVERNOR AND LT. GOVERNOR", "COMPTROLLER", "ATTORNEY GENERAL") or (office, district) in races:
            kept += lines[start:end]
    (FIXTURES / "state_ny.txt").write_text("\n".join(kept) + "\n", encoding="utf-8", newline="\n")
    print(f"state_ny.txt: {(FIXTURES / 'state_ny.txt').stat().st_size:,} bytes")

    for cd in sorted(seats):
        response = client.get(f"{fec.API}/elections/", headers={"X-Api-Key": key}, params={
            "state": "NY", "cycle": str(FEC_CYCLE), "election_full": "true", "per_page": "100", "sort": "-total_receipts",
            "office": "house", "district": f"{cd:02d}"})
        response.raise_for_status()
        save(f"fec_elections_ny_house_{cd:02d}.json", response.json())
    response = client.get(officeholders.LEGISLATURE.format(state="ny"))
    response.raise_for_status()
    columns = ("id", "name", "current_party", "current_district", "current_chamber", "given_name", "family_name")
    legislators = io.StringIO()
    writer = csv.DictWriter(legislators, columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(csv.DictReader(io.StringIO(response.text)))
    (FIXTURES / "officeholders_ny.csv").write_text(legislators.getvalue(), encoding="utf-8", newline="")
    response = client.get(officeholders.CONGRESS)
    response.raise_for_status()
    members = FIXTURES / "officeholders_congress.json"
    others = [m for m in json.loads(members.read_text(encoding="utf-8")) if m["terms"][-1].get("state") != "NY"]
    save(members.name, others + [m for m in response.json() if m["terms"][-1].get("state") == "NY"
                                 and m["terms"][-1].get("district") in seats])


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
        texas = [row for row in rows if row.get("state") == "Texas"]
        others = [row for row in rows if row.get("state") != "Texas"][:3]
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
    texas = [m for m in members if m["terms"][-1].get("state") == "TX"]
    others = [m for m in members if m["terms"][-1].get("state") != "TX"][:3]
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
    parser.add_argument("--only", choices=("ballots", "suggest", "fec", "nationwide", "state_lists", "state_ca", "state_nv", "state_ga", "state_wi", "state_oh", "state_ia", "state_nj", "state_ny", "state_co", "state_il", "polls", "key_dates", "officeholders",
                                           "wikidata", "tigerweb", "election_precincts", "county_precincts", "endorsement_feeds", "tec", "trackaipac", "voteforpeace"),
                        help="record just this part")
    parser.add_argument("--pdf", type=Path, help="state_ca: a copy of California's certified list, instead of downloading it; "
                                                 "state_nv: Nevada's, instead of the one saved in manual/state_nv; "
                                                 "state_ia: Iowa's, instead of the one saved in manual/state_ia; "
                                                 "state_ny: New York's, instead of the one saved in manual/state_ny")
    parser.add_argument("--json", type=Path, help="state_ga: Georgia's qualifying list, instead of the one saved in "
                                                  "manual/state_ga; state_oh: Ohio's, instead of manual/state_oh/ohio.json")
    parser.add_argument("--csv", type=Path, help="state_wi: Wisconsin's contests and candidates, instead of the one "
                                                 "saved in manual/state_wi")
    args = parser.parse_args(argv)
    only = args.only
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
        if only in (None, "state_ca"):
            record_ca(client, config.fec_api_key, args.pdf if only == "state_ca" else None)
        if only in (None, "state_nv"):
            record_nv(client, config.fec_api_key, args.pdf if only == "state_nv" else None)
        if only in (None, "state_ga"):
            record_ga(client, args.json if only == "state_ga" else None)
        if only in (None, "state_wi"):
            record_wi(client, config.fec_api_key, args.csv)
        if only in (None, "state_oh"):
            record_oh(client, config.fec_api_key, args.json if only == "state_oh" else None)
        if only in (None, "state_ia"):
            record_ia(client, config.fec_api_key, args.pdf if only == "state_ia" else None)
        if only in (None, "state_nj"):
            record_nj(client, config.fec_api_key)
        if only in (None, "state_ny"):
            record_ny(client, config.fec_api_key, args.pdf if only == "state_ny" else None)
        if only in (None, "state_co"):
            record_co(client, config.fec_api_key)
        if only in (None, "state_il"):
            record_il(client, config.fec_api_key)
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
