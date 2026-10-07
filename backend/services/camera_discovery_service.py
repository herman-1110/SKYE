"""Camera discovery (Prompt 131b): find VIGI cameras before they're on the map.

A camera only pushes an alarm when something happens, so SKYE looks for them
itself: one ONVIF WS-Discovery Probe (Types dn:NetworkVideoTransmitter) per
LAN interface of this machine, multicast to 239.255.255.250:3702 with TTL 1,
so it never leaves the local segment. No port sweeps, no address ranges, no
credentials. The real InSight S445 answered one probe in 4 ms (6 Oct) with
its IP in XAddrs, name/model in scopes, and its MAC in a VIGI-specific scope
(onvif://www.onvif.org/VigiInfoStream/98-BA-5F-8B-10-03/...). Without that
scope the MAC comes from the ARP table (utils/arp_utils.py). Only VIGI
cameras are kept; other ONVIF devices are counted and ignored.

VIGI's own discovery protocol (ODP, UDP 23001) isn't used: the API document
gives its header and reply but not the request payload, version or byte
order (UNCONFIRMED), and the ONVIF reply already carries everything needed.

Each round writes /cctv_heartbeats/{AA_BB_...} through
cctv_repository.update_heartbeat (partial updates):
  discovered_at, discovered_via, ip, and - unregistered cameras only -
  device_name. last_seen stays with the TCP liveness probe
  (camera_health_service), which also probes discovered cameras, so "online"
  keeps meaning "reachable now".
  ip_mismatch: a registered camera found at another IP gets the found IP
  (alarms are only accepted from the registered one); cleared when they
  match again, or when the registered IP is edited.
Unregistered entries (discovered_via set, MAC not registered) not seen for
10 minutes are pruned. A registered camera's node is never removed here, and
nodes without discovered_via (the simulator's) are never touched.
"""
import asyncio
import ipaddress
import logging
import re
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import unquote, urlparse

from config.settings import settings
from repositories.cctv_repository import cctv_repository
from services.cctv_service import cctv_service
from utils.arp_utils import arp_lookup
from utils.mac_utils import InvalidMacError, normalize_mac

log = logging.getLogger(__name__)

WS_DISCOVERY_ADDR = ("239.255.255.250", 3702)
PROBE_WAIT_S = 3.0
STALE_AFTER_S = 600.0

_PROBE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" '
    'xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
    'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
    'xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
    '<e:Header><w:MessageID>uuid:{msg_id}</w:MessageID>'
    '<w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>'
    '<w:Action e:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>'
    '</e:Header><e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body></e:Envelope>'
)


def _tags(xml: str, tag: str) -> List[str]:
    return [t.strip() for t in re.findall(rf"<(?:[\w-]+:)?{tag}\b[^>]*>(.*?)</(?:[\w-]+:)?{tag}>", xml, re.S)]


def parse_probe_match(xml: str, source_ip: str) -> Optional[dict]:
    """A VIGI camera from one ProbeMatch, or None. Keys: ip, mac (or None
    when the reply doesn't carry it), name, model. Pure, never raises."""
    try:
        if "ProbeMatch" not in xml or "NetworkVideoTransmitter" not in " ".join(_tags(xml, "Types")):
            return None
        name = model = mac = None
        vigi = False
        for scope in " ".join(_tags(xml, "Scopes")).split():
            low = scope.lower()
            if low.startswith("onvif://www.onvif.org/name/"):
                name = unquote(scope.split("/name/", 1)[1]).strip() or None
            elif low.startswith("onvif://www.onvif.org/hardware/"):
                model = unquote(scope.split("/hardware/", 1)[1]).strip() or None
            elif "/vigiinfostream/" in low:
                vigi = True
                candidate = scope[low.index("/vigiinfostream/") + len("/vigiinfostream/"):].split("/", 1)[0]
                try:
                    mac = normalize_mac(candidate)
                except InvalidMacError:
                    pass
        if not vigi and not re.search(r"vigi|insight", f"{name or ''} {model or ''}", re.I):
            return None
        ip = None
        for xaddr in " ".join(_tags(xml, "XAddrs")).split():
            host = urlparse(xaddr).hostname
            try:
                if host and ipaddress.IPv4Address(host).is_private:
                    ip = host
                    break
            except ValueError:
                continue
        ip = ip or source_ip
        return {"ip": ip, "mac": mac, "name": name, "model": model}
    except Exception:
        return None


@dataclass
class DiscoveredCamera:
    mac: str
    ip: str
    name: Optional[str] = None
    model: Optional[str] = None
    via: Set[str] = field(default_factory=set)

    @property
    def discovered_via(self) -> str:
        return "+".join(sorted(self.via))


class CameraDiscoveryService:
    def __init__(self) -> None:
        self._round_lock = threading.Lock()
        self._lock = threading.Lock()
        # Unregistered cameras found by discovery or by an alarm push:
        # mac -> (ip, unix time last found, how). Liveness probes these too.
        self._unregistered: Dict[str, Tuple[str, float, Set[str]]] = {}
        self._last_logged_set: Set[Tuple[str, str]] = set()
        self.target = WS_DISCOVERY_ADDR    # tests point this at a loopback responder

    # ── finding ──────────────────────────────────────────────────────────────
    @staticmethod
    def local_addresses() -> List[str]:
        """This machine's private, non-loopback IPv4 addresses (one probe each)."""
        found = set()
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                found.add(info[4][0])
        except OSError:
            pass
        out = []
        for addr in found:
            ip = ipaddress.IPv4Address(addr)
            if ip.is_private and not ip.is_loopback and not ip.is_link_local:
                out.append(addr)
        return sorted(out)

    def _probe(self, local_ip: str, wait: float) -> List[Tuple[str, str]]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        replies: List[Tuple[str, str]] = []
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip))
            except OSError:
                pass
            sock.bind((local_ip, 0))
            sock.settimeout(0.3)
            sock.sendto(_PROBE.format(msg_id=uuid.uuid4()).encode("utf-8"), self.target)
            deadline = time.monotonic() + wait
            while time.monotonic() < deadline:
                try:
                    data, addr = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                except ConnectionResetError:     # Windows: ICMP unreachable from an earlier send
                    continue
                replies.append((addr[0], data.decode("utf-8", "replace")))
        except OSError as e:
            log.info("[VIGI] discovery probe from %s failed: %s", local_ip, type(e).__name__)
        finally:
            sock.close()
        return replies

    def discover_once(self, wait: float = PROBE_WAIT_S) -> List[DiscoveredCamera]:
        """One round: probe, merge by MAC, record, prune. One round at a time."""
        with self._round_lock:
            addresses = self.local_addresses()
            replies: List[Tuple[str, str]] = []
            if addresses:
                with ThreadPoolExecutor(max_workers=len(addresses)) as pool:
                    for result in pool.map(lambda a: self._probe(a, wait), addresses):
                        replies.extend(result)
            found: Dict[str, DiscoveredCamera] = {}
            ignored = 0
            for source_ip, xml in replies:
                info = parse_probe_match(xml, source_ip)
                if info is None:
                    ignored += 1 if "ProbeMatch" in xml else 0
                    continue
                via = {"onvif"}
                mac = info["mac"]
                if mac is None:
                    mac = arp_lookup(info["ip"])
                    via.add("arp")
                if mac is None:
                    log.info("[VIGI] discovery: VIGI camera at %s gave no MAC and isn't in the ARP table; skipped",
                             info["ip"])
                    continue
                cam = found.get(mac)
                if cam is None:
                    cam = found[mac] = DiscoveredCamera(mac=mac, ip=info["ip"])
                cam.name = cam.name or info["name"]
                cam.model = cam.model or info["model"]
                cam.via |= via
            cameras = list(found.values())
            self.record(cameras)
            self.prune()
            if ignored:
                log.debug("[VIGI] discovery: %d non-VIGI ONVIF device(s) ignored", ignored)
            return cameras

    # ── recording ────────────────────────────────────────────────────────────
    def record(self, cameras: List[DiscoveredCamera]) -> None:
        registered = {}
        for c in cctv_service.all_cameras():
            if c.device_mac and c.device_mac not in registered:
                registered[c.device_mac] = c
        now = time.time()
        summary = set()
        for cam in cameras:
            reg = registered.get(cam.mac)
            values = {"discovered_at": int(now), "discovered_via": cam.discovered_via, "ip": cam.ip}
            remove = []
            if reg is None:
                values["device_name"] = cam.name or cam.model
                with self._lock:
                    prev = self._unregistered.get(cam.mac)
                    self._unregistered[cam.mac] = (cam.ip, now, set(cam.via) | (prev[2] if prev else set()))
            elif reg.ip and reg.ip != cam.ip:
                values["ip_mismatch"] = cam.ip
            else:
                remove.append("ip_mismatch")
            cctv_repository.update_heartbeat(cam.mac, values, remove=remove)
            mismatch = reg is not None and reg.ip and reg.ip != cam.ip
            summary.add((cam.mac, f"{cam.ip} (registered at {reg.ip})" if mismatch else cam.ip))
        if summary != self._last_logged_set:
            self._last_logged_set = summary
            log.info("[VIGI] discovery: %d VIGI camera(s): %s", len(summary),
                     ", ".join(f"{m} at {i}" for m, i in sorted(summary)) or "none")

    def record_alarm_device(self, mac: str, ip: str, device_name: Optional[str]) -> None:
        """An unregistered camera that pushed an alarm (vigi_service): listed and
        probed like a discovered one, with discovered_via including "alarm"."""
        now = time.time()
        with self._lock:
            prev = self._unregistered.get(mac)
            via = (prev[2] if prev else set()) | {"alarm"}
            self._unregistered[mac] = (ip, now, via)
        cctv_repository.update_heartbeat(mac, {"last_seen": int(now), "device_name": device_name, "ip": ip,
                                               "discovered_via": "+".join(sorted(via))})

    def unregistered_targets(self) -> Dict[str, str]:
        """{mac: ip} of unregistered cameras found in the last 10 minutes."""
        registered = {c.device_mac for c in cctv_service.all_cameras() if c.device_mac}
        cutoff = time.time() - STALE_AFTER_S
        with self._lock:
            return {mac: ip for mac, (ip, seen, _via) in self._unregistered.items()
                    if seen >= cutoff and mac not in registered}

    # ── pruning ──────────────────────────────────────────────────────────────
    def prune(self) -> int:
        """Remove unregistered discovered entries not seen for 10 minutes."""
        registered = {c.device_mac for c in cctv_repository.get_all_global() if c.device_mac}   # fresh read
        now = time.time()
        removed = 0
        for node in cctv_repository.get_all_heartbeats().values():
            if not isinstance(node, dict) or not node.get("discovered_via"):
                continue
            try:
                mac = normalize_mac(node.get("mac"))
            except InvalidMacError:
                continue
            if mac in registered:
                continue
            seen = max(v for v in (node.get("last_seen"), node.get("discovered_at"), 0) if isinstance(v, (int, float)))
            if now - seen > STALE_AFTER_S:
                cctv_repository.delete_cctv_heartbeat(mac)
                with self._lock:
                    self._unregistered.pop(mac, None)
                removed += 1
        with self._lock:
            for mac in [m for m, (_ip, seen, _v) in self._unregistered.items() if now - seen > STALE_AFTER_S]:
                self._unregistered.pop(mac, None)
        if removed:
            log.info("[VIGI] discovery: pruned %d unregistered camera entr%s not seen for 10 min",
                     removed, "y" if removed == 1 else "ies")
        return removed

    # ── loop ─────────────────────────────────────────────────────────────────
    async def discovery_loop(self) -> None:
        if settings.VIGI_DISCOVERY_INTERVAL_S <= 0:
            log.info("[VIGI] camera discovery is off (VIGI_DISCOVERY_INTERVAL_S=0); \"Scan now\" still works")
            return
        while True:
            try:
                await asyncio.to_thread(self.discover_once)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("[VIGI] camera discovery round failed, will retry")
            await asyncio.sleep(settings.VIGI_DISCOVERY_INTERVAL_S)


camera_discovery_service = CameraDiscoveryService()
