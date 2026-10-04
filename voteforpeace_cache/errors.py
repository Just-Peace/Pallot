"""Exception hierarchy for voteforpeace_cache."""

from __future__ import annotations


class VoteForPeaceCacheError(Exception):
    """Base class for every error raised by this package."""


class FetchError(VoteForPeaceCacheError):
    """The page could not be downloaded."""


class ParseError(VoteForPeaceCacheError):
    """The page doesn't hold the candidate list where it used to."""


class ValidationError(VoteForPeaceCacheError):
    """Parsed data failed the pre-write sanity checks; nothing was written."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__("refresh aborted, parsed data failed validation:\n  - " + "\n  - ".join(self.problems))
