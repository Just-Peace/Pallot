"""Settings that come from the environment: where data lives, timeouts, cache lifetimes."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Mapping

HOUR = 3600
DAY = 24 * HOUR

PROJECT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Ttls:
    """Cache lifetimes in seconds. Override any of them with VOTEBOT_TTL_<NAME>,
    e.g. VOTEBOT_TTL_SOS_BALLOT_ORDER=3600."""

    sos_reference: int = 30 * DAY  # counties, parties, status codes
    sos_elections: int = DAY
    sos_ballot_order: int = DAY
    sos_candidates: int = DAY  # the statewide candidate list, one per election
    sos_empty: int = 6 * HOUR  # an empty ballot order may fill in later
    past_election: int = 365 * DAY  # anything about an election that already happened
    geocode: int = 30 * DAY
    geocode_miss: int = DAY
    ballotpedia: int = DAY
    ballotpedia_backoff: int = HOUR  # after Ballotpedia refuses us, stop asking for this long


@dataclass(frozen=True)
class Config:
    data_dir: Path = PROJECT_DIR / "data"
    user_agent: str = "VoteBot/0.1 (personal ballot helper)"
    http_timeout: float = 30.0
    ttl: Ttls = field(default_factory=Ttls)

    @property
    def cache_path(self) -> Path:
        return self.data_dir / "cache.sqlite3"

    @property
    def settings_path(self) -> Path:
        return self.data_dir / "settings.json"

    @property
    def sboe_path(self) -> Path:
        return self.data_dir / "plane2106_kml.zip"

    @property
    def trackaipac_dir(self) -> Path:
        return self.data_dir / "trackaipac"


def load_config(env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    overrides = {
        f.name: int(env[key]) for f in fields(Ttls) if (key := f"VOTEBOT_TTL_{f.name.upper()}") in env
    }
    return Config(
        data_dir=Path(env["VOTEBOT_DATA_DIR"]) if env.get("VOTEBOT_DATA_DIR") else Config.data_dir,
        user_agent=env.get("VOTEBOT_USER_AGENT") or Config.user_agent,
        http_timeout=float(env.get("VOTEBOT_HTTP_TIMEOUT") or Config.http_timeout),
        ttl=Ttls(**overrides),
    )
