"""Every state with an adapter for its official list, by postal code. A state added here also
needs its entry in coverage.COVERED and its switch in sources.toml."""

from __future__ import annotations

from ..config import Ttls
from ..http_cache import HttpCache
from . import StateList
from .ak import AkList
from .ca import CaList
from .az import AzList
from .co import CoList
from .fl import FlList
from .ga import GaList
from .ia import IaList
from .il import IlList
from .me import MeList
from .mi import MiList
from .nc import NcList
from .ne import NeList
from .nj import NjList
from .nm import NmList
from .nv import NvList
from .ny import NyList
from .oh import OhList
from .pa import PaList
from .va import VaList
from .wi import WiList
from .wy import WyList

ADAPTERS: dict[str, type[StateList]] = {
    cls.state: cls for cls in (NcList, MiList, PaList, FlList, VaList, CaList, AzList, NvList, GaList, WiList, OhList,
                             IaList, NjList, NyList, CoList, WyList, IlList,
                             AkList, MeList, NeList, NmList)
}


def open_lists(cache: HttpCache, ttl: Ttls) -> dict[str, StateList]:
    return {state: cls(cache, ttl) for state, cls in ADAPTERS.items()}
