"""Exception hierarchy for trackaipac_cache."""

from __future__ import annotations


class TrackAipacCacheError(Exception):
    """Base class for every error raised by this package."""


class FetchError(TrackAipacCacheError):
    """A source page could not be downloaded."""


class ValidationError(TrackAipacCacheError):
    """Parsed data failed the pre-write sanity checks; nothing was written."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__("refresh aborted, parsed data failed validation:\n  - " + "\n  - ".join(self.problems))


class AmbiguousNameError(TrackAipacCacheError, LookupError):
    """A name lookup matched more than one candidate; use a candidate_id instead."""

    def __init__(self, query: str, candidate_ids: list[str]):
        self.query = query
        self.candidate_ids = list(candidate_ids)
        super().__init__(f"{query!r} matches several candidates: {', '.join(self.candidate_ids)}")
