"""Download the source pages as plain HTML."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import httpx

from .errors import FetchError
from .models import SOURCE_URLS

USER_AGENT = "Mozilla/5.0"
TIMEOUT = 30
ATTEMPTS = 3
BACKOFF_SECONDS = 2.0


def fetch_source(
    url: str,
    session: httpx.Client | None = None,
    *,
    attempts: int = ATTEMPTS,
    backoff: float = BACKOFF_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """GET ``url`` with retries on connection errors and 5xx. Any 4xx, a 429 included, stops
    at once, so a site that refuses us isn't asked again."""
    own_session = session is None
    session = session or _client()
    last_error = "no attempts made"
    try:
        for attempt in range(1, attempts + 1):
            try:
                resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code >= 500:
                    last_error = f"HTTP {resp.status_code}"
                elif resp.status_code >= 400:
                    raise FetchError(f"{url}: HTTP {resp.status_code}")
                else:
                    # Always UTF-8: the pages may name no charset, and a guessed one mangles names.
                    return resp.content.decode("utf-8", errors="replace")
            if attempt < attempts:
                sleep(backoff * 2 ** (attempt - 1))
        raise FetchError(f"{url}: giving up after {attempts} attempts ({last_error})")
    finally:
        if own_session:
            session.close()


def _client() -> httpx.Client:
    return httpx.Client(follow_redirects=True)


def fetch_all(session: httpx.Client | None = None, raw_dir: str | Path | None = None) -> dict[str, str]:
    """Fetch every source; optionally save each page to ``raw_dir/<source>.html``."""
    own_session = session is None
    session = session or _client()
    try:
        pages = {source: fetch_source(url, session) for source, url in SOURCE_URLS.items()}
    finally:
        if own_session:
            session.close()
    if raw_dir is not None:
        raw = Path(raw_dir)
        raw.mkdir(parents=True, exist_ok=True)
        for source, html in pages.items():
            (raw / f"{source}.html").write_text(html, encoding="utf-8")
    return pages
