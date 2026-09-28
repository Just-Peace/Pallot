"""Capture one TrackAIPAC HTML fixture per source into tests/trackaipac/fixtures/.

    python scripts/capture_trackaipac_fixtures.py              # fetch live pages
    python scripts/capture_trackaipac_fixtures.py --from raw   # reuse raw/<source>.html

Pages are shrunk by removing <script>, <style>, <svg> and Squarespace's
data-current-context attribute; a fixture is only written if the parser produces
identical rows before and after shrinking.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trackaipac_cache.fetch import fetch_all  # noqa: E402
from trackaipac_cache.models import SOURCE_URLS  # noqa: E402
from trackaipac_cache.parser import parse_source  # noqa: E402
from trackaipac_cache.store import snapshot_rows  # noqa: E402

FIXTURE_DIR = ROOT / "tests" / "trackaipac" / "fixtures"

_STRIP_PATTERNS = [
    re.compile(r"<script\b.*?</script>", re.S | re.I),
    re.compile(r"<style\b.*?</style>", re.S | re.I),
    re.compile(r"<svg\b.*?</svg>", re.S | re.I),
    re.compile(r'\sdata-current-context="[^"]*"', re.S),
    re.compile(r'\s(?:srcset|sizes|data-src|data-image)="[^"]*"'),
]
_INDENT_RE = re.compile(r"\n[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{2,}")


def shrink(html: str) -> str:
    for pattern in _STRIP_PATTERNS:
        html = pattern.sub("", html)
    return _BLANK_LINES_RE.sub("\n", _INDENT_RE.sub("\n", html))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_dir", help="read <source>.html from this directory instead of fetching")
    args = ap.parse_args()

    if args.from_dir:
        pages = {s: (Path(args.from_dir) / f"{s}.html").read_text(encoding="utf-8") for s in SOURCE_URLS}
    else:
        pages = fetch_all()

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for source, html in pages.items():
        small = shrink(html)
        full, reduced = parse_source(source, html), parse_source(source, small)
        if snapshot_rows(full.records) != snapshot_rows(reduced.records) or full.unnamed != reduced.unnamed:
            print(f"{source}: shrinking changed the parse result; not writing", file=sys.stderr)
            return 1
        (FIXTURE_DIR / f"{source}.html").write_text(small, encoding="utf-8", newline="\n")
        print(f"{source}: {len(html):,} -> {len(small):,} bytes, {len(reduced.records)} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
