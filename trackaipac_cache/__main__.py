"""CLI: python -m trackaipac_cache refresh [--force] [--dry-run] [--save-raw DIR] [--data-dir DIR]"""

from __future__ import annotations

import argparse
import sys

from .errors import TrackAipacCacheError
from .refresh import refresh


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trackaipac_cache")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("refresh", help="fetch trackaipac.com and update the cache if anything changed")
    cmd.add_argument("--force", action="store_true", help="write a snapshot even if nothing changed")
    cmd.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    cmd.add_argument("--save-raw", metavar="DIR", help="also save the fetched HTML pages to DIR")
    cmd.add_argument("--data-dir", metavar="DIR", help="cache directory (default: bundled package data)")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        result = refresh(force=args.force, dry_run=args.dry_run, data_dir=args.data_dir, raw_dir=args.save_raw)
    except TrackAipacCacheError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(result.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
