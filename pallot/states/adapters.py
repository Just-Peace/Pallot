"""Every state with an adapter for its official list, by postal code. A state added here also
needs its entry in coverage.COVERED and its switch in sources.toml."""

from __future__ import annotations

from ..config import Ttls
from ..http_cache import HttpCache
from . import StateList
from .ca import CaList
from .az import AzList
from .fl import FlList
from .ga import GaList
from .ia import IaList
from .mi import MiList
from .nc import NcList
from .nj import NjList
from .nv import NvList
from .oh import OhList
from .pa import PaList
from .va import VaList
from .wi import WiList

ADAPTERS: dict[str, type[StateList]] = {
    cls.state: cls for cls in (NcList, MiList, PaList, FlList, VaList, CaList, AzList, NvList, GaList, WiList, OhList,
                             IaList, NjList)
}


def open_lists(cache: HttpCache, ttl: Ttls) -> dict[str, StateList]:
    return {state: cls(cache, ttl) for state, cls in ADAPTERS.items()}
