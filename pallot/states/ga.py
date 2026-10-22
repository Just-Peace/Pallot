"""Georgia: two of the Secretary of State's official sources, together.

The party nominees come from its election results site (results.sos.ga.gov), which is open to
scripts: the winner of each party's May primary, by a majority of its votes, or of its June
runoff where no one had one, a recount's count standing in for the one it recounted. Only the
races the state runs are read from it: Congress, the statewide offices, the Public Service
Commission, the Legislature and the district attorneys. Its nonpartisan judges were elected in
May, and its party questions aren't races.

Everyone else on the November ballot (independents, political bodies' candidates, nonpartisan
and local offices, special elections) is on the SOS's list of qualified candidates
(mvp.sos.ga.gov), which, like sos.ga.gov, answers scripts with Cloudflare's challenge, so Pallot
never asks it: the maintainer saves its answer in their own browser and imports it
(manual/state_ga). It's the Salesforce answer the page reads, its candidates grouped by the
kind of office, then the county or city, then the office. Only the Qualified ones are kept, and
of each only their office, ballot name, party and whether they hold the seat: the file also
has their phones, emails and addresses.

A county's whole-county office reaches the county; one with a district, post or ward number,
and a county's district offices, only part of it. A city's office reaches the whole city, but a
district or ward only part of it. A district attorney's judicial circuit isn't said by county,
so those races are only counted.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from typing import Any

from .. import counties
from ..http_cache import RequestSpec
from ..sources.fec import race_name
from ..text import display_person
from . import Filing, ManualList, party
from .key_dates import first_tuesday_after_first_monday

RESULTS_API = "https://results.sos.ga.gov/results/public/api"
ELECTIONS = f"{RESULTS_API}/jurisdictions/Georgia"
ELECTION = RESULTS_API + "/elections/Georgia/{id}/data"
PAGE = "https://mvp.sos.ga.gov/s/qualifying-candidate-information"
STATEWIDE = {
    "GOVERNOR": "Governor", "LIEUTENANT GOVERNOR": "Lieutenant Governor", "SECRETARY OF STATE": "Secretary of State",
    "ATTORNEY GENERAL": "Attorney General", "COMMISSIONER OF AGRICULTURE": "Commissioner of Agriculture",
    "AGRICULTURE COMMISSIONER": "Commissioner of Agriculture", "COMMISSIONER OF INSURANCE": "Commissioner of Insurance",
    "INSURANCE COMMISSIONER": "Commissioner of Insurance",
    "INSURANCE AND FIRE SAFETY COMMISSIONER": "Commissioner of Insurance",
    "INSURANCE AND SAFETY FIRE COMMISSIONER": "Commissioner of Insurance",
    "STATE SCHOOL SUPERINTENDENT": "State School Superintendent", "COMMISSIONER OF LABOR": "Commissioner of Labor",
    "LABOR COMMISSIONER": "Commissioner of Labor",
}
NOMINEES = {"REP": "R", "DEM": "D"}
_CONTEST = re.compile(r"(?P<office>.+?)\s+-\s+(?P<party>Rep|Dem)", re.I)
_INCUMBENT = re.compile(r"\s*\(I\)\s*$")
_NUMBERED = re.compile(r"\b(?:DISTRICT|DIST|POST|WARD|SEAT|D)\s*#?\s*\d", re.I)
_PART_CITY = re.compile(r"\b(?:DISTRICT|WARD)\s*#?\s*\d", re.I)
_UNEXPIRED = re.compile(r"UNEXPIRED|VACAN|VAVANCY|SPECIAL ELECTION|TO FILL", re.I)
_MARKS = re.compile(r'^\s*(?:\(C\)\s*|FOR\s+|DUPLICATE\s*-\s*)+|\s*(?:"DUPLICATE"|\(DUPLICATE\))\s*$', re.I)
_SMALL = {"OF", "THE", "AND", "TO", "FOR", "IN", "AT"}
_PARTIES = {"DEMOCRAT": "D", "DEMOCRATIC": "D", "REPUBLICAN": "R", "LIBERTARIAN": "L"}
_NO_PARTY = ("", "INDEPENDENT", "NON-PARTISAN", "NONPARTISAN", "OTHER")
_YEAR = re.compile(r"\b(20\d\d)\b")


@dataclass(frozen=True)
class _Office:
    race: str  # the race's id: "STATE HOUSE 58", "SHERIFF (TOWNS)"
    shown: str
    family: str
    group: str
    reach: str
    district: str | None = None
    counties: tuple[str, ...] = ()
    city: str | None = None
    unexpired: bool = False


def _text(value: Any) -> str:
    """The English text of the results site's [{"languageId", "text"}]."""
    texts = [row.get("text") or "" for row in value or [] if isinstance(row, dict)]
    english = [row.get("text") or "" for row in value or [] if isinstance(row, dict) and row.get("languageId") == "en"]
    return " ".join((english or texts or [""])[0].split())


def _title(text: str) -> str:
    """ "BOARD OF EDUCATION DISTRICT 3" -> "Board of Education District 3", and "SOIL and WATER"
    too; mixed case as it is."""
    if sum(c.isupper() for c in text) <= sum(c.islower() for c in text):
        return text
    words = text.title().split(" ")
    return " ".join(word.lower() if i and word.upper() in _SMALL else word for i, word in enumerate(words))


def _tidy(office: str) -> str:
    """An office as the list names it, without its "For" and the marks of a record entered twice."""
    return _title(" ".join(_MARKS.sub("", " ".join(office.split())).split()))


def state_office(text: str) -> _Office | None:
    """A race the state runs, as either source names it ("US House of Representatives - District 5",
    "U.S House of Representatives, District 14"); None for any other."""
    upper = " ".join(re.sub(r"\(NP\)|\.", " ", _MARKS.sub("", text.split("/")[0])).upper().split())
    if upper == "US SENATE":
        return _Office("US SENATE", race_name("GA", None), "US SENATE", "federal", "state")
    if found := re.fullmatch(r"US HOUSE(?: OF REPRESENTATIVES)?\W+DISTRICT (\d+)", upper):
        number = str(int(found.group(1)))
        return _Office(f"US HOUSE {number}", race_name("GA", int(number)), "US HOUSE", "federal", "cd", number)
    for pattern, reach, family, label in (
        (r"STATE SENATE\W+DISTRICT (\d+)", "sd", "STATE SENATE", "State Senate"),
        (r"STATE HOUSE(?: OF REPRESENTATIVES)?\W+DISTRICT (\d+)", "hd", "STATE HOUSE", "State House"),
    ):
        if found := re.fullmatch(pattern, upper):
            number = str(int(found.group(1)))
            return _Office(f"{family} {number}", f"{label} District {number}", family, "legislature", reach, number)
    if found := re.fullmatch(r"(?:PSC|PUBLIC SERVICE COMMISSION(?:ER)?)\W+DISTRICT (\d+)", upper):
        number = str(int(found.group(1)))
        return _Office(f"PUBLIC SERVICE COMMISSION {number}", f"Public Service Commission District {number}",
                       "PUBLIC SERVICE COMMISSION", "state", "state", number)
    if upper in STATEWIDE:
        return _Office(STATEWIDE[upper].upper(), STATEWIDE[upper], STATEWIDE[upper].upper(), "state", "state")
    if found := re.fullmatch(r"(SPECIAL (?:PRIMARY )?)?DISTRICT ATTORNEY\W+(.+?) JUDICIAL CIRCUIT\b.*", upper):
        circuit = found.group(2).title()
        special = bool(found.group(1))
        return _Office(f"{'SPECIAL ' if special else ''}DISTRICT ATTORNEY {circuit.upper()}",
                       f"District Attorney, {circuit} Judicial Circuit{' (special election)' if special else ''}",
                       "District Attorney", "county", "unplaced", unexpired=special)
    return None


# -- the party nominees, from the results site ------------------------------------------------


def stages(elections: dict[str, Any], day: dt.date) -> list[tuple[str, bool]]:
    """The results that settle the nominees for the general on ``day``, in the order they do:
    (election id, whether it's a runoff's count), the year's general primary first, then any
    recount, then the runoff and its recounts. None before the year's primary is listed."""
    found: list[tuple[dt.date, int, str, str]] = []
    for election in elections.get("elections") or []:
        try:
            date = dt.date.fromisoformat(str(election.get("electionDate"))[:10])
        except ValueError:
            continue
        name = _text(election.get("name")).lower()
        kind = ("recount" if "recount" in name else "runoff" if "general primary runoff" in name
                else "primary" if "general primary" in name else None)
        if kind and date.year == day.year and date < day and election.get("publicElectionId"):
            found.append((date, kind == "recount", kind, str(election["publicElectionId"])))
    primary = min((date for date, _, kind, _ in found if kind == "primary"), default=None)
    if primary is None:
        return []
    runoffs = [date for date, _, kind, _ in found if kind == "runoff"]
    return [(election_id, kind == "runoff" or (kind == "recount" and any(r <= date for r in runoffs)))
            for date, _, kind, election_id in sorted(found) if date >= primary]


def contests(data: dict[str, Any]) -> list[tuple[_Office, str, list[tuple[str, int, bool]]]]:
    """Each party's contest for a race the state runs: (office, party code, [(name, votes,
    incumbent)]), write-ins left out. ValueError for an answer without its contests."""
    items = data.get("ballotItems")
    if not isinstance(items, list):
        raise ValueError("no ballotItems")
    found = []
    for item in items:
        contest = _CONTEST.fullmatch(_text(item.get("name")))
        office = state_office(contest.group("office")) if contest else None
        if office is None:
            continue
        options = []
        for option in (item.get("summaryResults") or {}).get("ballotOptions") or []:
            if option.get("isWriteIn"):
                continue
            name = _text(option.get("name"))
            options.append((_INCUMBENT.sub("", name), int(option.get("voteCount") or 0), bool(_INCUMBENT.search(name))))
        found.append((office, NOMINEES[contest.group("party").upper()], options))
    return found


def _winner(options: list[tuple[str, int, bool]], runoff: bool) -> tuple[str, int, bool] | None:
    """The one unopposed, a primary's majority, or a runoff's most votes; None for no winner yet."""
    if len(options) == 1:
        return options[0]
    ranked = sorted(options, key=lambda option: -option[1])
    if not ranked or ranked[0][1] == ranked[1][1]:
        return None
    if runoff or ranked[0][1] * 2 > sum(option[1] for option in options):
        return ranked[0]
    return None


def nominees(counts: list[tuple[bool, dict[str, Any]]], day: str) -> list[Filing]:
    """Each party's nominee for each race, from the counts in stages()' order, each a runoff's or
    not: a later count settles a contest an earlier one did, and a contest no count settled has
    no nominee."""
    decided: dict[tuple[str, str], tuple[_Office, tuple[str, int, bool] | None, int]] = {}
    for runoff, data in counts:
        for office, code, options in contests(data):
            key = (office.race, code)
            at = decided[key][2] if key in decided else len(decided)
            decided[key] = (office, _winner(options, runoff), at)
    return [
        Filing(day=day, office_id=office.race, office=office.shown, family=office.family, group=office.group,
               reach=office.reach, district=office.district, name=winner[0], party=code, incumbent=winner[2],
               unexpired=office.unexpired, order=at * 10 + (0 if code == "R" else 1))
        for (_, code), (office, winner, at) in decided.items() if winner
    ]


def trim(data: dict[str, Any]) -> dict[str, Any]:
    """An answer from the results site as bundled: the election list's elections, or an
    election's party contests for the races the state runs, with their candidates' names and
    votes, as the site words them (nothing about precincts or turnout)."""
    if "elections" in data:
        return {"elections": [{key: election.get(key) for key in ("publicElectionId", "electionDate", "name")}
                              for election in data.get("elections") or []]}
    wanted = []
    for item in data.get("ballotItems") or []:
        contest = _CONTEST.fullmatch(_text(item.get("name")))
        if not contest or state_office(contest.group("office")) is None:
            continue
        options = [{"name": option.get("name"), "voteCount": option.get("voteCount"), "isWriteIn": option.get("isWriteIn")}
                   for option in (item.get("summaryResults") or {}).get("ballotOptions") or []]
        wanted.append({"name": item.get("name"), "summaryResults": {"ballotOptions": options}})
    election = data.get("election") or {}
    return {"election": {"name": election.get("name"), "electionDate": election.get("electionDate")},
            "ballotItems": wanted}


# -- everyone else, from the qualifying list saved by hand -----------------------------------


def _party(row: dict[str, Any]) -> tuple[str | None, str | None]:
    raw = " ".join(str(row.get("Candidate_Party__c") or "").split())
    if raw.upper() in _PARTIES:
        return _PARTIES[raw.upper()], None
    if raw.upper() == "OTHER":
        body = " ".join(str(row.get("vr_Political_Bodies__c") or "").split())
        return None, (body if body.upper() not in _NO_PARTY else None)
    if raw.upper() in _NO_PARTY:
        return None, None
    return party(raw)


def _name(text: str) -> str:
    """ 'THOMAS "JOSH" SAPPINGTON' -> 'Thomas "Josh" Sappington'."""
    return " ".join(f'"{display_person(word.strip(chr(34)))}"' if word.startswith('"') else display_person(word)
                    for word in text.split())


def _county(place: str) -> str:
    found = counties.find("GA", place.replace("_", " "))
    return found.name.upper() if found else " ".join(place.replace("_", " ").upper().split())


def _city(place: str, rows: list[dict[str, Any]]) -> tuple[str, tuple[str, ...]]:
    """(city, its counties) of a city's offices: "DANVILLE_TWIGGS" is Danville, in Twiggs County;
    otherwise the counties its candidates live in."""
    words = place.replace("_", " ").upper().split()
    if len(words) > 1 and (county := counties.find("GA", words[-1])):
        return " ".join(words[:-1]), (county.name.upper(),)
    homes = {_county(str(row["County__c"])) for row in rows if str(row.get("County__c") or "").strip()}
    return " ".join(words), tuple(sorted(homes))


def _group(upper: str, municipal: bool) -> str:
    if re.search(r"\b(?:JUDGE|MAGISTRATE|PROBATE)\b", upper):
        return "judicial"
    if municipal or re.search(r"\b(?:SCHOOL|EDUCATION|BOE)\b", upper):
        return "local"
    return "county"


def _local(kind: str, place: str, name: str, rows: list[dict[str, Any]]) -> _Office:
    """The race of an office the qualifying list files under ``kind`` and ``place``."""
    if kind in ("Federal", "Statewide", "State Race"):
        found = state_office(name)
        if found:
            return found
        shown = _tidy(name)
        return _Office(shown.upper(), shown, shown.upper(), "state", "unplaced")
    shown = _tidy(name)
    unexpired = bool(_UNEXPIRED.search(name))
    if kind in ("Countywide", "County Level"):
        county = _county(place)
        if not shown or shown.upper() == "DUPLICATED CONTEST":
            shown, reach = "Office not named in the list", "part_county"
        else:
            reach = "county" if kind == "Countywide" and not _NUMBERED.search(shown) else "part_county"
        upper = shown.upper()
        return _Office(f"{upper} ({county})", shown, upper, _group(upper, False), reach, counties=(county,),
                       unexpired=unexpired)
    city, homes = _city(place, rows)
    if city.lower() not in shown.lower():
        shown = f"{shown}, City of {city.title()}"
    upper = shown.upper()
    reach = "city" if kind == "Municipalwide" and not _PART_CITY.search(upper) else "part_city"
    return _Office(f"{upper} ({city})", shown, upper.split(",")[0], _group(upper, True), reach, counties=homes,
                   city=city, unexpired=unexpired)


def qualified(text: str) -> list[Filing]:
    """Every qualified candidate in the saved answer, for the general election in the year they
    qualified; ValueError for a file that isn't that answer."""
    try:
        groups = json.loads(text)["actions"][0]["returnValue"]["returnValue"]
    except ValueError as exc:
        raise ValueError(f"not JSON ({exc})") from exc
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("no candidates where the qualifying page's answer has them") from exc
    if not isinstance(groups, dict):
        raise ValueError("no candidates where the qualifying page's answer has them")
    rows = [(kind, place, office, row) for kind, places in groups.items() for place, offices in (places or {}).items()
            for office, found in (offices or {}).items() for row in found or []]
    years = [int(year.group(1)) for *_, row in rows if (year := _YEAR.search(str(row.get("Date_Qualified__c") or "")))]
    if not years:
        raise ValueError("no qualifying dates")
    day = first_tuesday_after_first_monday(max(years), 11).isoformat()
    filings = []
    races: dict[tuple[str, str, str], _Office] = {}
    for index, (kind, place, name, row) in enumerate(rows):
        if not str(row.get("Declaration__c") or "").startswith("Qualified"):
            continue
        if (kind, place, name) not in races:
            races[kind, place, name] = _local(kind, place, name, groups[kind][place][name])
        office = races[kind, place, name]
        code, party_name = _party(row)
        filings.append(Filing(
            day=day, office_id=office.race, office=office.shown, family=office.family, group=office.group,
            reach=office.reach, district=office.district, name=_name(" ".join(str(row.get("Name_on_Ballot__c")).split())),
            party=code, party_name=party_name, counties=office.counties, city=office.city, unexpired=office.unexpired,
            incumbent=bool(row.get("Incumbent__c")), order=10_000 + index,
        ))
    if not filings:
        raise ValueError("no qualified candidates")
    return filings


def merge(nominated: list[Filing], listed: list[Filing]) -> list[Filing]:
    """The nominees, then everyone else qualified, leaving out a party's candidate the qualifying
    list also has for a race whose nominee the results settled."""
    settled = {(f.office_id, f.party) for f in nominated}
    return nominated + [f for f in listed if f.party not in ("D", "R") or (f.office_id, f.party) not in settled]


class GaList(ManualList):
    state = "GA"
    source = "state_ga"
    label = "Georgia Secretary of State"
    page = PAGE
    description = ("Georgia's official candidates, from its Secretary of State: each party's nominees, from its primary "
                   "results, and everyone else who qualified, from Congress to its counties and cities, imported by "
                   "hand.")
    folder = "manual/state_ga"
    challenge = ("Just a moment...", "challenges.cloudflare.com", "cf-browser-verification")
    fetched = True

    @classmethod
    def results(cls, election: str | None = None) -> RequestSpec:
        """The results site's list of elections, or one election's results."""
        return RequestSpec("GET", ELECTION.format(id=election) if election else ELECTIONS)

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        return qualified(raw if isinstance(raw, str) else "")

    @classmethod
    def shape(cls, raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict) and ("elections" in raw or "ballotItems" in raw):
            return trim(raw)
        return super().shape(raw)

    def check(self, value: Any) -> str | None:
        if isinstance(value, dict) and "elections" in value:
            return None if isinstance(value["elections"], list) else "its list of elections isn't a list"
        if isinstance(value, dict) and "ballotItems" in value:
            try:
                contests(value)
            except (ValueError, TypeError, AttributeError) as exc:
                return f"can't read its results: {exc}"
            return None
        return super().check(value)

    async def nominees(self, day: dt.date) -> list[Filing]:
        """Each party's nominee for the general on ``day``, from the year's primary, recounts and
        runoff; none before its primary is listed. UpstreamError when they can't be had."""
        elections = await self.cache.get_json(self.source, self.results(), ttl=self.ttl.state_list)
        counts = []
        for election, runoff in stages(elections.value, day):
            got = await self.cache.get_json(self.source, self.results(election), ttl=self.ttl.state_list)
            counts.append((runoff, got.value))
        return nominees(counts, day.isoformat())

    async def filings(self, day: dt.date) -> list[Filing] | None:
        listed = await super().filings(day) or []
        return merge(await self.nominees(day), listed) or None

    def missing(self, when: str) -> str:
        return f"Pallot doesn't have the {self.label}'s candidates for {when} yet"
