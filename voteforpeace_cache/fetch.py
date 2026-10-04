"""Download the All Candidates page as HTML: one request, about 7 MB."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import httpx

from .errors import FetchError
from .models import SOURCE_URL

USER_AGENT = "Mozilla/5.0"
TIMEOUT = 60
ATTEMPTS = 3
BACKOFF_SECONDS = 2.0


def fetch_page(
    url: str = SOURCE_URL,
    session: httpx.Client | None = None,
    *,
    attempts: int = ATTEMPTS,
    backoff: float = BACKOFF_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    raw_dir: str | Path | None = None,
) -> str:
    """GET ``url`` with retries on connection errors and 5xx. Any 4xx, a 429 included, stops
    at once, so a site that refuses us isn't asked again. With ``raw_dir``, the page is also
    saved there as candidates.html."""
    own_session = session is None
    session = session or httpx.Client(follow_redirects=True)
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
                    html = resp.content.decode("utf-8", errors="replace")
                    if raw_dir is not None:
                        raw = Path(raw_dir)
                        raw.mkdir(parents=True, exist_ok=True)
                        (raw / "candidates.html").write_text(html, encoding="utf-8")
                    return html
            if attempt < attempts:
                sleep(backoff * 2 ** (attempt - 1))
        raise FetchError(f"{url}: giving up after {attempts} attempts ({last_error})")
    finally:
        if own_session:
            session.close()
