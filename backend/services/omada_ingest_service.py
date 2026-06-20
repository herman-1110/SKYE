"""
Omada RSSI Ingestion Service

Inverts Omada's AP-centric BLE scan payloads into SKYE's beacon-centric telemetry,
buffering readings across multiple APs over a short rolling window before emitting
to the positioning pipeline.

AP-centric in:  one payload per AP, listing all beacons that AP heard.
Beacon-centric out: one OmadaTelemetryPayload per beacon, listing all APs that heard it.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from firebase_admin import db as rtdb

from config.beacon_registry import make_ibeacon_key, resolve_beacon_by_ibeacon
from models.telemetry import APRssiReading, OmadaTelemetryPayload
from repositories.ap_repository import ap_repository
from repositories.floor_repository import floor_repository
from services.positioning_service import positioning_service
from services.safety_service import safety_service
from utils.timestamp_utils import utcnow_iso

# How long a beacon's AP readings stay valid in the buffer (seconds).
# Omada APs report ~every 1 s but not synchronised; 2 s gives all APs time to chime in.
BUFFER_WINDOW_S = 2.0

# Minimum distinct APs that must hear a beacon before we attempt positioning.
MIN_APS_FOR_POSITION = 3


def _normalise_mac(mac: str) -> str:
    """Strip separators and uppercase. Works for both colon and colon-less forms."""
    return mac.replace(":", "").replace("-", "").upper()


def _format_mac_colons(mac_no_colons: str) -> str:
    """'CCBABD819DCD' → 'CC:BA:BD:81:9D:CD' (matches Firestore AP storage format)."""
    m = mac_no_colons.upper()
    return ":".join(m[i : i + 2] for i in range(0, len(m), 2))


@dataclass
class _BeaconReading:
    ap_mac_colons: str
    rssi: float
    ap_x: float
    ap_y: float
    received_at: float  # time.monotonic() when buffered


@dataclass
class _BeaconBuffer:
    readings: Dict[str, _BeaconReading] = field(default_factory=dict)


class OmadaIngestService:
    def __init__(self) -> None:
        # beacon MAC (colon-less) → buffer of per-AP readings
        self._buffers: Dict[str, _BeaconBuffer] = {}
        # AP MAC (colons) → (x_m, y_m); refreshed lazily every AP_CACHE_TTL_S seconds
        self._ap_coords: Dict[str, tuple[float, float]] = {}
        self._ap_cache_loaded_at: float = 0.0
        self._AP_CACHE_TTL_S = 30.0

    # ── AP coordinate cache ─────────────────────────────────────────────────────

    def _refresh_ap_cache(self) -> None:
        active_floor = floor_repository.get_any_active()
        if not active_floor:
            return
        aps = ap_repository.get_all(active_floor.building_id, active_floor.id)
        self._ap_coords = {ap.mac.upper(): (ap.x_m, ap.y_m) for ap in aps}
        self._ap_cache_loaded_at = time.monotonic()

    def _get_ap_coords(self, ap_mac_colons: str) -> Optional[tuple[float, float]]:
        if time.monotonic() - self._ap_cache_loaded_at > self._AP_CACHE_TTL_S:
            self._refresh_ap_cache()
        coords = self._ap_coords.get(ap_mac_colons.upper())
        if coords is None:
            # One forced refresh in case a new AP was just added
            self._refresh_ap_cache()
            coords = self._ap_coords.get(ap_mac_colons.upper())
        return coords

    # ── Heartbeat ───────────────────────────────────────────────────────────────

    def _write_ap_heartbeat(self, ap_mac_colons: str) -> None:
        """Write last-seen heartbeat for a reporting AP to RTDB.
        Called for every reporting AP — registered or not — so the dashboard can
        surface online-but-unplaced APs in the detection panel."""
        key = ap_mac_colons.replace(":", "_")
        try:
            rtdb.reference(f"/ap_heartbeats/{key}").set({
                "mac": ap_mac_colons,
                "last_seen": int(time.time()),
            })
        except Exception as e:
            print(f"[OMADA] WARNING: heartbeat write failed for {ap_mac_colons}: {e}")

    # ── Main entry point ────────────────────────────────────────────────────────

    def ingest(self, raw: dict) -> dict:
        """
        Process one raw Omada payload (one AP's scan results).
        Returns a summary dict for the HTTP response.
        """
        reporter = raw.get("reporter", {})
        ap_mac_raw = reporter.get("mac", "")
        reported: List[dict] = raw.get("reported", [])

        ap_name = reporter.get("name", "?")
        print(f"[OMADA] {ap_name} ({ap_mac_raw or 'NO MAC'}) heard {len(reported)} beacon(s)")

        if not ap_mac_raw:
            return {"status": "ignored", "reason": "no reporter.mac"}

        ap_mac_colons = _format_mac_colons(_normalise_mac(ap_mac_raw))

        # Write heartbeat for every reporting AP — even unregistered ones —
        # so the dashboard can surface online-but-unplaced APs.
        self._write_ap_heartbeat(ap_mac_colons)

        ap_coords = self._get_ap_coords(ap_mac_colons)
        if ap_coords is None:
            return {
                "status": "online_unregistered",
                "ap": ap_mac_colons,
                "reason": "AP online but not placed on active floor — heartbeat written",
            }
        ap_x, ap_y = ap_coords
        now_mono = time.monotonic()
        buffered = 0

        for entry in reported:
            ib = entry.get("ibeacon") or {}
            uuid  = ib.get("uuid", "")
            major = ib.get("major", "")
            minor = ib.get("minor", "")

            # Identify by stable iBeacon identity (survives BLE MAC rotation).
            # Skip entries with no iBeacon block (e.g. Eddystone-only) for now.
            if not uuid:
                continue
            if resolve_beacon_by_ibeacon(uuid, major, minor) is None:
                continue

            beacon_key = make_ibeacon_key(uuid, major, minor)

            rssi_block = entry.get("rssi", {})
            rssi_avg = rssi_block.get("avg")
            if rssi_avg is None:
                continue

            buf = self._buffers.setdefault(beacon_key, _BeaconBuffer())
            buf.readings[ap_mac_colons] = _BeaconReading(
                ap_mac_colons=ap_mac_colons,
                rssi=float(rssi_avg),
                ap_x=ap_x,
                ap_y=ap_y,
                received_at=now_mono,
            )
            buffered += 1

        emitted = self._flush_ready_beacons()

        return {
            "status": "ok",
            "ap": ap_mac_colons,
            "beacons_buffered": buffered,
            "beacons_positioned": emitted,
        }

    # ── Buffer flush ────────────────────────────────────────────────────────────

    def _flush_ready_beacons(self) -> int:
        """
        Evict stale readings, then emit positioning for beacons with enough fresh APs.
        Returns count of beacons sent to the pipeline this call.
        """
        now_mono = time.monotonic()
        emitted = 0

        for beacon_key, buf in list(self._buffers.items()):
            fresh = {
                ap_mac: r
                for ap_mac, r in buf.readings.items()
                if now_mono - r.received_at <= BUFFER_WINDOW_S
            }
            buf.readings = fresh

            if len(fresh) < MIN_APS_FOR_POSITION:
                continue

            # beacon_key is "uuid:major:minor"
            try:
                uuid, major, minor = beacon_key.split(":")
            except ValueError:
                continue
            identity = resolve_beacon_by_ibeacon(uuid, major, minor)
            if identity is None:
                continue

            readings = [
                APRssiReading(
                    ap_mac=r.ap_mac_colons,
                    rssi=r.rssi,
                    ap_x=r.ap_x,
                    ap_y=r.ap_y,
                )
                for r in fresh.values()
            ]

            # Use person_id as reporter_mac so the RTDB position key is stable
            # regardless of the phone's rotating BLE MAC.
            payload = OmadaTelemetryPayload(
                reporter_mac=identity["person_id"],
                timestamp=utcnow_iso(),
                readings=readings,
                person_id=identity["person_id"],
                person_type=identity["person_type"],
                label=identity["label"],
            )

            try:
                position = positioning_service.compute_position(payload)
                if position:
                    safety_service.run_all_checks(position)
                emitted += 1
            except Exception as e:
                print(f"[OMADA] positioning failed for beacon {beacon_key}: {e}")

        return emitted


omada_ingest_service = OmadaIngestService()
