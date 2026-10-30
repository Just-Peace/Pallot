"""Every state with an adapter for its official list, by postal code. A state added here also
needs its entry in coverage.COVERED and its switch in sources.toml."""

from __future__ import annotations

from ..config import Ttls
from ..http_cache import HttpCache
from . import StateList
from .ak import AkList
from .ar import ArList
from .ca import CaList
from .az import AzList
from .co import CoList
from .de import DeList
from .fl import FlList
from .ga import GaList
from .hi import HiList
from .ia import IaList
from .il import IlList
from .in_ import InList
from .ks import KsList
from .ky import KyList
from .la import LaList
from .ma import MaList
from .md import MdList
from .me import MeList
from .mi import MiList
from .mn import MnList
from .mo import MoList
from .ms import MsList
from .mt import MtList
from .nc import NcList
from .nd import NdList
from .ne import NeList
from .nh import NhList
from .nj import NjList
from .nm import NmList
from .nv import NvList
from .ny import NyList
from .oh import OhList
from .ok import OkList
from .or_ import OrList
from .pa import PaList
from .sc import ScList
from .sd import SdList
from .tn import TnList
from .ut import UtList
from .vt import VtList
from .va import VaList
from .wa import WaList
from .wi import WiList
from .wy import WyList

ADAPTERS: dict[str, type[StateList]] = {
    cls.state: cls for cls in (NcList, MiList, PaList, FlList, VaList, CaList, AzList, NvList, GaList, WiList, OhList,
                             IaList, NjList, NyList, CoList, WyList, IlList,
                             AkList, MeList, NeList, NmList, WaList, InList, MdList, MoList, ScList, KyList,
                             OkList, KsList, MtList, SdList, HiList, NdList, DeList, VtList, MsList, ArList,
                             MnList, NhList, TnList, MaList, LaList, OrList, UtList)
}


def open_lists(cache: HttpCache, ttl: Ttls) -> dict[str, StateList]:
    return {state: cls(cache, ttl) for state, cls in ADAPTERS.items()}
