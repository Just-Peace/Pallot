"""What every state's key dates are made of: a Guide to how its calendar files word them and how
to vote there, the Counts of days its deadlines are set by, and the days its election law counts
from. Each state's own (its Guide, its rule and the law behind them) are in its module, beside
its adapter; key_dates.py gathers them."""

from __future__ import annotations

import datetime as dt
import functools
from dataclasses import dataclass
from typing import Callable

from ..models import VoterInfo, VoterLink
from ..sources.key_dates import Deadlines


@dataclass(frozen=True)
class Guide:
    """A state's wording for its key dates, and how to vote there. ``register``, ``mail`` and the
    like are sentences with an ``{election}`` ("the November 3, 2026 election") to fill in; the
    ``check_``, ``where_`` and ``mail_`` fields and ``poll_hours`` are what the ballot's "When to
    vote" shows (voter_info)."""

    name: str
    source: str  # who the dates are from, or who explains the rules they're worked out by
    url: str
    computed: bool  # worked out from the state's election law, not read from a published list
    registration_url: str  # how to register
    mail_url: str  # how to vote by mail
    register: str
    mail_summary: str
    mail: str  # up to the colon before mail_url
    early_where: str
    credit: str  # the calendar file's line before the url
    poll_hours: str  # "7 a.m. – 8 p.m."
    check_url: str  # where voters check their registration
    check_hint: str
    where_url: str  # where voters find where to vote
    where_hint: str
    mail_label: str  # the words of the link to mail_url
    mail_eligibility: str  # who can vote by mail, and how the ballot gets back
    mail_deadline: str | None = None  # the words before the mail_apply_by date, where they aren't the usual
    local_office: str | None = None  # who sets where and when you vote, where it isn't the county elections office
    polls_text: str | None = None  # Election Day's line in the calendar file, where it isn't the usual (polls)
    late_registration: str | None = None  # how to register once register_by is over, where the state allows it

    @property
    def polls(self) -> str:
        """Election Day's line: "Polls are open 7 a.m. to 8 p.m.; if you're in line at 8, you can vote."."""
        if self.polls_text:
            return self.polls_text
        opens, closes = self.poll_hours.split(" – ")
        return f"Polls are open {opens} to {closes}; if you're in line at {closes.removesuffix(' p.m.')}, you can vote."

    def voter_info(self) -> VoterInfo:
        return VoterInfo(
            registration=VoterLink(label="Am I registered?", short="Registered?", url=self.check_url, hint=self.check_hint),
            county_offices=VoterLink(label="Where to vote", short="Where", url=self.where_url, hint=self.where_hint),
            mail_apply=VoterLink(label=self.mail_label, url=self.mail_url),
            mail_eligibility=self.mail_eligibility,
            mail_deadline=self.mail_deadline,
            local_office=self.local_office,
            poll_hours=self.poll_hours,
            late_registration=VoterLink(label=self.late_registration, url=self.registration_url)
            if self.late_registration else None,
        )


def first_tuesday_after_first_monday(year: int, month: int) -> dt.date:
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(0 - first.weekday()) % 7 + 1)


@dataclass(frozen=True)
class Counts:
    """A state whose deadlines are each a fixed count of days before its general election (its
    module's docstring gives the law): None where there's no such date (no application to make,
    early voting through Election Day, or no early voting)."""

    register: int
    mail: int | None
    early_start: int | None
    early_end: int | None
    every_year: bool = False  # a general election every November, not only in even years

    def on(self, state: str, day: dt.date) -> Deadlines | None:
        """The dates of the general election on ``day``, or None when there's none."""
        if (day.year % 2 and not self.every_year) or day != first_tuesday_after_first_monday(day.year, 11):
            return None

        def before(days: int | None) -> dt.date | None:
            return None if days is None else day - dt.timedelta(days=days)

        return Deadlines(
            day, "General Election", register_by=before(self.register), mail_apply_by=before(self.mail),
            early_start=before(self.early_start), early_end=before(self.early_end), state=state,
        )

    def rule(self, state: str) -> Callable[[dt.date], Deadlines | None]:
        """``state``'s rule (key_dates.RULES): the dates of its general election on a day."""
        return functools.partial(self.on, state)


def columbus_day(year: int) -> dt.date:
    """The second Monday of October, a state holiday in Georgia and a legal holiday in Ohio."""
    first = dt.date(year, 10, 1)
    return first + dt.timedelta(days=(0 - first.weekday()) % 7 + 7)
