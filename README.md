# pypla

Monitor TP-Link / Broadcom (BCM60500) powerline adapters natively over raw
Layer 2.

Pure Python + scapy.

Reimplements the management transactions [pla-util](https://github.com/serock/pla-util) performs, with byte
layouts taken from its Ada source:

- **discover** — broadcast Mediaxtream discover (EtherType `0x8912`) to find
  local adapters
- **network stats** — per-peer TX/RX PHY rates (Mbps)
- **discover list** — per-peer TEI / SNID / same-network / signal level
  (standard HomePlug AV, EtherType `0x88E1`)
- **station info / network info** — chip, firmware, uptime, NID, CCo role, …

Proven to work over Wi-Fi when the AP bridges the `0x88E1` / `0x8912`
EtherTypes (verified with a TL-PA9020P).

## Install

```sh
pip install -r requirements.txt   # just the runtime deps (scapy), or:
pip install .                     # install the `pypla` CLI + library
```

Raw L2 access needs root / BPF, so run the CLI under `sudo`.

## CLI

```sh
sudo pypla -i en0 discover          # list local adapters
sudo pypla -i en0 probe             # test whether the link carries PLC mgmt frames
sudo pypla -i en0 info              # adapter station-info + network-info
sudo pypla -i en0 once --json       # full snapshot (info + peer rates)
sudo pypla -i en0 watch -n 5        # poll every 5 s
# skip discovery and hit a known adapter directly:
sudo pypla -i en0 --adapter aa:bb:cc:dd:ee:ff once
```

`probe` is the diagnostic mode: it broadcasts the same discovery frames
pla-util uses and reports every responder, so you can tell whether your
Wi-Fi/AP path bridges PLC management traffic at all. Also runnable as
`sudo python3 -m pypla ...`.

## Library

```python
from pypla import Net, collect, discover

net = Net("en0", timeout=2.0)        # raw L2 needs root / BPF access
for adapter in collect(net, full=True):
    print(adapter.mac, adapter.station_info.firmware_version)
    for peer in adapter.stations:
        print(f"  {peer.mac}  tx={peer.tx_mbps} rx={peer.rx_mbps} Mbps")
```

## Stability monitoring (Raspberry Pi / Linux)

For long-term monitoring, run the Pi wired into the same L2 segment as the
adapters (best: directly into one adapter's Ethernet port) so a missed poll
means the powerline side, not Wi-Fi. JSON output is compact single-line when
redirected, so a log file is one snapshot per line (JSONL):

```sh
sudo apt install python3-venv git           # scapy needs no libpcap on Linux
git clone https://github.com/cyoung/pypla /opt/pypla && cd /opt/pypla
python3 -m venv venv && ./venv/bin/pip install -e .

# snapshot every minute via systemd (edit paths/interface in the unit first)
sudo cp deploy/pypla.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now pypla.timer

# later: summarize reboots, link-down events, gaps, and PHY-rate stats
./venv/bin/pypla report /var/log/pypla.jsonl
```

`report` flags four stability signals per adapter: snapshots where it
reported no peers (link down or adapter unreachable), `uptime_seconds`
decreases (the adapter rebooted), sampling gaps (the monitor itself missed
polls), and min/median/max TX/RX PHY rates per peer.

## Modules

- `pypla.protocol` — frame payloads, confirmation prefixes, parsers,
  dataclasses (`Adapter`, `Station`, `StationInfo`, `NetworkInfo`)
- `pypla.transport` — `Net`, a thin scapy send/sniff transaction wrapper
- `pypla.api` — `discover`, `query_stations`, `query_station_info`,
  `query_network_info`, `collect`, `to_dict`
- `pypla.cli` — the `pypla` command
