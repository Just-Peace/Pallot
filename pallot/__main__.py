"""python -m pallot [--port 8000] [--reload] -> serve the app on http://127.0.0.1:8000."""

from __future__ import annotations

import argparse

import uvicorn


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pallot", description="Personal ballot helper")
    parser.add_argument("--host", default="127.0.0.1", help="keep 127.0.0.1: the Settings actions have no login")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="restart on code changes (development)")
    args = parser.parse_args(argv)
    uvicorn.run("pallot.api:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
