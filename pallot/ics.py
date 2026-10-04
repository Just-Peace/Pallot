"""Calendar files (iCalendar, RFC 5545) of an election's key dates: one all-day event per
date, with no place, since polling places aren't known."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from .sources.key_dates import MAIL_APPLY_URL, REGISTRATION_URL, URL, Deadlines

EventId = Literal["register", "early_start", "early_end", "election", "mail"]


@dataclass(frozen=True)
class Event:
    id: EventId
    day: dt.date | None  # None: the page doesn't give it
    summary: str
    description: str


def _day(day: dt.date) -> str:
    return f"{day:%A}, {day:%B} {day.day}"


def events(found: Deadlines) -> list[Event]:
    """The election's dates in date order; one the page doesn't give is left out."""
    election = f"the {found.day:%B} {found.day.day}, {found.day.year} election"
    short = f"{found.day:%b} {found.day.day} election"
    source = f"Dates from the Texas Secretary of State: {URL}"
    early_end = f" It ends {_day(found.early_end)}." if found.early_end else ""
    listed = [
        Event("register", found.register_by, f"Last day to register to vote ({short})",
              f"The last day to register to vote in {election} in Texas. Check that you're registered: "
              f"{REGISTRATION_URL}\n\n{source}"),
        Event("mail", found.mail_apply_by, f"Mail-ballot application due ({short})",
              f"If you vote by mail in {election}, your application must reach your county's early voting clerk "
              f"today: received, not postmarked. Who can vote by mail, and how to apply: {MAIL_APPLY_URL}\n\n{source}"),
        Event("early_start", found.early_start, f"Early voting begins ({short})",
              f"Early voting in person begins for {election}.{early_end} Your county elections office lists the places "
              f"and hours.\n\n{source}"),
        Event("early_end", found.early_end, f"Last day of early voting ({short})",
              f"The last day to vote early in person in {election}. Your county elections office lists the places and "
              f"hours.\n\n{source}"),
        Event("election", found.day, f"Election Day ({short})",
              f"Election Day for {election} in Texas. Polls are open 7 a.m. to 7 p.m.; if you're in line at 7, you can "
              f"vote.\n\n{source}"),
    ]
    return sorted((e for e in listed if e.day), key=lambda e: e.day)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """A line longer than 75 octets goes on over the next lines, each starting with a space,
    without splitting a character."""
    parts, current, size = [], "", 0
    for char in line:
        width = len(char.encode("utf-8"))
        if size + width > 75:
            parts.append(current)
            current, size = " ", 1
        current += char
        size += width
    parts.append(current)
    return "\r\n".join(parts)


def calendar(found: Deadlines, *, today: dt.date, stamp: dt.datetime, only: EventId | None = None) -> str | None:
    """The file: just the ``only`` event, or else every date from ``today`` on except the
    mail-ballot deadline (only some voters can vote by mail). None when that's nothing.
    Each event's UID is fixed, so importing a file again updates its events."""
    chosen = [e for e in events(found) if (e.id == only if only else e.id != "mail" and e.day >= today)]
    if not chosen:
        return None
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Pallot//Key election dates//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH"]
    for event in chosen:
        lines += [
            "BEGIN:VEVENT",
            f"UID:tx-{found.day.isoformat()}-{event.id}@pallot",
            f"DTSTAMP:{stamp.astimezone(dt.timezone.utc):%Y%m%dT%H%M%SZ}",
            f"DTSTART;VALUE=DATE:{event.day:%Y%m%d}",
            f"DTEND;VALUE=DATE:{event.day + dt.timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escape(event.summary)}",
            f"DESCRIPTION:{_escape(event.description)}",
            f"URL:{URL}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "".join(_fold(line) + "\r\n" for line in lines)
