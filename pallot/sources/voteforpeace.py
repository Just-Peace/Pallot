"""Vote for Peace (voteforpeace.info) ratings, through the voteforpeace_cache package in this repo.

The package ships a snapshot of the site's All Candidates page. We copy it into
data/voteforpeace on first use, so lookups never call voteforpeace.info, and only fetch the
site when asked from the Settings page (the package's refresh() validates before writing and
writes only when the site changed). The site rates candidates at every level, from Congress to
a county's courts, so a race's seat is spelled the way the TEC's are (tec_seat, bp_seat), with
Congress as "TX-37" and county offices as the county, and the name is matched with the seat to
confirm it.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

import voteforpeace_cache
from voteforpeace_cache.models import SOURCE_URL

from ..matching import FIRST_LAST, FULL, INITIAL, NameIndex, match_person
from ..models import Badge, Fact, Link, Match, Race, SourceCard, Tone
from ..offices import OfficeScope
from ..text import display_date, display_time, web_url
from . import CardSet
from .ballotpedia import BpBallot
from .snapshot import BundledSnapshot, summary_of
from .tec import bp_seat, tec_seat

SOURCE = "voteforpeace"
LABEL = "Vote for Peace"
DESCRIPTION = (
    "Candidates rated Ally, Neutral or Opposed by Vote for Peace (voteforpeace.info, from Organize for Peace), "
    "on their stance on war, human rights and lobby money such as AIPAC's."
)
CANDIDATES_PAGE = SOURCE_URL
RATINGS = voteforpeace_cache.RATINGS  # "vote" -> "Ally"
FLAGS = {"vote": "ally", "reject": "opposed", "neutral": "neutral"}  # what Pick by rule tests
_TONES: dict[str, Tone] = {"vote": "good", "reject": "warn", "neutral": "info"}
_PARTIES = {"DEMOCRAT": "D", "DEMOCRATIC": "D", "REPUBLICAN": "R", "LIBERTARIAN": "L", "GREEN": "G", "INDEPENDENT": "I"}
_TITLE = re.compile(r"^(?:DR|MR|MRS|MS|HON)\.?\s+", re.IGNORECASE)
_STATEWIDE = (
    (r"^(?:LT\.?|LIEUTENANT) GOVERNOR\b", "LTGOVERNOR"),
    (r"^GOVERNOR\b", "GOVERNOR"),
    (r"\bATTORNEY GENERAL\b", "ATTYGEN"),
    (r"\bCOMPTROLLER\b", "COMPTROLLER"),
    (r"\bLAND COMMISSIONER\b", "LANDCOMM"),
    (r"\bAGRICULTURE COMMISSIONER\b", "AGRICULTUR"),
    (r"\bRAILROAD COMMISSIONER\b", "RRCOMM"),
)


def _num(text: str | None) -> int | None:
    found = re.search(r"\d+", text or "")
    return int(found.group()) if found else None


def entry_seats(entry: dict[str, Any]) -> set[str]:
    """The seats a Vote for Peace entry names, spelled as the ballot's races are: "U.S.
    Representative" and "37" is "TX-37", "TX State Senator" and "sd-9" is "STATESEN:9", "Harris
    District County Court Judge" and "228" is "JUDGEDIST:228", a county's office "COUNTY:HARRIS".
    The site names a court without its place ("TX Supreme Court Justice"), which is any place on
    that court: "JUSTICE_SC:*" (see _fit)."""
    state = entry.get("state") or ""
    office = re.sub(r"^(?:TX|TEXAS)\s+", "", " ".join((entry.get("office_title") or "").upper().split()))
    number = _num(entry.get("district"))
    seats: set[str] = set()
    if office.startswith("U.S. SENATOR"):
        seats.add(f"{state}-SEN")
    elif office.startswith("U.S. REPRESENTATIVE") and number is not None:
        seats.add(f"{state}-{number:02d}")
    elif re.search(r"\bSTATE REPRESENTATIVE\b", office) and number is not None:
        seats.add(f"STATEREP:{number}")
    elif re.search(r"\bSTATE SENATOR\b", office) and number is not None:
        seats.add(f"STATESEN:{number}")
    elif "BOARD OF EDUCATION" in office:
        seats.add(f"STATEEDU:{number}" if number is not None else "STATEEDU:*")
    elif "SUPREME COURT" in office:
        seats |= {"CHIEFJUSTICE_SC"} if "CHIEF" in office else {"JUSTICE_SC:*", "CHIEFJUSTICE_SC"}
    elif "COURT OF CRIMINAL APPEALS" in office:
        seats |= {"PRESIDINGJUDGE_COCA"} if "PRESIDING" in office else {"JUDGE_COCA:*", "PRESIDINGJUDGE_COCA"}
    elif "APPELLATE" in office or "COURT OF APPEALS" in office:
        if number is None:
            seats |= {"JUSTICE_COA:*", "CHIEFJUSTICE_COA:*"}
        else:
            seats |= {f"JUSTICE_COA:{number}:*", f"CHIEFJUSTICE_COA:{number}"}
    elif "DISTRICT" in office and ("JUDGE" in office or "COURT" in office) and number is not None:
        seats.add(f"JUDGEDIST:{number}")
    else:
        seats |= {code for pattern, code in _STATEWIDE if re.search(pattern, office)}
    if entry.get("level") in ("county", "local", "special_district") and entry.get("jurisdiction"):
        seats.add(f"COUNTY:{entry['jurisdiction'].upper()}")
    county = re.match(r"^(.+?) COUNTY\b", office)  # "Harris County Treasurer", which the site files as statewide
    if county and "DISTRICT" not in county.group(1) and entry.get("level") != "federal":
        seats.add(f"COUNTY:{county.group(1)}")
    return seats


def _fit(seats: set[str], seat: str | None) -> set[str]:
    """An entry's seats, with a court named without its place ("JUSTICE_SC:*") standing for
    the race's own place on that court."""
    return {seat if s.endswith("*") and seat and seat.startswith(s[:-1]) else s for s in seats}


def race_seat(race: Race, scope: OfficeScope | None, bp_race: Any, county: str | None) -> str | None:
    """The race's seat in entry_seats' spelling: Congress's own, a state office's as the TEC
    spells it, or else (a county, precinct or city office) the voter's county."""
    if race.seat:
        return race.seat
    seat = tec_seat(scope, county) if scope else bp_seat(bp_race, county) if bp_race else None
    if seat is None and race.group in ("county", "precinct", "local", "judicial") and county:
        return f"COUNTY:{county.upper()}"
    return seat


def party_code(entry: dict[str, Any]) -> str | None:
    return _PARTIES.get((entry.get("party") or "").upper())


def office_text(entry: dict[str, Any]) -> str:
    """ "U.S. Representative, District 37"."""
    office = entry.get("office_title") or "an office it doesn't name"
    number = _num(entry.get("district"))
    return f"{office}, District {number}" if number is not None else office


class VoteForPeace(BundledSnapshot):
    """The package's current.json: {"snapshot", "candidates": [...]}, a row per candidate."""

    EMPTY = {"snapshot": None, "candidates": []}
    LABEL = LABEL

    def __init__(
        self,
        data_dir: Path,
        *,
        refresh_fn: Callable[..., Any] | None = None,
        bundled_dir: Path | None = None,
    ):
        super().__init__(data_dir, voteforpeace_cache, refresh_fn=refresh_fn, bundled_dir=bundled_dir)

    def _discard(self) -> None:
        shutil.rmtree(self.data_dir, ignore_errors=True)  # refreshes add history files too

    async def _refresh(self) -> str:
        refresh = self._refresh_fn or voteforpeace_cache.refresh
        return summary_of(await asyncio.to_thread(refresh, data_dir=self.data_dir))

    def people(self, state: str | None = None) -> list[dict[str, Any]]:
        people = self.document().get("candidates", [])
        return [p for p in people if p.get("state") == state] if state else people

    def name_index(self, state: str) -> NameIndex:
        def build(document: dict[str, Any]) -> NameIndex:
            index = NameIndex()
            for person in document.get("candidates", []):
                if person.get("state") == state and person.get("name"):
                    index.add(_TITLE.sub("", person["name"]), person)
            return index

        return self._index(state, build)

    def snapshot_date(self) -> str | None:
        return self.meta().get("latest_snapshot")

    def details(self) -> list[Fact]:
        meta = self.meta()
        return [
            Fact(label="Snapshot", value=display_date(meta.get("latest_snapshot")) or "none"),
            Fact(label="Last changed", value=display_time(meta.get("last_refresh")) or "never"),
            Fact(label="Last checked", value=display_time(meta.get("last_checked")) or "never"),
            Fact(label="Texas candidates", value=f"{len(self.people('TX')):,}"),
            Fact(label="All candidates", value=f"{len(self.people()):,}"),
        ]


def card(person: dict[str, Any], match: Match, snapshot: str | None) -> SourceCard:
    rating = person.get("rating")
    label = RATINGS.get(rating or "", "Not rated")
    page = web_url(person.get("url")) or CANDIDATES_PAGE
    badges = [Badge(text=f"Vote for Peace: {label}", tone=_TONES.get(rating or "", "neutral"), url=page,
                    hint="How Vote for Peace rates them")]

    facts = [Fact(label="Rating", value=label), Fact(label="Office on Vote for Peace", value=office_text(person))]
    if person.get("party"):
        facts.append(Fact(label="Party on Vote for Peace", value=person["party"]))
    if person.get("election_label"):
        facts.append(Fact(label="Election", value=person["election_label"]))
    if person.get("election_result") not in (None, "pending"):
        facts.append(Fact(label="Result", value=person["election_result"].capitalize()))
    organizations = [e["organization"] for e in person.get("endorsements") or [] if e.get("organization")]
    if organizations:
        facts.append(Fact(label="Sources it cites", value=", ".join(organizations)))

    quotes = (person.get("notes") or "").splitlines()
    for article in person.get("articles") or []:
        title, url = article.get("title"), web_url(article.get("url"))
        head = f"[{title or url}]({url})" if url else title
        quotes.append(": ".join(filter(None, (head, article.get("description")))))

    links = []  # the candidate's page there is the card's own link
    for endorsement in person.get("endorsements") or []:
        if link := web_url(endorsement.get("link")):
            links.append(Link(label=f"{endorsement['organization']} (cited by Vote for Peace)", url=link))

    return SourceCard(
        source=SOURCE,
        label=LABEL,
        description=DESCRIPTION,
        url=page,
        as_of=snapshot,
        match=match,
        badges=badges,
        facts=facts,
        quotes=[quote for quote in quotes if quote],
        links=list({link.url: link for link in links}.values()),
        flags=[FLAGS[rating]] if rating in FLAGS else [],
    )


def cards(
    vfp: VoteForPeace,
    races: list[Race],
    scopes: dict[str, OfficeScope],
    county: str | None,
    bp_ballot: BpBallot | None = None,
) -> CardSet:
    """Cards for the candidates Vote for Peace rates in Texas, in any race. A race's seat comes
    from race_seat, so a name found for another seat or county is only "likely". One entry goes
    to one candidate in a race: "Kristen Hawkins" is also "K Hawkins", as Kyle Hawkins in the same
    race is, so the strongest match by name takes it, and a tie leaves it unmatched. A county seat
    is every office in the county, so there a last name alone ("Ebony Williams" for LaShawn
    Williams) isn't a match."""
    index = vfp.name_index("TX")
    snapshot = vfp.document().get("snapshot")
    bp_races = {f"bp:{r.id}": r for r in bp_ballot.races} if bp_ballot else {}
    out = CardSet()
    for race in races:
        seat = race_seat(race, scopes.get(race.key), bp_races.get(race.key), county)
        claims: dict[str, list[tuple[int, str, dict[str, Any], Match]]] = defaultdict(list)
        for candidate in race.candidates:
            found = match_person(
                index, candidate.name, candidate.party, seat,
                seats_of=lambda person: _fit(entry_seats(person), seat), party_of=party_code, source=LABEL,
                seat_text=office_text, name_of=lambda person: person.get("name"),
            )
            if found and not (_strength(found[1]) == _LAST_NAME and seat and seat.startswith("COUNTY:")):
                person, match = found
                claims[person["candidate_id"]].append((_strength(match), candidate.key, person, match))
        for claimed in claims.values():
            best = min(strength for strength, *_ in claimed)
            winners = [claim for claim in claimed if claim[0] == best]
            if len(winners) == 1:
                _, key, person, match = winners[0]
                out.candidates[key] = card(person, match, snapshot)
    return out


_RULES = (FULL, FIRST_LAST, INITIAL)
_LAST_NAME = len(_RULES)  # match_person's "last name, in the same seat"


def _strength(match: Match) -> int:
    """How closely the name matched: the full name first, a last name in the seat last."""
    return next((rank for rank, rule in enumerate(_RULES) if match.method.startswith(rule)), _LAST_NAME)
