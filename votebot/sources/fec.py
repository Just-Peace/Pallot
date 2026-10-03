"""Federal Election Commission campaign finance, from the OpenFEC API (api.open.fec.gov).

One call per congressional race lists everyone who filed for that seat with their totals.
That is enough for the race's money comparison and works with the shared DEMO_KEY. With
a free key (VOTEBOT_FEC_API_KEY, from https://api.open.fec.gov/developers/), each candidate
on the ballot gets five more calls: where the money came from, donation sizes, donors'
states, donors' employers, and outside spending for and against. Everything goes through
HttpCache for a week; the key travels in a header that HttpCache never stores. A 429 (the
rate limit) pauses the FEC for an hour, serving only what's cached meanwhile.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import dataclass
from typing import Any, Callable

from ..config import DEMO_KEY, Ttls
from ..http_cache import Cached, HttpCache, RequestSpec, UpstreamError
from ..matching import NameIndex, last_first, match_person
from ..models import Badge, Breakdown, Comparison, Fact, Link, Match, Race, Share, SourceCard
from ..text import display_date, display_office, display_org, display_person, display_time, money, money_short
from . import CardSet, compare

SOURCE = "fec"
LABEL = "FEC"
DESCRIPTION = (
    "Money raised and spent by congressional campaigns, and outside spending for or against them, "
    "from reports filed with the Federal Election Commission."
)
API = "https://api.open.fec.gov/v1"
SITE = "https://www.fec.gov/data"
KEY_SIGNUP = "https://api.open.fec.gov/developers/"
HOUSE_DISCLOSURES = "https://disclosures-clerk.house.gov/FinancialDisclosure"
SENATE_DISCLOSURES = "https://efdsearch.senate.gov/search/"
KEY_NOTE = (
    "Federal races show FEC totals only. For where each candidate's money comes from, set VOTEBOT_FEC_API_KEY "
    f"to a [free key from the OpenFEC developers page]({KEY_SIGNUP}) and restart VoteBot."
)

_PARTIES = (("DEMOCRAT", "D"), ("REPUBLICAN", "R"), ("LIBERTARIAN", "L"), ("GREEN", "G"), ("INDEPENDENT", "I"))
_SIZES = {0: "$200 and under", 200: "$200.01–$499.99", 500: "$500–$999.99", 1000: "$1,000–$1,999.99", 2000: "$2,000 and over"}
# Employer answers that don't say who the donors work for.
_NOT_EMPLOYERS = {
    "", "NONE", "N/A", "NA", "NOT EMPLOYED", "UNEMPLOYED", "SELF", "SELF EMPLOYED", "SELF-EMPLOYED", "RETIRED",
    "HOMEMAKER", "STUDENT", "REQUESTED", "INFORMATION REQUESTED", "INFORMATION REQUESTED PER BEST EFFORTS",
    "NOT APPLICABLE", "NULL",
}


class FecUnavailable(Exception):
    """The FEC couldn't be asked (rate limit, refused key, down) and nothing was cached."""


def cycle_of(day: dt.date) -> int:
    """The FEC's two-year period, named for its even year: 2026 covers 2025–26."""
    return day.year + day.year % 2


def party_code(party_full: str | None) -> str | None:
    text = (party_full or "").upper()
    return next((code for word, code in _PARTIES if word in text), None)


def candidate_page(candidate_id: str, cycle: int) -> str:
    return f"{SITE}/candidate/{candidate_id}/?cycle={cycle}&election_full=true"


def race_page(seat: str, cycle: int) -> str:
    state, _, district = seat.partition("-")
    if district == "SEN":
        return f"{SITE}/elections/senate/{state}/{cycle}/"
    return f"{SITE}/elections/house/{state}/{int(district):02d}/{cycle}/"


def _campaigns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per campaign committee: the FEC sometimes lists a candidate twice, under two
    candidate IDs that share one committee and one set of totals."""
    seen: set[str] = set()
    out = []
    for row in rows:
        committee = row.get("candidate_pcc_id")
        if committee and committee in seen:
            continue
        seen.add(committee or "")
        out.append(row)
    return out


def _number(*values: Any) -> float | None:
    """The first value that is a number (the API sends null for "not reported")."""
    return next((float(v) for v in values if isinstance(v, (int, float))), None)


@dataclass
class Details:
    """A candidate's breakdown calls; a part is None when its call failed."""

    totals: dict[str, Any] | None = None
    sizes: list[dict[str, Any]] | None = None
    states: list[dict[str, Any]] | None = None
    outside: list[dict[str, Any]] | None = None
    employers: list[dict[str, Any]] | None = None


class Fec:
    def __init__(self, cache: HttpCache, ttl: Ttls, api_key: str, today: Callable[[], dt.date] = dt.date.today):
        self.cache = cache
        self.ttl = ttl
        self.keyed = bool(api_key) and api_key != DEMO_KEY
        self.today = today
        self._gate = asyncio.Semaphore(4)
        cache.pause_on(SOURCE, (429,), ttl.fec_backoff)

    def lifetime(self, day: dt.date | None) -> float:
        return self.ttl.past_election if day and day < self.today() else self.ttl.fec

    async def _get(self, path: str, params: dict[str, str], ttl: float) -> Cached:
        spec = RequestSpec("GET", f"{API}{path}", params=params)
        async with self._gate:
            try:
                return await self.cache.get_json(SOURCE, spec, ttl=ttl)
            except UpstreamError as exc:
                if exc.until:  # paused: nothing cached for this request
                    raise FecUnavailable(f"paused until {display_time(exc.until)} after reaching the FEC's rate limit") from exc
                if exc.status == 429:
                    raise FecUnavailable("reached the FEC's rate limit") from exc
                if exc.status == 403:
                    raise FecUnavailable("the FEC refused the API key; check VOTEBOT_FEC_API_KEY") from exc
                raise FecUnavailable(str(exc)) from exc

    async def race(self, seat: str, cycle: int, ttl: float) -> list[dict[str, Any]]:
        """Everyone who filed for this seat this cycle (primary losers too), with totals."""
        state, _, district = seat.partition("-")
        params = {"state": state, "cycle": str(cycle), "election_full": "true", "per_page": "100", "sort": "-total_receipts"}
        if district == "SEN":
            params["office"] = "senate"
        else:
            params.update(office="house", district=f"{int(district):02d}")
        got = await self._get("/elections/", params, ttl)
        return _campaigns(list((got.value or {}).get("results") or []))

    async def details(self, row: dict[str, Any], cycle: int, ttl: float) -> Details:
        candidate_id = row["candidate_id"]
        whole = {"cycle": str(cycle), "election_full": "true"}
        ranked = {**whole, "candidate_id": candidate_id, "per_page": "100", "sort": "-total"}
        calls = {
            "totals": self._get(f"/candidate/{candidate_id}/totals/", whole, ttl),
            "sizes": self._get("/schedules/schedule_a/by_size/by_candidate/", {**whole, "candidate_id": candidate_id}, ttl),
            "states": self._get("/schedules/schedule_a/by_state/by_candidate/", ranked, ttl),
            "outside": self._get("/schedules/schedule_e/by_candidate/", ranked, ttl),
        }
        if row.get("candidate_pcc_id"):
            calls["employers"] = self._get(
                "/schedules/schedule_a/by_employer/",
                {"committee_id": row["candidate_pcc_id"], "cycle": str(cycle), "per_page": "40", "sort": "-total"},
                ttl,
            )
        parts: dict[str, Any] = {}
        for name, got in zip(calls, await asyncio.gather(*calls.values(), return_exceptions=True)):
            if isinstance(got, FecUnavailable):
                continue  # that part is left out; the rest of the card still shows
            if isinstance(got, BaseException):
                raise got
            results = (got.value or {}).get("results") or []
            parts[name] = (results[0] if results else None) if name == "totals" else results
        return Details(**parts)


# -- cards ----------------------------------------------------------------------------


def period(seat: str, cycle: int) -> str:
    """What the FEC's election totals cover: six years for a Senate seat, two for the House."""
    return f"{cycle - (5 if seat.endswith('-SEN') else 1)}–{str(cycle)[2:]}"


def _where_from(totals: dict[str, Any], raised: float | None, span: str) -> Breakdown | None:
    if not totals or not raised:
        return None
    candidate = (_number(totals.get("candidate_contribution")) or 0) + (_number(totals.get("loans_made_by_candidate")) or 0)
    parts = [
        ("Individuals giving $200 or less", _number(totals.get("individual_unitemized_contributions"))),
        ("Individuals giving more than $200", _number(totals.get("individual_itemized_contributions"))),
        ("PACs and other committees", _number(totals.get("other_political_committee_contributions"))),
        ("Party committees", _number(totals.get("political_party_committee_contributions"))),
        ("The candidate (gifts and loans)", candidate),
        ("Transfers from joint fundraising and other campaign committees",
         _number(totals.get("transfers_from_other_authorized_committee"))),
    ]
    parts.append(("Other receipts (other loans, refunds, interest…)", raised - sum(amount or 0 for _, amount in parts)))
    return Breakdown(
        title="Where the money came from",
        parts=[Share(label=label, amount=round(amount, 2)) for label, amount in parts if amount and amount >= 1],
        total=raised,
        note=f"Everything the campaign reported receiving for this election ({span}).",
    )


def _sizes(rows: list[dict[str, Any]] | None) -> Breakdown | None:
    rows = sorted((r for r in rows or [] if _number(r.get("total"))), key=lambda r: r.get("size") or 0)
    if not rows:
        return None
    parts = [
        Share(label=_SIZES.get(r.get("size"), f"{money(r.get('size'))} and over"), amount=_number(r["total"]), count=r.get("count"))
        for r in rows
    ]
    return Breakdown(
        title="Donations by size",
        parts=parts,
        total=sum(p.amount or 0 for p in parts),
        note="Donations from individuals, each by its own amount. The smallest group includes the small donations "
        "campaigns don't itemize.",
    )


def _states(rows: list[dict[str, Any]] | None, home: str) -> Breakdown | None:
    rows = sorted((r for r in rows or [] if _number(r.get("total"))), key=lambda r: -_number(r["total"]))
    if not rows:
        return None
    local = next((r for r in rows if r.get("state") == home), None)
    others = [r for r in rows if r is not local]
    parts = [Share(label=local.get("state_full") or home, amount=_number(local["total"]), count=local.get("count"))] if local else []
    parts += [Share(label=r.get("state_full") or r.get("state") or "Unknown", amount=_number(r["total"])) for r in others[:3]]
    rest = sum(_number(r["total"]) or 0 for r in others[3:])
    if rest:
        parts.append(Share(label="Other states", amount=rest))
    return Breakdown(
        title="Where donors live",
        parts=parts,
        total=sum(_number(r["total"]) or 0 for r in rows),
        note="Itemized donations from individuals (over $200 in total from one donor), by the donor's state.",
    )


def _home_or_away(rows: list[dict[str, Any]] | None, home: str, home_name: str) -> Breakdown | None:
    """Donors in the candidate's own state and everywhere else: the same two parts for every
    candidate, where _states lists each one's own top states."""
    rows = [r for r in rows or [] if _number(r.get("total"))]
    if not rows:
        return None
    parts = []
    for label, group in ((home_name, [r for r in rows if r.get("state") == home]),
                         ("Other states", [r for r in rows if r.get("state") != home])):
        counts = [r["count"] for r in group if isinstance(r.get("count"), int)]
        parts.append(Share(label=label, amount=sum(_number(r["total"]) or 0 for r in group), count=sum(counts) if counts else None))
    return Breakdown(title="Where donors live", parts=parts, total=sum(p.amount or 0 for p in parts))


def _employers(rows: list[dict[str, Any]] | None, cycle: int) -> Breakdown | None:
    named = [r for r in rows or [] if (r.get("employer") or "").strip().upper() not in _NOT_EMPLOYERS and _number(r.get("total"))]
    if not named:
        return None
    return Breakdown(
        title="Top donors' employers",
        parts=[Share(label=display_org(r["employer"].strip()), amount=_number(r["total"]), count=r.get("count")) for r in named[:8]],
        note=f"Donations from individuals, grouped by the employer they listed ({cycle - 1}–{cycle}). "
        "These are employees' own donations, not the employers'.",
    )


_OUTSIDE_NOTE = (
    "None of this went to the campaign: groups it doesn't control spent it on their own ads, mail and so on, for or "
    "against this candidate (independent expenditures reported to the FEC)."
)
_OUTSIDE_HINT = "Spent by groups the campaign doesn't control, on their own ads and mail; none of it went to the campaign"


def _outside(rows: list[dict[str, Any]] | None) -> Breakdown | None:
    rows = sorted((r for r in rows or [] if _number(r.get("total"))), key=lambda r: -_number(r["total"]))
    if not rows:
        return None
    parts = []
    for r in rows[:10]:
        support = r.get("support_oppose_indicator") == "S"
        parts.append(Share(
            label=display_org(r.get("committee_name") or "Unnamed committee"),
            amount=_number(r["total"]),
            tag="for" if support else "against",
            tone="info" if support else "warn",
        ))
    return Breakdown(title="Outside spending", parts=parts, note=_OUTSIDE_NOTE)


def _for_against(rows: list[dict[str, Any]] | None) -> tuple[float, float]:
    """Outside spending in all: (for the candidate, against them)."""
    def total(side: str) -> float:
        return sum(_number(r.get("total")) or 0 for r in rows or [] if r.get("support_oppose_indicator") == side)
    return total("S"), total("O")


def _outside_badges(rows: list[dict[str, Any]] | None, url: str) -> list[Badge]:
    """One badge for outside spending for the candidate (blue), one for against (amber)."""
    support, oppose = _for_against(rows)
    return [
        Badge(text=f"Outside spending {side}: {money_short(amount)}", tone=tone, url=url, hint=_OUTSIDE_HINT)
        for side, amount, tone in (("for", support, "info"), ("against", oppose, "warn"))
        if amount
    ]


@dataclass
class Money:
    """A campaign's totals: from its totals call when there was one, else the race list's row."""

    raised: float | None
    spent: float | None
    cash: float | None
    debts: float | None
    through: str | None  # the end of the latest report

    @classmethod
    def of(cls, row: dict[str, Any], totals: dict[str, Any]) -> Money:
        return cls(
            raised=_number(totals.get("receipts"), row.get("total_receipts")),
            spent=_number(totals.get("disbursements"), row.get("total_disbursements")),
            cash=_number(totals.get("last_cash_on_hand_end_period"), row.get("cash_on_hand_end_period")),
            debts=_number(totals.get("last_debts_owed_by_committee")),
            through=(totals.get("coverage_end_date") or row.get("coverage_end_date") or "")[:10] or None,
        )


def card(row: dict[str, Any], match: Match | None, details: Details | None, *, seat: str, cycle: int) -> SourceCard:
    """One candidate's FEC card: the race list's totals, and with ``details`` the breakdowns."""
    details = details or Details()
    totals = details.totals or {}
    candidate_id = row["candidate_id"]
    page = candidate_page(candidate_id, cycle)
    campaign = Money.of(row, totals)
    raised, spent, cash, debts, through = campaign.raised, campaign.spent, campaign.cash, campaign.debts, campaign.through
    report = totals.get("last_report_type_full")
    committee, committee_id = row.get("candidate_pcc_name"), row.get("candidate_pcc_id")
    span = period(seat, cycle)

    badges = []
    if raised is not None:
        badges.append(Badge(
            text=f"FEC: raised {money_short(raised)}",
            url=page,
            hint=f"Raised by the campaign for the {cycle} election ({span})"
            + (f", from reports through {display_date(through)}" if through else ""),
        ))
    badges += _outside_badges(details.outside, page)

    facts = [
        Fact(label="Raised", value=money(raised) or ""),
        Fact(label="Spent", value=money(spent) or ""),
        Fact(label="Cash on hand", value=(money(cash) or "") + (f" on {display_date(through)}" if cash is not None and through else "")),
        Fact(label="Debts owed", value=money(debts) if debts else ""),
        Fact(label="Latest report", value=" ".join(x for x in (display_office(report or ""), str(totals.get("last_report_year") or "")) if x)),
        Fact(label="Campaign committee", value=display_org(committee) if committee else "",
             url=f"{SITE}/committee/{committee_id}/?cycle={cycle}" if committee_id else None),
        Fact(label="Running as", value=row.get("incumbent_challenge_full") or ""),
        Fact(label="FEC candidate ID", value=candidate_id, url=page),
    ]
    senate = seat.endswith("-SEN")
    links = [Link(label="FEC candidate page", url=page)]
    if committee_id:
        links.append(Link(label="The campaign's reports on the FEC site", url=f"{SITE}/committee/{committee_id}/?tab=filings"))
    links += [
        Link(label="This race on the FEC site", url=race_page(seat, cycle)),
        Link(label=f"Personal financial disclosures ({'Senate' if senate else 'House Clerk'})",
             url=SENATE_DISCLOSURES if senate else HOUSE_DISCLOSURES),
    ]
    breakdowns = [
        _where_from(totals, raised, span),
        _sizes(details.sizes),
        _states(details.states, seat.partition("-")[0]),
        _employers(details.employers, cycle),
        _outside(details.outside),
    ]
    return SourceCard(
        source=SOURCE,
        label=LABEL,
        description=DESCRIPTION,
        url=page,
        as_of=through,
        match=match,
        badges=badges,
        facts=[f for f in facts if f.value],
        breakdowns=[b for b in breakdowns if b],
        links=links,
    )


def comparison(race: Race, rows: dict[str, dict[str, Any]], cycle: int, details: dict[str, Details]) -> Comparison:
    """The race's candidates side by side (the Compare dialog). ``details`` is keyed by FEC
    candidate ID; without it (no API key) only the race list's totals compare."""
    seat = race.seat or ""
    home = seat.partition("-")[0]
    span = period(seat, cycle)
    keys = [c.key for c in race.candidates if c.key in rows]
    more = {key: details.get(rows[key]["candidate_id"]) or Details() for key in keys}
    money_of = {key: Money.of(rows[key], more[key].totals or {}) for key in keys}
    sides = {key: _for_against(more[key].outside) if more[key].outside is not None else (None, None) for key in keys}
    home_name = next((r["state_full"] for d in more.values() for r in d.states or []
                      if r.get("state") == home and r.get("state_full")), home)

    def each(value: Callable[[str], Any]) -> dict[str, Any]:
        return {key: value(key) for key in keys}

    sections = [
        compare.figures("Totals", [
            compare.row("Raised", each(lambda k: money_of[k].raised)),
            compare.row("Spent", each(lambda k: money_of[k].spent)),
            compare.row("Cash on hand", each(lambda k: money_of[k].cash)),
            compare.row("Debts owed", each(lambda k: money_of[k].debts)),
            compare.row("Outside spending for them", each(lambda k: sides[k][0])),
            compare.row("Outside spending against them", each(lambda k: sides[k][1])),
        ], note=f"For the {cycle} election ({span}); cash on hand and debts at each campaign's latest report."),
        compare.bars("Where the money came from",
                     each(lambda k: _where_from(more[k].totals or {}, money_of[k].raised, span))),
        compare.bars("Donations by size", each(lambda k: _sizes(more[k].sizes)),
                     note="Donations from individuals, each by its own amount. The smallest group includes the small "
                     "unitemized donations."),
        compare.bars("Where donors live", each(lambda k: _home_or_away(more[k].states, home, home_name)),
                     note="Itemized donations from individuals (over $200 in total from one donor), by the donor's state."),
        compare.columns("Top donors' employers", each(lambda k: compare.named(_employers(more[k].employers, cycle))),
                        note="Donations from individuals, grouped by the employer they listed; these are employees' own "
                        "donations, not the employers'."),
        compare.columns("Outside spending", each(lambda k: compare.named(_outside(more[k].outside))),
                        note="None of this went to the campaigns: groups they don't control spent it on their own ads, "
                        "mail and so on, for or against each candidate."),
    ]
    return Comparison(
        candidates=keys,
        as_of={key: money_of[key].through for key in keys if money_of[key].through},
        sections=[s for s in sections if s],
    )


def race_card(race: Race, rows: dict[str, dict[str, Any]], cycle: int, details: dict[str, Details] | None = None) -> SourceCard:
    """The race comparison: what each candidate on the ballot has raised, and (for Compare)
    everything else side by side."""
    through = max((row.get("coverage_end_date") or "")[:10] for row in rows.values()) or None
    parts = []
    for candidate in race.candidates:
        row = rows.get(candidate.key)
        if row is None:
            parts.append(Share(label=candidate.name, note="not found in FEC data", candidate_key=candidate.key))
            continue
        cash = _number(row.get("cash_on_hand_end_period"))
        note = f"{money_short(cash)} on hand" if cash is not None else None
        date = (row.get("coverage_end_date") or "")[:10]
        if note and date and date != through:
            note += f" on {display_date(date)}"
        parts.append(Share(label=candidate.name, amount=_number(row.get("total_receipts")), note=note, candidate_key=candidate.key))
    return SourceCard(
        source=SOURCE,
        label=LABEL,
        description="Money raised by each candidate's campaign, from reports filed with the FEC.",
        url=race_page(race.seat or "", cycle),
        as_of=through,
        breakdowns=[Breakdown(title=f"Money raised for the {cycle} election ({period(race.seat or '', cycle)})", parts=parts)],
        comparison=comparison(race, rows, cycle, details or {}),
    )


async def cards(fec: Fec, races: list[Race], day: dt.date | None) -> CardSet:
    """Cards for candidates in congressional races that the FEC lists for that seat, and a
    money comparison for each such race. Raises FecUnavailable if no race could be loaded."""
    federal = [race for race in races if race.seat]
    out = CardSet()
    if not federal:
        return out
    day = day or fec.today()
    cycle, ttl = cycle_of(day), fec.lifetime(day)
    seats = sorted({race.seat for race in federal if race.seat})
    lists: dict[str, list[dict[str, Any]]] = {}
    failures: list[FecUnavailable] = []
    for seat, got in zip(seats, await asyncio.gather(*(fec.race(s, cycle, ttl) for s in seats), return_exceptions=True)):
        if isinstance(got, FecUnavailable):
            failures.append(got)
        elif isinstance(got, BaseException):
            raise got
        else:
            lists[seat] = got
    if failures and not lists:
        raise failures[0]
    if failures:
        out.warnings.append(f"Some federal races have no FEC data ({failures[0]}).")

    matched: list[tuple[str, str, dict[str, Any], Match]] = []  # candidate key, seat, FEC row, match
    compared: list[tuple[Race, dict[str, dict[str, Any]]]] = []  # races with anyone found, and their rows
    for race in federal:
        rows = lists.get(race.seat or "")
        if not rows:
            continue
        index = NameIndex()
        for row in rows:
            if row.get("candidate_name") and row.get("candidate_id"):
                index.add(last_first(row["candidate_name"]), row)
        found_rows = {}
        for candidate in race.candidates:
            found = match_person(
                index, candidate.name, candidate.party, race.seat,
                seats_of=lambda _row, seat=race.seat: {seat},
                party_of=lambda row: party_code(row.get("party_full")),
                source="the FEC",
                name_of=lambda row: display_person(last_first(row["candidate_name"])),
            )
            if found:
                found_rows[candidate.key] = found[0]
                matched.append((candidate.key, race.seat or "", found[0], found[1]))
        if found_rows:
            compared.append((race, found_rows))

    details: dict[str, Details] = {}
    if fec.keyed and matched:
        wanted = {row["candidate_id"]: row for _, _, row, _ in matched}
        got = await asyncio.gather(*(fec.details(row, cycle, ttl) for row in wanted.values()))
        details = dict(zip(wanted, got))
    for race, found_rows in compared:
        out.races[race.key] = race_card(race, found_rows, cycle, details)
    for key, seat, row, match in matched:
        out.candidates[key] = card(row, match, details.get(row["candidate_id"]), seat=seat, cycle=cycle)
    if matched and not fec.keyed:
        out.notes.append(KEY_NOTE)
    return out
