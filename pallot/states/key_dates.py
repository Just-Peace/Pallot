"""Each state's key dates: whose they are and how its calendar files word them, and, for a state
whose deadlines are fixed counts of days from Election Day, the dates worked out from that day
alone, with nothing fetched. Texas's come from its SOS's page (sources/key_dates.py) instead.

Michigan's rules, as its Department of State gives them: registration online or by mail closes
15 days before Election Day, then it's in person at the clerk's office with proof of residency
through Election Day (MCL 168.497); early voting runs at least from the second Saturday before
through the Sunday before (MCL 168.720a, from Proposal 2 of 2022); any voter can vote absentee,
applying online or by mail by 5 p.m. the Friday before. Only its even-year August primary and
November general are statewide, the elections those rules are for.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable

from ..sources import key_dates as texas
from ..sources.key_dates import Deadlines


@dataclass(frozen=True)
class Guide:
    """A state's wording for its key dates. ``register``, ``mail`` and the like are sentences
    with an ``{election}`` ("the November 3, 2026 election") to fill in."""

    name: str
    source: str  # who the dates are from, or who explains the rules they're worked out by
    url: str
    computed: bool  # worked out from the state's election law, not read from a published list
    registration_url: str
    mail_url: str
    register: str
    mail_summary: str
    mail: str  # up to the colon before mail_url
    early_where: str
    polls: str
    credit: str  # the calendar file's line before the url


TEXAS = Guide(
    name="Texas",
    source="Texas Secretary of State",
    url=texas.URL,
    computed=False,
    registration_url=texas.REGISTRATION_URL,
    mail_url=texas.MAIL_APPLY_URL,
    register="The last day to register to vote in {election} in Texas.",
    mail_summary="Mail-ballot application due",
    mail="If you vote by mail in {election}, your application must reach your county's early voting clerk today: "
         "received, not postmarked. Who can vote by mail, and how to apply:",
    early_where="Your county elections office lists the places and hours.",
    polls="Polls are open 7 a.m. to 7 p.m.; if you're in line at 7, you can vote.",
    credit="Dates from the Texas Secretary of State",
)

MICHIGAN = Guide(
    name="Michigan",
    source="Michigan Department of State",
    url="https://www.michigan.gov/sos/elections/voting",
    computed=True,
    registration_url="https://mvic.sos.state.mi.us/Voter/Index",
    mail_url="https://www.michigan.gov/sos/elections/voting/absentee-voting",
    register="The last day to register online or by mail for {election} in Michigan. After it, you can still "
             "register in person at your city or township clerk's office, with proof of residency, through Election "
             "Day.",
    mail_summary="Absentee application due",
    mail="If you vote absentee in {election}, an application made online or by mail must reach your city or township "
         "clerk by 5 p.m. today. In person, you can apply at the clerk's office until 4 p.m. the day before Election "
         "Day. Any voter can vote absentee; how to apply:",
    early_where="Your city or township clerk lists the places and hours, and may open early voting sooner.",
    polls="Polls are open 7 a.m. to 8 p.m.; if you're in line at 8, you can vote.",
    credit="Dates worked out from Michigan's election law; more from the Michigan Department of State",
)

GUIDES = {"TX": TEXAS, "MI": MICHIGAN}


def first_tuesday_after_first_monday(year: int, month: int) -> dt.date:
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(0 - first.weekday()) % 7 + 1)


def michigan(day: dt.date) -> Deadlines | None:
    """The dates of Michigan's statewide election on ``day``, or None when there's none."""
    if day.year % 2 or day.month not in (8, 11) or day != first_tuesday_after_first_monday(day.year, day.month):
        return None
    return Deadlines(
        day, "General Election" if day.month == 11 else "Primary Election",
        register_by=day - dt.timedelta(days=15),
        mail_apply_by=day - dt.timedelta(days=4),
        early_start=day - dt.timedelta(days=10),
        early_end=day - dt.timedelta(days=2),
        state="MI",
    )


RULES: dict[str, Callable[[dt.date], Deadlines | None]] = {"MI": michigan}


def computed(state: str | None, day: dt.date) -> Deadlines | None:
    """The state's key dates for the election on ``day``, when they're worked out by rule."""
    rule = RULES.get(state or "")
    return rule(day) if rule else None
