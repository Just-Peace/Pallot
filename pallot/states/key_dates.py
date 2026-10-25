"""Each state's key dates: whose they are and how its calendar files word them, and, for a state
whose deadlines are fixed counts of days from Election Day, the dates worked out from that day
alone, with nothing fetched. Texas's come from its SOS's page (sources/key_dates.py) instead, and
California's from its SOS's (sources/ca_key_dates.py).
Arizona's are entered by hand from its Secretary of State's list, whose site blocks scripts.

Michigan's rules, as its Department of State gives them: registration online or by mail closes
15 days before Election Day, then it's in person at the clerk's office with proof of residency
through Election Day (MCL 168.497); early voting runs at least from the second Saturday before
through the Sunday before (MCL 168.720a, from Proposal 2 of 2022); any voter can vote absentee,
applying online or by mail by 5 p.m. the Friday before. Only its even-year August primary and
November general are statewide, the elections those rules are for.

Nevada's, for its general election (NRS 293.12755: the first Tuesday after the first Monday of
November in an even year): registration by mail or in person at the county clerk's closes the
fourth Tuesday before, online on Election Day itself (NRS 293.560), and in person at a polling
place it goes on through Election Day (NRS 293.5772 to 293.5887); every active voter is mailed a
ballot, and so is anyone who registers or updates their registration by 14 days before
(NRS 293.269911); early voting runs from the third Saturday before through the Friday before
(NRS 293.3568); a mailed ballot must be postmarked by Election Day and reach the clerk by 5 p.m.
on the fourth day after (NRS 293.269921); polls are open 7 a.m. to 7 p.m. (NRS 293.273).

Georgia's, for its general election (O.C.G.A. 21-2-9: the first Tuesday after the first Monday of
November in an even year): registration closes the fifth Monday before (21-2-224); any voter can
vote absentee, applying by the eleventh day before (21-2-381(a)(1)(A)), and the ballot must reach
the county's registrars by 7 p.m. on Election Day (21-2-386); advance voting runs weekdays from the
fourth Monday before through the Friday before, and on the second and third Saturdays before
(21-2-385(d)(1)), but not on an observed state holiday, so it starts the next day when that
Monday is Columbus Day; polls are open 7 a.m. to 7 p.m. (21-2-403).

Ohio's, for its general election (ORC 3501.01(A): the first Tuesday after the first Monday of
November), checked on codes.ohio.gov on 2026-10-22: registration closes the thirtieth day before
(3503.19), always a Sunday, so the next day that's neither a Sunday nor a legal holiday (1.14,
whose holidays include Columbus Day); early voting in person runs from the day after through 5 p.m.
on the Sunday before (3509.051); any voter can vote absentee, applying by the close of business on
the seventh day before (3509.03(D)), and since SB 293 (effective March 20, 2026) the ballot must
reach the county board by the close of the polls on Election Day (3509.05(D)), except a military or
overseas voter's, counted through the fourth day after (3511.11); polls are open 6:30 a.m. to 7:30
p.m. (3501.32). There's no registration on Election Day.

Wisconsin's, for its general election (Wis. Stat. 5.02(5): the Tuesday after the first Monday of
November in an even year): registration by mail or online closes the third Wednesday before
(6.28(1)), then it's in person at the municipal clerk's office until 5 p.m. the Friday before
(6.29(2)(a)), or at the polling place on Election Day (6.55(2)); any voter can vote absentee,
asking by mail or online by 5 p.m. the fifth day before, or in person at the clerk's office from
the fourteenth day before through the Sunday before (6.86(1)(b)), and the ballot must reach the
polling place by 8 p.m. on Election Day (6.87(6)); polls are open 7 a.m. to 8 p.m. (6.78(1m)).

New York's, for its general election (Election Law 8-100(1)(c): the Tuesday after the first Monday
of November, every year), checked on nysenate.gov on 2026-10-24: a registration must reach the
county board by the tenth day before (5-210(3)); early voting runs from the tenth day before
through the second day before (8-600(1)); an absentee or early mail ballot application online or
by mail must reach the board by the tenth day before, in person by the day before (8-400); a
mailed ballot must be postmarked by Election Day and reach the board within seven days after
(8-412); polls are open 6 a.m. to 9 p.m. (8-100(2)).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable

from ..sources import ca_key_dates as california
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

CALIFORNIA = Guide(
    name="California",
    source="California Secretary of State",
    url=california.URL,
    computed=False,
    registration_url=california.REGISTRATION_URL,
    mail_url=california.MAIL_URL,
    register="The last day to register online or by mail (postmarked today) for {election} in California. After it, "
             "you can still register and vote at your county elections office or a vote center, through Election "
             "Day.",
    mail_summary="Ask for a replacement mail ballot",
    mail="Every active voter in California is mailed a ballot for {election}. If yours is lost or damaged, today is "
         "the Secretary of State's recommended last day to ask your county elections office for a new one:",
    early_where="Your county elections office lists the places and hours.",
    polls="Polls are open 7 a.m. to 8 p.m.; if you're in line at 8, you can vote.",
    credit="Dates from the California Secretary of State",
)

ARIZONA = Guide(
    name="Arizona",
    source="Arizona Secretary of State",
    url="https://azsos.gov/elections",
    computed=False,
    registration_url="https://my.arizona.vote/",
    mail_url="https://my.arizona.vote/",
    register="The last day to register to vote in {election} in Arizona, by 11:59 p.m.",
    mail_summary="Early ballot request due",
    mail="If you vote early by mail in {election}, ask your county recorder for your ballot in time for it to reach "
         "you and come back by Election Day. Any voter can vote early by mail; how to ask:",
    early_where="Your county recorder lists the places and hours.",
    polls="Polls are open 6 a.m. to 7 p.m.; if you're in line at 7, you can vote.",
    credit="Dates from the Arizona Secretary of State",
)

NEVADA = Guide(
    name="Nevada",
    source="Nevada Secretary of State",
    url="https://www.nvsos.gov/sos/elections",
    computed=True,
    registration_url="https://registertovote.nv.gov/",
    mail_url="https://www.nvsos.gov/sos/elections",
    register="The last day to register by mail or in person at your county clerk's office for {election} in Nevada. "
             "After it, you can still register online through Election Day, or in person at a polling place during "
             "early voting or on Election Day.",
    mail_summary="Last day to register and still be mailed a ballot",
    mail="Every active voter in Nevada is mailed a ballot for {election}. Register or update your registration by "
         "today to still be mailed one. Mailed back, it must be postmarked by Election Day and reach your county "
         "clerk by 5 p.m. on the fourth day after; or drop it off at any polling place or drop box by 7 p.m. on "
         "Election Day. More:",
    early_where="Your county clerk lists the places and hours.",
    polls="Polls are open 7 a.m. to 7 p.m.; if you're in line at 7, you can vote.",
    credit="Dates worked out from Nevada's election law; more from the Nevada Secretary of State",
)

GEORGIA = Guide(
    name="Georgia",
    source="Georgia Secretary of State",
    url="https://sos.ga.gov/elections",
    computed=True,
    registration_url="https://mvp.sos.ga.gov/s/",
    mail_url="https://securemyabsenteeballot.sos.ga.gov/s/",
    register="The last day to register to vote in {election} in Georgia.",
    mail_summary="Absentee ballot application due",
    mail="If you vote absentee in {election}, your application must reach your county's board of registrars today. "
         "Your ballot must reach them by 7 p.m. on Election Day; one that arrives later isn't counted. Any voter can "
         "vote absentee; how to apply:",
    early_where="Your county's board of registrars lists the places and hours. Early voting is on weekdays, and on "
                "the second and third Saturdays before Election Day; some counties also open on Sundays.",
    polls="Polls are open 7 a.m. to 7 p.m.; if you're in line at 7, you can vote.",
    credit="Dates worked out from Georgia's election law; more from the Georgia Secretary of State",
)

OHIO = Guide(
    name="Ohio",
    source="Ohio Secretary of State",
    url="https://www.ohiosos.gov/elections/",
    computed=True,
    registration_url="https://olvr.ohiosos.gov/",
    mail_url="https://www.ohiosos.gov/elections/request-an-absentee-ballot",
    register="The last day to register to vote in {election} in Ohio. There's no registration on Election Day.",
    mail_summary="Absentee ballot application due",
    mail="If you vote absentee in {election}, your application must reach your county board of elections by the "
         "close of business today. Your ballot must reach the board by 7:30 p.m. on Election Day; one that arrives "
         "later isn't counted, even if it was mailed in time. Any voter can vote absentee; how to apply:",
    early_where="Your county board of elections lists the place and hours. Early voting ends at 5 p.m. on the Sunday "
                "before Election Day.",
    polls="Polls are open 6:30 a.m. to 7:30 p.m.; if you're in line at 7:30, you can vote.",
    credit="Dates worked out from Ohio's election law; more from the Ohio Secretary of State",
)

WISCONSIN = Guide(
    name="Wisconsin",
    source="Wisconsin Elections Commission",
    url="https://elections.wi.gov/",
    computed=True,
    registration_url="https://myvote.wi.gov/",
    mail_url="https://myvote.wi.gov/",
    register="The last day to register online or by mail for {election} in Wisconsin. After it, you can still "
             "register in person at your municipal clerk's office until 5 p.m. on the Friday before, or at your "
             "polling place on Election Day, with proof of residence.",
    mail_summary="Absentee ballot request due",
    mail="If you vote absentee in {election}, a request made online or by mail must reach your municipal clerk by "
         "5 p.m. today. Your ballot must reach your polling place or clerk by 8 p.m. on Election Day; one that "
         "arrives later isn't counted. Any voter can vote absentee; how to ask:",
    early_where="Your municipal clerk sets the places and hours, and may start later than the first day allowed.",
    polls="Polls are open 7 a.m. to 8 p.m.; if you're in line at 8, you can vote.",
    credit="Dates worked out from Wisconsin's election law; more from the Wisconsin Elections Commission",
)

NEW_YORK = Guide(
    name="New York",
    source="New York State Board of Elections",
    url="https://elections.ny.gov/",
    computed=True,
    registration_url="https://elections.ny.gov/register-vote",
    mail_url="https://absenteeballot.elections.ny.gov/",
    register="The last day for your registration to reach your county board of elections for {election} in New York.",
    mail_summary="Early mail or absentee ballot application due",
    mail="If you vote by mail in {election}, an application made online or by mail must reach your county board of "
         "elections today; in person, you can apply until the day before Election Day. Your ballot must be "
         "postmarked by Election Day and reach the board within 7 days after. Any voter can vote early by mail; "
         "how to apply:",
    early_where="Your county board of elections sets the places and hours.",
    polls="Polls are open 6 a.m. to 9 p.m.; if you're in line at 9, you can vote.",
    credit="Dates worked out from New York's Election Law; more from the New York State Board of Elections",
)

GUIDES = {
    "TX": TEXAS, "MI": MICHIGAN, "CA": CALIFORNIA, "AZ": ARIZONA, "NV": NEVADA, "GA": GEORGIA, "WI": WISCONSIN,
    "OH": OHIO, "NY": NEW_YORK,
}


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


ARIZONA_DATES = {
    dt.date(2026, 11, 3): Deadlines(
        dt.date(2026, 11, 3), "General Election", register_by=dt.date(2026, 10, 5),
        early_start=dt.date(2026, 10, 7), state="AZ",
    ),
}


def arizona(day: dt.date) -> Deadlines | None:
    """The dates of Arizona's statewide election on ``day``, as its Secretary of State lists them."""
    return ARIZONA_DATES.get(day)


def nevada(day: dt.date) -> Deadlines | None:
    """The dates of Nevada's general election on ``day``, or None when there's none: register by
    mail or in person the fourth Tuesday before, still be mailed a ballot 14 days before, early
    voting the third Saturday before through the Friday before."""
    if day.year % 2 or day != first_tuesday_after_first_monday(day.year, 11):
        return None
    return Deadlines(
        day, "General Election",
        register_by=day - dt.timedelta(days=28),
        mail_apply_by=day - dt.timedelta(days=14),
        early_start=day - dt.timedelta(days=17),
        early_end=day - dt.timedelta(days=4),
        state="NV",
    )


def columbus_day(year: int) -> dt.date:
    """The second Monday of October, a state holiday in Georgia and a legal holiday in Ohio."""
    first = dt.date(year, 10, 1)
    return first + dt.timedelta(days=(0 - first.weekday()) % 7 + 7)


def georgia(day: dt.date) -> Deadlines | None:
    """The dates of Georgia's general election on ``day``, or None when there's none: register by
    the fifth Monday before, apply to vote absentee by the eleventh day before, early voting the
    fourth Monday before (the Tuesday when that's Columbus Day) through the Friday before."""
    if day.year % 2 or day != first_tuesday_after_first_monday(day.year, 11):
        return None
    early = day - dt.timedelta(days=22)
    if early == columbus_day(day.year):
        early += dt.timedelta(days=1)
    return Deadlines(
        day, "General Election",
        register_by=day - dt.timedelta(days=29),
        mail_apply_by=day - dt.timedelta(days=11),
        early_start=early,
        early_end=day - dt.timedelta(days=4),
        state="GA",
    )


def ohio(day: dt.date) -> Deadlines | None:
    """The dates of Ohio's general election on ``day``, or None when there's none: register by
    the thirtieth day before, moved past a Sunday or Columbus Day, early voting from the day after
    through the Sunday before, apply to vote absentee by the seventh day before."""
    if day != first_tuesday_after_first_monday(day.year, 11):
        return None
    register = day - dt.timedelta(days=30)
    while register.weekday() == 6 or register == columbus_day(day.year):
        register += dt.timedelta(days=1)
    return Deadlines(
        day, "General Election",
        register_by=register,
        mail_apply_by=day - dt.timedelta(days=7),
        early_start=register + dt.timedelta(days=1),
        early_end=day - dt.timedelta(days=2),
        state="OH",
    )


def wisconsin(day: dt.date) -> Deadlines | None:
    """The dates of Wisconsin's general election on ``day``, or None when there's none: register
    online or by mail by the third Wednesday before, ask for an absentee ballot by the fifth day
    before, vote absentee in person from the fourteenth day before through the Sunday before."""
    if day.year % 2 or day != first_tuesday_after_first_monday(day.year, 11):
        return None
    return Deadlines(
        day, "General Election",
        register_by=day - dt.timedelta(days=20),
        mail_apply_by=day - dt.timedelta(days=5),
        early_start=day - dt.timedelta(days=14),
        early_end=day - dt.timedelta(days=2),
        state="WI",
    )


def new_york(day: dt.date) -> Deadlines | None:
    """The dates of New York's general election on ``day``, or None when there's none: register and
    apply to vote by mail by the tenth day before, early voting the tenth day before through the
    second day before."""
    if day != first_tuesday_after_first_monday(day.year, 11):
        return None
    return Deadlines(
        day, "General Election",
        register_by=day - dt.timedelta(days=10),
        mail_apply_by=day - dt.timedelta(days=10),
        early_start=day - dt.timedelta(days=10),
        early_end=day - dt.timedelta(days=2),
        state="NY",
    )


RULES: dict[str, Callable[[dt.date], Deadlines | None]] = {
    "MI": michigan, "AZ": arizona, "NV": nevada, "GA": georgia, "WI": wisconsin, "OH": ohio, "NY": new_york,
}


def computed(state: str | None, day: dt.date) -> Deadlines | None:
    """The state's key dates for the election on ``day``, when they're worked out by rule or entered by hand."""
    rule = RULES.get(state or "")
    return rule(day) if rule else None
