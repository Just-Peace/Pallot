"""CLI: fec-cache refresh [--force] [--dry-run] [--data-dir DIR]"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fec-cache")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("refresh", help="ask the FEC what Texas's federal races need, and update the snapshot if it changed")
    cmd.add_argument("--force", action="store_true", help="write the snapshot even if nothing changed")
    cmd.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    cmd.add_argument("--data-dir", metavar="DIR", help="snapshot directory (default: the bundled package data)")
    args = parser.parse_args(argv)

    from .refresh import RefreshError, refresh  # imports Pallot, which reads this package at startup

    try:
        result = refresh(force=args.force, dry_run=args.dry_run, data_dir=args.data_dir)
    except RefreshError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(result.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
