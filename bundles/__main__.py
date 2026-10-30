"""CLI: pallot-bundle refresh [--only BUNDLE …] [--due] [--force] [--dry-run] [--data-dir DIR]
     pallot-bundle import-list STATE FILE [--data-dir DIR]
     pallot-bundle stats [--since REF] [--readme PATH]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    from .registry import BUNDLES

    parser = argparse.ArgumentParser(prog="pallot-bundle")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("refresh", help="ask each source what a lookup would, and update its bundle if it changed")
    cmd.add_argument("--only", nargs="+", metavar="BUNDLE", choices=[entry.name for entry in BUNDLES],
                     help="just these bundles: " + ", ".join(entry.name for entry in BUNDLES))
    cmd.add_argument("--due", action="store_true", help="skip a source checked more recently than its cadence (daily, weekly)")
    cmd.add_argument("--force", action="store_true", help="write the answers even if nothing changed")
    cmd.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    cmd.add_argument("--data-dir", metavar="DIR", help="bundle directory (default: the package's data)")
    imp = sub.add_parser("import-list", help="bundle a state's list of candidates saved by hand (its site blocks scripts)")
    imp.add_argument("state", metavar="STATE", help="the state's postal code, e.g. az")
    imp.add_argument("file", metavar="FILE", type=Path, help="the page or answer saved from the state's site (Tennessee's: the folder of its spreadsheets)")
    imp.add_argument("--data-dir", metavar="DIR", help="bundle directory (default: the package's data)")
    st = sub.add_parser("stats", help="print each bundled snapshot's counts as a Markdown table")
    st.add_argument("--since", metavar="REF", help="show each figure's change since this git ref (e.g. HEAD)")
    st.add_argument("--readme", metavar="PATH", type=Path, help="also write the table into this file's source-stats section")
    args = parser.parse_args(argv)

    if args.command == "stats":
        from .stats import stats, write_readme

        lines = stats(since=args.since)
        if args.readme:
            write_readme(args.readme, lines)
        print("\n".join(lines))
        return 0

    if args.command == "import-list":
        from .entry import BundleError
        from .manual import import_list

        try:
            outcome = import_list(args.state, args.file, data_dir=args.data_dir)
        except BundleError as exc:
            print(f"Not imported: {exc}.", file=sys.stderr)
            return 2
        print(outcome.summary())
        return 0

    from .refresh import refresh

    outcomes = refresh(args.only or (), due=args.due, force=args.force, dry_run=args.dry_run, data_dir=args.data_dir)
    for outcome in outcomes:
        print(outcome.summary(), file=sys.stderr if outcome.status == "failed" else sys.stdout)
    return 2 if any(outcome.status == "failed" for outcome in outcomes) else 0


if __name__ == "__main__":
    sys.exit(main())
