"""Display helpers: the state's data is ALL CAPS ("U. S. REPRESENTATIVE DISTRICT 10")."""

from __future__ import annotations

import datetime as dt
import email.utils
import re

_LOWER_WORDS = {"OF", "THE", "AT", "AND", "FOR", "IN", "ON", "TO"}
_ORDINAL = re.compile(r"^(\d+)(ST|ND|RD|TH)(\W*)$")
_ROMAN = {"II", "III", "IV", "V", "VI"}


def _cap(word: str) -> str:
    """Capitalize the first letter, keeping any leading punctuation ("(TEXAS)" -> "(Texas)")."""
    for i, ch in enumerate(word):
        if ch.isalpha():
            return word[:i] + ch.upper() + word[i + 1 :].lower()
    return word


def display_office(name: str) -> str:
    """ "JUDGE, COUNTY COURT AT LAW NO. 1" -> "Judge, County Court at Law No. 1"."""
    if not name.isupper():
        return name
    words = []
    for i, word in enumerate(name.split()):
        ordinal = _ORDINAL.match(word)
        if ordinal:
            words.append(ordinal.group(1) + ordinal.group(2).lower() + ordinal.group(3))
        elif i > 0 and word in _LOWER_WORDS:
            words.append(word.lower())
        elif len(word) <= 2 and word.endswith("."):  # "U." "S."
            words.append(word)
        else:
            words.append(_cap(word))
    return " ".join(words).replace("U. S. ", "U.S. ")


_ACRONYMS = {
    "PAC", "PACS", "LLC", "LLP", "PLLC", "USA", "US", "AIPAC", "SEIU", "AFL-CIO", "NEA", "AFT", "LCV", "NRA", "UAW",
    "IBEW", "CEO", "CFO", "COO", "CTO", "CPA", "VP", "MD", "DO", "UT", "ISD",
}


def display_org(name: str) -> str:
    """ "LONE STAR RISING PAC" -> "Lone Star Rising PAC": like display_office, but acronyms
    (and vowel-less words like NRCC) stay in capitals."""
    shown = display_office(name)
    if not name.isupper() or len(shown.split()) != len(name.split()):
        return shown
    words = []
    for word, pretty in zip(name.split(), shown.split()):
        bare = word.strip(".,()")
        keep = bare in _ACRONYMS or (bare.isalpha() and not re.search(r"[AEIOUY]", bare))
        words.append(word if keep else pretty)
    return " ".join(words)


def _name_part(part: str) -> str:
    bare = part.strip(".,")
    if bare in _ROMAN:
        return part
    if len(bare) == 1:  # an initial
        return part
    if bare.startswith("MC") and len(bare) > 2:
        return part.replace(bare, "Mc" + _cap(bare[2:]))
    if bare.startswith("O'") and len(bare) > 2:
        return part.replace(bare, "O'" + _cap(bare[2:]))
    return _cap(part)


def display_person(name: str) -> str:
    """ "BETH VAN DUYNE" -> "Beth Van Duyne"; names already in mixed case are left alone."""
    if not name.isupper():
        return name
    return " ".join("-".join(_name_part(p) for p in word.split("-")) for word in name.split())


def iso_utc(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat(timespec="seconds")


def web_url(value: str | None) -> str | None:
    """Candidate filings often omit the scheme ("www.tedbrown.org")."""
    if not value or not value.strip():
        return None
    value = value.strip()
    return value if re.match(r"^https?://", value, re.I) else f"https://{value}"


def money(amount: float | None) -> str | None:
    """Whole dollars: 219959 -> "$219,959"."""
    return None if amount is None else f"${round(amount):,}"


def money_short(amount: float | None) -> str | None:
    """For badges: 68560930 -> "$68.6M", 542119 -> "$542K", 950 -> "$950"."""
    if amount is None:
        return None
    sign, value = ("-" if amount < 0 else ""), abs(amount)
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if value >= size * 0.9995:  # 999,600 is "$1M", not "$1000K"
            scaled = value / size
            text = f"{scaled:.1f}" if scaled < 99.95 else f"{scaled:.0f}"
            return f"{sign}${text.removesuffix('.0')}{suffix}"
    return f"{sign}${value:,.0f}"


def display_size(num: int) -> str:
    """Bytes on disk or to download: 1_911_097 -> "1.8 MB", 40_960 -> "40 KB"."""
    return f"{num / 1_048_576:.1f} MB" if num >= 1_048_576 else f"{num / 1024:.0f} KB"


def parse_date(text: str | None) -> dt.date | None:
    """ "2026-06-30" or "2026-06-30T00:00:00" -> that date; None for anything else."""
    try:
        return dt.date.fromisoformat((text or "")[:10])
    except ValueError:
        return None


def display_date(value: str | dt.date | None) -> str | None:
    """ "2026-06-30" or "2026-06-30T00:00:00" -> "Jun 30, 2026"."""
    if isinstance(value, str):
        value = parse_date(value)
    return f"{value:%b} {value.day}, {value.year}" if value else None


def local_moment(value: float | str | None) -> dt.datetime | None:
    """A moment in the server's local time, which is the voter's when Pallot runs on their
    computer: from a timestamp, or "2026-09-28T18:25:03+00:00" (no zone means UTC), or an HTTP
    date ("Mon, 28 Sep 2026 18:18:01 GMT"); None for anything else."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            moment = dt.datetime.fromisoformat(value)
        except ValueError:
            try:
                moment = email.utils.parsedate_to_datetime(value)
            except (TypeError, ValueError):
                return None
        return (moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)).astimezone()
    return dt.datetime.fromtimestamp(value).astimezone()


def snapshot_day(snapshot: str | None, taken: str | None) -> str | None:
    """A snapshot's day in local time. The refreshes name a snapshot after the UTC day ("2026-10-04"),
    so one taken at "2026-10-04T02:31:02+00:00" is "2026-10-03" in Texas, the day "Last changed"
    shows beside it. A snapshot not taken at ``taken`` keeps its own day."""
    day, moment = parse_date(snapshot), local_moment(taken)
    if day and moment and moment.astimezone(dt.timezone.utc).date() == day:
        return moment.date().isoformat()
    return snapshot


def display_time(value: float | str | None) -> str | None:
    """local_moment's -> "Sep 28, 2026, 1:25 PM"."""
    moment = local_moment(value)
    if moment is None:
        return None
    return f"{moment:%b} {moment.day}, {moment.year}, {moment.hour % 12 or 12}:{moment:%M} {'AM' if moment.hour < 12 else 'PM'}"
