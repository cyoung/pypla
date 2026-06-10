"""pypla — monitor TP-Link / Broadcom (BCM60500) powerline adapters at raw L2.

Reimplements the pla-util management transactions in Python (scapy), so no
pla-util binary and no SSH hop are needed. Typical use:

    from pypla import Net, collect

    net = Net("en0")                     # raw L2 needs root / BPF access
    for adapter in collect(net, full=True):
        for peer in adapter.stations:
            print(peer.mac, peer.tx_mbps, peer.rx_mbps)
"""

from .api import (
    collect,
    discover,
    query_network_info,
    query_station_info,
    query_stations,
    to_dict,
)
from .protocol import Adapter, NetworkInfo, Station, StationInfo
from .transport import Net

__version__ = "0.1.0"

__all__ = [
    "Adapter",
    "Net",
    "NetworkInfo",
    "Station",
    "StationInfo",
    "collect",
    "discover",
    "query_network_info",
    "query_station_info",
    "query_stations",
    "to_dict",
    "__version__",
]
