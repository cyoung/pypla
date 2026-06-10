"""Raw Layer-2 transport via scapy/libpcap.

Sending raw frames needs root / BPF access (run under sudo). Works on macOS
and Linux, including over Wi-Fi when the AP bridges the 0x88E1/0x8912
EtherTypes.
"""

from __future__ import annotations

import time

from .protocol import BPF_FILTER


class Net:
    """Thin scapy wrapper: send one request, collect matching replies."""

    def __init__(self, iface: str, timeout: float = 2.0, repeat: int = 2):
        from scapy.all import Ether, Raw, AsyncSniffer, sendp, get_if_hwaddr
        self._Ether, self._Raw = Ether, Raw
        self._AsyncSniffer, self._sendp = AsyncSniffer, sendp
        self.iface = iface
        self.timeout = timeout
        self.repeat = repeat
        self.src = get_if_hwaddr(iface).lower()

    def transact(self, dst: str, ethertype: int, payload: bytes
                 ) -> list[tuple[str, int, bytes]]:
        """Send `payload` to `dst`; return [(src_mac, ethertype, payload), ...]."""
        sniffer = self._AsyncSniffer(
            iface=self.iface, filter=BPF_FILTER, store=True,
            lfilter=lambda p: (p.haslayer(self._Ether)
                               and p[self._Ether].src.lower() != self.src),
        )
        sniffer.start()
        time.sleep(0.2)
        frame = self._Ether(dst=dst, src=self.src, type=ethertype) / \
            self._Raw(load=payload)
        self._sendp([frame] * self.repeat, iface=self.iface, verbose=False)
        time.sleep(self.timeout)
        pkts = sniffer.stop() or []
        return [(p[self._Ether].src.lower(), p[self._Ether].type,
                 bytes(p)[14:]) for p in pkts]
