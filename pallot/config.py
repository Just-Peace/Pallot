"""Settings that come from the environment (or the project's .env file): where data lives,
timeouts, cache lifetimes, the FEC key."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Mapping

HOUR = 3600
DAY = 24 * HOUR

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"
DEMO_KEY = "DEMO_KEY"  # api.data.gov's shared key: a few requests an hour, per IP address


@dataclass(frozen=True)
class Ttls:
    """Cache lifetimes in seconds. Override any of them with PALLOT_TTL_<NAME>,
    e.g. PALLOT_TTL_SOS_BALLOT_ORDER=3600."""

    sos_reference: int = 30 * DAY  # counties, parties, status codes
    sos_elections: int = DAY
    sos_ballot_order: int = DAY
    sos_candidates: int = DAY  # the statewide candidate list, one per election
    sos_empty: int = 6 * HOUR  # an empty ballot order may fill in later
    sos_backoff: int = HOUR  # after Texas SOS refuses us, stop asking for this long
    past_election: int = 365 * DAY  # anything about an election that already happened
    geocode: int = 30 * DAY
    geocode_miss: int = DAY
    geocode_backoff: int = HOUR  # after the Census geocoder or Nominatim refuses us, stop asking that one for this long
    suggest: int = 30 * DAY  # address suggestions as you type
    suggest_backoff: int = HOUR  # after Ballotpedia refuses an address search, stop asking for this long
    ballotpedia: int = DAY
    ballotpedia_backoff: int = HOUR  # after Ballotpedia refuses us, stop asking for this long
    fec: int = 7 * DAY  # campaign finance: new FEC reports come every few weeks
    fec_backoff: int = HOUR  # after the FEC's rate limit, stop asking for this long
    polls: int = DAY  # FiftyPlusOne's poll lists: new polls come every few days
    polls_backoff: int = HOUR  # after FiftyPlusOne refuses us, stop asking for this long
    key_dates: int = DAY  # the Texas SOS's page of each election's deadlines
    key_dates_backoff: int = HOUR  # after that page is refused us, stop asking for this long
    outlines: int = 30 * DAY  # TIGERweb's district outlines for the map, as long as the geocoder's districts
    outlines_backoff: int = HOUR  # after TIGERweb refuses us, stop asking for this long
    tiles: int = 7 * DAY  # OpenStreetMap's map tiles: its tile usage policy asks for at least 7 days
    tiles_backoff: int = HOUR  # after OpenStreetMap's tile server refuses us, stop asking for this long
    election_precincts: int = 7 * DAY  # the TLC portal's list of precinct maps: a new one comes after each statewide election
    election_precincts_backoff: int = HOUR  # after the TLC portal refuses us, stop asking for this long
    county_precincts: int = 7 * DAY  # counties' lists of their election precincts and maps of commissioner and JP precincts
    county_precincts_backoff: int = HOUR  # after a county's map server refuses us, stop asking them for this long
    retry_after: int = 15 * 60  # after a failed request, serve its old copy this long before asking again
    prune_after: int = 30 * DAY  # at startup, delete suggestions and addresses not found that expired this long ago


@dataclass(frozen=True)
class Config:
    data_dir: Path = PROJECT_DIR / "data"
    # Names Pallot to every source; OpenStreetMap's tile policy asks for a way to reach it too.
    user_agent: str = "Pallot/0.1 (personal ballot helper; +https://github.com/Just-Peace/Pallot)"
    http_timeout: float = 30.0
    ttl: Ttls = field(default_factory=Ttls)
    # A free key from https://api.open.fec.gov/developers/ (issued by api.data.gov); without
    # one, the shared DEMO_KEY. Only ever sent to the FEC, never written to disk.
    fec_api_key: str = field(default=DEMO_KEY, repr=False)
    # Names Pallot answers to besides localhost and IP addresses, such as a LAN name or a
    # reverse proxy's domain ("*": any). Other names are refused, against DNS rebinding.
    allowed_hosts: tuple[str, ...] = ()

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
    def election_precincts_dir(self) -> Path:
        return self.data_dir / "election_precincts"

    @property
    def trackaipac_dir(self) -> Path:
        return self.data_dir / "trackaipac"

    @property
    def tec_dir(self) -> Path:
        return self.data_dir / "tec"

    @property
    def voteforpeace_dir(self) -> Path:
        return self.data_dir / "voteforpeace"


def read_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE lines of a .env file ("#" comments, optional quotes and "export"); {} if
    there is no file."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    values = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()  # a comment after an unquoted value
        values[key.strip()] = value
    return values


def load_config(env: Mapping[str, str] | None = None, *, env_file: Path | None = ENV_FILE) -> Config:
    """The config from ``env``, or by default from the environment on top of ``env_file``
    (variables already set in the environment win). The tiles' lifetime is kept at 7 days or more,
    the least OpenStreetMap's tile policy allows."""
    if env is None:
        env = {**(read_env_file(env_file) if env_file else {}), **os.environ}
    overrides = {
        f.name: int(env[key]) for f in fields(Ttls) if (key := f"PALLOT_TTL_{f.name.upper()}") in env
    }
    if "tiles" in overrides:
        overrides["tiles"] = max(overrides["tiles"], 7 * DAY)
    return Config(
        data_dir=Path(env["PALLOT_DATA_DIR"]) if env.get("PALLOT_DATA_DIR") else Config.data_dir,
        user_agent=env.get("PALLOT_USER_AGENT") or Config.user_agent,
        http_timeout=float(env.get("PALLOT_HTTP_TIMEOUT") or Config.http_timeout),
        ttl=Ttls(**overrides),
        fec_api_key=(env.get("PALLOT_FEC_API_KEY") or "").strip() or DEMO_KEY,
        allowed_hosts=tuple(
            name.strip().lower() for name in (env.get("PALLOT_ALLOWED_HOSTS") or "").split(",") if name.strip()
        ),
    )
