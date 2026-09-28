"""Exception hierarchy for tec_cache."""

from __future__ import annotations


class TecCacheError(Exception):
    """Base class for every error raised by this package."""


class FetchError(TecCacheError):
    """TEC's zip, or part of it, could not be read."""


class BlockedError(FetchError):
    """TEC's download server refused us (HTTP 403 or 429). Its CloudFront blocks bursts of
    requests, so wait a few hours, or download the zip in a browser and use --zip."""


class ZipChangedError(FetchError):
    """TEC replaced the zip while it was being read; nothing was written. Run it again."""


class ValidationError(TecCacheError):
    """The data failed the pre-write checks; nothing was written."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__("refresh aborted, TEC data failed validation:\n  - " + "\n  - ".join(self.problems))
