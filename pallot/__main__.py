"""python -m pallot [--port PALLOT_PORT] [--reload] -> serve the app on http://127.0.0.1:8000."""

from __future__ import annotations

import argparse

import uvicorn

from .config import load_config


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pallot", description="Personal ballot helper")
    parser.add_argument("--host", default=load_config().host, help="keep 127.0.0.1: Pallot has no login")
    parser.add_argument("--port", type=int, default=load_config().port, help="default: PALLOT_PORT, or 8000")
    parser.add_argument("--reload", action="store_true", help="restart on code changes (development)")
    args = parser.parse_args(argv)
    uvicorn.run("pallot.api:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
