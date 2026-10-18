"""Profiles and photos of officeholders from Wikidata (CC0), through its public query service.

Two SPARQL queries, both through HttpCache: PEOPLE, every living person who holds or held an
office in the ballot's state (a seat whose district is in the state, or an office whose
jurisdiction is the state), one answer per state, Texas's bundled with Pallot; then DETAILS, for
only the people matched on this ballot (their description, photo, birth date, party, website,
Wikipedia article and Ballotpedia page). Nothing about the voter is sent, only Wikidata's own
item ids and the state's. Matching is by name with the seat to corroborate
(seats.match_entries): Congress's seats in any state, and Texas's own offices; another state's
offices have no seat, so a match there is only "likely". Wikidata often leaves a Texas House
member's district out, so that office counts as any district's seat. Only a full (or first and
last) name with no party against it is kept (trusted), so the photo is used for every match kept.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec, UpstreamError
from ..matching import FIRST_LAST, FULL, NameIndex
from ..models import Fact, Link, Match, Race, SourceCard
from ..offices import OfficeScope
from ..text import display_date, iso_utc
from . import CardSet
from .ballotpedia import BpBallot
from .seats import match_entries

log = logging.getLogger("uvicorn.error")

SOURCE = "wikidata"
LABEL = "Wikidata"
DESCRIPTION = (
    "Photos, offices held and links for candidates who hold or held an office in your state, from Wikidata, the "
    "knowledge base behind Wikipedia."
)
ENDPOINT = "https://query.wikidata.org/sparql"
ITEM = "https://www.wikidata.org/wiki/"
CHUNK = 50  # people per DETAILS query, which keeps its URL short
PHOTO_WIDTH = 300
PEOPLE = """SELECT DISTINCT ?p ?label ?pos ?posL ?dL ?start ?end ?party WHERE {
  { ?p p:P39 ?st . ?st pq:P768 ?d0 . ?d0 wdt:P131 wd:%(state)s . }
  UNION { ?p p:P39 ?st . ?st pq:P768 wd:%(state)s . }
  UNION { ?p p:P39 ?st . ?st ps:P39 ?pos0 . ?pos0 wdt:P1001 wd:%(state)s . }
  ?p wdt:P31 wd:Q5 .
  FILTER NOT EXISTS { ?p wdt:P570 ?died }
  ?st ps:P39 ?pos .
  ?pos rdfs:label ?posL . FILTER(LANG(?posL) = "en")
  OPTIONAL { ?st pq:P768 ?d . ?d rdfs:label ?dL . FILTER(LANG(?dL) = "en") }
  OPTIONAL { ?st pq:P580 ?start }
  OPTIONAL { ?st pq:P582 ?end }
  OPTIONAL { ?p wdt:P102 ?party }
  ?p rdfs:label ?label . FILTER(LANG(?label) = "en")
}"""
DETAILS = """SELECT ?p ?desc ?img ?born ?site ?siteRole ?bp ?article ?partyL WHERE {
  VALUES ?p { %s }
  OPTIONAL { ?p schema:description ?desc . FILTER(LANG(?desc) = "en") }
  OPTIONAL { ?p wdt:P18 ?img }
  OPTIONAL { ?p wdt:P569 ?born }
  OPTIONAL { ?p p:P856 ?ws . ?ws ps:P856 ?site . FILTER NOT EXISTS { ?ws wikibase:rank wikibase:DeprecatedRank }
             OPTIONAL { ?ws pq:P3831 ?siteRole } }
  OPTIONAL { ?p wdt:P2390 ?bp }
  OPTIONAL { ?article schema:about ?p ; schema:isPartOf <https://en.wikipedia.org/> }
  OPTIONAL { ?p wdt:P102 ?party . ?party rdfs:label ?partyL . FILTER(LANG(?partyL) = "en") }
}"""
# Each office's seat as seats.race_seat spells it; "STATEREP:*" stands for any district (seats.fit).
US_HOUSE, US_SENATE, STATE_HOUSE, STATE_SENATE = "Q13218630", "Q4416090", "Q18604553", "Q18565274"
STATEWIDE = {
    "Q5589725": "GOVERNOR", "Q639115": "LTGOVERNOR", "Q7707525": "ATTYGEN", "Q8350359": "COMPTROLLER",
    "Q124518473": "LANDCOMM", "Q7707628": "AGRICULTUR", "Q1647484": "RRCOMM",
}
SPEAKER = "Q7574310"
_CHAMBERS = {"STATEREP": "State Representative", "STATESEN": "State Senator"}
SITE_ROLES = {"Q130304960": "Campaign website", "Q120942996": "Government website"}  # P3831 on a P856 statement
PARTIES = {"Q29552": "D", "Q29468": "R", "Q558334": "L"}
STATES = {
    "AK": "Q797", "AL": "Q173", "AR": "Q1612", "AZ": "Q816", "CA": "Q99", "CO": "Q1261", "CT": "Q779", "DC": "Q61",
    "DE": "Q1393", "FL": "Q812", "GA": "Q1428", "HI": "Q782", "IA": "Q1546", "ID": "Q1221", "IL": "Q1204", "IN": "Q1415",
    "KS": "Q1558", "KY": "Q1603", "LA": "Q1588", "MA": "Q771", "MD": "Q1391", "ME": "Q724", "MI": "Q1166", "MN": "Q1527",
    "MO": "Q1581", "MS": "Q1494", "MT": "Q1212", "NC": "Q1454", "ND": "Q1207", "NE": "Q1553", "NH": "Q759", "NJ": "Q1408",
    "NM": "Q1522", "NV": "Q1227", "NY": "Q1384", "OH": "Q1397", "OK": "Q1649", "OR": "Q824", "PA": "Q1400", "RI": "Q1387",
    "SC": "Q1456", "SD": "Q1211", "TN": "Q1509", "TX": "Q1439", "UT": "Q829", "VA": "Q1370", "VT": "Q16551",
    "WA": "Q1223", "WI": "Q1537", "WV": "Q1371", "WY": "Q1214",
}  # each state's Wikidata item, by postal code (its ISO 3166-2 code, P300)
_QID = re.compile(r"^Q\d+$")
_CONGRESS = re.compile(r"^.+'s (?:(\d+)(?:st|nd|rd|th)|at-large) congressional district$", re.IGNORECASE)


@dataclass
class Held:
    office: str  # Wikidata's label: "United States representative"
    seat: str | None  # as seat_of reads it: "TX-35", "STATESEN:2", "STATEREP:*"
    start: str | None  # ISO dates
    end: str | None

    def text(self) -> str:
        """ "State Senator, District 2 (2015–)", "U.S. Representative, TX-17 (2019–2021)", or
        Wikidata's label for any other office ("Texas Attorney General (2015–)")."""
        years = "–".join([(self.start or "")[:4], (self.end or "")[:4]]) if self.start or self.end else ""
        kind, _, number = (self.seat or "").partition(":")
        if kind in _CHAMBERS and not self.office.lower().startswith("speaker"):
            office = _CHAMBERS[kind] + (f", District {number}" if number.isdigit() else "")
        elif self.seat and re.fullmatch(r"[A-Z]{2}-SEN", self.seat):
            office = "U.S. Senator"
        elif self.seat and re.fullmatch(r"[A-Z]{2}-\d\d", self.seat):
            office = f"U.S. Representative, {self.seat}"
        else:
            office = f"{self.office[:1].upper()}{self.office[1:]}"
        return office + (f" ({years})" if years else "")


@dataclass
class Person:
    qid: str
    name: str
    party: str | None = None  # D, R or L, when Wikidata gives one party
    seats: set[str] = field(default_factory=set)
    held: list[Held] = field(default_factory=list)  # the state's offices, latest first

    def entry(self) -> dict[str, Any]:
        """The shape seats.match_entries reads: ``office_title`` words the latest office for a match's notes."""
        return {"qid": self.qid, "name": self.name, "party": self.party, "seats": self.seats,
                "office_title": self.held[0].text() if self.held else None, "person": self}


@dataclass
class Details:
    description: str | None = None
    photo: str | None = None
    born: str | None = None
    party: str | None = None
    article: str | None = None
    ballotpedia: str | None = None
    websites: dict[str, str] = field(default_factory=dict)  # url -> "Campaign website", "Government website" or "Website"


def _value(row: dict[str, Any], name: str) -> str | None:
    return (row.get(name) or {}).get("value") or None


def _qid(url: str | None) -> str | None:
    tail = (url or "").rsplit("/", 1)[-1]
    return tail if _QID.match(tail) else None


def _number(text: str | None) -> int | None:
    found = re.search(r"\b(\d+)\b", text or "")
    return int(found.group(1)) if found else None


def seat_of(position: str, district: str | None, state: str = "TX") -> str | None:
    """The seat an office held in ``state`` is, as the ballot's races spell it, or None for an
    office Pallot has no race for. Only Texas's own offices have seats; Congress's are any state's."""
    if position == US_HOUSE:
        found = _CONGRESS.match(district or "")
        return f"{state}-{int(found.group(1) or 0):02d}" if found else None
    if position == US_SENATE:
        return f"{state}-SEN" if district else None
    if state != "TX":
        return None
    if position in (STATE_HOUSE, STATE_SENATE):
        chamber = "STATEREP" if position == STATE_HOUSE else "STATESEN"
        number = _number(district) if district and "istrict" in district else None
        return f"{chamber}:{number}" if number else f"{chamber}:*"
    if position == SPEAKER:
        return "STATEREP:*"
    return STATEWIDE.get(position)


def people_from(answer: dict[str, Any], state: str = "TX") -> list[Person]:
    """PEOPLE's rows for ``state`` (one per office held, and per party) folded into one Person each."""
    people: dict[str, Person] = {}
    parties: dict[str, set[str]] = {}
    held: dict[str, dict[tuple[Any, ...], Held]] = {}
    for row in (answer.get("results") or {}).get("bindings") or []:
        qid, name = _qid(_value(row, "p")), _value(row, "label")
        if not qid or not name:
            continue
        person = people.setdefault(qid, Person(qid, name))
        if party := _qid(_value(row, "party")):
            parties.setdefault(qid, set()).add(party)
        position = _qid(_value(row, "pos"))
        seat = seat_of(position, _value(row, "dL"), state) if position else None
        if seat:
            person.seats.add(seat)
        office = Held(_value(row, "posL") or "", seat, (_value(row, "start") or "")[:10] or None,
                      (_value(row, "end") or "")[:10] or None)
        if office.office:
            held.setdefault(qid, {})[(office.office, office.seat, office.start, office.end)] = office
    for qid, person in people.items():
        found = parties.get(qid, set())
        person.party = PARTIES.get(next(iter(found))) if len(found) == 1 else None
        person.held = sorted(held.get(qid, {}).values(), key=lambda h: (h.end is None, h.end or "", h.start or ""),
                             reverse=True)
    return list(people.values())


def details_from(answer: dict[str, Any]) -> dict[str, Details]:
    """DETAILS's rows (one per website, party and so on) folded by item id."""
    out: dict[str, Details] = {}
    for row in (answer.get("results") or {}).get("bindings") or []:
        qid = _qid(_value(row, "p"))
        if not qid:
            continue
        found = out.setdefault(qid, Details())
        found.description = found.description or _value(row, "desc")
        found.photo = found.photo or photo_url(_value(row, "img"))
        found.born = found.born or (_value(row, "born") or "")[:10] or None
        found.party = found.party or _value(row, "partyL")
        found.article = found.article or _value(row, "article")
        found.ballotpedia = found.ballotpedia or _value(row, "bp")
        site = _value(row, "site")
        if site and site.startswith(("http://", "https://")):
            role = SITE_ROLES.get(_qid(_value(row, "siteRole")) or "")
            if role or site not in found.websites:
                found.websites[site] = role or "Website"
    return out


def photo_url(image: str | None) -> str | None:
    """A Commons file (Special:FilePath) at the width the page shows, over https."""
    if not image or "/Special:FilePath/" not in image:
        return None
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{image.split('/Special:FilePath/', 1)[1]}?width={PHOTO_WIDTH}"


def people_spec(state: str = "TX") -> RequestSpec:
    return RequestSpec("GET", ENDPOINT, params={"query": PEOPLE % {"state": STATES[state]}, "format": "json"},
                       headers={"Accept": "application/sparql-results+json"})


def details_spec(qids: list[str]) -> RequestSpec:
    values = " ".join(f"wd:{qid}" for qid in qids)
    return RequestSpec("GET", ENDPOINT, params={"query": DETAILS % values, "format": "json"},
                       headers={"Accept": "application/sparql-results+json"})


class Wikidata:
    def __init__(self, cache: HttpCache, ttl: Ttls):
        self.cache = cache
        self.ttl = ttl
        self._parsed: dict[str, tuple[float, list[Person], NameIndex]] = {}
        cache.pause_on(SOURCE, ttl.wikidata_backoff)

    async def _get(self, spec: RequestSpec) -> Any:
        return await self.cache.get_json(SOURCE, spec, ttl=self.ttl.wikidata)

    async def people(self, state: str = "TX") -> tuple[list[Person], NameIndex, float]:
        """Every officeholder in ``state`` Wikidata has, indexed by name, read once per stored copy."""
        got = await self._get(people_spec(state))
        parsed = self._parsed.get(state)
        if parsed is None or parsed[0] != got.fetched_at:
            people = people_from(got.value or {}, state)
            index = NameIndex()
            for person in people:
                index.add(person.name, person.entry())
            parsed = self._parsed[state] = (got.fetched_at, people, index)
        return parsed[1], parsed[2], got.fetched_at

    async def details(self, qids: list[str]) -> dict[str, Details]:
        out: dict[str, Details] = {}
        ordered = sorted(set(qids), key=lambda q: int(q[1:]))
        for start in range(0, len(ordered), CHUNK):
            got = await self._get(details_spec(ordered[start:start + CHUNK]))
            out.update(details_from(got.value or {}))
        return out


def card(person: Person, match: Match, found: Details | None, fetched_at: float, ballotpedia: bool = False) -> SourceCard:
    """The Profile tab's section. No description, which Settings already gives; the Ballotpedia
    link only while Ballotpedia is on (``ballotpedia``)."""
    item = f"{ITEM}{person.qid}"
    found = found or Details()
    facts = [
        Fact(label="Description", value=found.description or ""),
        Fact(label="Born", value=display_date(found.born) or ""),
        Fact(label="Party", value=found.party or ""),
        Fact(label="Offices held", value="; ".join(h.text() for h in person.held)),
    ]
    links = [Link(label="Wikidata item", url=item)]
    if found.article:
        links.append(Link(label="Wikipedia article", url=found.article))
    order = ("Campaign website", "Website", "Government website")
    links += [Link(label=role, url=site) for site, role in sorted(found.websites.items(), key=lambda s: order.index(s[1]))]
    if found.ballotpedia and ballotpedia:
        links.append(Link(label="Ballotpedia", url=f"https://ballotpedia.org/{quote(found.ballotpedia)}"))
    return SourceCard(
        source=SOURCE,
        kind="profile",
        label=LABEL,
        url=item,
        image=found.photo,
        as_of=iso_utc(fetched_at),
        match=match,
        facts=[f for f in facts if f.value],
        links=links,
    )


def trusted(match: Match, party: str | None, their_party: str | None) -> bool:
    """Whether a match is close enough to show. The list is everyone who has held a Texas office,
    not a list of candidates, so a first initial or a last name alone finds namesakes (a Senate
    candidate Bradford Hall found a former state senator "B. Hall"), and so does another party:
    only the full name, or the first and last name, with no party against it, counts."""
    return match.method.startswith((FULL, FIRST_LAST)) and not (party and their_party and party != their_party)


async def cards(
    wd: Wikidata, races: list[Race], scopes: dict[str, OfficeScope], county: str | None, bp_ballot: BpBallot | None,
    ballotpedia: bool, state: str,
) -> CardSet:
    """A card for each candidate found among ``state``'s officeholders on Wikidata (only the
    matches trusted() keeps). ``ballotpedia``: Ballotpedia is on, so the card may link to it.
    Raises UpstreamError when the list can't be had; without the matched people's details, the
    cards keep the item's link and offices, with a warning."""
    out = CardSet()
    if state not in STATES:
        return out
    _, index, fetched_at = await wd.people(state)
    parties = {c.key: c.party for race in races for c in race.candidates}
    found = {
        key: (entry, match)
        for key, (entry, match) in match_entries(index, races, scopes, county, bp_ballot, source=LABEL, entry_id="qid",
                                                 seats_of=lambda entry: entry["seats"]).items()
        if trusted(match, parties.get(key), entry["party"])
    }
    if not found:
        return out
    try:
        details = await wd.details([entry["qid"] for entry, _ in found.values()])
    except UpstreamError as exc:
        details = {}
        log.warning("%s", exc)
        out.warnings.append("Wikidata isn't answering right now, so its profiles have no photos or links.")
    for key, (entry, match) in found.items():
        out.candidates[key] = card(entry["person"], match, details.get(entry["qid"]), fetched_at, ballotpedia)
    return out
