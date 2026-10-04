"""pallot-cache: check, refresh and prune what the server keeps in data/, from the host. The
Settings page only shows what's kept; refreshing or deleting it is this command's, run by whoever
runs Pallot:

    uv run pallot-cache check                         # what's kept, and what's past its lifetime
    docker compose exec pallot pallot-cache refresh   # the same commands, in the container

It opens the same cache and files as the server, so it can run while Pallot does: the server
reads a row's newer copy, a new precinct map and a new snapshot when they change on disk.
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from typing import Any, Callable, Collection

from .admin import Admin, SourceInfo
from .ballot import Services
from .config import load_config
from .http_cache import SavedRequest
from .services import open_services, prune
from .sources import RefreshFailed
from .text import display_size, display_time

COMMANDS = {
    "check": "List each source's saved copies, and those past their lifetime (stale). Changes nothing.",
    "refresh": "Soft refresh: fetch again only what's past its lifetime, and a map that's missing or that the "
               "portal lists a newer one of.",
    "prune": "Delete what's no use even as a fallback: expired address suggestions and street map tiles, addresses "
             "that weren't found, and the oldest tiles and suggestions past their caps; then shrink the file. "
             "Never deletes another source's copies.",
    "hard-refresh": "Fetch everything again, fresh or not, and refresh the TrackAIPAC, Vote for Peace and Texas "
                    "Ethics Commission snapshots (TEC's may download about 1 GB).",
    "rebuild": "Delete every saved copy and map, then fetch them all again, as a hard refresh does (or not, with "
               "--delete-only). The bundled snapshots aren't deleted, only refreshed, unless --reset-snapshots puts "
               "them back as they came with Pallot first.",
}
_SLOW = {"ballotpedia", "nominatim", "polls"}  # one request at a time when refreshing


def _plural(count: int, word: str) -> str:
    return f"{count:,} {word}{'' if count == 1 else 's'}"


class Maintenance:
    """The commands, over ``svc``, for the sources in ``only`` (their ids, as Settings lists
    them), or all of them. ``say`` gets each line as it's done; ``failed`` is set when anything
    couldn't be fetched. ``reset_snapshots``: a rebuild also resets the bundled snapshots.
    ``delete_only``: a rebuild deletes and fetches nothing; the next lookups fetch what they need."""

    def __init__(self, svc: Services, only: Collection[str] = (), say: Callable[[str], Any] = print,
                 *, reset_snapshots: bool = False, delete_only: bool = False):
        self.svc = svc
        self.admin = Admin(svc)
        known = [info.id for info in self.admin.sources]
        if unknown := sorted(set(only) - set(known)):
            raise ValueError(f"Unknown source {', '.join(unknown)}. The sources are: {', '.join(known)}.")
        self.selected = [info for info in self.admin.sources if not only or info.id in only]
        self.everything = not only
        self.say = say
        self.reset_snapshots = reset_snapshots
        self.delete_only = delete_only
        self.failed = False

    # -- check --------------------------------------------------------------------------------

    def check(self) -> None:
        for info in self.selected:
            self.say(f"{info.label} [{info.id}]")
            for line in self._state(info):
                self.say(f"  {line}")
        if self.everything:
            total = self.svc.cache.file_bytes() + sum(
                kept.size() for info in self.selected if (kept := self.admin.kept(info)))
            self.say(f"Everything kept takes {display_size(total)}.")

    def _state(self, info: SourceInfo) -> list[str]:
        if info.frozen:
            return ["A frozen list that came with Pallot: nothing to refresh or prune."]
        lines = []
        stats = [self.svc.cache.stats(tag) for tag in info.cache_tags]
        entries = sum(s.entries for s in stats)
        if info.cache_tags:
            if entries:
                oldest = min(s.oldest for s in stats if s.oldest is not None)
                newest = max(s.newest for s in stats if s.newest is not None)
                expired = sum(s.expired for s in stats)
                lines.append(" · ".join([
                    _plural(entries, "saved response"),
                    display_size(sum(s.bytes for s in stats)),
                    f"{expired:,} stale" if expired else "none stale",
                    f"fetched {display_time(oldest)} to {display_time(newest)}",
                ]))
            else:
                lines.append("Nothing saved.")
            if not info.refreshable:
                lines.append("Only fetched as it's used: pruned, never refreshed.")
        if paused := self.admin.paused(info):
            lines.append(paused)
        if kept := self.admin.kept(info):
            lines += [f"{fact.label}: {fact.value}" for fact in kept.details()]
            if why := kept.stale():
                lines.append(f"Stale: {why}.")
        return lines

    # -- refresh ------------------------------------------------------------------------------

    async def refresh(self, *, hard: bool) -> None:
        for info in self.selected:
            if info.frozen or not info.refreshable:
                continue
            self.say(await self._refresh(info, hard=hard))

    async def _refresh(self, info: SourceInfo, *, hard: bool, saved: dict[str, list[SavedRequest]] | None = None) -> str:
        """Its cached responses (all of them, the expired ones, or ``saved`` after a rebuild's
        delete), then what it keeps in files: always with ``hard``, else when it's stale."""
        parts: list[str] = []
        refreshed = failed = skipped = 0
        errors: list[str] = []
        paused_until: float | None = None
        for tag in info.cache_tags:
            report = await self.svc.cache.refresh(
                tag, concurrency=1 if tag in _SLOW else 3, expired_only=not hard,
                saved=None if saved is None else saved.get(tag, []),
            )
            refreshed += report.refreshed
            failed += report.failed
            skipped += report.skipped
            errors += report.errors
            paused_until = paused_until or report.paused_until
        if info.cache_tags and (refreshed or hard):
            parts.append(f"Refreshed {_plural(refreshed, 'saved response')}.")
        kept = self.admin.kept(info)
        if kept and (hard or kept.stale()):
            try:
                parts.append(await kept.refresh())
            except RefreshFailed as exc:
                self.failed = True
                parts.append(str(exc))
        if failed:
            self.failed = True
            parts.append(f"{failed} failed and kept their old copy ({'; '.join(errors)}).")
        if paused_until:
            parts.append(f"It's paused until {display_time(paused_until)} after refusing a request"
                         + (f", so {skipped} weren't asked." if skipped else "."))
        return f"{info.label}: {' '.join(parts) or 'nothing past its lifetime.'}"

    # -- prune --------------------------------------------------------------------------------

    def prune(self) -> None:
        before = self.svc.cache.file_bytes()
        removed = prune(self.svc.cache, self.svc.config)
        after = self.svc.cache.file_bytes()
        self.say(f"Pruned {_plural(removed, 'saved response')}; the cache went from {display_size(before)} to "
                 f"{display_size(after)}.")

    # -- rebuild ------------------------------------------------------------------------------

    async def rebuild(self) -> None:
        """Note every saved request, delete them all (with the pauses and failure flags, when
        it's everything) and the maps, then ask them all again. Tiles and suggestions are only
        deleted: they're fetched again as they're used. The bundled snapshots are only refreshed,
        unless ``reset_snapshots``. With ``delete_only``, nothing is fetched."""
        cache = self.svc.cache
        saved = {tag: cache.saved(tag) for info in self.selected if info.refreshable for tag in info.cache_tags}
        if self.everything:
            removed = cache.clear()
        else:
            removed = sum(cache.clear(tag) for info in self.selected for tag in info.cache_tags)
        cleared = []
        for info in self.selected:
            kept = self.admin.kept(info)
            if kept and not info.frozen and (self.reset_snapshots or not info.bundled):
                kept.clear()
                cleared.append(info.label)
        self.say(f"Deleted {_plural(removed, 'saved response')}"
                 + (f", and what {', '.join(cleared)} kept in files." if cleared else "."))
        if self.delete_only:
            return
        for info in self.selected:
            if info.refreshable and not info.frozen:
                self.say(await self._refresh(info, hard=True, saved=saved))


async def run(command: str, only: Collection[str] = (), say: Callable[[str], Any] = print, *,
              reset_snapshots: bool = False, delete_only: bool = False, **options: Any) -> int:
    """One command, on services made as the server makes them (``options``: open_services'
    arguments, the config included); the exit status."""
    config = options.pop("config", None) or load_config()
    async with open_services(config, tidy=False, **options) as svc:
        try:
            jobs = Maintenance(svc, only, say, reset_snapshots=reset_snapshots, delete_only=delete_only)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 2
        try:
            if command == "check":
                jobs.check()
            elif command == "prune":
                jobs.prune()
            elif command == "rebuild":
                await jobs.rebuild()
            else:
                await jobs.refresh(hard=command == "hard-refresh")
        except sqlite3.OperationalError as exc:  # the server holding the database, for a VACUUM
            print(f"The cache is busy ({exc}); try again in a moment.", file=sys.stderr)
            return 1
    return 1 if jobs.failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pallot-cache",
        description="Check, refresh and prune what Pallot keeps in its data folder (PALLOT_DATA_DIR). "
                    "It can run while Pallot does.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    for name, text in COMMANDS.items():
        sub = commands.add_parser(name, help=text, description=text)
        if name != "prune":
            sub.add_argument("--only", nargs="+", default=[], metavar="SOURCE",
                             help="just these sources, by the ids check shows in brackets (sos, fec, …)")
        if name == "rebuild":
            sub.add_argument("--yes", action="store_true", help="don't ask first")
            sub.add_argument("--reset-snapshots", action="store_true",
                             help="put the TrackAIPAC, Vote for Peace and TEC snapshots back as they came with Pallot "
                                  "before refreshing them")
            sub.add_argument("--delete-only", action="store_true",
                             help="delete, and fetch nothing again: the next lookups fetch what they need (to erase "
                                  "the addresses saved, say)")
    args = parser.parse_args(argv)
    if args.command == "rebuild" and not args.yes:
        scope = ", ".join(args.only) if args.only else "every source"
        then = "" if args.delete_only else " and fetch it all again"
        answer = input(f"Delete everything saved from {scope}{then}? This can't be undone. [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Nothing was deleted.")
            return 1
    return asyncio.run(run(args.command, getattr(args, "only", []), reset_snapshots=getattr(args, "reset_snapshots", False),
                           delete_only=getattr(args, "delete_only", False)))


if __name__ == "__main__":
    sys.exit(main())
