"""CLI: pallot-bundle refresh [--only BUNDLE …] [--due] [--force] [--dry-run] [--data-dir DIR]"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    from .registry import BUNDLES
    from .refresh import refresh

    parser = argparse.ArgumentParser(prog="pallot-bundle")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("refresh", help="ask each source what a lookup would, and update its bundle if it changed")
    cmd.add_argument("--only", nargs="+", metavar="BUNDLE", choices=[entry.name for entry in BUNDLES],
                     help="just these bundles: " + ", ".join(entry.name for entry in BUNDLES))
    cmd.add_argument("--due", action="store_true", help="skip a source checked more recently than its cadence (daily, weekly)")
    cmd.add_argument("--force", action="store_true", help="write the answers even if nothing changed")
    cmd.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    cmd.add_argument("--data-dir", metavar="DIR", help="bundle directory (default: the package's data)")
    args = parser.parse_args(argv)

    outcomes = refresh(args.only or (), due=args.due, force=args.force, dry_run=args.dry_run, data_dir=args.data_dir)
    for outcome in outcomes:
        print(outcome.summary(), file=sys.stderr if outcome.status == "failed" else sys.stdout)
    return 2 if any(outcome.status == "failed" for outcome in outcomes) else 0


if __name__ == "__main__":
    sys.exit(main())
