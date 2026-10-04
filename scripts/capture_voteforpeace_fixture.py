"""Capture the Vote for Peace test page into tests/voteforpeace/fixtures/candidates.html.

    python scripts/capture_voteforpeace_fixture.py              # fetch the live page (one request)
    python scripts/capture_voteforpeace_fixture.py --from raw   # reuse raw/candidates.html

The page (about 7 MB) is shrunk to its Next.js data alone, with every Texas candidate and the
first of each other state's, split over two scripts as the site splits it. The fixture is
only written if the parser reads exactly those candidates from it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voteforpeace_cache.fetch import fetch_page  # noqa: E402
from voteforpeace_cache.parser import parse_page, payload  # noqa: E402

FIXTURE = ROOT / "tests" / "voteforpeace" / "fixtures" / "candidates.html"
KEEP_ALL = "TX"


def _script(text: str) -> str:
    return f"<script>self.__next_f.push([1,{json.dumps(text).replace('<', chr(92) + 'u003c')}])</script>"


def shrink(page: str) -> str:
    text = payload(page)
    start = text.index('{"sections":[')
    found, end = json.JSONDecoder().raw_decode(text, start)
    for section in found["sections"]:
        if section.get("key") != KEEP_ALL:
            section["candidates"] = section["candidates"][:1]
        section.pop("header", None)  # the state's dates and rules, drawn as page elements
    small = text[:start] + json.dumps(found, ensure_ascii=False, separators=(",", ":")) + text[end:]
    half = len(small) // 2
    return "<!DOCTYPE html><html><body>\n" + _script(small[:half]) + "\n" + _script(small[half:]) + "\n</body></html>\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_dir", help="read candidates.html from this directory instead of fetching")
    args = ap.parse_args()
    page = (Path(args.from_dir) / "candidates.html").read_text(encoding="utf-8") if args.from_dir else fetch_page()

    small = shrink(page)
    full = parse_page(page).records
    kept = [r.snapshot_row() for r in parse_page(small).records]
    seen: set[str] = set()
    expected = []
    for record in full:
        first = record.section not in seen
        seen.add(record.section)
        if record.state == KEEP_ALL or first:
            expected.append(record.snapshot_row())
    if kept != expected:
        print("shrinking changed the parse result; not writing", file=sys.stderr)
        return 1
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(small, encoding="utf-8", newline="\n")
    print(f"{len(page):,} -> {len(small):,} bytes, {len(kept)} candidates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
