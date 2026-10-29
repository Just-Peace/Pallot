"""Every state's key dates, by postal code: whose they are and how its calendar files word them
(GUIDES), and, for a state whose dates are worked out from its election law or entered by hand,
the rule that gives them (RULES), with nothing fetched. Each such state's Guide, rule and law
are in its own module, beside its adapter, and a new one adds a line to STATES. Texas's come
from its SOS's page (sources/key_dates.py) instead, and California's from its SOS's
(sources/ca_key_dates.py); their Guides are here."""

from __future__ import annotations

import datetime as dt
from types import ModuleType
from typing import Callable

from ..sources import ca_key_dates as california
from ..sources import key_dates as texas
from ..sources.key_dates import Deadlines
from . import ak, az, co, fl, ga, ia, il, in_, md, me, mi, mo, nc, ne, nj, nm, nv, ny, oh, pa, sc, va, wa, wi, wy
from .dates import Guide, columbus_day, first_tuesday_after_first_monday, mailed_to_every_voter, only_if

__all__ = ["GUIDES", "PAGES", "RULES", "STATES", "Guide", "columbus_day", "computed", "first_tuesday_after_first_monday"]

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
    credit="Dates from the Texas Secretary of State",
    poll_hours="7 a.m. – 7 p.m.",
    check_url=texas.REGISTRATION_URL,
    check_hint="My Voter Portal (Texas SOS): your registration, and your polling place once you log in",
    where_url="https://www.votetexas.gov/voting/where.html",
    where_hint="Every county's elections office (Texas SOS); yours publishes where and when you can vote",
    mail_label="How to apply",
    mail_eligibility=only_if("you're 65 or older", "sick or disabled",
                             "away from your county for all of early voting and Election Day",
                             "expecting to give birth around Election Day", "in jail but still eligible to vote"),
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
    early_where="Your county elections office takes ballots in person through Election Day; where your county has "
                "vote centers, they open at least 10 days before. Your county lists the places and hours.",
    credit="Dates from the California Secretary of State",
    poll_hours="7 a.m. – 8 p.m.",
    check_url=california.REGISTRATION_URL,
    check_hint="My Voter Status (California SOS): your registration, and where your mail ballot is",
    where_url=california.COUNTY_OFFICES_URL,
    where_hint="Every county's elections office (California SOS); yours lists its vote centers, polling places and drop "
               "boxes",
    mail_label="Voting by mail",
    mail_eligibility=mailed_to_every_voter("Mail it back postmarked by Election Day (it must reach your county within 7 "
                                           "days), or drop it off by 8 p.m. on Election Day."),
    mail_deadline="If yours is lost or damaged, the Secretary of State recommends asking your county for a new one by ",
    late_registration="After that, register and vote in person at your county elections office or a vote center "
                      "through Election Day",
)

STATES: dict[str, ModuleType] = {  # each module's GUIDE and RULE
    "MI": mi, "AZ": az, "NV": nv, "GA": ga, "WI": wi, "OH": oh, "IA": ia, "NJ": nj, "NY": ny, "CO": co, "WY": wy,
    "IL": il, "AK": ak, "FL": fl, "NC": nc, "PA": pa, "VA": va, "ME": me, "NE": ne, "NM": nm, "WA": wa,
    "IN": in_, "MD": md, "MO": mo, "SC": sc,
}
GUIDES: dict[str, Guide] = {
    "TX": TEXAS, "CA": CALIFORNIA, **{state: module.GUIDE for state, module in STATES.items()},
}
RULES: dict[str, Callable[[dt.date], Deadlines | None]] = {state: module.RULE for state, module in STATES.items()}
PAGES = {"TX": texas.SOURCE, "CA": california.SOURCE}  # the states whose dates are read from their office's page
MICHIGAN = mi.GUIDE


def computed(state: str | None, day: dt.date) -> Deadlines | None:
    """The state's key dates for the election on ``day``, when they're worked out by rule or entered by hand."""
    rule = RULES.get(state or "")
    return rule(day) if rule else None
