"""Record the live API responses that Pallot's tests replay, into tests/fixtures/.

    python scripts/record_fixtures.py              # everything
    python scripts/record_fixtures.py --only fec   # just the FEC responses (or ballots, suggest, nationwide, state_lists, state_va, state_ca, state_nv, state_ga, state_wi, state_oh, state_ia, state_nj, state_ny, state_co, state_wy, state_il, state_ak, state_me, state_ne, state_nm, state_wa, state_in, state_md, state_mo, state_sc, state_ky, state_ok, state_ks, state_mt, state_sd, state_hi, state_nd, state_de, state_vt, state_ms, state_ar, grid, polls, key_dates, officeholders, congress_gov, wikidata, tigerweb, election_precincts, county_precincts, endorsement_feeds, tec, trackaipac, voteforpeace)

The ballots take about 30 requests (Census geocoder, Nominatim, Texas SOS), and
the address suggestions two (Google's Places Autocomplete, with PALLOT_GOOGLE_API_KEY), the polls three (FiftyPlusOne, one per kind of race),
the key dates one (the Texas SOS's Important Election Dates page, kept as served), the seat
holders two (Congress's current members, cut down to Texas's and a few others, and Open States'
Texas legislators, cut down to the columns Pallot reads), Congress.gov two (one member's newest
sponsored and cosponsored bills; DEMO_KEY allows 10 an hour), Wikidata two (its Texas officeholders,
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
fields read) and Virginia's (state_va records it alone: its Candidates & Referendums page cut down
to its links, the election's list of all offices, and 2023's General Assembly list, without their
contact columns), their seats' FEC filers, and their legislators. California's (state_ca) takes a Los Angeles address and its
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
lists it links, rewritten as small text PDFs without the candidates' addresses, and the same for
the odd years' lists for the State Senate and General Assembly (NJ_ODD_YEARS). New York's (state_ny) takes a
Manhattan and an Albany address and the certification saved by hand in manual/state_ny (--pdf
another copy), never downloaded, cut down to some races' text lines. Colorado's (state_co) takes a
Denver address and the SOS's candidate spreadsheet as served (it has no contact details). Wyoming's (state_wy) takes the
SOS's candidates data file with every candidate's contact details made up, and its legislators. Illinois's
(state_il) takes a Chicago address, the State Board's list of elections cut down to its table, the
election's download page cut down to its form, and the candidate data file it posts back for, with
its contact columns emptied. Alaska's (state_ak) takes an Anchorage address and the Division of
Elections' list, its three pages one at a time, without the candidates' contact details. Maine's
(state_me) takes a Bangor address, the Secretary of State's Upcoming Elections page cut down to its
links, and the candidate spreadsheet and declared write-ins PDF it links, as served (they have
no contact details). Nebraska's (state_ne) takes an Omaha address, the Secretary of State's
elections page cut down to its links, its candidate list rewritten without contact details (its
pages turned sideways, as served) and its judges for retention as served. New Mexico's (state_nm)
takes an Albuquerque address, the Secretary of State's home page cut down to its links to the
candidate list, and the list's grid page for the election without contact details. Washington's
(state_wa) takes a Seattle address; its list is the grid's fixtures (grid). Indiana's (state_in)
takes a Fort Wayne address, the Election Division's home page cut down to its link to the
candidate list, and the spreadsheet it links, as served (it has no contact details). Maryland's (state_md)
takes an Annapolis address, the State Board of Elections' general candidate listings page cut down to
its link to the statewide list, and that CSV with its contact columns emptied. Missouri's (state_mo)
takes a Jefferson City address, with its U.S. House district on the 2022 map from TIGERweb, the
Secretary of State's elections page cut down to its links, and the certification it links as its
text alone (it has no contact details). South Carolina's (state_sc) takes a Columbia address, the
State Election Commission's list of the year's elections, and its search of the general election's
candidates cut down to the rows it places and two of each office it leaves out. Kentucky's (state_ky)
takes a Frankfort address, the Secretary of State's candidate filings page cut down to its election
dropdown, and the list of all candidates its postback answers, each row without its post office box
or email. Oklahoma's (state_ok) takes a Tulsa address, and the State Election Board's list of
elections cut down to a few counties' sections, as served (it has no contact details). Kansas's
(state_ks) takes a Topeka address, the Secretary of State's candidate list page cut down to its
election dropdown, and the list its postback answers, each row cut down to its first six columns,
without addresses, phones or emails. Montana's (state_mt) takes a Helena address, the Secretary of
State's candidate list page cut down to its election dropdown, and the CSV its postback exports,
without the candidates' contact details. South Dakota's (state_sd) takes a Pierre address, the
Secretary of State's Upcoming Elections page cut down to its menu's link to the candidate list, the
grid's page cut down to its form's hidden fields, and the CSV its postback exports, without the
candidates' mailing addresses. Hawaii's (state_hi) takes a Honolulu address, the Office of
Elections' Candidate Reports page cut down to its year and its link to the report, the grid's page
cut down to its form's hidden fields, and the CSV its postback exports, without the candidates'
legal names, addresses, phones, emails and websites. North Dakota's (state_nd) takes a Bismarck
address, the Secretary of State's Candidate page cut down to its link to the candidate list, the
grid's page cut down to its form's hidden fields, and the table its Search postback answers, each
row cut down to its contest, term, district, county, name and party. Delaware's (state_de) takes a
Georgetown address, and the Department of Elections' candidate list and declared write-ins, each
sheet cut down to its office, name, party, status and dates. Vermont's (state_vt) takes a
Montpelier address, and the Secretary of State's qualified candidates, the sheet cut down to
its contest, district, name, party and seats, with the justices of the peace of one town. Mississippi's
(state_ms) takes a Jackson address, and the Secretary of State's Candidate Qualifying List, as served
without its scripts (it has no contact details). Arkansas's (state_ar) takes a Little Rock address
and the candidate search saved by hand in manual/state_ar (--csv another copy), never downloaded,
cut down to Congress, the statewide offices and a few districts' rows. A Census answer whose
/geographies fails is its /locations match with TIGERweb's identify. The candidate-list grid six states share (grid) takes Washington's page, cut down to its election
dropdown and its table's first rows, and the CSV it exports, both without contact details. The
TrackAIPAC, Vote for Peace and Texas Ethics
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
import time
import zipfile
from pathlib import Path
from typing import Collection

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pallot.config import DEMO_KEY, load_config  # noqa: E402
from pallot.http_cache import hidden_fields, trusting  # noqa: E402
from pallot.offices import classify  # noqa: E402
from pallot.sources import (  # noqa: E402
    ca_key_dates, census, congress_gov, county_precincts, election_precincts, fec, google, key_dates, nominatim,
    officeholders, polls, sos, suggestions, tigerweb, wikidata,
)
from pallot.matching import full_key  # noqa: E402
from pallot.sources.endorsement_feeds import FEEDS  # noqa: E402
from pallot.text import display_person  # noqa: E402
from pallot.sources.tec import _seats, tec_seat  # noqa: E402
from pallot.sources.fec import general_day  # noqa: E402
from pallot.states import _ORDINALS, Rows, ak, ar, ca, co, de, fl, ga, grid, ia, il, in_, ks, md, me, ky, mi, mo, ms, mt, nc, nd, ne, nj, nm, ok, ordinal, pa, pdf_lines, sc, sd, hi, sheet_rows, va, vt, wy  # noqa: E402
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
# New Jersey's newest odd years: 2025's lists (the General Assembly, and the State Senate's special
# election in the 35th district) and 2023's, the newest list of the whole State Senate.
NJ_ODD_YEARS = {2025: ("state-senate", "general-assembly"), 2023: ("state-senate",)}
CO_ADDRESS = ("denver", "1437 Bannock St, Denver, CO 80202")  # the City and County Building: CO-1
WY_CONTACT = {"Mailing Address": "PO Box 1", "Mailing City State & Zip": "CHEYENNE WY 82001",
              "Campaign Telephone": "307-555-0100", "Email Address": "CANDIDATE@EXAMPLE.COM",
              "Web Address": "EXAMPLE.COM"}  # made up
IL_ADDRESS = ("chicago", "121 N LaSalle St, Chicago, IL 60602")  # City Hall: Cook County
AK_ADDRESS = ("anchorage", "632 W 6th Ave, Anchorage, AK 99501")  # City Hall: Senate District I, up in 2026
ME_ADDRESS = ("bangor", "73 Harlow St, Bangor, ME 04401")  # City Hall: ME-2, ranked-choice in 2026
NE_ADDRESS = ("omaha", "4917 Underwood Ave, Omaha, NE 68132")  # Dundee, Douglas County: NE-2, Legislature District 8
WA_ADDRESS = ("seattle", "600 4th Ave, Seattle, WA 98104")  # City Hall: King County
IN_ADDRESS = ("fortwayne", "200 E Berry St, Fort Wayne, IN 46802")  # Citizens Square: Allen County
MD_ADDRESS = ("annapolis", "100 State Cir, Annapolis, MD 21401")  # the State House: Anne Arundel County
# The Capitol, Cole County: MO-3 on Missouri's 2022 map, in force in 2026, and MO-5 on the 2025 one the geocoder gives.
MO_ADDRESS = ("jeffersoncity", "201 W Capitol Ave, Jefferson City, MO 65101")
SC_ADDRESS = ("columbia", "1100 Gervais St, Columbia, SC 29201")  # the State House: Richland County
KY_ADDRESS = ("frankfort", "700 Capital Ave, Frankfort, KY 40601")  # the Capitol: Franklin County, Senate District 20
KS_ADDRESS = ("topeka", "300 SW 10th Ave, Topeka, KS 66612")  # the Statehouse: Shawnee County, its district judges
MT_ADDRESS = ("helena", "1301 E 6th Ave, Helena, MT 59601")  # the Capitol: Lewis and Clark County
SD_ADDRESS = ("pierre", "500 E Capitol Ave, Pierre, SD 57501")  # the Capitol: Hughes County, District 24
HI_ADDRESS = ("honolulu", "415 S Beretania St, Honolulu, HI 96813")  # the State Capitol: HI-1
ND_ADDRESS = ("bismarck", "600 E Boulevard Ave, Bismarck, ND 58505")  # the State Capitol: Burleigh County
DE_ADDRESS = ("georgetown", "39 The Circle, Georgetown, DE 19947")  # Town Hall: Sussex, Senate District 19 (up in 2026)
VT_ADDRESS = ("montpelier", "115 State St, Montpelier, VT 05633")  # the State House: Washington County
MS_ADDRESS = ("jackson", "400 High St, Jackson, MS 39201")  # the Capitol: Hinds County, its District Attorney 7
AR_ADDRESS = ("littlerock", "500 Woodlane St, Little Rock, AR 72201")  # the State Capitol: Pulaski County, AR-2
# Arkansas's offices kept in its fixture besides Congress, the statewide ones and the address's districts: House 8's
# full term and its special, an independent's race, and a circuit judge's runoff, which is left out.
AR_OFFICES = ("State Representative District 08", "State Representative District 23",
              "Circuit Judge, District 04, Division 02")
OK_ADDRESS = ("tulsa", "175 E 2nd St, Tulsa, OK 74103")  # City Hall: Tulsa County, OK-1, its district judges
# Oklahoma's list's counties kept in its fixture: the Tulsa address's and a district judge's with it (Pawnee),
# enough districts for its minimum, Le Flore (written "LEFLORE"), and county offices and judges of each kind.
OK_COUNTIES = ("ALFALFA", "CANADIAN", "CLEVELAND", "COMANCHE", "LEFLORE", "OKLAHOMA", "PAWNEE", "PITTSBURG", "TULSA")
NM_ADDRESS = ("albuquerque", "400 Marquette Ave NW, Albuquerque, NM 87102")  # the Government Center: NM-1
# Virginia's newest odd-year list still served, for both chambers: 2025's (the House of Delegates
# alone) answered 404 by 2026-10-29, and 2023's moved to the previous candidate lists.
VA_ODD_YEAR = ("https://www.elections.virginia.gov/casting-a-ballot/previous-candidate-lists/"
               "2023-november-general-election---ga-candidates/")
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


LEGISLATOR_COLUMNS = ("id", "name", "current_party", "current_district", "current_chamber", "given_name", "family_name")


def record_census(client: httpx.Client, name: str, address: str) -> census.Place:
    """``address``'s Census answer, saved as census_<name>.json; the place it gives. When the
    geocoder's /geographies answers a 5xx, its /locations match with the geographies from
    TIGERweb's identify at its point, the same layers Pallot's own fallback reads."""
    normalized = census.normalize_address(address)
    response = client.get(f"{census.BASE}/onelineaddress", params={"address": normalized, **census.PARAMS})
    if response.status_code >= 500:
        response = client.get(f"{census.LOCATIONS}/onelineaddress", params={
            "address": normalized, "benchmark": census.PARAMS["benchmark"], "format": "json"})
        response.raise_for_status()
        answer = response.json()
        match = answer["result"]["addressMatches"][0]
        index = client.get(tigerweb.index_spec().url, params=tigerweb.index_spec().params)
        index.raise_for_status()
        spec = tigerweb.identify_spec(tigerweb.place_layer_ids(index.json()), match["coordinates"]["y"],
                                      match["coordinates"]["x"])
        found = client.get(spec.url, params=spec.params)
        found.raise_for_status()
        match["geographies"] = tigerweb.geographies(found.json())
    else:
        response.raise_for_status()
        answer = response.json()
    save(f"census_{name}.json", answer)
    match = answer["result"]["addressMatches"][0]
    return census.parse_geographies(match["geographies"], match["coordinates"]["y"], match["coordinates"]["x"], None)


def record_filers(client: httpx.Client, key: str, state: str, district: int | None = None) -> None:
    """The FEC's filers for ``state``'s U.S. Senate race, or for its House ``district`` (0 at large)."""
    house = {} if district is None else {"district": f"{district:02d}"}
    response = client.get(f"{fec.API}/elections/", headers={"X-Api-Key": key}, params={
        "state": state, "cycle": str(FEC_CYCLE), "election_full": "true", "per_page": "100", "sort": "-total_receipts",
        "office": "senate" if district is None else "house", **house})
    response.raise_for_status()
    save(f"fec_elections_{state.lower()}_{'senate' if district is None else f'house_{district:02d}'}.json",
         response.json())


def record_legislators(client: httpx.Client, state: str) -> None:
    """``state``'s Open States legislators, the columns officeholders.py reads."""
    response = client.get(officeholders.LEGISLATURE.format(state=state.lower()))
    response.raise_for_status()
    out = io.StringIO()
    writer = csv.DictWriter(out, LEGISLATOR_COLUMNS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(csv.DictReader(io.StringIO(response.text)))
    (FIXTURES / f"officeholders_{state.lower()}.csv").write_text(out.getvalue(), encoding="utf-8", newline="")


def record_members(client: httpx.Client, state: str, districts: Collection[int | None] | None = None) -> None:
    """``state``'s members of Congress (those of ``districts`` only, a senator's None) in place of
    the ones officeholders_congress.json had."""
    response = client.get(officeholders.CONGRESS)
    response.raise_for_status()
    path = FIXTURES / "officeholders_congress.json"
    others = [m for m in json.loads(path.read_text(encoding="utf-8")) if m["terms"][-1].get("state") != state]
    save(path.name, others + [m for m in response.json() if m["terms"][-1].get("state") == state
                              and (districts is None or m["terms"][-1].get("district") in districts)])


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


def va_list(text: str, locality: str | None = None) -> tuple[str, int]:
    """One of Virginia's lists as a page with only its heading and the columns states/va.py reads
    (no candidates' emails, phones or addresses); with ``locality``, the list of all offices cut
    down to the first row of each candidate for an office it reads, and every row of that
    locality. The page and its rows."""
    reader = Rows(cells=("td", "th"))
    reader.feed(text)
    header = next(i for i, row in enumerate(reader.rows) if "Office Title" in row and "Candidate Name" in row)
    names = reader.rows[header]
    read = [names.index(name) for options in va.COLUMNS.values() for name in options if name in names]
    if locality:
        read.insert(0, names.index("Locality"))
    rows, seen = [[names[i] for i in read]], set()
    for row in reader.rows[header + 1:]:
        if len(row) < len(names):
            continue
        key = (row[names.index("Office Title")], row[names.index("Candidate Name")])
        if locality and row[names.index("Locality")] != locality and (key in seen or not va._race(*key[:1], "1")):
            continue
        seen.add(key)
        rows.append([row[i] for i in read])
    heading = " ".join(re.search(r"<h1[^>]*>.*?</h1>", text, re.S).group(0).split())
    table = "\n".join("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<html><body>{heading}\n<table>\n{table}\n</table></body></html>\n", len(rows) - 1


def record_va(client: httpx.Client) -> None:
    """Virginia: the Department of Elections' Candidates & Referendums page cut down to its title,
    heading and links to the general election's lists; the election's list of all offices (va_list),
    cut down to each candidate's first row and Richmond's; and VA_ODD_YEAR's list for the General
    Assembly, cut down the same way."""
    response = client.get(va.PAGE)
    response.raise_for_status()
    title = " ".join(re.search(r"<title>[^<]*</title>", response.text).group(0).split())
    heading = " ".join(re.search(r"<h1[^>]*>.*?</h1>", response.text, re.S).group(0).split())
    anchors = [" ".join(a.split()) for a in re.findall(r"<a [^>]*href=\"[^\"]*-gen-elect-[^\"]*\".*?</a>", response.text, re.S)]
    (FIXTURES / "state_va.html").write_text(
        f"<html><head>{title}</head><body>{heading}\n" + "\n".join(f"<p>{a}</p>" for a in anchors) + "\n</body></html>\n",
        encoding="utf-8", newline="")
    day = general_day(dt.date(FEC_CYCLE, 1, 1))
    for url, fixture, locality in ((va.read(va.links(response.text)["links"][day.isoformat()])[0], "state_va_all.html",
                                    "RICHMOND CITY"), (VA_ODD_YEAR, "state_va_2023.html", None)):
        time.sleep(2)
        response = client.get(url)
        response.raise_for_status()
        page, rows = va_list(response.text, locality)
        (FIXTURES / fixture).write_text(page, encoding="utf-8", newline="")
        print(f"{fixture}: {rows:,} rows, {len(va.VaList.parse(page))} candidates")


def record_state_lists(client: httpx.Client, key: str) -> None:
    """The states with an official list: STATE_ADDRESSES' Census answers; North Carolina's list cut
    down to NC_COUNTIES and to the columns states/nc.py reads (no addresses, phones or emails);
    Michigan's report without its inline styles; the FEC's filers for each address's seats; their
    Open States legislators (the columns officeholders.py reads), and their members of Congress
    added to officeholders_congress.json."""
    seats, places = [], {}
    for name, address in STATE_ADDRESSES.items():
        place = record_census(client, name, address)
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
    for state in states:
        record_legislators(client, state)
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
    place = record_census(client, name, address)
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

    record_filers(client, key, "CA", place.cd)
    record_legislators(client, "ca")
    record_members(client, "CA", (None, place.cd))


def record_nv(client: httpx.Client, key: str, pdf: Path | None) -> None:
    """Nevada: NV_ADDRESS's Census answer; the SOS's certified list, never downloaded (its site
    blocks scripts): ``pdf``, or the copy saved in manual/state_nv, cut down to the first page (the
    column headings and the statewide races) and the pages with the address's county or city; its
    seat's FEC filers, its legislators, and its representative added to officeholders_congress.json."""
    name, address = NV_ADDRESS
    place = record_census(client, name, address)
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

    record_filers(client, key, "NV", place.cd)
    record_legislators(client, "nv")
    record_members(client, "NV", (None, place.cd))


def record_oh(client: httpx.Client, key: str, saved: Path | None) -> None:
    """Ohio: OH_ADDRESS's Census answer; the statewide list transcribed by hand into
    manual/state_oh (``saved`` another copy), never downloaded (its site blocks scripts), copied as
    it is (it holds only offices, names and parties); its House seat's FEC filers, its legislators,
    and its members of Congress added to officeholders_congress.json."""
    name, address = OH_ADDRESS
    place = record_census(client, name, address)
    saved = saved or ROOT / "manual" / "state_oh" / "ohio.json"
    if not saved.exists():
        raise SystemExit("state_oh: save Ohio's list as manual/state_oh/ohio.json (see its README), or pass --json")
    save("state_oh.json", json.loads(saved.read_text(encoding="utf-8")))
    record_filers(client, key, "OH", place.cd)
    record_legislators(client, "oh")
    record_members(client, "OH", (None, place.cd))


def record_ia(client: httpx.Client, key: str, pdf: Path | None) -> None:
    """Iowa: IA_ADDRESS's Census answer; the candidate list saved by hand in manual/state_ia
    (``pdf`` another copy), never downloaded (its site blocks scripts), as its text lines cut down
    to Congress, the statewide offices, the address's and the next districts' races and one with
    a party's "--", with every candidate's address, phone and email made up (IA_CONTACT); its
    seats' FEC filers, its legislators, and its members of Congress added to officeholders_congress.json."""
    name, address = IA_ADDRESS
    place = record_census(client, name, address)
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
    for district in (None, place.cd):
        record_filers(client, key, "IA", district)
    record_legislators(client, "ia")
    record_members(client, "IA", (None, place.cd))


def text_pdf(pages: list[list[str]], width: int = 612) -> bytes:
    """A PDF of ``pages`` of lines in Courier, each laid out as written, for a fixture that
    stands in for a list whose real file carries what Pallot never keeps; ``width`` points wide."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "", "<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"]
    kids = []
    for lines in pages:
        escaped = [re.sub(r"([\\()])", r"\\\1", line) for line in lines]
        stream = "\n".join(f"BT /F1 5 Tf 20 {770 - 9 * i} Td ({line}) Tj ET" for i, line in enumerate(escaped))
        objects.append(f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} 792] /Resources << /Font << /F1 3 0 R >> >> "
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
    line keeps its name and party where they were, a name or running mate wrapped onto the lines
    under it keeps only that, and the address lines are left out."""
    lines = pdf_lines(raw)
    labels = nj._labels(lines)
    pages: list[list[str]] = []
    totals = False
    for line in lines:
        if re.match(r"\s*\d{2}/\d{2}/\d{4}\s.*Official List", line):
            pages.append([])
        if not line.strip() or not pages:
            continue
        indent = len(line) - len(line.lstrip())
        if indent and indent < 50 and not re.search(r"Candidates for|GENERAL ELECTION|Official List", line):
            continue
        text = " ".join(line.split())
        totals = totals or text.startswith("Candidate Totals")
        cells = re.split(r"\s{2,}", line.strip())
        if not (indent or totals or re.match(r"Name\s{2,}Address|\d{2}/\d{2}/\d{4}", line) or "District:" in line):
            label = next((label for label in labels if text.endswith(label)), None)
            line = (cells[0].ljust(max(len(line.rstrip()) - len(label), len(cells[0]) + 2)) + label if label
                    else cells[0][:cells[0].index(")") + 1] if cells[0].startswith("(") and ")" in cells[0] else cells[0])
        pages[-1].append(line)
    return pages


def nj_page(client: httpx.Client, year: int, fixture: str) -> dict[str, str]:
    """New Jersey's election information page for ``year``, written to ``fixture`` cut down to its
    title and its links to the general election's lists. Its links (nj.links)."""
    response = client.get(nj.URL.format(year=year))
    response.raise_for_status()
    title = " ".join(re.search(r"<title>[^<]*</title>", response.text).group(0).split())
    anchors = [" ".join(a.split()) for a in re.findall(r"<a [^>]*href=\"[^\"]*\.pdf\".*?</a>", response.text, re.S)
               if "-general-candidates-" in a or re.search(r"-general-results-us-(senate|house)\.pdf", a)]
    (FIXTURES / fixture).write_text(
        f"<html><head>{title}</head><body>\n" + "\n".join(f"<p>{a}</p>" for a in anchors) + "\n</body></html>\n",
        encoding="utf-8", newline="")
    return nj.links(response.text)["links"]


def nj_list(client: httpx.Client, url: str, fixture: str) -> None:
    """One of New Jersey's lists, written to ``fixture`` without its candidates' addresses."""
    response = client.get(url)
    response.raise_for_status()
    (FIXTURES / fixture).write_bytes(text_pdf(without_addresses(response.content)))
    print(f"{fixture}: {len(nj.NjList.parse((FIXTURES / fixture).read_bytes()))} candidates")


def record_nj_odd_years(client: httpx.Client) -> None:
    """New Jersey's lists for the Legislature: for each of NJ_ODD_YEARS, its page cut down to its
    links (state_nj_{year}.html) and the lists named, without the candidates' addresses."""
    for year, kinds in NJ_ODD_YEARS.items():
        found = nj_page(client, year, f"state_nj_{year}.html")
        for kind in kinds:
            time.sleep(2)
            nj_list(client, found[kind], f"state_nj_{year}_{kind.replace('-', '_')}.pdf")


def record_nj(client: httpx.Client, key: str) -> None:
    """New Jersey: NJ_ADDRESS's Census answer; the Division of Elections' election information
    page, cut down to its title and its links to the general election's lists; the U.S. Senate and
    House lists it links, rewritten without the candidates' addresses; the odd years' lists for the
    Legislature (record_nj_odd_years); the address's FEC filers for U.S. Senate and House, its
    legislators, and its members of Congress added to officeholders_congress.json."""
    name, address = NJ_ADDRESS
    place = record_census(client, name, address)
    for kind, url in nj_page(client, FEC_CYCLE, "state_nj.html").items():
        nj_list(client, url, f"state_nj_{kind}.pdf")
    record_nj_odd_years(client)
    for district in (None, place.cd):
        record_filers(client, key, "NJ", district)
    record_legislators(client, "nj")
    record_members(client, "NJ", (None, place.cd))

def record_co(client: httpx.Client, key: str) -> None:
    """Colorado: CO_ADDRESS's Census answer; the SOS's candidate spreadsheet, kept as served (it has
    no contact details); the address's FEC filers for U.S. Senate and House, its legislators, and
    its members of Congress added to officeholders_congress.json."""
    name, address = CO_ADDRESS
    place = record_census(client, name, address)
    response = client.get(co.URL.format(year=FEC_CYCLE))
    response.raise_for_status()
    (FIXTURES / "state_co.xlsx").write_bytes(response.content)
    print(f"state_co.xlsx: {len(co.CoList.parse(response.content))} candidates")
    for district in (None, place.cd):
        record_filers(client, key, "CO", district)
    record_legislators(client, "co")
    record_members(client, "CO", (None, place.cd))


def record_il(client: httpx.Client, key: str) -> None:
    """Illinois: IL_ADDRESS's Census answer; the State Board's list of elections, cut down to its
    table; the election's download page, cut down to its form with its hidden fields' values made
    up; the candidate data file it posts back for, with every contact column emptied; the address's
    FEC filers for U.S. Senate and House, its legislators, and its members of Congress added to
    officeholders_congress.json."""
    name, address = IL_ADDRESS
    place = record_census(client, name, address)
    response = client.get(il.INDEX)
    response.raise_for_status()
    table = re.search(r"<table[^>]*id=\"ContentPlaceHolder1_gvElections\".*?</table>", response.text, re.S).group(0)
    (FIXTURES / "state_il.html").write_text(f"<html><body>\n{table}\n</body></html>\n", encoding="utf-8", newline="")
    url = il.DOWNLOAD.format(id=il.elections(response.text)["elections"][general_day(dt.date.today()).isoformat()])
    response = client.get(url)
    response.raise_for_status()
    fields = hidden_fields(response.text)
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
    for district in (None, place.cd):
        record_filers(client, key, "IL", district)
    record_legislators(client, "il")
    record_members(client, "IL", (None, place.cd))


GRID_PAGE = "https://voter.votewa.gov/CandidateList.aspx"  # Washington's: the grid states/grid.py is built on
GRID_CONTACT = ("MAILING ADDRESS", "EMAIL", "PHONE")


def record_grid(client: httpx.Client) -> None:
    """The candidate-list grid (states/grid.py), on Washington's: the page for the next general
    election, then the CSV export it posts back for; written by grid_fixtures."""
    page = client.get(GRID_PAGE)
    page.raise_for_status()
    election = grid.elections(page.text)["elections"][general_day(dt.date.today()).isoformat()]
    url = f"{GRID_PAGE}?e={election}"
    page = client.get(url)
    page.raise_for_status()
    response = client.post(url, data={**hidden_fields(page.text), **grid.EXPORT})
    response.raise_for_status()
    grid_fixtures(page.text, response.content)


def grid_fixtures(page: str, export: bytes) -> None:
    """grid_wa.html: the page cut down to its election dropdown, its hidden fields with made-up
    values, its export button, and its table's headings and first rows; grid_wa.csv: the export.
    Both without the candidates' addresses, emails and phones."""
    select = next(m for m in re.finditer(r"(<select\b[^>]*>)(.*?)</select>", page, re.S) if "ddlElection" in m.group(1))
    options = re.findall(r"<option\b[^>]*>[^<]*</option>", select.group(2))[:16]  # back to 2024's
    dropdown = select.group(1) + "\n" + "\n".join(options) + "\n</select>"
    inputs = "\n".join(f'<input type="hidden" name="{field}" id="{field}" value="{field.strip("_")}-recorded" />'
                       for field in hidden_fields(page))
    headings = re.findall(r'<th scope="col" class="rgHeader">([^<]*)</th>', page)
    contact = {i for i, heading in enumerate(headings) if heading.upper() in GRID_CONTACT}
    rows = []
    for row in re.findall(r'<tr class="rg(?:Alt)?Row"[^>]*>(.*?)</tr>', page, re.S)[:6]:
        cells = re.findall(r"<td>(.*?)</td>", row, re.S)
        rows.append("<tr>" + "".join(f"<td>{'&nbsp;' if i in contact else ' '.join(cell.split())}</td>"
                                     for i, cell in enumerate(cells)) + "</tr>")
    table = ('<table class="rgMasterTable">\n<thead><tr>' + "".join(f'<th scope="col">{h}</th>' for h in headings)
             + "</tr>\n<tr class=\"rgFilterRow\">" + "<td></td>" * len(headings) + "</tr></thead>\n<tbody>\n"
             + "\n".join(rows) + "\n</tbody>\n</table>")
    button = f'<input type="submit" name="{next(iter(grid.EXPORT))}" value=" " title="Export to CSV" />'
    (FIXTURES / "grid_wa.html").write_text(
        f'<html><body><form method="post" action="./CandidateList.aspx" id="form1">\n{inputs}\n{dropdown}\n{button}\n'
        f"{table}\n</form></body></html>\n", encoding="utf-8", newline="")
    lines = list(csv.reader(io.StringIO(export.decode("utf-8-sig"))))
    contact = {i for i, heading in enumerate(lines[0]) if heading.upper() in GRID_CONTACT}
    out = io.StringIO()
    csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(
        [lines[0], *(["" if i in contact else cell for i, cell in enumerate(line)] for line in lines[1:] if line)])
    (FIXTURES / "grid_wa.csv").write_text(out.getvalue(), encoding="utf-8", newline="")
    print(f"grid_wa.csv: {len(grid.rows(out.getvalue()))} candidates")


def without_contacts(text: str) -> str:
    """A page of Alaska's list with only what Pallot reads: its title, the election, each race's
    heading and each row's first cell (name, registration, status), and the links to its pages;
    never the campaign's address, phone, email or website."""
    title = '<h1 class="entry-title" itemprop="headline">Candidates</h1>'
    election = re.search(r'<div class="election-info">.*?</div>', text, re.S)
    races = []
    for section in re.findall(r'<section class="candidates-table">.*?</section>', text, re.S):
        heading = re.search(r"<h4>.*?</h4>", section, re.S).group(0)
        cells = [re.search(r"<td[^>]*>.*?</td>", row, re.S).group(0)
                 for row in re.findall(r"<tr>(?:(?!</tr>).)*?<td.*?</tr>", section, re.S)]
        races.append(f'<section class="candidates-table">{heading}\n<table><tbody>\n'
                     + "".join(f"<tr>{' '.join(cell.split())}</tr>\n" for cell in cells) + "</tbody></table></section>")
    pages = sorted(set(re.findall(r"<a href=\"[^\"]*frm-page-\d+=\d+\"[^>]*>[^<]*</a>", text)))
    return "\n".join(["<html><body>", title, election.group(0) if election else "", *races, *pages, "</body></html>"]) + "\n"


def record_ak(client: httpx.Client, key: str) -> None:
    """Alaska: AK_ADDRESS's Census answer; the Division of Elections' list's pages, one at a time,
    without the candidates' contact details (without_contacts), and the next even year's page,
    which has no list yet; its FEC filers for U.S. Senate and House, its legislators, and its
    members of Congress added to officeholders_congress.json."""
    name, address = AK_ADDRESS
    response = client.get(f"{census.BASE}/onelineaddress", params={"address": census.normalize_address(address), **census.PARAMS})
    response.raise_for_status()
    save(f"census_{name}.json", response.json())
    with httpx.Client(timeout=90, headers=client.headers, follow_redirects=True,
                      verify=trusting(ak.AkList.cafile)) as alaska:
        urls = [ak.URL.format(year=FEC_CYCLE % 100)]
        for number, url in enumerate(urls, 1):
            time.sleep(2)
            response = alaska.get(url)
            response.raise_for_status()
            (FIXTURES / f"state_ak_{number}.html").write_text(without_contacts(response.text), encoding="utf-8", newline="")
            kept = ak.read_page((FIXTURES / f"state_ak_{number}.html").read_text(encoding="utf-8"))
            print(f"state_ak_{number}.html: {len(kept['filings'])} candidates")
            if number == 1:
                urls += kept["pages"]
        time.sleep(2)
        response = alaska.get(ak.URL.format(year=(FEC_CYCLE + 2) % 100))
        response.raise_for_status()
        (FIXTURES / "state_ak_none.html").write_text(without_contacts(response.text), encoding="utf-8", newline="")
    for district in (None, 0):
        record_filers(client, key, "AK", district)
    record_legislators(client, "ak")
    record_members(client, "AK")


def record_me(client: httpx.Client, key: str) -> None:
    """Maine: ME_ADDRESS's Census answer; the Secretary of State's Upcoming Elections page, cut down
    to its title and its links to the candidate list and the declared write-ins; the two files it
    links, as served (a town for each candidate, no contact details), asked with a browser's headers
    as Pallot asks them; the address's FEC filers for U.S. Senate and House, its legislators, and
    its members of Congress added to officeholders_congress.json."""
    name, address = ME_ADDRESS
    place = record_census(client, name, address)
    response = client.get(me.PAGE, headers=me.HEADERS)
    response.raise_for_status()
    title = " ".join(re.search(r"<title>[^<]*</title>", response.text).group(0).split())
    found = me.links(response.text)
    urls = [found["links"][str(FEC_CYCLE)], *found["write_ins"]]
    anchors = [" ".join(a.split()) for a in re.findall(r"<a [^>]*href=\"[^\"]*\.(?:xlsx|pdf)\".*?</a>", response.text, re.S)
               if any(html.unescape(re.search(r'href="([^"]*)"', a).group(1)) in url for url in urls)]
    (FIXTURES / "state_me.html").write_text(
        f"<html><head>{title}</head><body>\n" + "\n".join(f"<p>{a}</p>" for a in anchors) + "\n</body></html>\n",
        encoding="utf-8", newline="")
    for url, fixture in zip(urls, ("state_me.xlsx", "state_me_write_ins.pdf")):
        time.sleep(2)
        response = client.get(url, headers=me.HEADERS)
        response.raise_for_status()
        (FIXTURES / fixture).write_bytes(response.content)
        print(f"{fixture}: {len(me.MeList.parse(response.content))} candidates")
    for district in (None, place.cd):
        record_filers(client, key, "ME", district)
    record_legislators(client, "me")
    record_members(client, "ME", (None, place.cd))


def ne_without_contacts(raw: bytes) -> list[list[str]]:
    """Nebraska's candidate list, the pages with offices of the state ("For …"), without the
    candidates' contact details: a row cut after its Incumbent or Nonincumbent, and the lines
    under it keeping only what's left of the incumbency column (a wrapped party or office)."""
    pages: list[list[str]] = []
    for line in pdf_lines(raw):
        if "Final Statewide General Candidate List" in line:
            pages.append([])
        if not pages or not line.strip() or re.search(r"Page \d+ of \d+", line):
            continue
        status = re.search(r"\b(?:Incumbent|Nonincumbent)\b", line)
        line = line[:status.end()] if status else "".join(
            word.group() if word.start() < 285 else " " * len(word.group()) for word in re.finditer(r"\s+|\S+", line)
        ).rstrip()
        if line:
            pages[-1].append(line)
    return [page for page in pages if any(line.startswith("For ") for line in page)]


def record_ne(client: httpx.Client, key: str) -> None:
    """Nebraska: NE_ADDRESS's Census answer; the Secretary of State's elections page, cut down to
    its title and its links to the candidate list and the judges for retention; the candidate list
    rewritten without contact details (ne_without_contacts), its pages turned sideways as served;
    the judges' list as served (it has no contact details); the address's FEC filers for U.S.
    Senate and House, its legislators, and its members of Congress added to officeholders_congress.json."""
    name, address = NE_ADDRESS
    place = record_census(client, name, address)
    response = client.get(ne.PAGE)
    response.raise_for_status()
    title = " ".join(re.search(r"<title>[^<]*</title>", response.text).group(0).split())
    found = ne.links(response.text)
    urls = [found["links"][str(FEC_CYCLE)], found["retention"][str(FEC_CYCLE)]]
    anchors = [" ".join(a.split()) for a in re.findall(r"<a [^>]*href=\"[^\"]*\.pdf\".*?</a>", response.text, re.S)
               if any(html.unescape(re.search(r'href="([^"]*)"', a).group(1)) in url for url in urls)]
    (FIXTURES / "state_ne.html").write_text(
        f"<html><head>{title}</head><body>\n" + "\n".join(f"<p>{a}</p>" for a in anchors) + "\n</body></html>\n",
        encoding="utf-8", newline="")
    time.sleep(2)
    response = client.get(urls[0])
    response.raise_for_status()
    reader = PdfReader(io.BytesIO(text_pdf(ne_without_contacts(response.content), width=900)))
    writer = PdfWriter()
    for page in reader.pages:
        page.rotate(90)
        page.transfer_rotation_to_content()
        writer.add_page(page.rotate(270))
    with (FIXTURES / "state_ne.pdf").open("wb") as fh:
        writer.write(fh)
    print(f"state_ne.pdf: {len(ne.NeList.parse((FIXTURES / 'state_ne.pdf').read_bytes()))} candidates")
    time.sleep(2)
    response = client.get(urls[1])
    response.raise_for_status()
    (FIXTURES / "state_ne_retention.pdf").write_bytes(response.content)
    print(f"state_ne_retention.pdf: {len(ne.NeList.parse(response.content))} judges")
    for district in (None, place.cd):
        record_filers(client, key, "NE", district)
    record_legislators(client, "ne")
    record_members(client, "NE", (None, place.cd))


NM_CONTACT = ("PHYSICAL ADDRESS", "MAILING ADDRESS", "EMAIL/PHONE", "ADDRESS", "CITY", "STATE", "ZIP", "PHONE", "EMAIL",
              "WEBSITE")


def nm_without_contacts(page: str) -> str:
    """New Mexico's grid page for an election with only what Pallot reads: its form (the grid's
    address), its heading, and its table's every row, the candidates' addresses, phones, emails and
    websites emptied."""
    form = re.search(r"<form\b[^>]*>", page).group(0)
    heading = re.search(r'<span id="MainContent_lblFormHeader">[^<]*</span>', page).group(0)
    parser = Rows(cells=("th", "td"))
    parser.feed(page[page.index("rgMasterTable"):])
    header = next(row for row in parser.rows if "Contest" in row and "Name" in row)
    contact = {i for i, heading in enumerate(header) if heading.upper() in NM_CONTACT}
    rows = [row for row in parser.rows[parser.rows.index(header) + 1:] if len(row) == len(header) and any(row)]
    cells = ["<tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in header) + "</tr>"]
    cells += ["<tr>" + "".join(f"<td>{'' if i in contact else html.escape(cell)}</td>" for i, cell in enumerate(row))
              + "</tr>" for row in rows]
    return (f"<html><body>{form}\n{heading}\n<table class=\"rgMasterTable\">\n" + "\n".join(cells)
            + "\n</table>\n</form></body></html>\n")


def record_nm(client: httpx.Client, key: str) -> None:
    """New Mexico: NM_ADDRESS's Census answer; the Secretary of State's home page, cut down to its
    links to the candidate list; the list's grid page for the year's general election, without the
    candidates' contact details (nm_without_contacts); the address's FEC filers for U.S. Senate and
    House, its legislators, and its members of Congress added to officeholders_congress.json."""
    name, address = NM_ADDRESS
    place = record_census(client, name, address)
    response = client.get(nm.INDEX)
    response.raise_for_status()
    anchors = [" ".join(a.split()) for a in re.findall(r"<a [^>]*href=\"[^\"]*CandidateList\.aspx[^\"]*\".*?</a>",
                                                      response.text, re.S)]
    (FIXTURES / "state_nm.html").write_text(
        "<html><body>\n" + "\n".join(f"<p>{a}</p>" for a in anchors) + "\n</body></html>\n", encoding="utf-8", newline="")
    election = nm.NmList.read_index(response.content)["elections"][str(FEC_CYCLE)]
    time.sleep(2)
    response = client.get(nm.PAGE, params={**nm.NmList.query, nm.NmList.election: election})
    response.raise_for_status()
    (FIXTURES / "state_nm_list.html").write_text(nm_without_contacts(response.text), encoding="utf-8", newline="")
    print(f"state_nm_list.html: {len(nm.NmList.parse((FIXTURES / 'state_nm_list.html').read_bytes()))} candidates")
    for district in (None, place.cd):
        record_filers(client, key, "NM", district)
    record_legislators(client, "nm")
    record_members(client, "NM", (None, place.cd))


def record_wa(client: httpx.Client, key: str) -> None:
    """Washington: WA_ADDRESS's Census answer, the address's FEC filers for U.S. House, its
    legislators, and its members of Congress added to officeholders_congress.json. Its list is the
    grid's fixtures (record_grid), which Upstream serves for its page and its export."""
    name, address = WA_ADDRESS
    place = record_census(client, name, address)
    record_filers(client, key, "WA", place.cd)
    record_legislators(client, "wa")
    record_members(client, "WA", (None, place.cd))


def record_mt(client: httpx.Client, key: str) -> None:
    """Montana: MT_ADDRESS's Census answer; the Secretary of State's candidate list page, cut down to
    its election dropdown and its hidden fields with made-up values; the CSV export its postback
    answers for the general election, without the candidates' addresses, emails, websites and phones
    (a declared write-in's "WRITE-IN" mark kept); the address's FEC filers for U.S. House, its
    legislators, and its members of Congress added to officeholders_congress.json."""
    name, address = MT_ADDRESS
    place = record_census(client, name, address)
    page = client.get(mt.PAGE)
    page.raise_for_status()
    election = grid.elections(page.text)["elections"][general_day(dt.date.today()).isoformat()]
    url = f"{mt.PAGE}?e={election}"
    time.sleep(2)
    page = client.get(url)
    page.raise_for_status()
    fields = hidden_fields(page.text)
    select = next(m.group(0) for m in re.finditer(r"<select\b[^>]*>.*?</select>", page.text, re.S)
                  if "ddlElection" in m.group(0))
    inputs = "\n".join(f'<input type="hidden" name="{field}" id="{field}" value="{field.strip("_")}-recorded" />'
                       for field in fields)
    (FIXTURES / "state_mt.html").write_text(
        f'<html><body><form name="frmMain" method="post" action="./CandidateList.aspx?e={election}" id="frmMain">\n'
        f"{inputs}\n{select}\n</form></body></html>\n", encoding="utf-8", newline="")
    time.sleep(2)
    response = client.post(url, data={**fields, **mt.EXPORT})
    response.raise_for_status()
    lines = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    contact = {i for i, heading in enumerate(lines[0]) if heading.upper() in ("MAILING ADDRESS", mt.WEB, "PHONE")}

    def kept(i: int, cell: str) -> str:
        if i not in contact:
            return cell
        return "WRITE-IN" if lines[0][i].upper() == mt.WEB and re.search(r"\bWRITE[- ]?IN\b", cell, re.I) else ""

    out = io.StringIO()
    csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(
        [lines[0], *([kept(i, cell) for i, cell in enumerate(line)] for line in lines[1:] if line)])
    (FIXTURES / "state_mt.csv").write_text(out.getvalue(), encoding="utf-8", newline="")
    print(f"state_mt.csv: {len(mt.MtList.parse(out.getvalue()))} candidates, "
          f"{len(mt.MtList.parse(response.content))} as served")
    record_filers(client, key, "MT", place.cd)
    record_legislators(client, "mt")
    record_members(client, "MT", (None, place.cd))


def record_sd(client: httpx.Client, key: str) -> None:
    """South Dakota: SD_ADDRESS's Census answer; the Secretary of State's Upcoming Elections page, cut
    down to its menu's year and its link to the candidate list; the grid's page for that election,
    cut down to its form and its hidden fields with made-up values; the CSV export its postback
    answers, without the candidates' mailing addresses; its FEC filers for U.S. Senate and House, its
    legislators, and its members of Congress added to officeholders_congress.json."""
    name, address = SD_ADDRESS
    record_census(client, name, address)
    index = client.get(sd.INDEX)
    index.raise_for_status()
    link = re.search(r"""<a\b[^>]*candidatelist\.aspx\?eid=\d+[^>]*>[^<]*</a>""", index.text, re.I)
    year = list(re.finditer(r"<a\b[^>]*>\s*\d{4} Election Information\s*</a>", index.text[:link.start()], re.I))[-1]
    (FIXTURES / "state_sd.html").write_text(
        f"<html><body><ul><li>{year.group(0)}<ul><li>{link.group(0)}</li></ul></li></ul></body></html>\n",
        encoding="utf-8", newline="")
    election = sd.SdList.read_index(index.content)["elections"][str(general_day(dt.date.today()).year)]
    url = f"{sd.PAGE}?eid={election}"
    time.sleep(2)
    page = client.get(url)
    page.raise_for_status()
    fields = hidden_fields(page.text)
    inputs = "\n".join(f'<input type="hidden" name="{field}" id="{field}" value="{field.strip("_")}-recorded" />'
                       for field in fields)
    (FIXTURES / "state_sd_grid.html").write_text(
        f'<html><body><form method="post" action="./candidatelist.aspx?eid={election}" id="Form1">\n{inputs}\n'
        "</form></body></html>\n", encoding="utf-8", newline="")
    time.sleep(2)
    response = client.post(url, data={**fields, **sd.EXPORT})
    response.raise_for_status()
    lines = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    contact = {i for i, heading in enumerate(lines[0]) if heading.upper() == "MAILING ADDRESS"}
    out = io.StringIO()
    csv.writer(out, lineterminator="\r\n").writerows(
        [lines[0], *([("" if i in contact else cell) for i, cell in enumerate(line)] for line in lines[1:] if line)])
    (FIXTURES / "state_sd.csv").write_text(out.getvalue(), encoding="utf-8", newline="")
    print(f"state_sd.csv: {len(sd.SdList.parse(out.getvalue()))} candidates, "
          f"{len(sd.SdList.parse(response.content))} as served")
    for district in (None, 0):
        record_filers(client, key, "SD", district)
    record_legislators(client, "sd")
    record_members(client, "SD")


def record_hi(client: httpx.Client, key: str) -> None:
    """Hawaii: HI_ADDRESS's Census answer; the Office of Elections' Candidate Reports page, cut down
    to the paragraph naming the year and its link to the report; the grid's page for that election,
    cut down to its form and its hidden fields with made-up values; the CSV export its postback
    answers, without the candidates' legal names, addresses, phones, emails and websites; the
    address's FEC filers for U.S. House, its legislators, and its members of Congress added to
    officeholders_congress.json."""
    name, address = HI_ADDRESS
    place = record_census(client, name, address)
    index = client.get(hi.INDEX)
    index.raise_for_status()
    link = re.search(r"""<a\b[^>]*CandidateFiling\.aspx\?elid=\d+[^>]*>[^<]*</a>""", index.text, re.I)
    year = list(re.finditer(r"<p>[^<]*\b\d{4} Elections?\b[^<]*</p>", index.text[:link.start()], re.I))[-1]
    (FIXTURES / "state_hi.html").write_text(
        f"<html><body>{year.group(0)}\n<p>{link.group(0)}</p></body></html>\n", encoding="utf-8", newline="")
    election = hi.HiList.read_index(index.content)["elections"][str(general_day(dt.date.today()).year)]
    url = f"{hi.PAGE}?elid={election}"
    time.sleep(2)
    page = client.get(url)
    page.raise_for_status()
    fields = hidden_fields(page.text)
    inputs = "\n".join(f'<input type="hidden" name="{field}" id="{field}" value="{field.strip("_")}-recorded" />'
                       for field in fields)
    (FIXTURES / "state_hi_grid.html").write_text(
        f'<html><body><form method="post" action="./CandidateFiling.aspx?elid={election}" id="form1">\n{inputs}\n'
        "</form></body></html>\n", encoding="utf-8", newline="")
    time.sleep(2)
    response = client.post(url, data={**fields, **hi.EXPORT, hi.DROPDOWN: election})
    response.raise_for_status()
    lines = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    contact = {i for i, heading in enumerate(lines[0])
               if heading.upper() in ("LEGALNAME", "MAILINGADDRESS", "CITYSTATEZIP", "PHONE", "EMAIL", "WEBSITE")}
    out = io.StringIO()
    csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(
        [lines[0], *([("" if i in contact else cell) for i, cell in enumerate(line)] for line in lines[1:] if line)])
    (FIXTURES / "state_hi.csv").write_text(out.getvalue(), encoding="utf-8", newline="")
    print(f"state_hi.csv: {len(hi.HiList.parse(out.getvalue()))} candidates, "
          f"{len(hi.HiList.parse(response.content))} as served")
    record_filers(client, key, "HI", place.cd)
    record_legislators(client, "hi")
    record_members(client, "HI", (None, place.cd))


def record_nd(client: httpx.Client, key: str) -> None:
    """North Dakota: ND_ADDRESS's Census answer; the Secretary of State's Candidate page, cut down to
    its link to the candidate list, as text; the grid's page for that election, cut down to its form
    and its hidden fields with made-up values; the table its Search postback answers, each row cut
    down to its contest, term, district, county, name and party, without the candidates' addresses,
    emails, websites and phones; the address's FEC filers for U.S. House, its legislators, and its
    members of Congress added to officeholders_congress.json."""
    name, address = ND_ADDRESS
    record_census(client, name, address)
    index = client.get(nd.INDEX)
    index.raise_for_status()
    link = re.search(r"""<a\b[^>]*href="([^"]*candidatelist\.aspx\?eid=\d+)"[^>]*>(.*?)</a>""", index.text, re.I | re.S)
    words = html.escape(" ".join(html.unescape(re.sub(r"<[^>]+>", " ", link.group(2))).split()))
    (FIXTURES / "state_nd.html").write_text(
        f'<html><body><p><a href="{link.group(1)}">{words}</a></p></body></html>\n', encoding="utf-8", newline="")
    election = nd.NdList.read_index(index.content)["elections"][str(general_day(dt.date.today()).year)]
    url = f"{nd.PAGE}?eid={election}"
    form = f'<form name="aspnetForm" method="post" action="./candidatelist.aspx?eid={election}" id="aspnetForm">'
    time.sleep(2)
    page = client.get(url)
    page.raise_for_status()
    fields = hidden_fields(page.text)
    inputs = "\n".join(f'<input type="hidden" name="{field}" id="{field}" value="{field.strip("_")}-recorded" />'
                       for field in fields)
    (FIXTURES / "state_nd_grid.html").write_text(f"<html><body>{form}\n{inputs}\n</form></body></html>\n",
                                                 encoding="utf-8", newline="")
    time.sleep(2)
    response = client.post(url, data={**fields, **nd.SEARCH})
    response.raise_for_status()
    kept = ("CONTEST", "TERM LENGTH", "DISTRICT", "COUNTY", "NAME", "PARTY")
    rows = "\n".join("<tr>" + "".join(f"<td>{html.escape(row[heading])}</td>" for heading in kept) + "</tr>"
                     for row in grid.table(response.content))
    heading = "".join(f"<th>{html.escape(name.title())}</th>" for name in kept)
    (FIXTURES / "state_nd_list.html").write_text(
        f"<html><body>{form}\n<table>\n<tr>{heading}</tr>\n{rows}\n</table>\n</form></body></html>\n",
        encoding="utf-8", newline="")
    print(f"state_nd_list.html: {len(nd.NdList.parse((FIXTURES / 'state_nd_list.html').read_bytes()))} candidates, "
          f"{len(nd.NdList.parse(response.content))} as served")
    record_filers(client, key, "ND", 0)
    record_legislators(client, "nd")
    record_members(client, "ND")


def write_sheet(path: Path, rows: list[list[str]]) -> None:
    """``rows`` as a spreadsheet (.xlsx) of one sheet, each cell its text inline: what sheet_rows reads."""
    def cell(text: str) -> str:
        return f'<c t="inlineStr"><is><t xml:space="preserve">{html.escape(text, quote=False)}</t></is></c>'

    body = "".join(f"<row>{''.join(cell(text) for text in row)}</row>" for row in rows)
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rels = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package = "http://schemas.openxmlformats.org/package/2006"
    parts = {
        "[Content_Types].xml": f'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="{package}/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{package}/relationships">'
        f'<Relationship Id="rId1" Type="{rels}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="{main}" xmlns:r="{rels}"><sheets>'
        '<sheet name="Sheet" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<?xml version="1.0" encoding="UTF-8"?><Relationships '
        f'xmlns="{package}/relationships"><Relationship Id="rId1" Type="{rels}/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{main}"><sheetData>'
        f"{body}</sheetData></worksheet>",
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as book:
        for name, text in parts.items():
            book.writestr(zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)), text)
    path.write_bytes(out.getvalue())


def record_de(client: httpx.Client, key: str) -> None:
    """Delaware: DE_ADDRESS's Census answer; the Department of Elections' general election
    candidate list and its declared write-ins, each sheet cut down to the columns the adapter reads
    and the dates (no legal names, addresses, websites, emails or phones); the FEC's filers for the
    U.S. Senate and the House seat, its legislators, and its members of Congress added to
    officeholders_congress.json."""
    name, address = DE_ADDRESS
    record_census(client, name, address)
    kept = ("County", "Office", "Withdrawal Date", "BallotName", "Party", "Filing Date", "DisplayedStatus")
    for kind, fixture in (("fcddt", "state_de.xlsx"), ("wcddt", "state_de_write_ins.xlsx")):
        time.sleep(2)
        response = client.get(f"{de.LISTS}genl_{kind}_{FEC_CYCLE}.xlsx")
        response.raise_for_status()
        heading, *rows = sheet_rows(response.content)[1]
        columns = [heading.index(column) for column in kept if column in heading]
        write_sheet(FIXTURES / fixture, [[row[at] if at < len(row) else "" for at in columns] for row in [heading, *rows]])
        print(f"{fixture}: {len(de.DeList.parse((FIXTURES / fixture).read_bytes()))} candidates, "
              f"{len(de.DeList.parse(response.content))} as served")
    record_filers(client, key, "DE")
    record_filers(client, key, "DE", 0)
    record_legislators(client, "de")
    record_members(client, "DE")


def record_vt(client: httpx.Client, key: str) -> None:
    """Vermont: VT_ADDRESS's Census answer; the Secretary of State's qualified candidates, the sheet
    cut down to the columns the adapter reads (no towns, addresses, phones, emails, websites or
    disclosures), with the justices of the peace of Montpelier alone; the FEC's filers for the
    House seat, its legislators, and its members of Congress added to officeholders_congress.json."""
    name, address = VT_ADDRESS
    record_census(client, name, address)
    response = client.get(f"{vt.LISTS}{FEC_CYCLE}_general_election_qualified_candidates.xlsx")
    response.raise_for_status()
    heading, *rows = sheet_rows(response.content)[1]
    columns = [heading.index(column) for column in vt.COLUMNS]
    rows = [row for row in rows if row and (row[0] != "JUSTICE OF THE PEACE" or row[1] == "MONTPELIER")]
    write_sheet(FIXTURES / "state_vt.xlsx", [[row[at] if at < len(row) else "" for at in columns]
                                             for row in [heading, *rows]])
    print(f"state_vt.xlsx: {len(vt.VtList.parse((FIXTURES / 'state_vt.xlsx').read_bytes()))} candidates, "
          f"{len(vt.VtList.parse(response.content))} as served")
    record_filers(client, key, "VT", 0)
    record_legislators(client, "vt")
    record_members(client, "VT")


def record_ms(client: httpx.Client, key: str) -> None:
    """Mississippi: MS_ADDRESS's Census answer; the Secretary of State's Candidate Qualifying List,
    as served without its scripts (it has no contact details); the FEC's filers for the U.S. Senate
    and the House seat, its legislators, and its members of Congress added to officeholders_congress.json."""
    name, address = MS_ADDRESS
    place = record_census(client, name, address)
    response = client.get(ms.PAGE)
    response.raise_for_status()
    text = re.sub(r"<script\b.*?</script>", "", response.content.decode("utf-8"), flags=re.S)
    (FIXTURES / "state_ms.html").write_bytes(text.encode("utf-8"))
    print(f"state_ms.html: {len(ms.MsList.parse((FIXTURES / 'state_ms.html').read_bytes()))} candidates, "
          f"{len(ms.MsList.parse(response.content))} as served")
    record_filers(client, key, "MS")
    record_filers(client, key, "MS", place.cd)
    record_legislators(client, "ms")
    record_members(client, "MS", (None, place.cd))


def record_in(client: httpx.Client, key: str) -> None:
    """Indiana: IN_ADDRESS's Census answer; the Election Division's home page, cut down to its title
    and its link to the year's general election candidate list; the list as served (it has no
    contact details); the address's FEC filers for U.S. House, its legislators, and its members of
    Congress added to officeholders_congress.json."""
    name, address = IN_ADDRESS
    place = record_census(client, name, address)
    response = client.get(in_.PAGE)
    response.raise_for_status()
    title = " ".join(re.search(r"<title>[^<]*</title>", response.text).group(0).split())
    url = in_.links(response.text)["links"][str(FEC_CYCLE)]
    anchors = [" ".join(a.split()) for a in re.findall(r"<a [^>]*href=\"[^\"]*\.xlsx\".*?</a>", response.text, re.S)
               if html.unescape(re.search(r'href="([^"]*)"', a).group(1)) in url]
    (FIXTURES / "state_in.html").write_text(
        f"<html><head>{title}</head><body>\n" + "\n".join(f"<p>{a}</p>" for a in anchors) + "\n</body></html>\n",
        encoding="utf-8", newline="")
    time.sleep(2)
    response = client.get(url)
    response.raise_for_status()
    (FIXTURES / "state_in.xlsx").write_bytes(response.content)
    print(f"state_in.xlsx: {len(in_.InList.parse(response.content))} candidates")
    record_filers(client, key, "IN", place.cd)
    record_legislators(client, "in")
    record_members(client, "IN", (None, place.cd))


def record_md(client: httpx.Client, key: str) -> None:
    """Maryland: MD_ADDRESS's Census answer; the State Board of Elections' general candidate
    listings page for the year, cut down to its heading and its link to the statewide list; the
    list with every column the adapter doesn't read emptied (its contact details); the address's FEC filers for
    U.S. House, its legislators, and its members of Congress added to officeholders_congress.json."""
    name, address = MD_ADDRESS
    place = record_census(client, name, address)
    page = md.PAGE.format(year=FEC_CYCLE)
    response = client.get(page)
    response.raise_for_status()
    title = " ".join(re.search(r"<title>[^<]*</title>", response.text).group(0).split())
    heading = " ".join(re.search(r"<h1>.*?</h1>", response.text, re.S).group(0).split())
    anchors = [" ".join(a.split()) for a in re.findall(r"<a href=[^>]*statewide_candidatelist[^>]*>.*?</a>",
                                                         response.text, re.S)]
    (FIXTURES / "state_md.html").write_text(
        f"<html><head>{title}</head><body>\n{heading}\n" + "\n".join(f"<p>{a}</p>" for a in anchors)
        + "\n</body></html>\n", encoding="utf-8", newline="")
    url = md.links(response.text)["links"][str(FEC_CYCLE)]
    time.sleep(2)
    response = client.get(url)
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")))
    out = io.StringIO()
    writer = csv.DictWriter(out, [f for f in reader.fieldnames if f], extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows({f: (row[f] if f in md.COLUMNS else "") for f in writer.fieldnames} for row in reader)
    (FIXTURES / "state_md.csv").write_text(out.getvalue(), encoding="utf-8", newline="")
    print(f"state_md.csv: {len(md.MdList.parse(out.getvalue()))} candidates")
    record_filers(client, key, "MD", place.cd)
    record_legislators(client, "md")
    record_members(client, "MD", (None, place.cd))


def mo_lines(raw: bytes) -> list[list[str]]:
    """Missouri's certification as its text alone, without its emblems: pdf_lines' lines, each run
    of blank lines made one, in pages of 80 lines, in the characters text_pdf can write."""
    lines: list[str] = []
    for line in pdf_lines(raw):
        if line.strip() or (lines and lines[-1].strip()):
            lines.append(line.encode("latin-1", "replace").decode("latin-1"))
    return [lines[at:at + 80] for at in range(0, len(lines), 80)]


def record_mo(client: httpx.Client, key: str) -> None:
    """Missouri: MO_ADDRESS's Census answer, and its U.S. House district on the map in force from
    TIGERweb (the service's layers cut down to its congressional districts, and its identify
    answer); the Secretary of State's elections page cut down to its title and its links to the
    certified candidates (the one left in an HTML comment too); the certification as its text alone
    (mo_lines; it has no contact details); the address's FEC filers for U.S. House, its
    legislators, and its members of Congress added to officeholders_congress.json."""
    name, address = MO_ADDRESS
    place = record_census(client, name, address)
    service = tigerweb.GOVERNING["MO"]
    response = client.get(service, params={"f": "json"})
    response.raise_for_status()
    index = response.json()
    save("tigerweb_layers_mo.json", {"layers": [{"id": layer["id"], "name": layer["name"]} for layer in index["layers"]
                                                if "Congressional Districts" in layer["name"]]})
    spec = tigerweb.identify_spec([tigerweb.layer_id(index, "cd")], place.lat, place.lon, service)
    response = client.get(spec.url, params=spec.params)
    response.raise_for_status()
    save(f"tigerweb_identify_{name}.json", response.json())
    cd = census.parse_geographies(tigerweb.geographies(response.json()), place.lat, place.lon, None).cd
    print(f"{name}: MO-{cd} on the map in force, MO-{place.cd} on the geocoder's")
    time.sleep(2)
    response = client.get(mo.PAGE)
    response.raise_for_status()
    title = " ".join(re.search(r"<title>[^<]*</title>", response.text).group(0).split())
    anchors = []
    for found in re.finditer(r"<a [^>]*href=\"[^\"]*Candidates[^\"]*\.pdf\".*?</a>", response.text, re.S):
        before = response.text[:found.start()]
        commented = before.rfind("<!--") > before.rfind("-->")
        anchor = " ".join(found.group(0).split())
        anchors.append(f"<!--{anchor}-->" if commented else anchor)
    (FIXTURES / "state_mo.html").write_text(
        f"<html><head>{title}</head><body>\n" + "\n".join(f"<div>{a}</div>" for a in anchors) + "\n</body></html>\n",
        encoding="utf-8", newline="")
    url = mo.links(response.text)["links"][str(FEC_CYCLE)]
    time.sleep(2)
    response = client.get(url)
    response.raise_for_status()
    (FIXTURES / "state_mo.pdf").write_bytes(text_pdf(mo_lines(response.content)))
    print(f"state_mo.pdf: {len(mo.MoList.parse((FIXTURES / 'state_mo.pdf').read_bytes()))} candidates, "
          f"{len(mo.MoList.parse(response.content))} as served")
    record_filers(client, key, "MO", cd)
    record_legislators(client, "mo")
    record_members(client, "MO", (None, cd))


def record_ky(client: httpx.Client, key: str) -> None:
    """Kentucky: KY_ADDRESS's Census answer; the Secretary of State's candidate filings page, cut
    down to its heading, its election dropdown and its hidden fields with made-up values; the list
    of all candidates its postback answers for the general election, each row rewritten as its name
    (a running mate's under it), office, district and party, without the post office box or email;
    the address's FEC filers for U.S. House, its legislators, and its members of Congress added to
    officeholders_congress.json."""
    name, address = KY_ADDRESS
    place = record_census(client, name, address)
    page = client.get(ky.PAGE)
    page.raise_for_status()
    fields = hidden_fields(page.text)
    election = ky.elections(page.text)["elections"][general_day(dt.date.today()).isoformat()]

    def cut(text: str, header: str, rows: str = "") -> str:
        select = re.search(r"<select\b[^>]*ddlElection.*?</select>", text, re.S).group(0)
        inputs = "\n".join(f'<input type="hidden" name="{field}" id="{field}" value="{field.strip("_")}-recorded" />'
                           for field in fields)
        return (f'<html><body><form method="post" action="./Default.aspx" id="form1">\n{inputs}\n'
                f'<span id="ctl00_MainContent_lblSearchHeader">{header}</span>\n{select}\n{rows}</form></body></html>\n')

    (FIXTURES / "state_ky.html").write_text(cut(page.text, "Search Criteria"), encoding="utf-8", newline="")
    time.sleep(2)
    response = client.post(ky.PAGE, data={**fields, ky.ELECTION: election, **ky.FORM})
    response.raise_for_status()
    text = response.text
    wdd = re.search(r'<div id="ctl00_MainContent_pnlWddResults"', text)

    def table(part: str) -> str:
        out = []
        for row in re.findall(r"<tr\b[^>]*class=[\"']boldleft[\"'][^>]*>(.*?)</tr>", part, re.S):
            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.S)
            names = [" ".join(html.unescape(re.sub(r"<[^>]*>", " ", n)).split()) for n in re.split(r"<br\s*/?>", cells[0])]
            plain = [html.escape(" ".join(html.unescape(re.sub(r"<[^>]*>", " ", c)).split())) for c in cells[2:5]]
            out.append(f'<tr class="boldleft"><td>{"<br />".join(html.escape(n) for n in names if n)}</td><td></td>'
                       + "".join(f"<td>{c}</td>" for c in plain) + "</tr>")
        return "<table>\n" + "\n".join(out) + "\n</table>\n"

    rows = (f'<div id="ctl00_MainContent_pnlResults">\n{table(text[:wdd.start()] if wdd else text)}</div>\n'
            + (f'<div id="ctl00_MainContent_pnlWddResults">\n{table(text[wdd.start():])}</div>\n' if wdd else ""))
    (FIXTURES / "state_ky_list.html").write_text(cut(text, "All Candidates", rows), encoding="utf-8", newline="")
    print(f"state_ky_list.html: {len(ky.KyList.parse((FIXTURES / 'state_ky_list.html').read_bytes()))} candidates, "
          f"{len(ky.KyList.parse(response.content))} as served")
    record_filers(client, key, "KY", place.cd)
    record_legislators(client, "ky")
    record_members(client, "KY", (None, place.cd))


def record_ok(client: httpx.Client, key: str) -> None:
    """Oklahoma: OK_ADDRESS's Census answer; the State Election Board's list of elections, as served
    but for the counties not in OK_COUNTIES (it has no contact details); the address's FEC filers
    for U.S. House, its legislators, and its members of Congress added to officeholders_congress.json."""
    name, address = OK_ADDRESS
    place = record_census(client, name, address)
    time.sleep(2)
    response = client.get(ok.PAGE)
    response.raise_for_status()
    text = response.content.decode("utf-8")
    footer = text.rindex('<font size="2" >')
    head, *sections = re.split(r'(?=<font size="5" >)', text[:footer])
    kept = [s for s in sections if re.search(r"<A NAME=\d+>([^<]+)</A>", s).group(1).strip() in OK_COUNTIES]
    (FIXTURES / "state_ok.html").write_bytes((head + "".join(kept) + text[footer:]).encode("utf-8"))
    print(f"state_ok.html: {len(ok.OkList.parse((FIXTURES / 'state_ok.html').read_bytes()))} candidates, "
          f"{len(ok.OkList.parse(response.content))} as served")
    record_filers(client, key, "OK", place.cd)
    record_legislators(client, "ok")
    record_members(client, "OK", (None, place.cd))


def record_ks(client: httpx.Client, key: str) -> None:
    """Kansas: KS_ADDRESS's Census answer; the Secretary of State's candidate list page, cut down to
    its election dropdown and its hidden fields with made-up values; the list its postback answers
    for the general election, each row cut down to its name, office, district, position, division
    and party, without the addresses, phones or emails; the address's FEC filers for U.S. House, its
    legislators, and its members of Congress added to officeholders_congress.json."""
    name, address = KS_ADDRESS
    place = record_census(client, name, address)
    page = client.get(ks.PAGE)
    page.raise_for_status()
    fields = hidden_fields(page.text)
    election = ks.elections(page.text)["elections"][general_day(dt.date.today()).isoformat()]

    def cut(text: str, rows: str = "") -> str:
        select = re.search(r"<select\b[^>]*ddlElections.*?</select>", text, re.S).group(0)
        inputs = "\n".join(f'<input type="hidden" name="{field}" id="{field}" value="{field.strip("_")}-recorded" />'
                           for field in fields)
        return (f'<html><body><form method="post" action="./elections_upcoming_candidate.aspx" id="frmMain">\n'
                f"{inputs}\n{select}\n{rows}</form></body></html>\n")

    (FIXTURES / "state_ks.html").write_text(cut(page.text), encoding="utf-8", newline="")
    time.sleep(2)
    response = client.post(ks.PAGE, data={**fields, ks.ELECTION: election, **ks.FORM})
    response.raise_for_status()
    text = response.text
    label = re.search(r'<span id="lblElection">([^<]*)</span>', text).group(1)
    table = re.search(r'<table\b[^>]*id="gvCandidateList".*?</table>', text, re.S).group(0)
    rows = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table, re.S):
        cells = re.findall(r"<(t[dh])\b[^>]*>(.*?)</t[dh]>", row, re.S)[:len(ks.COLUMNS)]
        rows.append("<tr>" + "".join(f"<{tag}>{html.escape(' '.join(html.unescape(re.sub(r'<[^>]*>', ' ', cell)).split()))}"
                                     f"</{tag}>" for tag, cell in cells) + "</tr>")
    body = (f'<h2>Candidates for the <span id="lblElection">{label}</span></h2>\n'
            f'<table id="gvCandidateList">\n' + "\n".join(rows) + "\n</table>\n")
    (FIXTURES / "state_ks_list.html").write_text(cut(text, body), encoding="utf-8", newline="")
    print(f"state_ks_list.html: {len(ks.KsList.parse((FIXTURES / 'state_ks_list.html').read_bytes()))} candidates, "
          f"{len(ks.KsList.parse(response.content))} as served")
    record_filers(client, key, "KS", place.cd)
    record_legislators(client, "ks")
    record_members(client, "KS", (None, place.cd))


def record_sc(client: httpx.Client, key: str) -> None:
    """South Carolina: SC_ADDRESS's Census answer; the State Election Commission's list of the
    year's statewide elections, as served; the search of the general election's candidates, its
    table cut down to the rows of the races the adapter places (withdrawn and defeated candidates
    included) and two of each office it leaves out (it has no contact details); the address's FEC
    filers for U.S. House, its legislators, and its members of Congress added to
    officeholders_congress.json."""
    name, address = SC_ADDRESS
    place = record_census(client, name, address)
    lists = sc.ScList.__new__(sc.ScList)
    day = general_day(dt.date(FEC_CYCLE, 1, 1))
    spec = lists.spec(day)
    response = client.get(spec.url, params=spec.params)
    response.raise_for_status()
    (FIXTURES / "state_sc.json").write_text(response.text, encoding="utf-8", newline="")
    search = lists.follow(sc.ScList.read_index(response.content), day)[0]
    time.sleep(2)
    response = client.post(search.url, data=search.form)
    response.raise_for_status()
    text = response.text
    body = re.search(r"<tbody>(.*)</tbody>", text, re.S)
    seen: dict[str, int] = {}
    kept = []
    for row in re.findall(r"<tr\b.*?</tr>", body.group(1), re.S):
        cells = [" ".join(html.unescape(re.sub(r"<[^>]*>", " ", c)).split())
                 for c in re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.S)]
        office, where = cells[0], cells[1]
        placed = sc._race(office, where) is not None
        seen[office] = seen.get(office, 0) + 1
        if placed or seen[office] <= 2:
            kept.append(row)
    (FIXTURES / "state_sc.html").write_text(
        text[:body.start(1)] + "".join(kept) + text[body.end(1):], encoding="utf-8", newline="")
    print(f"state_sc.html: {len(sc.ScList.parse((FIXTURES / 'state_sc.html').read_bytes()))} candidates, "
          f"{len(sc.ScList.parse(response.content))} as served")
    record_filers(client, key, "SC", place.cd)
    record_legislators(client, "sc")
    record_members(client, "SC", (None, place.cd))


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
            if (office and office.office_id in GA_RACES) or ga._text(item["name"]) in GA_SKIPPED:
                items.append({"name": item["name"], "summaryResults": {"ballotOptions": [
                    {key: option.get(key) for key in ("name", "voteCount", "isWriteIn", "party")}
                    for option in item["summaryResults"]["ballotOptions"]]}})
        save(f"state_ga_{election}.json", {"election": {key: data["election"].get(key) for key in ("name", "electionDate")},
                                           "ballotItems": items})
    record_legislators(client, "ga")


def record_wi(client: httpx.Client, key: str, saved: Path | None) -> None:
    """Wisconsin: WI_ADDRESS's Census answer; the Elections Commission's contests and candidates,
    never downloaded (its site blocks scripts): ``saved``, or the copy in manual/state_wi, cut down
    to the state's rows and WI_JURISDICTIONS'; its seat's FEC filers, its legislators, and its
    representative added to officeholders_congress.json."""
    name, address = WI_ADDRESS
    place = record_census(client, name, address)
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

    record_filers(client, key, "WI", place.cd)
    record_legislators(client, "wi")
    record_members(client, "WI", (None, place.cd))


def record_ar(client: httpx.Client, key: str, saved: Path | None) -> None:
    """Arkansas: AR_ADDRESS's Census answer; the Secretary of State's candidate search, never
    downloaded (it has no file): ``saved``, or the CSV in manual/state_ar, cut down to Congress, the
    statewide offices, the address's districts and AR_OFFICES; the FEC's filers for the U.S. Senate
    and the address's seat, its legislators, and its members of Congress added to officeholders_congress.json."""
    name, address = AR_ADDRESS
    place = record_census(client, name, address)
    path = saved or next(iter(sorted((ROOT / "manual" / "state_ar").glob("*.csv"))), None)
    if path is None:
        raise SystemExit("state_ar: save Arkansas's candidate search in manual/state_ar (see its README), or pass --csv")
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig")))
    kept = {f"State Senate District {place.sd:02d}", f"State Representative District {place.hd:02d}", *AR_OFFICES}
    out = io.StringIO()
    writer = csv.DictWriter(out, reader.fieldnames or (), quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writeheader()
    writer.writerows(row for row in reader if row["Position/Office"] in kept or row["Position/Office"].startswith("U.S. ")
                     or row["Position/Office"] in ar.STATEWIDE)
    (FIXTURES / "state_ar.csv").write_text(out.getvalue(), encoding="utf-8", newline="")
    print(f"state_ar.csv: {len(ar.parse_rows(out.getvalue()))} candidates")
    record_filers(client, key, "AR")
    record_filers(client, key, "AR", place.cd)
    record_legislators(client, "ar")
    record_members(client, "AR", (None, place.cd))


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
        place = record_census(client, name, address)
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
        record_filers(client, key, "NY", cd)
    record_legislators(client, "ny")
    record_members(client, "NY", seats)


def record_wy(client: httpx.Client) -> None:
    """Wyoming: the Secretary of State's General Election Candidates data file, every candidate's
    address, phone, email and website made up (WY_CONTACT); and its legislators. Cheyenne's Census
    answer and its FEC filers are the ballots' and the nationwide ones'."""
    response = client.get(wy.URL.format(year=FEC_CYCLE))
    response.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    out = io.StringIO()
    writer = csv.DictWriter(out, list(rows[0]), quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows({**row, **{column: WY_CONTACT.get(column, value) for column, value in row.items()}} for row in rows)
    (FIXTURES / "state_wy.csv").write_text(out.getvalue(), encoding="utf-8", newline="")
    print(f"state_wy.csv: {len(wy.WyList.parse(out.getvalue()))} candidates")
    record_legislators(client, "wy")


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


def record_congress_gov(client: httpx.Client, key: str) -> None:
    """John Cornyn's newest sponsored and cosponsored bills, as Pallot asks Congress.gov for them
    (the tests make him the Senate race's Ken Paxton, so the holder is on the ballot)."""
    for which, _ in congress_gov.LISTS:
        response = client.get(f"{congress_gov.API}/member/C001056/{which}-legislation", headers={"X-Api-Key": key},
                              params={"format": "json", "limit": str(congress_gov.NEWEST)})
        response.raise_for_status()
        save(f"congress_gov_C001056_{which}.json", response.json())


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
    record_legislators(client, "tx")
    path = FIXTURES / "officeholders_tx.csv"
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
    """TIGERweb's layer list, then the Capitol's districts, sent as Pallot sends them, and what's at
    the Capitol's point, as the address lookup asks when the geocoder's districts are down."""

    def get(spec) -> dict:
        response = client.get(spec.url, params=spec.params)
        response.raise_for_status()
        return response.json()

    index = get(tigerweb.index_spec())
    save("tigerweb_layers.json", index)
    for kind, number in OUTLINES.items():
        save(f"tigerweb_{tigerweb.geoid(kind, number)}.json",
             get(tigerweb.outline_spec(tigerweb.layer_id(index, kind), kind, number)))
    coords = json.loads((FIXTURES / "census_capitol.json").read_text())["result"]["addressMatches"][0]["coordinates"]
    save("tigerweb_identify_capitol.json",
         get(tigerweb.identify_spec(tigerweb.place_layer_ids(index), coords["y"], coords["x"])))


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
    parser.add_argument("--only", choices=("ballots", "suggest", "fec", "nationwide", "state_lists", "state_va", "state_ca", "state_nv", "state_ga", "state_wi", "state_oh", "state_ia", "state_nj", "state_ny", "state_co", "state_wy", "state_il", "state_ak", "state_me", "state_ne", "state_nm", "state_wa", "state_in", "state_md", "state_mo", "state_sc", "state_ky", "state_ok", "state_ks", "state_mt", "state_sd", "state_hi", "state_nd", "state_de", "state_vt", "state_ms", "state_ar", "grid", "polls", "key_dates", "officeholders",
"congress_gov", "wikidata", "tigerweb", "election_precincts", "county_precincts", "endorsement_feeds", "tec", "trackaipac", "voteforpeace"),
                        help="record just this part")
    parser.add_argument("--pdf", type=Path, help="state_ca: a copy of California's certified list, instead of downloading it; "
                                                 "state_nv: Nevada's, instead of the one saved in manual/state_nv; "
                                                 "state_ia: Iowa's, instead of the one saved in manual/state_ia; "
                                                 "state_ny: New York's, instead of the one saved in manual/state_ny")
    parser.add_argument("--json", type=Path, help="state_ga: Georgia's qualifying list, instead of the one saved in "
                                                  "manual/state_ga; state_oh: Ohio's, instead of manual/state_oh/ohio.json")
    parser.add_argument("--csv", type=Path, help="state_wi: Wisconsin's contests and candidates, instead of the one "
                                                 "saved in manual/state_wi; state_ar: Arkansas's candidate search, "
                                                 "instead of the one saved in manual/state_ar")
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
        if only == "state_va":
            record_va(client)
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
        if only in (None, "state_wy"):
            record_wy(client)
        if only in (None, "state_il"):
            record_il(client, config.fec_api_key)
        if only in (None, "state_ak"):
            record_ak(client, config.fec_api_key)
        if only in (None, "state_me"):
            record_me(client, config.fec_api_key)
        if only in (None, "state_ne"):
            record_ne(client, config.fec_api_key)
        if only in (None, "state_nm"):
            record_nm(client, config.fec_api_key)
        if only in (None, "state_wa"):
            record_wa(client, config.fec_api_key)
        if only in (None, "state_in"):
            record_in(client, config.fec_api_key)
        if only in (None, "state_md"):
            record_md(client, config.fec_api_key)
        if only in (None, "state_mo"):
            record_mo(client, config.fec_api_key)
        if only in (None, "state_sc"):
            record_sc(client, config.fec_api_key)
        if only in (None, "state_ky"):
            record_ky(client, config.fec_api_key)
        if only in (None, "state_ok"):
            record_ok(client, config.fec_api_key)
        if only in (None, "state_ks"):
            record_ks(client, config.fec_api_key)
        if only in (None, "state_mt"):
            record_mt(client, config.fec_api_key)
        if only in (None, "state_sd"):
            record_sd(client, config.fec_api_key)
        if only in (None, "state_hi"):
            record_hi(client, config.fec_api_key)
        if only in (None, "state_nd"):
            record_nd(client, config.fec_api_key)
        if only in (None, "state_de"):
            record_de(client, config.fec_api_key)
        if only in (None, "state_vt"):
            record_vt(client, config.fec_api_key)
        if only in (None, "state_ms"):
            record_ms(client, config.fec_api_key)
        if only in (None, "state_ar"):
            record_ar(client, config.fec_api_key, args.csv if only == "state_ar" else None)
        if only in (None, "grid"):
            record_grid(client)
        if only in (None, "polls"):
            record_polls(client)
        if only in (None, "key_dates"):
            record_key_dates(client)
        if only in (None, "officeholders"):
            record_officeholders(client)
        if only in (None, "congress_gov"):
            record_congress_gov(client, config.fec_api_key)
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
