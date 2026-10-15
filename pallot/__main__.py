"""python -m pallot [--port PALLOT_PORT] [--reload] -> serve the app on http://127.0.0.1:8000."""

from __future__ import annotations

import argparse
import sys

import uvicorn

from .config import BadConfig, load_config


def main(argv: list[str] | None = None) -> None:
    try:
        config = load_config()
    except BadConfig as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2) from None
    parser = argparse.ArgumentParser(prog="pallot", description="Personal ballot helper")
    parser.add_argument("--host", default=config.host, help="keep 127.0.0.1: Pallot has no login")
    parser.add_argument("--port", type=int, default=config.port, help="default: PALLOT_PORT, or 8000")
    parser.add_argument("--reload", action="store_true", help="restart on code changes (development)")
    args = parser.parse_args(argv)
    watch = {"reload_includes": ["*.py", "*.js", "*.css", "*.html", "*.svg"]} if args.reload else {}
    uvicorn.run("pallot.api:create_app", factory=True, host=args.host, port=args.port, reload=args.reload,
                server_header=False, forwarded_allow_ips=config.trusted_proxies, **watch)


if __name__ == "__main__":
    main()
