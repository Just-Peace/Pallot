"""Which commit this copy of VoteBot runs, for the footer. A checkout's comes from its ``.git``,
read without running git; the Docker image has no ``.git``, so its build writes the hash into
the installed package (``python -m votebot.version /app``)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PACKAGE = Path(__file__).parent
BAKED = PACKAGE / "COMMIT"
HASH = re.compile(r"[0-9a-f]{40}")


def git_commit(root: Path) -> str | None:
    """The full hash of the commit ``root``'s checkout is at, or None outside one."""
    git = root / ".git"
    try:
        if git.is_file():  # a worktree: .git names its own folder, and the refs are shared
            git = root / git.read_text().split(":", 1)[1].strip()
        common = git / (git / "commondir").read_text().strip() if (git / "commondir").is_file() else git
        head = (git / "HEAD").read_text().strip()
        if not head.startswith("ref: "):
            return head if HASH.fullmatch(head) else None
        ref = head[5:]
        if (common / ref).is_file():
            found = (common / ref).read_text().strip()
        else:
            found = next((line.split()[0] for line in (common / "packed-refs").read_text().splitlines()
                          if line.endswith(" " + ref)), "")
    except (OSError, IndexError):
        return None
    return found if HASH.fullmatch(found) else None


def short_commit() -> str | None:
    """The running commit's short hash, as ``git describe`` shows it, or None when it's unknown."""
    full = BAKED.read_text().strip() if BAKED.is_file() else git_commit(PACKAGE.parent)
    return full[:7] if full and HASH.fullmatch(full) else None


if __name__ == "__main__":
    if full := git_commit(Path(sys.argv[1])):
        BAKED.write_text(full + "\n")
