from __future__ import annotations

import socket
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise RuntimeError("network access is disabled in tests")

    monkeypatch.setattr(httpx.Client, "send", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture(scope="session")
def page() -> str:
    return (FIXTURES / "candidates.html").read_text(encoding="utf-8")


def at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc)


def edit(page: str, old: str, new: str) -> str:
    """The page with its data's first ``old`` replaced; ``old`` as the data's JSON writes it."""
    escaped = lambda text: text.replace("\\", "\\\\").replace('"', '\\"')  # noqa: E731
    assert escaped(old) in page, old
    return page.replace(escaped(old), escaped(new), 1)
