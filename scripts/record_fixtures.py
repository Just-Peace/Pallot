"""Record the live API responses that VoteBot's tests replay, into tests/fixtures/.

    python scripts/record_fixtures.py

Makes about 30 requests (Census geocoder, Nominatim, Texas SOS, Ballotpedia). The 2.6 MB
statewide candidate list is cut down to the candidates on the recorded ballots, and the
TrackAIPAC fixture is a Texas subset of trackaipac_cache's bundled data (no request).
The tests pin "today" to 2026-09-27; after the Nov 3, 2026 election, re-recording means
updating ELECTIONS below and the tests' expectations.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from votebot.config import Config  # noqa: E402
from votebot.sources import ballotpedia, census, nominatim, sos  # noqa: E402

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
BALLOTPEDIA_AT = ("capitol",)
TRACKAIPAC_PEOPLE = (
    "tx-ken-paxton", "tx-james-talarico", "tx-august-pfluger", "tx-greg-casar", "tx-lloyd-doggett",
    "tx-michael-cloud", "tx-tanya-lloyd", "tx-ted-cruz", "tx-michael-mccaul", "tx-christian-menefee",
)


def save(name: str, data: object) -> None:
    path = FIXTURES / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{name}: {path.stat().st_size:,} bytes")


def main() -> int:
    with httpx.Client(timeout=90, headers={"User-Agent": Config.user_agent}, follow_redirects=True) as client:

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

    bundled = ROOT / "trackaipac_cache" / "data"
    current = json.loads((bundled / "current.json").read_text(encoding="utf-8"))
    people = [p for p in current["candidates"] if p["candidate_id"] in TRACKAIPAC_PEOPLE]
    save("trackaipac/current.json", {"snapshot": current["snapshot"], "candidates": people})
    save("trackaipac/meta.json", json.loads((bundled / "meta.json").read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
