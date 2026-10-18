"""Calendar files (iCalendar, RFC 5545) of an election's key dates: one all-day event per
date, with no place, since polling places aren't known."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from .sources.key_dates import Deadlines
from .states.key_dates import GUIDES

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
    """The election's dates in date order, worded for its state; one not given is left out."""
    guide = GUIDES[found.state]
    election = f"the {found.day:%B} {found.day.day}, {found.day.year} election"
    short = f"{found.day:%b} {found.day.day} election"
    source = f"{guide.credit}: {guide.url}"
    early_end = f" It ends {_day(found.early_end)}." if found.early_end else ""
    listed = [
        Event("register", found.register_by, f"Last day to register to vote ({short})",
              f"{guide.register.format(election=election)} Check that you're registered: "
              f"{guide.registration_url}\n\n{source}"),
        Event("mail", found.mail_apply_by, f"{guide.mail_summary} ({short})",
              f"{guide.mail.format(election=election)} {guide.mail_url}\n\n{source}"),
        Event("early_start", found.early_start, f"Early voting begins ({short})",
              f"Early voting in person begins for {election}.{early_end} {guide.early_where}\n\n{source}"),
        Event("early_end", found.early_end, f"Last day of early voting ({short})",
              f"The last day to vote early in person in {election}. {guide.early_where}\n\n{source}"),
        Event("election", found.day, f"Election Day ({short})",
              f"Election Day for {election} in {guide.name}. {guide.polls}\n\n{source}"),
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
    mail-ballot deadline (not every voter votes by mail). None when that's nothing.
    Each event's UID is fixed, so importing a file again updates its events."""
    chosen = [e for e in events(found) if (e.id == only if only else e.id != "mail" and e.day >= today)]
    if not chosen:
        return None
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Pallot//Key election dates//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH"]
    for event in chosen:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{found.state.lower()}-{found.day.isoformat()}-{event.id}@pallot",
            f"DTSTAMP:{stamp.astimezone(dt.timezone.utc):%Y%m%dT%H%M%SZ}",
            f"DTSTART;VALUE=DATE:{event.day:%Y%m%d}",
            f"DTEND;VALUE=DATE:{event.day + dt.timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escape(event.summary)}",
            f"DESCRIPTION:{_escape(event.description)}",
            f"URL:{GUIDES[found.state].url}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "".join(_fold(line) + "\r\n" for line in lines)
