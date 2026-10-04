from __future__ import annotations

import httpx
import pytest

from voteforpeace_cache import __main__ as cli
from voteforpeace_cache.errors import FetchError
from voteforpeace_cache.fetch import USER_AGENT, fetch_page
from voteforpeace_cache.models import SOURCE_URL, RefreshResult

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


def test_one_request_for_the_page_saved_when_asked(tmp_path):
    session = FakeSession(FakeResponse(200, "<p>Angélica</p>".encode("utf-8")))
    assert fetch_page(session=session, raw_dir=tmp_path) == "<p>Angélica</p>"
    assert session.calls == [(SOURCE_URL, {"User-Agent": USER_AGENT})]
    assert (tmp_path / "candidates.html").read_text(encoding="utf-8") == "<p>Angélica</p>"


def test_retries_transient_failures():
    sleeps: list[float] = []
    session = FakeSession(httpx.ConnectError("reset"), FakeResponse(503), FakeResponse(200, b"ok"))
    assert fetch_page(session=session, sleep=sleeps.append) == "ok"
    assert sleeps == [2.0, 4.0]


@pytest.mark.parametrize("status", [403, 429])
def test_a_refusal_is_not_retried(status):
    session = FakeSession(FakeResponse(status))
    with pytest.raises(FetchError, match=f"HTTP {status}"):
        fetch_page(session=session, sleep=lambda s: None)
    assert len(session.calls) == 1


def test_cli_prints_the_summary_or_the_error(monkeypatch, capsys):
    monkeypatch.setattr(cli, "refresh", lambda **kwargs: RefreshResult(status="no_changes", checked_at=at(4), record_count=791))
    assert cli.main(["refresh"]) == 0
    assert capsys.readouterr().out == "no changes\ncandidates: 791\n"

    def fail(**kwargs):
        raise FetchError("https://voteforpeace.info/candidates: HTTP 403")

    monkeypatch.setattr(cli, "refresh", fail)
    assert cli.main(["refresh", "--dry-run"]) == 2
    assert "HTTP 403" in capsys.readouterr().err
