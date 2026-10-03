from __future__ import annotations

import re
import socket
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from trackaipac_cache.parser import ParseResult, parse_source
from trackaipac_cache.refresh import refresh

FIXTURES = Path(__file__).parent / "fixtures"
SOURCES = ("candidates", "endorsements", "congress")
LIST_ITEM_RE = re.compile(r'<li\s+class="[^"]*\blist-item\b[^"]*"[^>]*>.*?</li>', re.S)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise RuntimeError("network access is disabled in tests")

    monkeypatch.setattr(httpx.Client, "send", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture(scope="session")
def pages() -> dict[str, str]:
    return {s: (FIXTURES / f"{s}.html").read_text(encoding="utf-8") for s in SOURCES}


@pytest.fixture(scope="session")
def parsed(pages) -> dict[str, ParseResult]:
    return {s: parse_source(s, html) for s, html in pages.items()}


def at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 9, day, hour, tzinfo=timezone.utc)


def keep_items(html: str, n: int) -> str:
    """Drop every list item after the first n."""
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        count += 1
        return m.group(0) if count <= n else ""

    return LIST_ITEM_RE.sub(repl, html)


def drop_item(html: str, name: str) -> str:
    return LIST_ITEM_RE.sub(lambda m: "" if f">{name}</h2>" in m.group(0) else m.group(0), html)


def edit_item(html: str, name: str, old: str, new: str, occurrence: int = 1) -> str:
    """Replace ``old`` with ``new`` inside the nth list item for ``name``."""
    seen = 0

    def repl(m: re.Match) -> str:
        nonlocal seen
        if f">{name}</h2>" not in m.group(0):
            return m.group(0)
        seen += 1
        if seen != occurrence:
            return m.group(0)
        assert old in m.group(0), f"{old!r} not in {name}'s item"
        return m.group(0).replace(old, new, 1)

    return LIST_ITEM_RE.sub(repl, html)


def move_item_to_end(html: str, name: str) -> str:
    """Move a list item after the last list item of the page."""
    items = list(LIST_ITEM_RE.finditer(html))
    target = next(m for m in items if f">{name}</h2>" in m.group(0))
    last = items[-1]
    return html[: target.start()] + html[target.end() : last.end()] + target.group(0) + html[last.end() :]


def tree_bytes(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def data_dir(tmp_path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def run(pages, data_dir):
    """run(overrides=None, day=1, **refresh_kwargs) -> RefreshResult, offline."""

    def _run(overrides: dict[str, str] | None = None, *, day: int = 1, **kwargs):
        current = {**pages, **(overrides or {})}
        return refresh(data_dir=data_dir, fetcher=lambda: current, now=at(day), **kwargs)

    return _run
