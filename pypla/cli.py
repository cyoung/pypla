"""pypla command-line interface.

  sudo pypla -i en0 discover          # list local adapters
  sudo pypla -i en0 probe             # test whether the link carries PLC mgmt
  sudo pypla -i en0 info              # adapter station-info + network-info
  sudo pypla -i en0 once [--json]     # full snapshot (info + peer rates)
  sudo pypla -i en0 watch -n 5        # poll every 5s
  pypla report /var/log/pypla.jsonl   # summarize a snapshot log (no root needed)
  # skip discovery and hit a known adapter directly:
  sudo pypla -i en0 --adapter aa:bb:cc:dd:ee:ff once

JSON output is pretty-printed on a TTY and compact (one line per snapshot,
JSONL-friendly) when redirected to a file or pipe.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import api
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
    STATION_INFO_CNF,
    STATION_INFO_REQ,
    Adapter,
    format_uptime,
    mmtype,
    parse_discover_list,
    parse_network_info,
    parse_station_info,
)
from .transport import Net


def _fmt(v) -> str:
    return "-" if v is None else str(v)


def _dump(adapters: list[Adapter]) -> str:
    """Pretty JSON on a TTY; compact single-line (JSONL) when piped to a log."""
    return json.dumps(api.to_dict(adapters),
                      indent=2 if sys.stdout.isatty() else None)


def print_tables(adapters: list[Adapter]) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    if not adapters:
        print(f"[{ts}] no local adapters discovered")
        return
    for a in adapters:
        ver = f"  ({a.version})" if a.version else ""
        print(f"[{ts}] adapter {a.mac}{ver} — {len(a.stations)} peer(s)")
        si = a.station_info
        if si:
            print(f"  device: chip {si.chip_version}  fw {si.firmware_version}  "
                  f"rom {si.rom_version}  uptime {format_uptime(si.uptime_seconds)}  "
                  f"HPAV {si.homeplug_version}  maxrate {si.max_bit_rate_mbps} Mbps")
        for ni in a.networks:
            print(f"  network: NID {ni.nid}  SNID {ni.snid}  TEI {ni.tei}  "
                  f"role {ni.role}  CCo {ni.cco_mac}  status {ni.status}  "
                  f"kind {ni.kind}")
        if a.stations:
            print(f"  {'PEER MAC':<18} {'TX Mbps':>7} {'RX Mbps':>7} "
                  f"{'TEI':>4} {'SNID':>4}  signal")
            for s in a.stations:
                print(f"  {s.mac:<18} {_fmt(s.tx_mbps):>7} {_fmt(s.rx_mbps):>7} "
                      f"{_fmt(s.tei):>4} {_fmt(s.snid):>4}  "
                      f"{_fmt(s.signal_level)}")


# --- probe: does this link carry PLC management frames at all? ----------------

PROBES = {
    "discover-list": (ETH_HOMEPLUG, DISCOVER_LIST_REQ,
                      "CC_DISCOVER_LIST.REQ (HomePlug AV, 0x88E1)"),
    "mediaxtream": (ETH_MEDIAXTREAM, MEDIAXTREAM_DISCOVER_REQ,
                    "Mediaxtream discover (Broadcom, 0x8912)"),
}


def _classify(ethertype: int, payload: bytes) -> str:
    if payload[:2] == DISCOVER_LIST_CNF:
        return "CC_DISCOVER_LIST.CNF  <- HomePlug AV station replied"
    if payload[:3] == MEDIAXTREAM_CNF:
        return "Mediaxtream discover CNF  <- Broadcom adapter replied"
    et = {ETH_HOMEPLUG: "0x88E1", ETH_MEDIAXTREAM: "0x8912"}.get(
        ethertype, hex(ethertype))
    return f"other PLC mgmt frame ({et}, MMTYPE={mmtype(payload):#06x})"


def run_probe(net: Net, dst: str, which: str, verbose: bool) -> int:
    selected = list(PROBES) if which == "both" else [which]
    print(f"interface {net.iface} (src {net.src}) -> dst {dst}")

    seen: dict[tuple, tuple[int, bytes]] = {}
    for name in selected:
        ethertype, payload, label = PROBES[name]
        print(f"  probe: {label}")
        for smac, et, pl in net.transact(dst, ethertype, payload):
            # dedupe by (responder, ethertype, mmtype) but keep first payload
            seen.setdefault((smac, et, mmtype(pl)), (et, pl))

    if not seen:
        print("\nNO RESPONSE.")
        print("  Ambiguous: either the network didn't bridge 0x88E1/0x8912 to")
        print("  this interface, or no adapter was reachable. Best control:")
        print("  run the same probe from a host wired to the adapter.")
        return 2

    print(f"\nGOT {len(seen)} responder(s) -- the link carried the frames:\n")
    for (smac, et, _mt), (ethertype, payload) in seen.items():
        print(f"  from {smac}  [{_classify(ethertype, payload)}]")
        if payload[:2] == DISCOVER_LIST_CNF:
            stations = parse_discover_list(payload)
            print(f"      stations reported: {len(stations)}")
            for i, (mac, f) in enumerate(stations.items(), 1):
                print(f"        station {i}: {mac}  "
                      f"same_network={'YES' if f['same_network'] else 'NO'}")
        if verbose:
            print(f"      raw: {payload.hex()}")
    return 0


# --- report: summarize a JSONL snapshot log -----------------------------------

def run_report(path: str) -> int:
    import statistics

    samples = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # tolerate partial/corrupt lines
    if not samples:
        print(f"no parsable snapshots in {path}", file=sys.stderr)
        return 2
    samples.sort(key=lambda s: s["timestamp"])

    t0, t1 = samples[0]["timestamp"], samples[-1]["timestamp"]
    span = format_uptime(int(t1 - t0)) or "0m"
    print(f"{len(samples)} snapshots over {span}  "
          f"({time.strftime('%Y-%m-%d %H:%M', time.localtime(t0))} -> "
          f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(t1))})")

    # sampling gaps: monitor host down, or `once` produced no output
    if len(samples) > 2:
        ivals = [b["timestamp"] - a["timestamp"]
                 for a, b in zip(samples, samples[1:])]
        med = statistics.median(ivals)
        gaps = [(a["timestamp"], iv) for (a, _b), iv
                in zip(zip(samples, samples[1:]), ivals)
                if iv > max(2 * med, med + 30)]
        print(f"sampling: median interval {med:.0f}s, {len(gaps)} gap(s)")
        for ts, iv in gaps:
            print(f"  gap of {format_uptime(int(iv))} after "
                  f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))}")

    per: dict[str, dict] = {}
    for s in samples:
        for a in s["adapters"]:
            d = per.setdefault(a["mac"], {
                "seen": 0, "down": 0, "reboots": [], "last_up": None,
                "peers": {},
            })
            d["seen"] += 1
            if not a["stations"]:
                d["down"] += 1
            up = (a.get("station_info") or {}).get("uptime_seconds")
            if up is not None:
                if d["last_up"] is not None and up < d["last_up"]:
                    d["reboots"].append(s["timestamp"])
                d["last_up"] = up
            for st in a["stations"]:
                r = d["peers"].setdefault(st["mac"], {"tx": [], "rx": []})
                if st["tx_mbps"] is not None:
                    r["tx"].append(st["tx_mbps"])
                if st["rx_mbps"] is not None:
                    r["rx"].append(st["rx_mbps"])

    def _stats(v: list[int]) -> str:
        if not v:
            return "no data"
        zeros = sum(1 for x in v if x == 0)
        return (f"min {min(v)} / med {statistics.median(v):.0f} / "
                f"max {max(v)} Mbps  (zero-rate in {zeros}/{len(v)} samples)")

    for mac, d in per.items():
        print(f"\nadapter {mac}: in {d['seen']}/{len(samples)} snapshots, "
              f"no-peer/unreachable in {d['down']}, "
              f"{len(d['reboots'])} reboot(s)")
        for ts in d["reboots"]:
            print(f"  reboot detected near "
                  f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))}")
        for pmac, r in d["peers"].items():
            print(f"  peer {pmac}: tx {_stats(r['tx'])}")
            print(f"  peer {pmac}: rx {_stats(r['rx'])}")
    return 0


# --- entry point ---------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="pypla", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-i", "--iface", default="en0",
                   help="interface (default en0 = Wi-Fi on most Macs)")
    p.add_argument("--adapter", default=None, metavar="MAC",
                   help="skip discovery; query this adapter MAC directly")
    p.add_argument("--timeout", type=float, default=2.0,
                   help="seconds to wait per transaction (default 2)")
    sub = p.add_subparsers(dest="mode", required=True)
    sub.add_parser("discover", help="list local adapters")
    p_probe = sub.add_parser("probe", help="test whether the link carries "
                                           "PLC management frames")
    p_probe.add_argument("--dst", default=BROADCAST,
                         help="destination MAC (default broadcast)")
    p_probe.add_argument("--probe", choices=[*PROBES, "both"], default="both",
                         help="which probe(s) to send (default both)")
    p_probe.add_argument("-v", "--verbose", action="store_true",
                         help="hex-dump every captured frame")
    p_info = sub.add_parser("info", help="adapter station-info + network-info")
    p_info.add_argument("--json", action="store_true")
    p_info.add_argument("--raw", action="store_true",
                        help="also dump the raw reply hex (for verification)")
    p_once = sub.add_parser("once", help="full snapshot (info + peer rates)")
    p_once.add_argument("--json", action="store_true")
    p_watch = sub.add_parser("watch", help="poll on an interval")
    p_watch.add_argument("-n", "--interval", type=float, default=5.0)
    p_watch.add_argument("--json", action="store_true")
    p_rep = sub.add_parser("report", help="summarize a JSONL snapshot log")
    p_rep.add_argument("logfile", help="file of one `once --json` line per sample")
    args = p.parse_args(argv)

    if args.mode == "report":  # offline; needs no interface or root
        return run_report(args.logfile)

    try:
        net = Net(args.iface, args.timeout)
    except ImportError:
        print("error: scapy not installed.  pip install scapy", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"error: cannot open {args.iface}: {e}", file=sys.stderr)
        return 1

    try:
        if args.mode == "discover":
            adapters = api.discover(net)
            if not adapters:
                print("no local adapters discovered")
                return 2
            for a in adapters:
                print(f"  {a.mac}  {a.version or ''}")
            return 0

        if args.mode == "probe":
            return run_probe(net, args.dst, args.probe, args.verbose)

        if args.mode == "info":
            adapters = ([Adapter(mac=args.adapter.lower())] if args.adapter
                        else api.discover(net))
            if not adapters:
                print("no local adapters discovered")
                return 2
            for a in adapters:
                si_reps = net.transact(a.mac, ETH_MEDIAXTREAM, STATION_INFO_REQ)
                ni_reps = net.transact(a.mac, ETH_MEDIAXTREAM, NETWORK_INFO_REQ)
                a.station_info = next(
                    (parse_station_info(pl) for s, _e, pl in si_reps
                     if s == a.mac and pl[:9] == STATION_INFO_CNF), None)
                a.networks = next(
                    (parse_network_info(pl) for s, _e, pl in ni_reps
                     if s == a.mac and pl[:9] == NETWORK_INFO_CNF), [])
                if args.raw:
                    for label, reps, cnf in (("station-info", si_reps, STATION_INFO_CNF),
                                             ("network-info", ni_reps, NETWORK_INFO_CNF)):
                        for s, _e, pl in reps:
                            if s == a.mac and pl[:9] == cnf:
                                print(f"  raw {label} <{s}>: {pl.hex()}")
            if args.json:
                print(_dump(adapters))
            else:
                print_tables(adapters)
            return 0

        if args.mode == "once":
            adapters = api.collect(net, args.adapter, full=True)
            if args.json:
                print(_dump(adapters))
            else:
                print_tables(adapters)
            return 0 if adapters else 2

        if args.mode == "watch":
            # discover once up front (unless an adapter was pinned), then poll
            pinned = ([Adapter(mac=args.adapter.lower())] if args.adapter
                      else api.discover(net))
            if not pinned:
                print("no local adapters discovered", file=sys.stderr)
                return 2
            while True:
                for a in pinned:
                    a.stations = api.query_stations(net, a.mac)
                if args.json:
                    print(_dump(pinned), flush=True)
                else:
                    print_tables(pinned)
                time.sleep(args.interval)
    except KeyboardInterrupt:
        return 130
    return 0
