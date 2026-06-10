"""High-level operations: discover adapters and query them for stats/info."""

from __future__ import annotations

import time
from dataclasses import asdict

from .protocol import (
    BROADCAST,
    DISCOVER_LIST_CNF,
    DISCOVER_LIST_REQ,
    ETH_HOMEPLUG,
    ETH_MEDIAXTREAM,
    MEDIAXTREAM_CNF,
    MEDIAXTREAM_DISCOVER_REQ,
    NETWORK_INFO_CNF,
    NETWORK_INFO_REQ,
    NETWORK_STATS_CNF,
    NETWORK_STATS_REQ,
    STATION_INFO_CNF,
    STATION_INFO_REQ,
    Adapter,
    NetworkInfo,
    Station,
    StationInfo,
    parse_discover_list,
    parse_network_info,
    parse_network_stats,
    parse_station_info,
    printable,
)
from .transport import Net


def discover(net: Net) -> list[Adapter]:
    """Broadcast a Mediaxtream discover; return responding local adapters."""
    adapters: dict[str, Adapter] = {}
    for smac, _et, pl in net.transact(BROADCAST, ETH_MEDIAXTREAM,
                                      MEDIAXTREAM_DISCOVER_REQ):
        if pl[:3] == MEDIAXTREAM_CNF:
            adapters.setdefault(smac, Adapter(mac=smac, version=printable(pl)))
    return list(adapters.values())


def query_stations(net: Net, adapter_mac: str) -> list[Station]:
    """Per-peer TX/RX PHY rates merged with discover-list fields, by peer MAC."""
    stations: dict[str, Station] = {}

    for smac, _et, pl in net.transact(adapter_mac, ETH_MEDIAXTREAM,
                                      NETWORK_STATS_REQ):
        if smac == adapter_mac and pl[:9] == NETWORK_STATS_CNF:
            for s in parse_network_stats(pl):
                stations[s.mac] = s
            break

    for smac, _et, pl in net.transact(adapter_mac, ETH_HOMEPLUG,
                                      DISCOVER_LIST_REQ):
        if smac == adapter_mac and pl[:2] == DISCOVER_LIST_CNF:
            for mac, f in parse_discover_list(pl).items():
                st = stations.setdefault(mac, Station(mac=mac))
                st.tei, st.snid = f["tei"], f["snid"]
                st.same_network, st.cco = f["same_network"], f["cco"]
                st.signal_level = f["signal_level"]
            break

    return list(stations.values())


def query_station_info(net: Net, mac: str) -> StationInfo | None:
    for smac, _et, pl in net.transact(mac, ETH_MEDIAXTREAM, STATION_INFO_REQ):
        if smac == mac and pl[:9] == STATION_INFO_CNF:
            return parse_station_info(pl)
    return None


def query_network_info(net: Net, mac: str) -> list[NetworkInfo]:
    for smac, _et, pl in net.transact(mac, ETH_MEDIAXTREAM, NETWORK_INFO_REQ):
        if smac == mac and pl[:9] == NETWORK_INFO_CNF:
            return parse_network_info(pl)
    return []


def collect(net: Net, adapter_mac: str | None = None,
            full: bool = False) -> list[Adapter]:
    """Snapshot one adapter (or all discovered ones) with peer stations.

    With full=True, also fetch station-info and network-info per adapter.
    """
    adapters = ([Adapter(mac=adapter_mac.lower())] if adapter_mac
                else discover(net))
    for a in adapters:
        a.stations = query_stations(net, a.mac)
        if full:
            a.station_info = query_station_info(net, a.mac)
            a.networks = query_network_info(net, a.mac)
    return adapters


def to_dict(adapters: list[Adapter]) -> dict:
    """JSON-serializable snapshot of a list of adapters."""
    return {
        "timestamp": time.time(),
        "adapters": [
            {"mac": a.mac, "version": a.version,
             "station_info": asdict(a.station_info) if a.station_info else None,
             "networks": [asdict(n) for n in a.networks],
             "stations": [asdict(s) for s in a.stations]}
            for a in adapters
        ],
    }
