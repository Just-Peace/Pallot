"""Display helpers: the state's data is ALL CAPS ("U. S. REPRESENTATIVE DISTRICT 10")."""

from __future__ import annotations

import datetime as dt
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


def money(amount: int | None) -> str | None:
    return None if amount is None else f"${amount:,}"
