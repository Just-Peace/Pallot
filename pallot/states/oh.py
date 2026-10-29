"""Ohio: its statewide races for a general election, transcribed by hand from the Secretary of
State's official sample ballot (the 2026 one is Directive 2026-45) into manual/state_oh/ohio.json.

Ohio has no statewide list of candidates: its 88 county boards of elections certify them, and
ohiosos.gov answers scripts with Cloudflare's challenge, so Pallot never asks it. The file holds
only the races every Ohio voter has (Governor and Lieutenant Governor as a ticket, the other
statewide offices, the Supreme Court and the U.S. Senate), says so in its ``scope``, and is refused
when it says anything else. The U.S. House race comes from the FEC's filers instead (ballot.py),
and the Legislature's and the county's races aren't shown.

Ohio's key dates, for its general election (ORC 3501.01(A): the first Tuesday after the first Monday
of November), checked on codes.ohio.gov on 2026-10-22: registration closes the thirtieth day before
(3503.19), always a Sunday, so the next day that's neither a Sunday nor a legal holiday (1.14, whose
holidays include Columbus Day); early voting in person runs from the day after through 5 p.m. on the
Sunday before (3509.051); any voter can vote absentee, applying by the close of business on the
seventh day before (3509.03(D)), and since SB 293 (effective March 20, 2026) the ballot must reach
the county board by the close of the polls on Election Day (3509.05(D)), except a military or
overseas voter's, counted through the fourth day after (3511.11); polls are open 6:30 a.m. to 7:30
p.m. (3501.32). There's no registration on Election Day.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
from typing import Any

from ..sources.key_dates import Deadlines
from ..text import display_person
from . import Filing, ManualList, Office, party, us_senate
from .dates import Guide, columbus_day, first_tuesday_after_first_monday

PAGE = "https://www.ohiosos.gov/assets/dir2026-45-official-sample-ballot-november-3-2026.pdf"
SCOPE = "statewide_offices_only"
_PARTY_NAMES = {"OTHER-PARTY CANDIDATE": "Other party"}  # the ballot's label for a party Ohio doesn't recognize
_OFFICES = (
    (r"Governor", "GOVERNOR", "state", "Governor and Lieutenant Governor"),
    (r"Attorney General", "ATTORNEY GENERAL", "state", "Attorney General"),
    (r"Auditor", "AUDITOR OF STATE", "state", "Auditor of State"),
    (r"Secretary of State", "SECRETARY OF STATE", "state", "Secretary of State"),
    (r"Treasurer", "TREASURER OF STATE", "state", "Treasurer of State"),
    (r"Chief Justice", "CHIEF JUSTICE", "judicial", "Chief Justice of the Supreme Court"),
    (r"Justice", "SUPREME COURT", "judicial", "Justice of the Supreme Court"),
)


def _office(text: str) -> Office:
    """A contest's office, statewide; an office it doesn't know keeps its own name."""
    if re.match(r"U\.?\s*S\.?\s*Senat", text, re.I):
        return us_senate("OH")
    for pattern, race, group, shown in _OFFICES:
        if re.match(pattern, text, re.I):
            return Office(race, shown, race, group, "state")
    upper = " ".join(text.upper().split())
    return Office(upper, " ".join(text.split()), upper, "state", "state")


def _term(contest: dict[str, Any]) -> str | None:
    """When a contest's term begins, from its ``term`` ("Full term commencing 2027-01-01"), to tell
    apart two races for the same office: "January 1, 2027"."""
    found = re.search(r"commencing\s+(\d{4}-\d{2}-\d{2})", str(contest.get("term") or ""), re.I)
    if not found:
        return None
    day = dt.date.fromisoformat(found.group(1))
    return f"{day:%B} {day.day}, {day.year}"


class OhList(ManualList):
    state = "OH"
    source = "state_oh"
    label = "Ohio Secretary of State"
    page = PAGE
    description = ("Ohio's statewide races (Governor, the other statewide offices, the Supreme Court and the U.S. "
                   "Senate), transcribed by hand from its Secretary of State's official sample ballot.")
    folder = "manual/state_oh"
    challenge = ("Just a moment...", "challenges.cloudflare.com", "cf-browser-verification")
    scope_note = ("Pallot has Ohio's statewide races from the Secretary of State's sample ballot, and the U.S. House "
                  "race from FEC filings. The rest of your ballot (the Legislature, county and local races and "
                  "issues) isn't covered: your county board of elections' sample ballot has it.")

    @classmethod
    def parse(cls, raw: Any) -> list[Filing]:
        try:
            data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        except ValueError as exc:
            raise ValueError(f"not JSON ({exc})") from exc
        if not isinstance(data, dict):
            raise ValueError("not the list's JSON object")
        scope = (data.get("scope") or {}).get("type")
        if scope != SCOPE:
            raise ValueError(f"its scope is {scope!r}, not {SCOPE!r}")
        try:
            day = dt.date.fromisoformat(str((data.get("election") or {}).get("date"))).isoformat()
        except ValueError as exc:
            raise ValueError("no election date") from exc
        contests = [c for c in data.get("contests") or [] if isinstance(c, dict) and c.get("candidates")]
        if not contests:
            raise ValueError("no contests with candidates")
        offices = [_office(str(c.get("office") or "")) for c in contests]
        ids = [office.office_id for office in offices]
        filings = []
        for number, (contest, office) in enumerate(zip(contests, offices)):
            if not contest.get("office"):
                raise ValueError(f"contest {number + 1} has no office")
            race = dataclasses.replace(
                office, seats=int(contest.get("vote_for") or 1),
                unexpired=office.family == "US SENATE"
                or "unexpired" in f"{contest.get('office')} {contest.get('term')}".lower(),
            )
            if ids.count(office.office_id) > 1:
                term = _term(contest)
                race = dataclasses.replace(
                    race, office_id=f"{office.family} {term.upper() if term else number + 1}",
                    office=f"{office.office} (term beginning {term})" if term else f"{office.office} ({number + 1})",
                )
            for index, candidate in enumerate(contest["candidates"]):
                name = " ".join(str(candidate.get("name") or "").split())
                if not name:
                    raise ValueError(f"a candidate without a name under {race.office}")
                name = display_person(name)
                if mate := " ".join(str(candidate.get("running_mate") or "").split()):
                    name = f"{name} and {display_person(mate)}"
                code, party_name = party(candidate.get("party"), _PARTY_NAMES)
                filings.append(race.filing(
                    day=day, name=name, party=code, party_name=party_name, write_in=bool(candidate.get("write_in")),
                    incumbent=bool(candidate.get("incumbent")), order=number * 100 + index,
                ))
        return filings


GUIDE = Guide(
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
    credit="Dates worked out from Ohio's election law; more from the Ohio Secretary of State",
    poll_hours="6:30 a.m. – 7:30 p.m.",
    check_url="https://voterlookup.ohiosos.gov/voterlookup.aspx",
    check_hint="Ohio Secretary of State's voter lookup: your registration and your polling place",
    where_url="https://www.ohiosos.gov/elections/county-boards-of-elections-directory",
    where_hint="Every county board of elections (Ohio Secretary of State); yours publishes where and when you can vote "
               "early",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote absentee by mail, no reason needed. Your ballot must reach your "
                     "county board by 7:30 p.m. on Election Day: one mailed in time but arriving later isn't counted.",
    mail_deadline="Your application must reach your county board by the close of business on ",
    local_office="Your county board of elections",
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


RULE = ohio
