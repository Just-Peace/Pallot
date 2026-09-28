"""CLI: python -m tec_cache refresh [--force] [--dry-run] [--data-dir DIR] [--zip PATH] [--pause SECONDS]"""

from __future__ import annotations

import argparse
import sys

from .errors import TecCacheError
from .refresh import refresh


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tec_cache")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("refresh", help="read TEC's campaign finance export and update the snapshot if anything changed")
    cmd.add_argument("--force", action="store_true", help="rebuild and write even if nothing changed")
    cmd.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    cmd.add_argument("--data-dir", metavar="DIR", help="snapshot directory (default: the bundled package data)")
    cmd.add_argument("--zip", metavar="PATH", help="a TEC_CF_CSV.zip downloaded in a browser, instead of downloading")
    cmd.add_argument("--pause", type=float, default=10.0, metavar="SECONDS", help="between download requests (default 10)")
    cmd.add_argument("--user-agent", metavar="TEXT", help="User-Agent for the download")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        result = refresh(
            force=args.force, dry_run=args.dry_run, data_dir=args.data_dir, zip_path=args.zip,
            pause=args.pause, user_agent=args.user_agent,
        )
    except TecCacheError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(result.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
