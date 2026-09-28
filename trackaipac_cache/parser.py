"""Regex parser over html2text output of the trackaipac.com list pages.

Every source renders a person as a Squarespace ``<li class="list-item">`` holding an
``<h2>`` name and ``<p>``/``<br>`` lines, grouped into titled list sections ("Tennessee",
"Our Endorsed Incumbents"). Each list item is cut out of the page, converted with
html2text, and split on ``## ``.

Every list item becomes exactly one record, in page order: nothing is skipped, merged
or corrected. ``lines`` keeps the item's text verbatim; the other fields are parsed
from it and are None/empty when the page does not show that value.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

import html2text

from .models import BASE_URL, SOURCE_CATEGORIES, STATES, ParsedRecord

_STATE_BY_NAME = {name.lower(): code for code, name in STATES.items()}

_SECTION_SPLIT_RE = re.compile(r"(?=<section\b)")
_SECTION_TITLE_RE = re.compile(r'<div\s+class="list-section-title"[^>]*>(.*?)</div>', re.S)
_LIST_ITEM_RE = re.compile(r'<li\s+class="[^"]*\blist-item\b[^"]*"[^>]*>.*?</li>', re.S)
_BLOCK_SPLIT_RE = re.compile(r"(?m)^[ \t]*(?:[*+-][ \t]+)?## ")
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]*)\)")
_WS_RE = re.compile(r"\s+")

_TITLE_RE = re.compile(
    r"^(?:Candidate\s+for\s+U\.?\s?S\.?\s+(?P<office>House|Senate|Congress)"
    r"|U\.?\s?S\.?\s+(?P<held>Representative|Senator))\b",
    re.I,
)
_AMOUNT = r"(\$\s*[\d,]+|TBD)"
_TOTAL_RE = re.compile(r"(?:Israel\s+)?Lobby\s+Total\s*:\s*" + _AMOUNT, re.I)
_DONATIONS_RE = re.compile(r"\b(?:Donations|PACs)\s*:\s*" + _AMOUNT, re.I)
_IE_RE = re.compile(r"\bIE\s*:\s*" + _AMOUNT)
_DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),?\s+(\d{4})"
)

_PARTY_RE = re.compile(r"[\[(]\s*([A-Z])\s*[\])]\s*$")
_TRAILING_PAREN_RE = re.compile(r"\s*\(([^)]*)\)\s*$")
_SEAT_CODE_RE = re.compile(r"([A-Z]{2})(?:\s*-\s*(\d{1,2}|AL|SEN|[Aa]t[\s-]?[Ll]arge))?")

# First token must be an all-caps/digit acronym ("AIPAC", "MAGA KY", "314 Action"), which
# keeps lines such as "Endorsed by DMFI" or "Retiring 2026" out of the PAC list.
_PAC_ITEM_RE = re.compile(r"[A-Z0-9][A-Z0-9&.\-]+(?:\s+[A-Za-z0-9&.\-]+){0,4}(?:\s*\([^)]*\))?\*?")
_PAC_SPLIT_RE = re.compile(r",|(?<=\))\s+(?=[A-Z0-9])")


@dataclass(frozen=True)
class SeatInfo:
    state: str
    district: str | None  # "03", "AL", or None when the line gives no district
    senate: bool  # explicit "-SEN"
    party: str | None
    extra: str | None  # trailing parenthetical, e.g. "TX-37 2026"


@dataclass
class ParseResult:
    source: str
    records: list[ParsedRecord] = field(default_factory=list)
    unnamed: list[str] = field(default_factory=list)  # list items with no name heading
    total_items: int = 0


# --------------------------------------------------------------------------- helpers


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def normalize_name(text: str) -> str:
    """Accent-, case- and punctuation-insensitive form used for name matching."""
    return slugify(text).replace("-", " ")


def make_candidate_id(state: str | None, name: str) -> str:
    """"tx-greg-casar"; "unk-<name>" when the page gives no state at all."""
    return f"{state.lower() if state else 'unk'}-{slugify(name)}"


def parse_money(text: str | None) -> int | None:
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    return int(digits) if digits else None


def parse_election_date(text: str) -> str | None:
    m = _DATE_RE.fullmatch(text.strip())
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").date().isoformat()
    except ValueError:
        return None


def parse_seat(text: str) -> SeatInfo | None:
    """Parse seat lines such as "AZ-01 [D]", "MO-01 (D)", "TX- 23", "ND-At Large", "Montana [R]"."""
    s = _WS_RE.sub(" ", text).strip()
    party = extra = None
    for _ in range(2):
        m = _PARTY_RE.search(s)
        if m and party is None:
            party = m.group(1)
            s = s[: m.start()].strip()
            continue
        m = _TRAILING_PAREN_RE.search(s)
        if m and extra is None:
            extra = m.group(1).strip()
            s = s[: m.start()].strip()
    m = _SEAT_CODE_RE.fullmatch(s)
    if m and m.group(1) in STATES:
        state, dist = m.group(1), m.group(2)
        if dist is None:
            return SeatInfo(state, None, False, party, extra)
        if dist.upper() == "SEN":
            return SeatInfo(state, None, True, party, extra)
        district = f"{int(dist):02d}" if dist.isdigit() else "AL"
        return SeatInfo(state, district, False, party, extra)
    code = _STATE_BY_NAME.get(s.lower())
    if code:
        return SeatInfo(code, None, False, party, extra)
    return None


def split_pacs(text: str) -> list[str] | None:
    """Split a PAC line ("AIPAC ('24), DMFI, MAGA KY") into its items as written, or
    return None if the line isn't a PAC list."""
    items = [p.strip() for p in _PAC_SPLIT_RE.split(text)]
    items = [p for p in items if p]
    if not items or not all(_PAC_ITEM_RE.fullmatch(p) for p in items):
        return None
    return items


def _abs_url(url: str) -> str:
    return BASE_URL + url if url.startswith("/") else url


def _plain(line: str) -> str:
    """Line text with markdown links replaced by their text."""
    return _WS_RE.sub(" ", _LINK_RE.sub(lambda m: m.group(1), line)).strip()


def _urls(line: str) -> list[str]:
    return [_abs_url(u) for _, u in _LINK_RE.findall(line) if u]


# --------------------------------------------------------------------------- page level


def html_to_text(fragment: str) -> str:
    h = html2text.HTML2Text()
    h.body_width = 0
    h.ignore_images = True
    h.ignore_emphasis = True
    h.unicode_snob = True
    return h.handle(fragment)


def extract_sections(html: str) -> list[tuple[str | None, list[str]]]:
    """[(section title or None, [list item html, ...]), ...] in page order."""
    sections = []
    for chunk in _SECTION_SPLIT_RE.split(html):
        items = _LIST_ITEM_RE.findall(chunk)
        if not items:
            continue
        m = _SECTION_TITLE_RE.search(chunk)
        title = _plain(html_to_text(m.group(1))) if m else ""
        sections.append((title or None, items))
    return sections


def split_blocks(text: str) -> list[str]:
    """Split html2text output on "## " headings; text before the first heading is dropped."""
    return [b for b in _BLOCK_SPLIT_RE.split(text)[1:] if b.strip()]


def parse_source(source: str, html: str) -> ParseResult:
    category = SOURCE_CATEGORIES[source]
    result = ParseResult(source=source)
    for section, items in extract_sections(html):
        for item in items:
            result.total_items += 1
            text = html_to_text(item)
            records = [r for r in (_parse_block(b, source, category, section) for b in split_blocks(text)) if r]
            if not records:
                result.unnamed.append(_WS_RE.sub(" ", text).strip()[:200])
            result.records += records
    return result


# --------------------------------------------------------------------------- block level


def _parse_block(block: str, source: str, category: str, section: str | None) -> ParsedRecord | None:
    raw_lines = [ln.strip() for ln in block.splitlines()]
    raw_lines = [ln for ln in raw_lines if ln]
    if not raw_lines:
        return None
    name = _plain(raw_lines[0])
    if not name:
        return None
    body = raw_lines[1:]

    idx = 0
    title = office = campaign_url = None
    held = False
    if body and (m := _TITLE_RE.match(_plain(body[0]))):
        title = _plain(body[0])
        office = (m.group("office") or m.group("held")).lower()
        held = bool(m.group("held"))
        urls = _urls(body[0])
        campaign_url = urls[0] if urls else None
        idx = 1

    seat = seat_text = None
    if idx < len(body) and (seat := parse_seat(_plain(body[idx]))):
        seat_text = _plain(body[idx])
        idx += 1

    total = donations = ie = None
    pacs: list[str] | None = None
    election_date = donate_url = None
    notes: list[str] = []
    last_funding: int | None = None
    for pos, line in enumerate(body[idx:]):
        plain = _plain(line)
        hit = False
        if m := _TOTAL_RE.search(plain):
            total, hit = parse_money(m.group(1)), True
        if m := _DONATIONS_RE.search(plain):
            donations, hit = parse_money(m.group(1)), True
        if m := _IE_RE.search(plain):
            ie, hit = parse_money(m.group(1)), True
        if hit:
            last_funding = pos
            continue
        links = _LINK_RE.findall(line)
        if len(links) == 1 and _LINK_RE.fullmatch(line) and links[0][0].strip().lower().startswith("support "):
            donate_url = _abs_url(links[0][1])
            continue
        if election_date is None and (iso := parse_election_date(plain)):
            election_date = iso
            continue
        if pacs is None and last_funding is not None and pos == last_funding + 1:
            items = split_pacs(plain)
            if items:
                pacs = items
                continue
        notes.append(line)

    state = seat.state if seat else _STATE_BY_NAME.get((section or "").strip().lower())
    chamber = _chamber(office, seat)
    return ParsedRecord(
        candidate_id=make_candidate_id(state, name),
        source=source,
        category=category,
        section=section,
        name=name,
        title=title,
        seat_text=seat_text,
        state=state,
        district=seat.district if seat and chamber == "house" else None,
        chamber=chamber,
        party=seat.party if seat else None,
        incumbent=None if office is None else held,
        israel_lobby_total=total,
        donations=donations,
        ie=ie,
        pacs=tuple(pacs or ()),
        election_date=election_date,
        campaign_url=campaign_url,
        donate_url=donate_url,
        notes=tuple(notes),
        lines=tuple(body),
    )


def _chamber(office: str | None, seat: SeatInfo | None) -> str | None:
    if office in ("senate", "senator"):
        return "senate"
    if office in ("house", "representative"):
        return "house"
    if seat is None:
        return None
    if seat.senate:
        return "senate"
    return "house" if seat.district else None
