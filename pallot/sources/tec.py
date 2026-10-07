"""Texas Ethics Commission (TEC) campaign finance, through the tec_cache package in this repo.

The package ships a snapshot built from TEC's nightly CSV export: for each state candidate
and officeholder, the totals of their regular reports since the last November general
election, their itemized donations broken down, and outside spending that named them. We
copy it into data/tec on first use, so ballot lookups never call TEC. pallot-cache's hard refresh
rebuilds it from TEC's zip in a separate process (a big download; see tec_cache), or from
a zip the voter downloaded into data/tec/TEC_CF_CSV.zip.

TEC covers state offices. County, precinct, city and school candidates file with their
county or city instead, so those races get nothing from here.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Any, Callable

import tec_cache
from tec_cache.models import SIZE_BUCKETS

from ..matching import NameIndex, full_key, match_person
from ..models import Badge, Breakdown, Comparison, Fact, Link, Match, Race, Share, SourceCard, Tone
from ..offices import OfficeScope
from ..text import display_date, display_office, display_org, display_time, money, money_short
from . import CardSet, compare
from .ballotpedia import BpBallot, BpRace
from .snapshot import BundledSnapshot, summary_of

SOURCE = "tec"
LABEL = "TEC"
DESCRIPTION = (
    "Money raised and spent by state candidates and officeholders, their largest donors, and outside spending "
    "naming them, from reports filed with the Texas Ethics Commission."
)
SEARCH = tec_cache.SEARCH_URL
PFS_INFO = "https://www.ethics.state.tx.us/resources/FAQs/FAQ_PFS.php"
LOCAL_ZIP = "TEC_CF_CSV.zip"
STATE_GROUPS = ("state", "legislature", "judicial")
# Answers that say nothing: left out of a donor's line ("Retired" as an occupation stays).
_NO_ANSWER = frozenset({"", "-", "N/A", "NA", "NONE", "NULL", "NOT APPLICABLE", "REQUESTED", "INFORMATION REQUESTED",
                        "INFORMATION REQUESTED PER BEST EFFORTS", "BEST EFFORTS"})
_NOT_EMPLOYERS = _NO_ANSWER | {"NOT EMPLOYED", "UNEMPLOYED", "RETIRED", "SELF", "SELF EMPLOYED", "SELF-EMPLOYED",
                               "HOMEMAKER", "STUDENT"}

_OFFICE_NAMES = {
    "STATEREP": "State Representative", "STATESEN": "State Senator", "STATEEDU": "State Board of Education",
    "GOVERNOR": "Governor", "LTGOVERNOR": "Lieutenant Governor", "ATTYGEN": "Attorney General",
    "COMPTROLLER": "Comptroller", "LANDCOMM": "Land Commissioner", "AGRICULTUR": "Agriculture Commissioner",
    "RRCOMM": "Railroad Commissioner", "RRCOMM_UNEXPIRED": "Railroad Commissioner (unexpired term)",
    "SOS": "Secretary of State", "JUSTICE_SC": "Supreme Court Justice", "CHIEFJUSTICE_SC": "Supreme Court Chief Justice",
    "JUDGE_COCA": "Court of Criminal Appeals Judge", "PRESIDINGJUDGE_COCA": "Court of Criminal Appeals Presiding Judge",
    "JUSTICE_COA": "Court of Appeals Justice", "CHIEFJUSTICE_COA": "Court of Appeals Chief Justice",
    "JUDGEDIST": "District Judge", "JUDGEDIST_MULTI": "District Judge", "JUDGEDIST_FAMILY": "Family District Judge",
    "JUDGE_BUS": "Business Court Judge", "CRIMINAL_JUDGEDIST": "Criminal District Judge",
    "DISTATTY": "District Attorney", "DISTATTY_MULTI": "District Attorney", "CRIMINAL_DISTATTY": "Criminal District Attorney",
    "JUDGESTATCO": "Statutory County Court Judge",
}
_DISTRICT_OFFICES = {"hd": "STATEREP", "sd": "STATESEN", "sboe": "STATEEDU"}
_STATEWIDE = (
    (r"^GOVERNOR$", "GOVERNOR"),
    (r"^LIEUTENANT GOVERNOR$", "LTGOVERNOR"),
    (r"^ATTORNEY GENERAL$", "ATTYGEN"),
    (r"^COMPTROLLER\b", "COMPTROLLER"),
    (r"GENERAL LAND OFFICE", "LANDCOMM"),
    (r"COMMISSIONER OF AGRICULTURE", "AGRICULTUR"),
    (r"^RAILROAD COMMISSIONER", "RRCOMM"),
    (r"^CHIEF JUSTICE,? SUPREME COURT", "CHIEFJUSTICE_SC"),
    (r"^PRESIDING JUDGE,? COURT OF CRIMINAL APPEALS", "PRESIDINGJUDGE_COCA"),
)


class TecRefreshError(Exception):
    """The refresh process failed; TEC's data in data/tec is unchanged."""


# -- seats: one spelling for TEC's offices and the ballot's races ------------------------


def _num(text: str | None) -> str:
    found = re.search(r"\d+", text or "")
    return str(int(found.group())) if found else ""


def seat_key(office: str | None, district: str | None = None, place: str | None = None, county: str | None = None) -> str | None:
    """TEC's office code and district/place as a seat, e.g. STATEREP + 49 -> "STATEREP:49"."""
    code = (office or "").upper()
    if code in ("STATEREP", "STATESEN", "STATEEDU", "DISTATTY", "DISTATTY_MULTI", "CHIEFJUSTICE_COA"):
        code = "DISTATTY" if code.startswith("DISTATTY") else code
        return f"{code}:{_num(district)}" if _num(district) else None
    if code in ("GOVERNOR", "LTGOVERNOR", "ATTYGEN", "COMPTROLLER", "LANDCOMM", "AGRICULTUR", "SOS",
                "CHIEFJUSTICE_SC", "PRESIDINGJUDGE_COCA"):
        return code
    if code.startswith("RRCOMM"):
        return "RRCOMM"
    if code in ("JUSTICE_SC", "JUDGE_COCA"):
        return f"{code}:{_num(place)}"
    if code == "JUSTICE_COA":
        return f"JUSTICE_COA:{_num(district)}:{_num(place)}"
    if code in ("JUDGEDIST", "JUDGEDIST_MULTI", "JUDGEDIST_FAMILY"):
        return f"JUDGEDIST:{_num(district)}" if _num(district) else None
    if code.startswith("CRIMINAL_JUDGEDIST"):
        return f"CRIMINAL_JUDGEDIST:{_num(district) or _num(place)}"
    if code in ("CRIMINAL_DISTATTY", "JUDGESTATCO"):
        return f"{code}:{(county or '').upper()}"
    return None


def tec_seat(scope: OfficeScope, county: str | None) -> str | None:
    """The seat of a Texas SOS race, spelled as seat_key spells TEC's offices; None for the
    offices TEC doesn't cover (county, precinct and local ones)."""
    if scope.kind in _DISTRICT_OFFICES:
        return f"{_DISTRICT_OFFICES[scope.kind]}:{scope.number}"
    name = scope.name.upper()
    for pattern, code in _STATEWIDE:
        if re.search(pattern, name):
            return code
    place = re.search(r"PLACE\s*(?:NO\.?\s*)?(\d+)", name)
    place_no = str(int(place.group(1))) if place else ""
    if re.match(r"^JUSTICE,? SUPREME COURT", name):
        return f"JUSTICE_SC:{place_no}"
    if re.match(r"^JUDGE,? COURT OF CRIMINAL APPEALS", name):
        return f"JUDGE_COCA:{place_no}"
    appeals = re.search(r"(\d+)(?:ST|ND|RD|TH)? (?:DISTRICT )?COURT OF APPEALS", name)
    if appeals:
        number = str(int(appeals.group(1)))
        return f"CHIEFJUSTICE_COA:{number}" if name.startswith("CHIEF JUSTICE") else f"JUSTICE_COA:{number}:{place_no}"
    district = re.search(r"(\d+)(?:ST|ND|RD|TH)? (?:JUDICIAL )?DISTRICT", name)
    if "CRIMINAL DISTRICT ATTORNEY" in name:
        return f"CRIMINAL_DISTATTY:{(county or '').upper()}"
    if "DISTRICT ATTORNEY" in name and district:
        return f"DISTATTY:{int(district.group(1))}"
    if "CRIMINAL DISTRICT COURT" in name or name.startswith("CRIMINAL DISTRICT JUDGE"):
        court = re.search(r"(?:NO\.?|COURT)\s*(\d+)", name)
        return f"CRIMINAL_JUDGEDIST:{int(court.group(1))}" if court else None
    if "DISTRICT JUDGE" in name and district:
        return f"JUDGEDIST:{int(district.group(1))}"
    return None  # county courts at law file with the county too (TEC's data has one such judge, ever)


_BP_LEGISLATURE = {"State Legislative (Lower)": "STATEREP", "State Legislative (Upper)": "STATESEN"}
_BP_STATEWIDE = (
    (r"^LIEUTENANT GOVERNOR\b", "LTGOVERNOR"),
    (r"^GOVERNOR\b", "GOVERNOR"),
    (r"^ATTORNEY GENERAL\b", "ATTYGEN"),
    (r"\bCOMPTROLLER\b", "COMPTROLLER"),
    (r"\bLAND COMMISSIONER\b|\bGENERAL LAND OFFICE\b", "LANDCOMM"),
    (r"\bAGRICULTURE\b", "AGRICULTUR"),
    (r"\bRAILROAD COMMISSION", "RRCOMM"),
    (r"\bSUPREME COURT\b.*\bCHIEF JUSTICE\b", "CHIEFJUSTICE_SC"),
    (r"\bCOURT OF CRIMINAL APPEALS\b.*\bPRESIDING JUDGE\b", "PRESIDINGJUDGE_COCA"),
)
_BP_COUNTY_COURT = re.compile(r"\bCOUNTY (?:CIVIL |CRIMINAL )?COURT\b|\bPROBATE COURT\b", re.IGNORECASE)
_ORDINALS = {word: n for n, word in enumerate(
    ("FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH", "EIGHTH", "NINTH", "TENTH", "ELEVENTH",
     "TWELFTH", "THIRTEENTH", "FOURTEENTH", "FIFTEENTH"), start=1)}


def bp_seat(race: BpRace, county: str | None) -> str | None:
    """The seat of a Ballotpedia race (for ballots without Texas SOS), spelled as seat_key
    spells TEC's offices: "Texas House of Representatives District 49" -> "STATEREP:49",
    "Texas Third District Court of Appeals Chief Justice" -> "CHIEFJUSTICE_COA:3". None for
    what TEC doesn't cover, or can't be told."""
    if race.district_type in _BP_LEGISLATURE:
        number = _num(race.district_name)
        return f"{_BP_LEGISLATURE[race.district_type]}:{number}" if number else None
    name = re.sub(r"^TEXAS\s+|\s+OF TEXAS$", "", " ".join(race.office.upper().split()))
    if "STATE BOARD OF EDUCATION" in name:
        return f"STATEEDU:{_num(name)}" if _num(name) else None
    for pattern, code in _BP_STATEWIDE:
        if re.search(pattern, name):
            return code
    place = re.search(r"\bPLACE (\d+)", name)
    place_no = str(int(place.group(1))) if place else ""
    if name.startswith("SUPREME COURT"):
        return f"JUSTICE_SC:{place_no}" if place_no else None
    if name.startswith("COURT OF CRIMINAL APPEALS"):
        return f"JUDGE_COCA:{place_no}" if place_no else None
    appeals = re.search(r"\b(\w+) (?:DISTRICT )?COURT OF APPEALS\b", name)
    if appeals:
        word = appeals.group(1)
        number = _ORDINALS.get(word) or (int(_num(word)) if _num(word) else None)
        if number is None:
            return None
        if "CHIEF JUSTICE" in name:
            return f"CHIEFJUSTICE_COA:{number}"
        return f"JUSTICE_COA:{number}:{place_no}" if place_no else None
    if "CRIMINAL DISTRICT ATTORNEY" in name:
        return f"CRIMINAL_DISTATTY:{(county or '').upper()}" if county else None
    district = re.search(r"\b(\d+)(?:ST|ND|RD|TH)? (?:JUDICIAL )?DISTRICT\b", name)
    if district and "DISTRICT ATTORNEY" in name:
        return f"DISTATTY:{int(district.group(1))}"
    if district and name.endswith("DISTRICT COURT") and "CRIMINAL" not in name:
        return f"JUDGEDIST:{int(district.group(1))}"
    return None


def _seats(entry: dict[str, Any]) -> set[str]:
    seats = set()
    for side in ("seek", "hold"):
        office = entry.get(side) or {}
        seat = seat_key(office.get("office"), office.get("district"), office.get("place"), office.get("county"))
        if seat:
            seats.add(seat)
    return seats


def office_text(office: dict[str, Any] | None) -> str:
    """ "State Representative, District 49"."""
    if not office or not office.get("office") or office["office"] in ("NONE", "OTHER"):
        return (office or {}).get("descr", "")
    parts = [_OFFICE_NAMES.get(office["office"], display_office(office["office"].replace("_", " ")))]
    if office.get("district"):
        parts.append(f"District {office['district']}")
    if office.get("place"):
        parts.append(f"Place {office['place']}")
    if office.get("county"):
        parts.append(f"{display_office(office['county'].upper())} County")
    return ", ".join(parts)


# -- the snapshot -------------------------------------------------------------------------


class Tec(BundledSnapshot):
    """The snapshot: {"snapshot", "window", "filers", "outside", ...}."""

    EMPTY = {"snapshot": None, "filers": [], "outside": []}
    LABEL = "Texas Ethics Commission"

    def __init__(
        self,
        data_dir: Path,
        *,
        refresh_fn: Callable[..., Any] | None = None,
        bundled_dir: Path | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(data_dir, tec_cache, refresh_fn=refresh_fn, bundled_dir=bundled_dir)
        self._user_agent = user_agent

    @property
    def local_zip(self) -> Path:
        return self.data_dir / LOCAL_ZIP

    def _discard(self) -> None:
        for path in (self.current_path, self.meta_path):  # a zip the voter downloaded into data/tec stays
            path.unlink(missing_ok=True)

    async def _refresh(self) -> str:
        """From TEC's zip (or the voter's downloaded copy), in a separate process, since it
        reads a couple of GB of CSV."""
        zip_path = self.local_zip if self.local_zip.exists() else None
        if self._refresh_fn is not None:
            return summary_of(await asyncio.to_thread(self._refresh_fn, data_dir=self.data_dir, zip_path=zip_path))
        return await self._run_refresh(zip_path)

    async def _run_refresh(self, zip_path: Path | None) -> str:
        args = [sys.executable, "-m", "tec_cache", "refresh", "--data-dir", str(self.data_dir)]
        if zip_path:
            args += ["--zip", str(zip_path)]
        if self._user_agent:
            args += ["--user-agent", self._user_agent]
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await process.communicate()
        if process.returncode != 0:
            detail = err.decode("utf-8", "replace").strip().removeprefix("error: ")
            raise TecRefreshError(detail or f"tec_cache exited with code {process.returncode}")
        return out.decode("utf-8", "replace").strip()

    def notice(self) -> tuple[str, Tone] | None:
        """A failed refresh, or how old the snapshot is."""
        if failed := super().notice():
            return failed
        document = self.document()
        if not document.get("snapshot"):
            return "No snapshot yet: refresh to download one from the Texas Ethics Commission.", "warn"
        since = display_date((document.get("window") or {}).get("start"))
        return f"Snapshot of {display_date(self.snapshot_date())}: money raised since {since}.", "info"

    def details(self) -> list[Fact]:
        document, meta = self.document(), self.meta()
        return [
            Fact(label="Snapshot", value=display_date(self.snapshot_date()) or "none"),
            Fact(label="Money raised since", value=display_date((document.get("window") or {}).get("start")) or "unknown"),
            Fact(label="TEC data from", value=display_time(document.get("tec_updated")) or "unknown"),
            Fact(label="Last checked", value=display_time(meta.get("last_checked")) or "never"),
            Fact(label="Candidates and officeholders", value=f"{len(document.get('filers') or []):,}"),
        ]

    def name_index(self) -> NameIndex:
        return self._index("filers", lambda document: _people_index(document.get("filers") or []))

    def outside_index(self) -> NameIndex:
        return self._index("outside", lambda document: _people_index(document.get("outside") or []))


def _people_index(entries: list[dict[str, Any]]) -> NameIndex:
    index = NameIndex()
    for entry in entries:
        first, last = entry.get("first") or "", entry.get("last") or ""
        if not last:
            continue
        index.add(f"{first} {last}", entry)
        if entry.get("short"):
            index.add(f"{entry['short']} {last}", entry)  # the nickname they go by
    return index


# -- cards ----------------------------------------------------------------------------------


def _since(window: str | None) -> str:
    return display_date(window) or "the last general election"


def _place(city: str | None, state: str | None) -> str:
    city = display_office(city.upper()) if city and city.isupper() else (city or "")
    return ", ".join(part for part in (city, state) if part)


def _where_from(filer: dict[str, Any], raised: float) -> Breakdown | None:
    if not raised:
        return None
    kinds = filer.get("by_kind") or {}
    individuals, groups = kinds.get("INDIVIDUAL") or {}, kinds.get("ENTITY") or {}
    parts = [
        ("Small donations (unitemized)", (filer.get("totals") or {}).get("unitemized"), None),
        ("Individuals", individuals.get("amount"), individuals.get("count")),
        ("PACs, businesses and other groups", groups.get("amount"), groups.get("count")),
    ]
    other = raised - sum(amount or 0 for _, amount, _ in parts)
    if other >= 1:
        parts.append(("Other contributions", other, None))
    return Breakdown(
        title="Where the money came from",
        parts=[Share(label=label, amount=amount, count=count) for label, amount, count in parts if amount and amount >= 1],
        total=raised,
    )


def _answer(text: str | None, non_answers: frozenset[str]) -> str:
    text = (text or "").strip()
    return "" if text.upper().rstrip(".") in non_answers else text


def _donor(donor: dict[str, Any]) -> Share:
    employer = _answer(donor.get("employer"), _NOT_EMPLOYERS)
    occupation = _answer(donor.get("occupation"), _NO_ANSWER)
    work = f"{employer} ({occupation})" if employer and occupation else employer or occupation
    details = [_place(donor.get("city"), donor.get("state")), display_org(work) if work.isupper() else work]
    return Share(
        label=display_org(donor.get("name") or "Unknown") if (donor.get("name") or "").isupper() else donor.get("name") or "Unknown",
        amount=donor.get("amount"),
        count=donor.get("count"),
        note=" · ".join(d for d in details if d) or None,
    )


def _largest(filer: dict[str, Any]) -> Breakdown | None:
    donors = filer.get("top_donors") or []
    if not donors:
        return None
    return Breakdown(
        title="Largest donors",
        parts=[_donor(d) for d in donors],
        note="Itemized donations, added up by donor name and state. Texas has no contribution limits for most state offices.",
    )


def _sizes(filer: dict[str, Any]) -> Breakdown | None:
    sizes = filer.get("sizes") or []
    parts = [Share(label=label, amount=size.get("amount"), count=size.get("count"))
             for (_, label), size in zip(SIZE_BUCKETS, sizes) if size.get("amount")]
    if not parts:
        return None
    unitemized = (filer.get("totals") or {}).get("unitemized")
    return Breakdown(
        title="Itemized donations by size",
        parts=parts,
        total=sum(p.amount or 0 for p in parts),
        note="Each itemized donation by its own amount." + (f" Small unitemized donations add {money(unitemized)} more." if unitemized else ""),
    )


def _states(filer: dict[str, Any]) -> Breakdown | None:
    places, counts = filer.get("by_state") or {}, filer.get("by_state_count") or {}  # older snapshots have no counts
    parts = [Share(label=label, amount=places.get(key), count=counts.get(key)) for key, label in
             (("TX", "Texas"), ("other", "Other states"), ("unknown", "No address given")) if places.get(key)]
    if not parts:
        return None
    return Breakdown(title="Where donors live", parts=parts, total=sum(p.amount or 0 for p in parts),
                     note="Itemized donations, by the donor's address.")


def _spender(spender: dict[str, Any]) -> Share:
    name = spender["name"]
    return Share(label=display_org(name) if name.isupper() else name, amount=spender.get("amount"), count=spender.get("count"))


def _outside(entry: dict[str, Any] | None) -> Breakdown | None:
    spenders = (entry or {}).get("spenders") or []
    if not spenders:
        return None
    return Breakdown(
        title="Outside spending naming this candidate",
        parts=[_spender(s) for s in spenders],
        note="Direct campaign expenditures that groups reported to the TEC as made for this candidate's race. "
        "The TEC doesn't record whether they supported or opposed the candidate.",
    )


def card(filer: dict[str, Any], match: Match | None, outside: dict[str, Any] | None, *, window: str | None) -> SourceCard:
    totals = filer.get("totals") or {}
    raised = totals.get("raised") or 0.0
    since = _since(window)
    latest = totals.get("latest") or {}
    badges = [Badge(
        text=f"TEC: raised {money_short(raised)}",
        url=SEARCH,
        hint=f"Raised since {since}, from reports to the Texas Ethics Commission (filer ID {filer['id']})",
    )]
    if outside and outside.get("total"):
        badges.append(Badge(
            text=f"Outside spending: {money_short(outside['total'])}",
            tone="info",
            url=SEARCH,
            hint="Direct campaign expenditures by others naming this candidate; the TEC doesn't record whether for or against",
        ))
    report = ""
    if latest:
        report = (latest.get("name") or "").capitalize()
        if latest.get("period_end"):
            report += f", through {display_date(latest['period_end'])}"
        if latest.get("filed"):
            report += f" (filed {display_date(latest['filed'])})"
    seeking, holding = office_text(filer.get("seek")), office_text(filer.get("hold"))
    facts = [
        Fact(label="Raised", value=money(raised) or ""),
        Fact(label="Spent", value=money(totals.get("spent")) or ""),
        Fact(label="Cash on hand", value=(money(totals.get("cash")) or "")
             + (f" on {display_date(totals['as_of'])}" if totals.get("as_of") and totals.get("cash") is not None else "")),
        Fact(label="Outstanding loans", value=money(totals.get("loans")) if totals.get("loans") else ""),
        Fact(label="Latest report", value=report),
        Fact(label="Reports counted", value=f"{totals.get('reports', 0)} since {since}"),
        Fact(label="Running for", value=seeking),
        Fact(label="Holds", value=holding if holding != seeking else ""),
        Fact(label="TEC filer ID", value=filer["id"], url=SEARCH),
    ]
    breakdowns = [_where_from(filer, raised), _largest(filer), _sizes(filer), _states(filer), _outside(outside)]
    return SourceCard(
        source=SOURCE,
        kind="money",
        label=LABEL,
        description=DESCRIPTION,
        url=SEARCH,
        as_of=totals.get("as_of"),
        match=match,
        badges=badges,
        facts=[f for f in facts if f.value],
        breakdowns=[b for b in breakdowns if b],
        links=[
            Link(label="Texas Ethics Commission campaign finance search", url=SEARCH),
            Link(label="Personal financial statements (not online; the TEC explains how to request one)", url=PFS_INFO),
        ],
        figures={key: value for key, value in (("raised", raised), ("spent", totals.get("spent")), ("cash", totals.get("cash")))
                 if value is not None},
    )


def _donor_name(donor: dict[str, Any]) -> str:
    """Who a donor is across candidates' lists: the TEC's donors are added up by name and
    state, so two Pat Smiths in different states stay apart."""
    return f"{full_key(donor.get('name') or '')}|{(donor.get('state') or '').upper()}"


def comparison(race: Race, filers: dict[str, dict[str, Any]], outside: dict[str, dict[str, Any]], window: str | None) -> Comparison:
    """The race's candidates side by side (the Compare dialog): totals, the categories their
    money splits into, and their largest donors and outside spenders in columns."""
    keys = [c.key for c in race.candidates if c.key in filers]
    totals = {key: filers[key].get("totals") or {} for key in keys}
    sizes = {key: filers[key].get("sizes") or [] for key in keys}
    spenders = {key: (outside.get(key) or {}).get("spenders") or [] for key in keys}

    def each(value: Callable[[str], Any]) -> dict[str, Any]:
        return {key: value(key) for key in keys}

    sections = [
        compare.figures("Totals", [
            compare.row("Raised", each(lambda k: totals[k].get("raised"))),
            compare.row("Spent", each(lambda k: totals[k].get("spent"))),
            compare.row("Cash on hand", each(lambda k: totals[k].get("cash"))),
            compare.row("Outstanding loans", each(lambda k: totals[k].get("loans"))),
            compare.row("Itemized donations", each(lambda k: sum(s.get("amount") or 0 for s in sizes[k])),
                        each(lambda k: sum(s.get("count") or 0 for s in sizes[k]))),
            compare.row("Outside spending naming them", each(lambda k: (outside.get(k) or {}).get("total") or 0.0),
                        each(lambda k: (outside.get(k) or {}).get("count", 0 if k not in outside else None)),
                        counted="expenditure"),  # older snapshots have no count
        ], note=f"Raised, spent and itemized donations since {_since(window)}; cash on hand and loans at each "
           "candidate's latest report. Outside spending is what groups reported spending in the candidate's race."),
        compare.bars("Where the money came from", each(lambda k: _where_from(filers[k], totals[k].get("raised") or 0.0))),
        compare.bars("Itemized donations by size", each(lambda k: _sizes(filers[k])),
                     note="Each itemized donation by its own amount; small unitemized donations aren't listed one by one."),
        compare.bars("Where donors live", each(lambda k: _states(filers[k])), note="Itemized donations, by the donor's address."),
        compare.columns("Largest donors", each(lambda k: [(_donor(d), _donor_name(d)) for d in filers[k].get("top_donors") or []]),
                        note="Each candidate's largest itemized donors, added up by donor name and state."),
        compare.columns("Outside spending naming them", each(lambda k: [(_spender(s), full_key(s["name"])) for s in spenders[k]]),
                        note="The TEC doesn't record whether the spending supported or opposed the candidate.",
                        counted="expenditure"),
    ]
    return Comparison(
        candidates=keys,
        as_of={key: totals[key]["as_of"] for key in keys if totals[key].get("as_of")},
        sections=[s for s in sections if s],
    )


def race_card(
    race: Race, filers: dict[str, dict[str, Any]], window: str | None, outside: dict[str, dict[str, Any]] | None = None
) -> SourceCard:
    """The race comparison: what each candidate on the ballot has raised since the window
    start, and (for Compare) everything else side by side."""
    through = max(((f.get("totals") or {}).get("as_of") or "") for f in filers.values()) or None
    parts = []
    for candidate in race.candidates:
        filer = filers.get(candidate.key)
        if filer is None:
            parts.append(Share(label=candidate.name, note="not found in TEC data", candidate_key=candidate.key))
            continue
        totals = filer.get("totals") or {}
        cash = totals.get("cash")
        parts.append(Share(
            label=candidate.name,
            amount=totals.get("raised"),
            note=f"{money_short(cash)} on hand" if cash is not None else None,
            candidate_key=candidate.key,
        ))
    return SourceCard(
        source=SOURCE,
        kind="money",
        label=LABEL,
        description="Money raised by each candidate, from reports filed with the Texas Ethics Commission.",
        url=SEARCH,
        as_of=through,
        breakdowns=[Breakdown(title=f"Money raised since {_since(window)}", parts=parts)],
        comparison=comparison(race, filers, outside or {}, window),
    )


def cards(
    tec: Tec, races: list[Race], scopes: dict[str, OfficeScope], county: str | None, bp_ballot: BpBallot | None = None
) -> CardSet:
    """Cards for candidates in state races (statewide, legislature, SBOE, appellate and
    district courts, DAs) found in the snapshot, and a money comparison for each such race.
    A race's seat comes from its Texas SOS office (``scopes``), or else from Ballotpedia's.
    Ballotpedia lists county and probate courts as judicial districts, but their judges file
    with the county, so those races are left out as the SOS's county courts are."""
    document = tec.document()
    out = CardSet()
    if not document.get("filers"):
        return out
    window = (document.get("window") or {}).get("start")
    filers, spending = tec.name_index(), tec.outside_index()
    bp_races = {f"bp:{r.id}": r for r in bp_ballot.races} if bp_ballot else {}
    for race in races:
        scope, bp_race = scopes.get(race.key), bp_races.get(race.key)
        seat = tec_seat(scope, county) if scope else bp_seat(bp_race, county) if bp_race else None
        local = race.group not in STATE_GROUPS or bool(bp_race and _BP_COUNTY_COURT.search(bp_race.office))
        if race.group == "federal" or (seat is None and local):
            continue
        found_rows: dict[str, dict[str, Any]] = {}
        found_outside: dict[str, dict[str, Any]] = {}
        for candidate in race.candidates:
            found = match_person(
                filers, candidate.name, None, seat,
                seats_of=_seats, source="the TEC", seat_text=lambda f: office_text(f.get("seek") or f.get("hold")),
                name_of=lambda f: f.get("name"),
            )
            if not found:
                continue
            outside = match_person(spending, candidate.name, None, seat, seats_of=_seats)
            out.candidates[candidate.key] = card(found[0], found[1], outside[0] if outside else None, window=window)
            found_rows[candidate.key] = found[0]
            if outside:
                found_outside[candidate.key] = outside[0]
        if found_rows:
            out.races[race.key] = race_card(race, found_rows, window, found_outside)
    return out
