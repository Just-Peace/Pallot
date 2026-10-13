"""Profiles and photos of Texas officeholders from Wikidata (CC0), through its public query service.

Two SPARQL queries, both through HttpCache: PEOPLE, every living person who holds or held a
Texas office (a seat whose district is in Texas, or an office whose jurisdiction is Texas), one
answer for the whole state and bundled with Pallot; then DETAILS, for only the people matched on
this ballot (their description, photo, birth date, party, website, Wikipedia article and
Ballotpedia page). Nothing about the voter is sent, only Wikidata's own item ids. Matching is by
name with the seat to corroborate (seats.match_entries); Wikidata often leaves a Texas House
member's district out, so that office counts as any district's seat. A photo is used only on an
exact match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from ..config import Ttls
from ..http_cache import HttpCache, RequestSpec, UpstreamError
from ..matching import NameIndex
from ..models import Badge, Fact, Link, Match, Race, SourceCard
from ..offices import OfficeScope
from ..text import display_date, display_time, iso_utc
from . import CardSet
from .ballotpedia import BpBallot
from .seats import match_entries

SOURCE = "wikidata"
LABEL = "Wikidata"
DESCRIPTION = (
    "Profiles of Texas officeholders, past and present, from Wikidata, the free knowledge base behind Wikipedia: "
    "a photo, the offices they've held, and links to their Wikidata item, Wikipedia article and website. "
    "Pallot fetches the whole list of Texas officeholders, so nothing about you is sent."
)
ENDPOINT = "https://query.wikidata.org/sparql"
ITEM = "https://www.wikidata.org/wiki/"
REFUSALS = (403, 429)  # answers that pause it for Ttls.wikidata_backoff
CHUNK = 50  # people per DETAILS query, which keeps its URL short
PHOTO_WIDTH = 300
PEOPLE = """SELECT DISTINCT ?p ?label ?pos ?posL ?dL ?start ?end ?party WHERE {
  { ?p p:P39 ?st . ?st pq:P768 ?d0 . ?d0 wdt:P131 wd:Q1439 . }
  UNION { ?p p:P39 ?st . ?st pq:P768 wd:Q1439 . }
  UNION { ?p p:P39 ?st . ?st ps:P39 ?pos0 . ?pos0 wdt:P1001 wd:Q1439 . }
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
DETAILS = """SELECT ?p ?desc ?img ?born ?site ?bp ?article ?partyL WHERE {
  VALUES ?p { %s }
  OPTIONAL { ?p schema:description ?desc . FILTER(LANG(?desc) = "en") }
  OPTIONAL { ?p wdt:P18 ?img }
  OPTIONAL { ?p wdt:P569 ?born }
  OPTIONAL { ?p wdt:P856 ?site }
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
PARTIES = {"Q29552": "D", "Q29468": "R", "Q558334": "L"}
_QID = re.compile(r"^Q\d+$")
_CONGRESS = re.compile(r"^Texas's (\d+)(?:st|nd|rd|th) congressional district$")


class WikidataUnavailable(Exception):
    """The list of Texas officeholders couldn't be fetched (refused, paused, down) and none was cached."""


@dataclass
class Held:
    office: str  # Wikidata's label: "United States representative"
    district: str | None  # "Texas's 35th congressional district"
    start: str | None  # ISO dates
    end: str | None

    def text(self, capital: bool = True) -> str:
        """ "Member of the Texas House of Representatives (2018–)"; uncapitalized, as Wikidata
        labels it, inside a sentence."""
        years = "–".join([(self.start or "")[:4], (self.end or "")[:4]]) if self.start or self.end else ""
        where = f", {self.district}" if self.district and self.district != "Texas" else ""
        office = f"{self.office[:1].upper()}{self.office[1:]}" if capital else self.office
        return f"{office}{where}" + (f" ({years})" if years else "")


@dataclass
class Person:
    qid: str
    name: str
    party: str | None = None  # D, R or L, when Wikidata gives one party
    seats: set[str] = field(default_factory=set)
    held: list[Held] = field(default_factory=list)  # the Texas offices, latest first

    def entry(self) -> dict[str, Any]:
        """The shape seats.match_entries reads: ``office_title`` words the latest office for a match's notes."""
        return {"qid": self.qid, "name": self.name, "party": self.party, "seats": self.seats,
                "office_title": self.held[0].text(capital=False) if self.held else None, "person": self}


@dataclass
class Details:
    description: str | None = None
    photo: str | None = None
    born: str | None = None
    party: str | None = None
    article: str | None = None
    ballotpedia: str | None = None
    websites: list[str] = field(default_factory=list)


def _value(row: dict[str, Any], name: str) -> str | None:
    return (row.get(name) or {}).get("value") or None


def _qid(url: str | None) -> str | None:
    tail = (url or "").rsplit("/", 1)[-1]
    return tail if _QID.match(tail) else None


def _number(text: str | None) -> int | None:
    found = re.search(r"\b(\d+)\b", text or "")
    return int(found.group(1)) if found else None


def seat_of(position: str, district: str | None) -> str | None:
    """The seat an office held is, as the ballot's races spell it, or None for an office Pallot has no race for."""
    if position == US_HOUSE:
        found = _CONGRESS.match(district or "")
        return f"TX-{int(found.group(1)):02d}" if found else None
    if position == US_SENATE:
        return "TX-SEN" if "Texas" in (district or "") else None
    if position in (STATE_HOUSE, STATE_SENATE):
        chamber = "STATEREP" if position == STATE_HOUSE else "STATESEN"
        number = _number(district) if district and "istrict" in district else None
        return f"{chamber}:{number}" if number else f"{chamber}:*"
    if position == SPEAKER:
        return "STATEREP:*"
    return STATEWIDE.get(position)


def people_from(answer: dict[str, Any]) -> list[Person]:
    """PEOPLE's rows (one per office held, and per party) folded into one Person each."""
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
        position, district = _qid(_value(row, "pos")), _value(row, "dL")
        if position and (seat := seat_of(position, district)):
            person.seats.add(seat)
        office = Held(_value(row, "posL") or "", district, (_value(row, "start") or "")[:10] or None,
                      (_value(row, "end") or "")[:10] or None)
        if office.office:
            held.setdefault(qid, {})[(office.office, office.district, office.start, office.end)] = office
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
        if site and site.startswith(("http://", "https://")) and site not in found.websites:
            found.websites.append(site)
    return out


def photo_url(image: str | None) -> str | None:
    """A Commons file (Special:FilePath) at the width the page shows, over https."""
    if not image or "/Special:FilePath/" not in image:
        return None
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{image.split('/Special:FilePath/', 1)[1]}?width={PHOTO_WIDTH}"


def people_spec() -> RequestSpec:
    return RequestSpec("GET", ENDPOINT, params={"query": PEOPLE, "format": "json"},
                       headers={"Accept": "application/sparql-results+json"})


def details_spec(qids: list[str]) -> RequestSpec:
    values = " ".join(f"wd:{qid}" for qid in qids)
    return RequestSpec("GET", ENDPOINT, params={"query": DETAILS % values, "format": "json"},
                       headers={"Accept": "application/sparql-results+json"})


class Wikidata:
    def __init__(self, cache: HttpCache, ttl: Ttls):
        self.cache = cache
        self.ttl = ttl
        self._parsed: tuple[float, list[Person], NameIndex] | None = None
        cache.pause_on(SOURCE, REFUSALS, ttl.wikidata_backoff)

    async def _get(self, spec: RequestSpec) -> Any:
        try:
            return await self.cache.get_json(SOURCE, spec, ttl=self.ttl.wikidata)
        except UpstreamError as exc:
            if exc.until:
                raise WikidataUnavailable(f"paused until {display_time(exc.until)} after Wikidata refused a request") from exc
            raise WikidataUnavailable(str(exc).removeprefix(f"{SOURCE}: ")) from exc

    async def people(self) -> tuple[list[Person], NameIndex, float]:
        """Every Texas officeholder Wikidata has, indexed by name, read once per stored copy."""
        got = await self._get(people_spec())
        if self._parsed is None or self._parsed[0] != got.fetched_at:
            people = people_from(got.value or {})
            index = NameIndex()
            for person in people:
                index.add(person.name, person.entry())
            self._parsed = (got.fetched_at, people, index)
        return self._parsed[1], self._parsed[2], got.fetched_at

    async def details(self, qids: list[str]) -> dict[str, Details]:
        out: dict[str, Details] = {}
        ordered = sorted(set(qids), key=lambda q: int(q[1:]))
        for start in range(0, len(ordered), CHUNK):
            got = await self._get(details_spec(ordered[start:start + CHUNK]))
            out.update(details_from(got.value or {}))
        return out


def card(person: Person, match: Match, found: Details | None, fetched_at: float) -> SourceCard:
    item = f"{ITEM}{person.qid}"
    found = found or Details()
    facts = [
        Fact(label="Description", value=found.description or ""),
        Fact(label="Born", value=display_date(found.born) or ""),
        Fact(label="Party", value=found.party or ""),
        Fact(label="Texas offices held", value="; ".join(h.text() for h in person.held)),
    ]
    links = [Link(label="Wikidata item", url=item)]
    if found.article:
        links.append(Link(label="Wikipedia article", url=found.article))
    links += [Link(label="Official website", url=site) for site in found.websites]
    if found.ballotpedia:
        links.append(Link(label="Ballotpedia", url=f"https://ballotpedia.org/{quote(found.ballotpedia)}"))
    return SourceCard(
        source=SOURCE,
        kind="profile",
        label=LABEL,
        description=DESCRIPTION,
        url=item,
        image=found.photo if match.confidence == "exact" else None,
        as_of=iso_utc(fetched_at),
        match=match,
        badges=[Badge(text="Wikidata", tone="info", url=item)],
        facts=[f for f in facts if f.value],
        links=links,
    )


async def cards(
    wd: Wikidata, races: list[Race], scopes: dict[str, OfficeScope], county: str | None, bp_ballot: BpBallot | None,
) -> CardSet:
    """A card for each candidate found among Texas's officeholders on Wikidata. Raises
    WikidataUnavailable when the list can't be had; without the matched people's details, the cards
    keep the item's link and offices, with a warning."""
    _, index, fetched_at = await wd.people()
    found = match_entries(index, races, scopes, county, bp_ballot, source=LABEL, entry_id="qid",
                          seats_of=lambda entry: entry["seats"])
    out = CardSet()
    if not found:
        return out
    try:
        details = await wd.details([entry["qid"] for entry, _ in found.values()])
    except WikidataUnavailable as exc:
        details = {}
        out.warnings.append(f"Wikidata profiles are missing their photos and links ({exc}).")
    for key, (entry, match) in found.items():
        out.candidates[key] = card(entry["person"], match, details.get(entry["qid"]), fetched_at)
    return out
