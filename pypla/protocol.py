"""Wire formats for HomePlug AV / Broadcom Mediaxtream management frames.

Request payloads and reply byte layouts are taken from pla-util's Ada source
(messages-constructors.adb and the get_* operation parsers). Two EtherTypes
are involved:

  * 0x88E1  standard HomePlug AV management (CC_DISCOVER_LIST)
  * 0x8912  Broadcom "Mediaxtream" vendor management (everything else)
"""

from __future__ import annotations

from dataclasses import dataclass, field

ETH_HOMEPLUG = 0x88E1
ETH_MEDIAXTREAM = 0x8912
BROADCAST = "ff:ff:ff:ff:ff:ff"
BPF_FILTER = "ether proto 0x8912 or ether proto 0x88e1"


def _pad(data: bytes, length: int = 46) -> bytes:
    """HomePlug payloads pad with zeros to a minimum (46 -> 60-byte frame)."""
    return data + bytes(max(0, length - len(data)))


# --- request payloads (verbatim from pla-util) --------------------------------

MEDIAXTREAM_DISCOVER_REQ = _pad(bytes([
    0x01, 0x70, 0xa0, 0x00, 0x00, 0x00, 0x1f, 0x84, 0x01,
    0xa3, 0x97, 0xa2, 0x55, 0x53, 0xbe, 0xf1, 0xfc,
    0xf9, 0x79, 0x6b, 0x52, 0x14, 0x13, 0xe9, 0xe2,
]))
NETWORK_STATS_REQ = _pad(bytes([
    0x02, 0x2c, 0xa0, 0x00, 0x00, 0x00, 0x1f, 0x84, 0x02, 0x00,
    0xb0, 0xf2, 0xe6, 0x95, 0x66, 0x6b, 0x03,
]))
DISCOVER_LIST_REQ = _pad(bytes([0x01, 0x14]))
STATION_INFO_REQ = _pad(bytes([0x02, 0x4c, 0xa0, 0x00, 0x00, 0x00, 0x1f, 0x84, 0x02]))
NETWORK_INFO_REQ = _pad(bytes([0x02, 0x28, 0xa0, 0x00, 0x00, 0x00, 0x1f, 0x84, 0x02]))

# --- expected confirmation prefixes --------------------------------------------

MEDIAXTREAM_CNF = bytes([0x02, 0x71, 0xa0])
NETWORK_STATS_CNF = bytes([0x02, 0x2d, 0xa0, 0x00, 0x00, 0x00, 0x1f, 0x84, 0x02])
DISCOVER_LIST_CNF = bytes([0x01, 0x15])
STATION_INFO_CNF = bytes([0x02, 0x4d, 0xa0, 0x00, 0x00, 0x00, 0x1f, 0x84, 0x02])
NETWORK_INFO_CNF = bytes([0x02, 0x29, 0xa0, 0x00, 0x00, 0x00, 0x1f, 0x84, 0x02])


# --- data model ----------------------------------------------------------------

@dataclass
class Station:
    mac: str
    tx_mbps: int | None = None    # avg PHY rate local -> peer
    rx_mbps: int | None = None    # avg PHY rate peer -> local
    tei: int | None = None
    snid: int | None = None
    same_network: bool | None = None
    cco: bool | None = None
    signal_level: int | None = None


@dataclass
class StationInfo:
    chip_version: str | None = None
    hardware_version: int | None = None
    firmware_revision: int | None = None
    rom_version: str | None = None
    param_config_builtin: int | None = None
    param_config_nvm: int | None = None
    uptime_seconds: int | None = None
    firmware_boot_message: str | None = None
    firmware_version: str | None = None
    flash_model: str | None = None
    homeplug_version: str | None = None
    max_bit_rate_mbps: str | None = None


@dataclass
class NetworkInfo:
    nid: str | None = None
    snid: int | None = None
    tei: int | None = None
    role: str | None = None
    cco_mac: str | None = None
    kind: str | None = None
    num_coord_networks: int | None = None
    status: str | None = None
    bcco_mac: str | None = None


@dataclass
class Adapter:
    mac: str
    version: str | None = None
    stations: list[Station] = field(default_factory=list)
    station_info: StationInfo | None = None
    networks: list[NetworkInfo] = field(default_factory=list)


# --- lookup tables ---------------------------------------------------------------

CHIP_VERSIONS = {
    0x017f0000: "BCM60500_A0", 0x017f024e: "BCM60500_A1", 0x117f024e: "BCM60500_B0",
    0x017f024f: "BCM60333_A1", 0x117f024f: "BCM60333_B0", 0x017f025a: "BCM60335_A0",
}
FLASH_MODELS = {
    0x00000001: "DEFAULT", 0x00014015: "S25FL216K", 0x001c3114: "EN25F80",
    0x00bf2541: "SST25VF016B", 0x00bf254a: "SST25VF032B", 0x00bf258e: "SST25VF080B",
    0x00c22014: "MX25L8006E", 0x00c22015: "MX25L1606E", 0x00c22016: "MX25L3206E",
    0x00c22017: "MX25L6406E",  # observed on TL-PA9020P (not in pla-util's table)
    0x00c84014: "GD25Q80B", 0x00c84015: "GD25Q16B", 0x00c84016: "GD25Q32B",
    0x00ef4014: "W25Q80BV", 0x00ef4015: "W25Q16BV", 0x00ef4016: "W25Q32BV",
    0x00f83215: "FM25S16",
}
FW_NAMES = {0: "CONCORDE", 5: "GEMINI", 6: "APOLLO", 7: "HYDRA"}
MAX_BIT_RATE = {0: "200", 1: "1000", 2: "1800"}
HPAV_VERSION = {0: "1.1", 1: "2.0"}
STATION_ROLE = {0: "Unassoc-STA", 1: "Unassoc-CCo", 2: "STA", 3: "CCo"}
NETWORK_KIND = {0: "in-home", 1: "access"}
NET_STATUS = {0: "joined", 1: "not-joined(have-NMK)", 2: "not-joined(no-NMK)"}


# --- small helpers ---------------------------------------------------------------

def _mac(b: bytes) -> str:
    return ":".join(f"{x:02x}" for x in b)


def _u32le(b: bytes, off: int) -> int:
    return int.from_bytes(b[off:off + 4], "little")


def printable(payload: bytes) -> str | None:
    """First ASCII run of >= 4 chars in a payload (e.g. version string)."""
    import re
    runs = re.findall(rb"[\x20-\x7e]{4,}", payload)
    return runs[0].decode("ascii", "replace") if runs else None


def mmtype(payload: bytes) -> int:
    """MMTYPE = payload[1..2], little-endian. (payload[0] is MMV.)"""
    return payload[1] | (payload[2] << 8) if len(payload) >= 3 else -1


def format_uptime(secs: int | None) -> str | None:
    if secs is None:
        return None
    d, r = divmod(secs, 86400)
    h, r = divmod(r, 3600)
    out = (f"{d}d " if d else "") + (f"{h}h " if (d or h) else "") + f"{r // 60}m"
    return out.strip()


# --- parsers (offsets per pla-util get_network_stats.adb / get_discover_list.adb)

def parse_network_stats(payload: bytes) -> list[Station]:
    if payload[:9] != NETWORK_STATS_CNF:
        return []
    out: list[Station] = []
    n = payload[9]                       # Confirmation(10)
    x = 10                               # Confirmation(11), 0-based
    for _ in range(n):
        if x + 10 > len(payload):
            break
        tx = payload[x + 6] + 256 * (payload[x + 7] & 0x07)
        rx = payload[x + 8] + 256 * (payload[x + 9] & 0x07)
        out.append(Station(mac=_mac(payload[x:x + 6]), tx_mbps=tx, rx_mbps=rx))
        x += 10
    return out


def parse_discover_list(payload: bytes) -> dict[str, dict]:
    if payload[:2] != DISCOVER_LIST_CNF:
        return {}
    d: dict[str, dict] = {}
    n = payload[5]                       # Confirmation(6)
    x = 6                                # Confirmation(7), 0-based
    for _ in range(n):
        if x + 11 > len(payload):
            break
        d[_mac(payload[x:x + 6])] = {
            "tei": payload[x + 6],
            "same_network": bool(payload[x + 7]),
            "snid": payload[x + 8] & 0x0f,
            "cco": bool(payload[x + 9] & 0x20),
            "signal_level": payload[x + 10],
        }
        x += 12
    return d


def parse_station_info(payload: bytes) -> StationInfo | None:
    if payload[:9] != STATION_INFO_CNF or len(payload) < 34:
        return None
    info = StationInfo()
    cv = _u32le(payload, 9)              # Confirmation(10..13)
    info.chip_version = CHIP_VERSIONS.get(cv, f"unknown({cv:#010x})")
    info.hardware_version = _u32le(payload, 13)
    info.firmware_revision = _u32le(payload, 17)
    c22, c23 = payload[21], payload[22]  # ROM version is bit-packed
    info.rom_version = (f"{c23 >> 4}.{((c22 & 0xc0) >> 6) + ((c23 & 0x0f) * 4)}"
                        f".{c22 & 0x3f}")
    info.param_config_builtin = _u32le(payload, 25)
    info.param_config_nvm = _u32le(payload, 29)
    i = 34 + 5 * payload[33]             # skip Num_Ucodes * 5-byte entries
    try:
        info.uptime_seconds = _u32le(payload, i)
        i += 4
        boot_len = payload[i]
        i += 1
        info.firmware_boot_message = \
            payload[i:i + boot_len].decode("ascii", "replace").strip("\x00") or None
        i += boot_len
        info.firmware_version = (f"{FW_NAMES.get(payload[i + 3], 'INVALID')} "
                                 f"{payload[i + 2]}.{payload[i + 1]}.{payload[i]}")
        i += 8
        fm = _u32le(payload, i)
        info.flash_model = FLASH_MODELS.get(fm, f"unknown({fm:#010x})")
        i += 4
        info.homeplug_version = HPAV_VERSION.get(payload[i], "unknown")
        i += 1
        info.max_bit_rate_mbps = MAX_BIT_RATE.get(payload[i], "unknown")
    except IndexError:
        pass  # short reply -> keep the fixed-offset fields already parsed
    return info


def parse_network_info(payload: bytes) -> list[NetworkInfo]:
    if payload[:9] != NETWORK_INFO_CNF:
        return []
    out: list[NetworkInfo] = []
    n = payload[9]                       # Confirmation(10)
    x = 10                               # Confirmation(11), 0-based
    for _ in range(n):
        if x + 19 > len(payload):
            break
        ni = NetworkInfo()
        ni.nid = payload[x:x + 7].hex()  # 7-byte NID, little-endian on wire
        ni.snid = payload[x + 7] & 0x0f
        ni.tei = payload[x + 8]
        ni.role = STATION_ROLE.get(payload[x + 9], str(payload[x + 9]))
        ni.cco_mac = _mac(payload[x + 10:x + 16])
        ni.kind = NETWORK_KIND.get(payload[x + 16], str(payload[x + 16]))
        ni.num_coord_networks = payload[x + 17]
        ni.status = NET_STATUS.get(payload[x + 18], str(payload[x + 18]))
        out.append(ni)
        x += 19
    for ni in out:                       # trailing block: backup-CCo MAC per net
        if x + 6 > len(payload):
            break
        ni.bcco_mac = _mac(payload[x:x + 6])
        x += 6
    return out
