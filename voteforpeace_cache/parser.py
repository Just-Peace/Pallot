"""Read the candidate list out of the All Candidates page.

The page is a Next.js app: besides the HTML it carries its own data as a React Server
Components payload, in ``self.__next_f.push([1, "..."])`` scripts. Joined and unescaped,
that payload holds one ``{"sections": [...]}`` object, a section per state with every
candidate the site rates there. We read that object, not the HTML around it, so a change
to the page's styling doesn't break the parse.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from typing import Any

from .errors import ParseError
from .models import BASE_URL, Article, Endorsement, ParsedRecord

_PUSH = re.compile(r"self\.__next_f\.push\(\[1,(\"(?:[^\"\\]|\\.)*\")\]\)", re.S)
_SECTIONS = '{"sections":['
_BREAK = re.compile(r"<br\s*/?>|</p>|</li>|</div>", re.I)
_TAG = re.compile(r"<[^>]+>")


@dataclass
class ParseResult:
    records: list[ParsedRecord] = field(default_factory=list)
    unnamed: list[str] = field(default_factory=list)  # candidates without a name, by id


def payload(page: str) -> str:
    """The page's server-components payload, its chunks joined and unescaped."""
    chunks = _PUSH.findall(page)
    if not chunks:
        raise ParseError("no Next.js data on the page (no self.__next_f.push scripts)")
    try:
        return "".join(json.loads(chunk) for chunk in chunks)
    except ValueError as exc:
        raise ParseError(f"the page's Next.js data isn't a string it can read: {exc}") from exc


def sections(page: str) -> list[dict[str, Any]]:
    text = payload(page)
    start = text.find(_SECTIONS)
    if start < 0:
        raise ParseError("the page's data has no candidate sections")
    try:
        found, _ = json.JSONDecoder().raw_decode(text, start)
    except ValueError as exc:
        raise ParseError(f"the candidate sections aren't JSON: {exc}") from exc
    if not isinstance(found.get("sections"), list):
        raise ParseError("the candidate sections aren't a list")
    return found["sections"]


def _text(value: Any) -> str | None:
    """A string with its whitespace collapsed; None when empty or not a string."""
    if not isinstance(value, str):
        return None
    return " ".join(value.split()) or None


def plain_text(value: Any) -> str | None:
    """The site's notes as plain text: "<p>Endorsed by Our Revolution.</p>" -> "Endorsed by
    Our Revolution.", a paragraph per line."""
    if not isinstance(value, str):
        return None
    lines = (html.unescape(_TAG.sub("", line)) for line in _BREAK.split(value))
    return "\n".join(filter(None, (" ".join(line.split()) for line in lines))) or None


def _record(entry: dict[str, Any], section: dict[str, Any]) -> ParsedRecord:
    state_slug, slug = _text(section.get("stateSlug")), _text(entry.get("slug"))
    state = _text(entry.get("state_abbr")) or _text(section.get("key"))
    return ParsedRecord(
        candidate_id=str(entry.get("id") or slug or ""),
        name=_text(entry.get("name")) or "",
        slug=slug,
        url=f"{BASE_URL}/{state_slug}/{slug}" if state_slug and slug else None,
        state=state.upper() if state else None,
        section=_text(section.get("label")),
        party=_text(entry.get("party")),
        rating=_text(entry.get("our_rating")),
        office_title=_text(entry.get("office_title")),
        district=_text(entry.get("district")),
        level=_text(entry.get("level")),
        jurisdiction=_text(entry.get("jurisdiction")),
        election_date=_text(entry.get("election_date")),
        election_label=_text(entry.get("election_label")),
        election_stage=_text(entry.get("election_stage")),
        election_result=_text(entry.get("election_result")),
        featured_text=_text(entry.get("featured_text")),
        notes=plain_text(entry.get("public_notes")),
        endorsements=tuple(
            Endorsement(
                organization=_text(item.get("organization_name")) or "",
                type=_text(item.get("type")),
                notes=plain_text(item.get("notes")),
                link=_text(item.get("link")),
            )
            for item in entry.get("endorsement_details") or ()
            if _text(item.get("organization_name"))
        ),
        articles=tuple(
            Article(title=_text(item.get("title")), url=_text(item.get("url")), description=plain_text(item.get("description")))
            for item in entry.get("articles") or ()
        ),
    )


def parse_page(page: str) -> ParseResult:
    """Every candidate on the page, in page order (state by state, as the site sorts them)."""
    result = ParseResult()
    for section in sections(page):
        for entry in section.get("candidates") or ():
            record = _record(entry, section)
            if record.name:
                result.records.append(record)
            else:
                result.unnamed.append(record.candidate_id or "(no id)")
    return result
