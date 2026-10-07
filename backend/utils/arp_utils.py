"""MAC address of a LAN host from the Windows ARP table (Prompt 131b D4).

`arp -a <ip>` needs no admin rights. Its lines look like
    "  192.168.0.101         98-ba-5f-8b-10-03     dynamic"
under an "Interface: 192.168.0.5 --- 0x7" header. Broadcast and multicast
entries (ff-ff-ff-ff-ff-ff, 01-00-5e-...) are skipped. A host only appears
after this machine has exchanged packets with it, which a discovery reply
has just done.
"""
import re
import subprocess
from typing import Dict, Optional

from utils.mac_utils import InvalidMacError, normalize_mac

_LINE = re.compile(r"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9A-Fa-f]{2}(?:[-:][0-9A-Fa-f]{2}){5})\s+\S+", re.MULTILINE)


def parse_arp_output(text: str) -> Dict[str, str]:
    """{ip: "AA:BB:CC:DD:EE:FF"} from `arp -a` output; unicast entries only."""
    table: Dict[str, str] = {}
    for ip, raw_mac in _LINE.findall(text or ""):
        try:
            mac = normalize_mac(raw_mac)
        except InvalidMacError:
            continue
        first_octet = int(mac[:2], 16)
        if mac == "FF:FF:FF:FF:FF:FF" or first_octet & 1:   # broadcast / multicast
            continue
        table[ip] = mac
    return table


def arp_lookup(ip: str, timeout: float = 3.0) -> Optional[str]:
    try:
        out = subprocess.run(["arp", "-a", ip], capture_output=True, text=True, timeout=timeout,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_arp_output(out).get(ip)
