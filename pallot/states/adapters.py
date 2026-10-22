"""Every state with an adapter for its official list, by postal code. A state added here also
needs its entry in coverage.COVERED and its switch in sources.toml."""

from __future__ import annotations

from ..config import Ttls
from ..http_cache import HttpCache
from . import StateList
from .ca import CaList
from .az import AzList
from .fl import FlList
from .mi import MiList
from .nc import NcList
from .pa import PaList
from .va import VaList

ADAPTERS: dict[str, type[StateList]] = {cls.state: cls for cls in (NcList, MiList, PaList, FlList, VaList, CaList, AzList)}


def open_lists(cache: HttpCache, ttl: Ttls) -> dict[str, StateList]:
    return {state: cls(cache, ttl) for state, cls in ADAPTERS.items()}
