from __future__ import annotations

import pytest
import requests

from trackaipac_cache import __main__ as cli
from trackaipac_cache.errors import FetchError, ValidationError
from trackaipac_cache.fetch import USER_AGENT, fetch_all, fetch_source
from trackaipac_cache.models import SOURCE_URLS, RefreshResult

from .conftest import at


class FakeResponse:
    def __init__(self, status_code: int, content: bytes = b""):
        self.status_code = status_code
        self.content = content


class FakeSession:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers or {}))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def close(self):
        pass


def test_success_decodes_utf8_and_sends_user_agent():
    session = FakeSession(FakeResponse(200, "<h2>Angélica Dueñas</h2>".encode("utf-8")))
    assert fetch_source("https://example.test/x", session) == "<h2>Angélica Dueñas</h2>"
    assert session.calls[0][1]["User-Agent"] == USER_AGENT


def test_retries_transient_failures():
    sleeps: list[float] = []
    session = FakeSession(requests.ConnectionError("reset"), FakeResponse(503), FakeResponse(200, b"ok"))
    assert fetch_source("https://example.test/x", session, sleep=sleeps.append) == "ok"
    assert sleeps == [2.0, 4.0]


def test_gives_up_after_all_attempts():
    session = FakeSession(FakeResponse(500), FakeResponse(502), FakeResponse(429))
    with pytest.raises(FetchError, match=r"giving up after 3 attempts \(HTTP 429\)"):
        fetch_source("https://example.test/x", session, sleep=lambda s: None)
    assert len(session.calls) == 3


def test_client_error_is_not_retried():
    session = FakeSession(FakeResponse(404))
    with pytest.raises(FetchError, match="HTTP 404"):
        fetch_source("https://example.test/x", session, sleep=lambda s: None)
    assert len(session.calls) == 1


def test_fetch_all_saves_raw(tmp_path):
    session = FakeSession(*[FakeResponse(200, f"<p>{s}</p>".encode()) for s in SOURCE_URLS])
    pages = fetch_all(session, raw_dir=tmp_path / "raw")
    assert pages == {s: f"<p>{s}</p>" for s in SOURCE_URLS}
    assert [url for url, _ in session.calls] == list(SOURCE_URLS.values())
    assert (tmp_path / "raw" / "congress.html").read_text(encoding="utf-8") == "<p>congress</p>"


def test_tests_cannot_reach_the_network():
    with pytest.raises(RuntimeError, match="network access is disabled"):
        requests.get("https://www.trackaipac.com/candidates", timeout=1)


def test_cli_refresh(monkeypatch, capsys, tmp_path):
    seen = {}

    def fake_refresh(**kwargs):
        seen.update(kwargs)
        return RefreshResult(status="no_changes", checked_at=at(1), record_counts={"candidates": 54})

    monkeypatch.setattr(cli, "refresh", fake_refresh)
    assert cli.main(["refresh", "--dry-run", "--data-dir", str(tmp_path)]) == 0
    assert seen == {"force": False, "dry_run": True, "data_dir": str(tmp_path), "raw_dir": None}
    assert capsys.readouterr().out.startswith("no changes")


def test_cli_reports_aborts(monkeypatch, capsys):
    def failing_refresh(**kwargs):
        raise ValidationError(["candidates: parsed 0 records, expected at least 20"])

    monkeypatch.setattr(cli, "refresh", failing_refresh)
    assert cli.main(["refresh"]) == 2
    assert "candidates: parsed 0 records" in capsys.readouterr().err
