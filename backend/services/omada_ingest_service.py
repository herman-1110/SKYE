"""
Omada RSSI Ingestion Service

Inverts Omada's AP-centric BLE scan payloads into SKYE's beacon-centric telemetry,
buffering readings across multiple APs over a short rolling window before emitting
to the positioning pipeline.

AP-centric in:  one payload per AP, listing all beacons that AP heard.
Beacon-centric out: one OmadaTelemetryPayload per beacon, listing all APs that heard it.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from firebase_admin import db as rtdb

from config.beacon_registry import make_ibeacon_key, BeaconIdentity
from models.telemetry import APRssiReading, OmadaTelemetryPayload
from repositories.ap_repository import ap_repository
from repositories.beacon_repository import beacon_repository
from repositories.floor_repository import floor_repository
from services.positioning_service import positioning_service
from services.proximity_service import proximity_service
from services.safety_service import safety_service
from utils.timestamp_utils import utcnow_iso

# How long a beacon's AP readings stay valid in the buffer (seconds).
# Omada APs report ~every 1 s but not synchronised; 2 s gives all APs time to chime in.
BUFFER_WINDOW_S = 2.0

# Minimum distinct APs that must hear a beacon before we attempt positioning.
MIN_APS_FOR_POSITION = 3

# Cap how often positioning runs per beacon. The 3 APs POST independently
# (~every 2 s, staggered), so without this guard _flush_ready_beacons emits on
# EVERY POST — 3 solves/cycle on 1-fresh-2-stale readings, which stutters the
# Kalman velocity estimate and makes the dot hop while moving. Emitting at most
# once per AP-report period collapses that to a single solve on the freshest
# reading from each AP. Set to ~0.9x your per-AP report interval.
EMIT_MIN_INTERVAL_S = 1.8


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
    floor_id: str
    building_id: str
    received_at: float  # time.monotonic() when buffered


@dataclass
class _BeaconBuffer:
    readings: Dict[str, _BeaconReading] = field(default_factory=dict)


class OmadaIngestService:
    def __init__(self) -> None:
        # beacon MAC (colon-less) → buffer of per-AP readings
        self._buffers: Dict[str, _BeaconBuffer] = {}
        # Floor is resolved per-AP (which floor is THIS AP actually placed on),
        # not from a single global "active floor" — two floors can be active in
        # two different buildings at once, and this must not conflate them.
        #   floor_id -> {ap_mac (colons, upper): (x_m, y_m)}
        self._ap_coords: Dict[str, Dict[str, tuple[float, float]]] = {}
        #   floor_id -> time.monotonic() this floor's AP set was last loaded
        self._ap_cache_loaded_at: Dict[str, float] = {}
        #   ap_mac (colons, upper) -> (floor_id, building_id) it currently resolves to
        self._ap_floor_of: Dict[str, tuple[str, str]] = {}
        self._AP_CACHE_TTL_S = 30.0
        # beacon key (uuid:major:minor) -> time.monotonic() of last positioning emit
        self._last_emit: Dict[str, float] = {}
        # iBeacon identity cache (hot path) — mirrors the AP cache above
        self._beacon_cache: Dict[str, BeaconIdentity] = {}
        self._beacon_cache_loaded_at: float = 0.0
        self._BEACON_CACHE_TTL_S = 30.0
        # /beacon_scans janitor: drop ambient-BLE nodes that haven't been heard in a while.
        # Registered beacons are kept regardless of age (Status column needs them, and the
        # set is bounded). Throttle ensures we don't hammer RTDB on every AP report.
        self._last_janitor_run: float = 0.0
        self._JANITOR_INTERVAL_S = 60.0      # run no more than once per 60 s
        self._STALE_BEACON_S = 300.0         # unregistered + last_seen > 300 s ago → delete

    # ── AP coordinate cache ─────────────────────────────────────────────────────

    def _refresh_ap_cache(self, ap_mac: str) -> None:
        """Resolve which floor `ap_mac` is actually placed on (via a global,
        cross-building lookup by MAC — not "whichever floor happens to be
        active"), then load that whole floor's AP set in one shot so peers on
        the same floor benefit from this same refresh."""
        mac_key = ap_mac.upper()
        matches = ap_repository.get_by_mac_global(ap_mac)
        if not matches:
            # AP is online but not placed on any floor. Leave it unresolved —
            # the caller falls back to the online_unregistered response.
            self._ap_floor_of.pop(mac_key, None)
            return
        if len(matches) > 1:
            matches = sorted(matches, key=lambda a: a.floor_id)
            competing = sorted({a.floor_id for a in matches})
            print(
                f"[OMADA] WARNING: AP {ap_mac} is placed on multiple floors "
                f"{competing} — using {matches[0].floor_id} deterministically"
            )
        resolved = matches[0]
        floor_id, building_id = resolved.floor_id, resolved.building_id

        aps = ap_repository.get_all(building_id, floor_id)

        # Every AP on the floor sitting at exactly (0, 0) means they were
        # placed before the floor was calibrated (create-time guard now
        # prevents new instances of this, but pre-existing data isn't
        # migrated). Cheap to check here since it only runs on a cache
        # miss/TTL-expiry — names the exact fix rather than leaving the
        # symptom (everyone clamped into a corner) to be debugged from scratch.
        if aps and all(a.x_m == 0.0 and a.y_m == 0.0 for a in aps):
            print(
                f"[OMADA] WARNING: all {len(aps)} APs on floor {floor_id} have zeroed "
                f"coordinates — re-save the floor scale to re-derive them."
            )

        self._ap_coords[floor_id] = {a.mac.upper(): (a.x_m, a.y_m) for a in aps}
        self._ap_cache_loaded_at[floor_id] = time.monotonic()
        for a in aps:
            self._ap_floor_of[a.mac.upper()] = (floor_id, building_id)

    def _get_ap_coords(self, ap_mac_colons: str) -> Optional[tuple[float, float, str, str]]:
        """Returns (x_m, y_m, floor_id, building_id) for this AP, resolved from
        whichever floor it's actually placed on. None if the AP is online but
        not placed anywhere — callers must not fall back to any other floor."""
        mac_key = ap_mac_colons.upper()

        resolution = self._ap_floor_of.get(mac_key)
        if resolution is not None:
            floor_id, building_id = resolution
            loaded_at = self._ap_cache_loaded_at.get(floor_id, 0.0)
            if time.monotonic() - loaded_at <= self._AP_CACHE_TTL_S:
                coords = self._ap_coords.get(floor_id, {}).get(mac_key)
                if coords is not None:
                    return (coords[0], coords[1], floor_id, building_id)

        # Not yet resolved, this floor's cache TTL expired, or this specific AP
        # is missing from it (e.g. just placed) — force a resolve for this AP.
        self._refresh_ap_cache(ap_mac_colons)
        resolution = self._ap_floor_of.get(mac_key)
        if resolution is None:
            return None
        floor_id, building_id = resolution
        coords = self._ap_coords.get(floor_id, {}).get(mac_key)
        if coords is None:
            return None
        return (coords[0], coords[1], floor_id, building_id)

    # ── Beacon identity cache (resolve iBeacon triple → person) ──────────────────

    def _refresh_beacon_cache(self) -> None:
        beacons = beacon_repository.get_all()
        self._beacon_cache = {
            make_ibeacon_key(b.uuid, b.major, b.minor): {
                "person_id": b.person_id,
                "person_type": b.person_type,
                "label": b.label,
                "tx_power": b.tx_power,
            }
            for b in beacons
        }
        self._beacon_cache_loaded_at = time.monotonic()

    def _resolve_beacon(self, uuid: str, major: str, minor: str) -> Optional[BeaconIdentity]:
        """Cached identity lookup. Misses return None WITHOUT a Firestore read — ambient
        BLE makes misses common, so refresh-per-miss would hammer Firestore. Newly added
        beacons resolve on the next packet via invalidate_beacon_cache()."""
        if time.monotonic() - self._beacon_cache_loaded_at > self._BEACON_CACHE_TTL_S:
            self._refresh_beacon_cache()
        return self._beacon_cache.get(make_ibeacon_key(uuid, major, minor))

    def invalidate_beacon_cache(self) -> None:
        """Mark the cache stale so the next _resolve_beacon reloads from Firestore.
        Called by beacon_service after any create/update/delete."""
        self._beacon_cache_loaded_at = 0.0

    # ── Heartbeat ───────────────────────────────────────────────────────────────

    def _write_ap_heartbeat(self, ap_mac_colons: str, name: str = "") -> None:
        """Write last-seen heartbeat for a reporting AP to RTDB.
        Called for every reporting AP — registered or not — so the dashboard can
        surface online-but-unplaced APs (with their reported name) in the detection panel."""
        key = ap_mac_colons.replace(":", "_")
        try:
            rtdb.reference(f"/ap_heartbeats/{key}").set({
                "mac": ap_mac_colons,
                "name": name or "",
                "last_seen": int(time.time()),
            })
        except Exception as e:
            print(f"[OMADA] WARNING: heartbeat write failed for {ap_mac_colons}: {e}")

    def _write_beacon_scan(
        self,
        beacon_key: str,           # "uuid:major:minor" from make_ibeacon_key
        uuid: str,
        major: str,
        minor: str,
        rssi: float,
        ap_mac_colons: str,
        registered: bool,
    ) -> None:
        """Write a lightweight last-seen record to RTDB for every heard beacon.
        Called before the solve gate so both registered and unknown beacons are visible.
        Node key uses underscores (RTDB keys cannot contain colons)."""
        node_key = beacon_key.replace(":", "_")
        try:
            rtdb.reference(f"/beacon_scans/{node_key}").set({
                "uuid": uuid,
                "major": major,
                "minor": minor,
                "rssi": float(rssi),
                "ap_mac": ap_mac_colons,
                "last_seen": int(time.time()),
                "registered": registered,
            })
        except Exception as e:
            print(f"[OMADA] WARNING: beacon_scan write failed for {node_key}: {e}")

    def _prune_stale_unregistered_scans(self) -> None:
        """Delete /beacon_scans/{key} nodes that are unregistered AND haven't been
        heard for > _STALE_BEACON_S seconds. Registered nodes are kept regardless
        of age — bounded set + useful debug timestamp. Called only via the throttle
        in ingest() so the full-tree read happens at most once per _JANITOR_INTERVAL_S."""
        try:
            snap = rtdb.reference("/beacon_scans").get() or {}
            if not isinstance(snap, dict):
                return
            cutoff = int(time.time()) - int(self._STALE_BEACON_S)
            for node_key, data in snap.items():
                if not isinstance(data, dict):
                    continue
                if data.get("registered"):
                    continue
                if int(data.get("last_seen", 0)) < cutoff:
                    rtdb.reference(f"/beacon_scans/{node_key}").delete()
        except Exception as e:
            print(f"[OMADA] WARNING: beacon_scans janitor failed: {e}")

    # ── Main entry point ────────────────────────────────────────────────────────

    def ingest(self, raw: dict) -> dict:
        """
        Process one raw Omada payload (one AP's scan results).
        Returns a summary dict for the HTTP response.

        Holds positioning_service.pipeline_lock for the full call — this
        service's beacon buffers (_buffers, _last_emit, _ap_coords, etc.)
        are plain unlocked dicts, only ever safe because every call used to
        run serialized on the event loop. Now that the route offloads this
        to a threadpool, concurrent AP POSTs (routinely ~3 per cycle, per
        BUFFER_WINDOW_S above) must stay mutually exclusive, and mutually
        exclusive with the /telemetry (simulation) path, which shares
        positioning_service/safety_service state with this one.
        """
        with positioning_service.pipeline_lock:
            return self._ingest_locked(raw)

    def _ingest_locked(self, raw: dict) -> dict:
        reporter = raw.get("reporter", {})
        ap_mac_raw = reporter.get("mac", "")
        reported: List[dict] = raw.get("reported", [])
        ap_name = reporter.get("name", "?")

        # Throttled janitor: prune stale unregistered /beacon_scans nodes.
        # No-op on most ingest cycles — only fires once per _JANITOR_INTERVAL_S.
        janitor_now = time.monotonic()
        if janitor_now - self._last_janitor_run > self._JANITOR_INTERVAL_S:
            self._last_janitor_run = janitor_now
            self._prune_stale_unregistered_scans()

        if not ap_mac_raw:
            return {"status": "ignored", "reason": "no reporter.mac"}

        ap_mac_colons = _format_mac_colons(_normalise_mac(ap_mac_raw))

        # Write heartbeat for every reporting AP — even unregistered ones —
        # so the dashboard can surface online-but-unplaced APs (with their name).
        self._write_ap_heartbeat(ap_mac_colons, reporter.get("name", ""))

        # ── DEBUG: full raw Omada payload dump — every reporting AP ──────
        # Runs before the registration gate below: an AP that hasn't been
        # placed on a floor yet still returns "online_unregistered" and never
        # reaches the positioning pipeline, but you still want to see exactly
        # what it sent while wiring it up.
        print("[OMADA] ═══════════════════════════════════════════════════════════")
        print(f"[OMADA] AP REPORT from '{ap_name}' ({ap_mac_raw or 'NO MAC'})")
        print(f"[OMADA] ── Reporter block ──")
        for k, v in reporter.items():
            print(f"[OMADA]     {k:12s}: {v}")
        print(f"[OMADA] ── Reported beacons: {len(reported)} ──")
        if not reported:
            print("[OMADA]     (none — AP scanned no beacons this cycle)")
        for i, b in enumerate(reported):
            bmac     = b.get("mac", "?")
            dclass   = b.get("deviceClass", [])
            model    = b.get("model", "")
            lastseen = b.get("lastseen", "?")
            rssi_avg = (b.get("rssi") or {}).get("avg", "?")
            ib       = b.get("ibeacon", {}) or {}
            txpower  = b.get("txpower", "")
            sensors  = b.get("sensors", {}) or {}

            print(f"[OMADA]   ┌─ Beacon #{i + 1}: {bmac}")
            print(f"[OMADA]   │   deviceClass : {dclass}")
            if model:
                print(f"[OMADA]   │   model       : {model}")
            print(f"[OMADA]   │   lastseen    : {lastseen}")
            print(f"[OMADA]   │   rssi.avg    : {rssi_avg} dBm")
            if ib:
                print(f"[OMADA]   │   iBeacon     : uuid={ib.get('uuid','?')} "
                      f"major={ib.get('major','?')} minor={ib.get('minor','?')} "
                      f"power={ib.get('power','?')}")
            if txpower != "":
                print(f"[OMADA]   │   txpower     : {txpower}")
            if sensors:
                print(f"[OMADA]   │   sensors     : {sensors}")
            print(f"[OMADA]   └─")

        print(f"[OMADA] ── Raw JSON ──")
        print(f"[OMADA] {json.dumps(raw, separators=(',', ':'))}")
        print("[OMADA] ═══════════════════════════════════════════════════════════")
        # ─────────────────────────────────────────────────────────────────

        ap_coords = self._get_ap_coords(ap_mac_colons)
        if ap_coords is None:
            return {
                "status": "online_unregistered",
                "ap": ap_mac_colons,
                "reason": "AP online but not placed on any floor — heartbeat written",
            }
        ap_x, ap_y, ap_floor_id, ap_building_id = ap_coords

        now_mono = time.monotonic()
        buffered = 0

        for entry in reported:
            ib = entry.get("ibeacon") or {}
            uuid  = ib.get("uuid", "")
            major = ib.get("major", "")
            minor = ib.get("minor", "")

            # Skip entries with no iBeacon block (e.g. Eddystone-only) for now.
            if not uuid:
                continue

            beacon_key = make_ibeacon_key(uuid, major, minor)
            identity = self._resolve_beacon(uuid, major, minor)

            # Write scan record for ALL heard beacons (registered or not) BEFORE the
            # solve gate. Powers online/offline status + unknown beacon discovery.
            rssi_block_scan = entry.get("rssi", {})
            rssi_avg_scan = rssi_block_scan.get("avg")
            if rssi_avg_scan is not None:
                self._write_beacon_scan(
                    beacon_key=beacon_key,
                    uuid=uuid,
                    major=major,
                    minor=minor,
                    rssi=float(rssi_avg_scan),
                    ap_mac_colons=ap_mac_colons,
                    registered=(identity is not None),
                )

            # Unregistered beacons stop here — they don't enter the positioning pipeline.
            if identity is None:
                continue

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
                floor_id=ap_floor_id,
                building_id=ap_building_id,
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
        Positioning is rate-limited per beacon (EMIT_MIN_INTERVAL_S) so the 3 staggered
        AP POSTs in a cycle produce a single solve, not three.
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

            if not fresh:
                continue

            # Rate-limit: collapse the staggered AP POSTs/cycle into one solve —
            # applies to both the multilateration path and the proximity fallback.
            if now_mono - self._last_emit.get(beacon_key, 0.0) < EMIT_MIN_INTERVAL_S:
                continue

            # beacon_key is "uuid:major:minor"
            try:
                uuid, major, minor = beacon_key.split(":")
            except ValueError:
                continue
            identity = self._resolve_beacon(uuid, major, minor)
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
            tx_power = identity.get("tx_power", -59.0)

            # Which floor is this beacon actually being heard on? Per-beacon, from
            # its own fresh readings — never a global "active floor" guess. Usually
            # every fresh reading agrees (all APs on one floor); on genuine
            # cross-floor bleed, trust the strongest signal.
            fresh_list = list(fresh.values())
            floor_ids = {r.floor_id for r in fresh_list if r.floor_id}
            if len(floor_ids) > 1:
                strongest = max(fresh_list, key=lambda r: r.rssi)
                beacon_floor_id, beacon_building_id = strongest.floor_id, strongest.building_id
                print(
                    f"[OMADA] beacon {beacon_key} heard across floors "
                    f"{sorted(floor_ids)}, using {beacon_floor_id}"
                )
            else:
                beacon_floor_id, beacon_building_id = fresh_list[0].floor_id, fresh_list[0].building_id

            # Stamp BEFORE solving so a thrown exception can't bypass the rate-limit.
            self._last_emit[beacon_key] = now_mono

            if len(fresh) < MIN_APS_FOR_POSITION:
                # Too few APs for a multilateration solve — anchor to the closest
                # AP instead of dropping the reading. Hops to a new AP on its own
                # the next time a different one reports the strongest RSSI.
                try:
                    position = proximity_service.compute_position(
                        person_id=identity["person_id"],
                        person_type=identity["person_type"],
                        label=identity["label"],
                        readings=readings,
                        tx_power=tx_power,
                        floor_id=beacon_floor_id,
                        building_id=beacon_building_id,
                    )
                    if position:
                        safety_service.run_all_checks(position)
                    emitted += 1
                except Exception as e:
                    print(f"[OMADA] proximity fallback failed for beacon {beacon_key}: {e}")
                continue

            # Use person_id as reporter_mac so the RTDB position key is stable
            # regardless of the phone's rotating BLE MAC.
            payload = OmadaTelemetryPayload(
                reporter_mac=identity["person_id"],
                timestamp=utcnow_iso(),
                readings=readings,
                person_id=identity["person_id"],
                person_type=identity["person_type"],
                label=identity["label"],
                tx_power=tx_power,
            )

            try:
                position = positioning_service.compute_position(
                    payload, floor_id=beacon_floor_id, building_id=beacon_building_id
                )
                if position:
                    safety_service.run_all_checks(position)
                emitted += 1
            except Exception as e:
                print(f"[OMADA] positioning failed for beacon {beacon_key}: {e}")

        return emitted


omada_ingest_service = OmadaIngestService()
