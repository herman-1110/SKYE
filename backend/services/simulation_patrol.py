"""
SKYE Simulation — Pure Patrol (File 1)

Two guards patrol between AP zones in opposite directions.
Each guard wanders naturally within each AP's zone before moving on.
No safety events. Use this to demonstrate clean patrol behaviour.

Run: venv/Scripts/python.exe services/simulation_patrol.py
"""
from __future__ import annotations
import asyncio
import math
import os
import random
import sys
import time
import uuid
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import httpx
import firebase_admin
from firebase_admin import credentials, db as rtdb

from config.settings import settings
from models.patrol_log import PatrolLogRecord
from repositories.ap_repository import ap_repository
from repositories.floor_repository import floor_repository
from repositories.patrol_log_repository import patrol_log_repository
from utils.timestamp_utils import utcnow_iso

# ── Constants ─────────────────────────────────────────────────────────────
TICK_INTERVAL_S    = 1.0
BACKEND_URL        = "http://localhost:8000"
TELEMETRY_ENDPOINT = f"{BACKEND_URL}/telemetry"

# How long (in ticks) a guard wanders within an AP zone before moving on
WANDER_TICKS_MIN = 5
WANDER_TICKS_MAX = 8

# Wander radius around each AP in metres
WANDER_RADIUS_M = 2.0

SIMULATED_CCTVS: List[Dict] = [
    {"mac": "A8:57:4E:3C:11:01", "name": "VIGI C340 (Sim)"},
]

# ── Mutable state ─────────────────────────────────────────────────────────
_floor_aps: List[Dict] = []
_BOUNDARY: Dict[str, float] = {"x_min": 0.0, "x_max": 12.0, "y_min": 0.0, "y_max": 10.0}

SIMULATED_BEACONS: List[Dict] = [
    {
        "mac": "AA:BB:CC:DD:EE:01", "person_id": "guard-001",
        "person_type": "guard", "label": "Guard Alpha",
        "x_m": 0.0, "y_m": 0.0, "vx": 0.0, "vy": 0.0,
        "ap_order": [],        # populated at startup: [0, 1, 2] forward
        "current_ap_idx": 0,   # index into ap_order
        "wander_ticks": 0,     # ticks remaining in current AP zone
        "state": "moving",     # "moving" | "wandering"
        "wander_target": None,
        "shift_id": "",        # rotates every time this guard completes a full loop
        "loops_completed": 0,  # increments on each full loop completion
        "checkpoints_this_loop": 0,   # counts AP visits in current loop; resets on loop completion
    },
    {
        "mac": "AA:BB:CC:DD:EE:04", "person_id": "guard-002",
        "person_type": "guard", "label": "Guard Beta",
        "x_m": 0.0, "y_m": 0.0, "vx": 0.0, "vy": 0.0,
        "ap_order": [],        # populated at startup: same forward route as Alpha, offset start
        "current_ap_idx": 0,
        "wander_ticks": 0,
        "state": "moving",
        "wander_target": None,
        "shift_id": "",        # rotates every time this guard completes a full loop
        "loops_completed": 0,  # increments on each full loop completion
        "checkpoints_this_loop": 0,   # counts AP visits in current loop; resets on loop completion
    },
]

# ── Runtime AP removal (called by floor_service on AP delete) ─────────────
def remove_ap(mac: str) -> None:
    global _floor_aps
    idx = next((i for i, ap in enumerate(_floor_aps) if ap["mac"] == mac), None)
    if idx is None:
        return
    _floor_aps = [ap for ap in _floor_aps if ap["mac"] != mac]
    for beacon in SIMULATED_BEACONS:
        beacon["ap_order"] = [
            i if i < idx else i - 1
            for i in beacon["ap_order"] if i != idx
        ]
        if beacon["ap_order"]:
            beacon["current_ap_idx"] = beacon["current_ap_idx"] % len(beacon["ap_order"])
        else:
            beacon["current_ap_idx"] = 0
        beacon["checkpoints_this_loop"] = 0

# ── Firebase init ─────────────────────────────────────────────────────────
def _init_firebase_if_needed() -> None:
    if not firebase_admin._apps:
        cred = credentials.Certificate(settings.FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred, {"databaseURL": settings.FIREBASE_RTDB_URL})

# ── Heartbeat writer ──────────────────────────────────────────────────────
def _write_heartbeats() -> None:
    now = int(time.time())
    for ap in _floor_aps:
        key = ap["mac"].replace(":", "_")
        rtdb.reference(f"/ap_heartbeats/{key}").set({"last_seen": now, "mac": ap["mac"]})
    for cctv in SIMULATED_CCTVS:
        key = cctv["mac"].replace(":", "_")
        rtdb.reference(f"/cctv_heartbeats/{key}").set({
            "last_seen": now, "mac": cctv["mac"], "device_name": cctv["name"]
        })

# ── Movement helpers ──────────────────────────────────────────────────────
def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)

def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))

def _clamp_position(x: float, y: float) -> tuple[float, float]:
    return (
        _clamp(x, _BOUNDARY["x_min"], _BOUNDARY["x_max"]),
        _clamp(y, _BOUNDARY["y_min"], _BOUNDARY["y_max"]),
    )

def _move_toward(beacon: Dict, tx: float, ty: float, speed: float) -> bool:
    """Move beacon toward target. Returns True when arrived (within 0.5m)."""
    dx = tx - beacon["x_m"]
    dy = ty - beacon["y_m"]
    d = math.sqrt(dx * dx + dy * dy)
    if d < 0.5:
        beacon["vx"] = 0.0
        beacon["vy"] = 0.0
        return True
    step = min(speed, d)
    beacon["x_m"] += (dx / d) * step
    beacon["y_m"] += (dy / d) * step
    beacon["vx"] = (dx / d) * speed
    beacon["vy"] = (dy / d) * speed
    return False

def _scale_speed(base: float) -> float:
    """Scale speed proportionally to actual AP spread so movement is
    visible regardless of floor size. Falls back to base if < 2 APs."""
    if len(_floor_aps) < 2:
        return base
    xs = [ap["x_m"] for ap in _floor_aps]
    ys = [ap["y_m"] for ap in _floor_aps]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    spread = math.sqrt(w * w + h * h)          # diagonal of AP bounding box
    if spread < 1.0:
        return base
    # Target: cross the full AP spread in ~10 ticks at base speed
    natural_speed = spread / 10.0
    # Allow up to 2× the natural speed; never below base
    return max(base, min(natural_speed, base * 2.0))

def _wander_within_ap(beacon: Dict, ap: Dict) -> None:
    """
    Move beacon to a random point within WANDER_RADIUS_M of the AP.
    A new target is only chosen once the beacon arrives at the current one,
    preventing the random-walk drift that carries beacons outside the zone.
    """
    if beacon.get("wander_target") is None:
        beacon["wander_target"] = _clamp_position(
            ap["x_m"] + random.uniform(-WANDER_RADIUS_M, WANDER_RADIUS_M),
            ap["y_m"] + random.uniform(-WANDER_RADIUS_M, WANDER_RADIUS_M),
        )
    tx, ty = beacon["wander_target"]
    arrived = _move_toward(beacon, tx, ty, speed=_scale_speed(0.4))
    if arrived:
        beacon["wander_target"] = None

# ── LDPL RSSI ─────────────────────────────────────────────────────────────
def _rssi_from_distance(d: float) -> int:
    d = max(d, 0.1)
    rssi = settings.TX_POWER_DEFAULT - 10.0 * settings.PATH_LOSS_EXPONENT * math.log10(d)
    return int(round(rssi + random.gauss(0, settings.RSSI_NOISE_STD)))

def _build_payload(beacon: Dict, timestamp: str) -> Dict:
    readings = []
    for ap in _floor_aps:
        d = _dist(ap["x_m"], ap["y_m"], beacon["x_m"], beacon["y_m"])
        rssi = _rssi_from_distance(d)
        if rssi < -95:
            continue
        readings.append({"ap_mac": ap["mac"], "rssi": rssi, "ap_x": ap["x_m"], "ap_y": ap["y_m"]})
    return {
        "reporter_mac": beacon["mac"],
        "timestamp": timestamp,
        "readings": readings,
        "person_id": beacon["person_id"],
        "person_type": beacon["person_type"],
        "label": beacon.get("label", ""),
    }

# ── Patrol log writer ─────────────────────────────────────────────────────
def _write_patrol_log(beacon: Dict, ap: Dict) -> None:
    record = PatrolLogRecord(
        log_id=str(uuid.uuid4()),
        guard_id=beacon["person_id"],
        checkpoint_id=ap["mac"],
        checkpoint_name=ap["name"],
        expected_arrival=utcnow_iso(),
        actual_arrival=utcnow_iso(),
        dwell_time_seconds=random.randint(settings.MIN_DWELL_SECONDS, 60),
        min_dwell_required=settings.MIN_DWELL_SECONDS,
        ble_detected=True,
        vigi_detected=True,
        compliant=True,
        shift_id=beacon["shift_id"],
    )
    patrol_log_repository.save(record)

# ── Per-guard shift rotation ──────────────────────────────────────────────
def _rotate_shift(beacon: Dict) -> None:
    """Assign a new shift_id to this guard after completing a full loop."""
    old = beacon["shift_id"]
    beacon["shift_id"] = f"shift-{uuid.uuid4().hex[:8]}"
    print(
        f"[SIM] ── {beacon['label']} shift complete "
        f"(loop {beacon['loops_completed']}) ──────────────────"
    )
    print(f"[SIM]    Closed : {old}")
    print(f"[SIM]    New    : {beacon['shift_id']}")
    print(f"[SIM] ───────────────────────────────────────────────────────────")

# ── Guard patrol tick ─────────────────────────────────────────────────────
def _tick_guard(beacon: Dict) -> None:
    """
    State machine:
      moving   → walk toward current AP zone centre
      wandering → wander within AP zone for WANDER_TICKS ticks, then advance to next AP
    """
    ap_order = beacon["ap_order"]
    if not ap_order:
        return

    current_ap = _floor_aps[ap_order[beacon["current_ap_idx"]]]

    if beacon["state"] == "moving":
        arrived = _move_toward(
            beacon, current_ap["x_m"], current_ap["y_m"],
            speed=_scale_speed(0.6)
        )
        if arrived:
            beacon["state"] = "wandering"
            beacon["wander_ticks"] = random.randint(WANDER_TICKS_MIN, WANDER_TICKS_MAX)
            try:
                _write_patrol_log(beacon, current_ap)
            except Exception as e:
                print(f"[SIM] WARNING: patrol log write failed for {beacon['label']} "
                      f"at {current_ap['name']}: {e}")
            print(f"[SIM] {beacon['label']:12s} arrived at {current_ap['name']} — wandering for {beacon['wander_ticks']} ticks")

    elif beacon["state"] == "wandering":
        _wander_within_ap(beacon, current_ap)
        beacon["wander_ticks"] -= 1
        if beacon["wander_ticks"] <= 0:
            beacon["checkpoints_this_loop"] += 1
            n_aps = len(beacon["ap_order"])

            if beacon["checkpoints_this_loop"] >= n_aps:
                beacon["loops_completed"] += 1
                beacon["checkpoints_this_loop"] = 0
                beacon["current_ap_idx"] = 0
                try:
                    _rotate_shift(beacon)
                except Exception as e:
                    print(f"[SIM] WARNING: shift rotation failed for {beacon['label']}: {e}")
                    beacon["shift_id"] = f"shift-{uuid.uuid4().hex[:8]}"
            else:
                beacon["current_ap_idx"] = (beacon["current_ap_idx"] + 1) % n_aps

            beacon["state"] = "moving"
            beacon["wander_target"] = None

            next_ap = _floor_aps[beacon["ap_order"][beacon["current_ap_idx"]]]
            print(f"[SIM] {beacon['label']:12s} moving to {next_ap['name']}")

# ── Main loop ─────────────────────────────────────────────────────────────
async def run_simulation() -> None:
    global _floor_aps, _BOUNDARY

    _init_firebase_if_needed()

    active_floor = floor_repository.get_any_active()
    if not active_floor:
        print("[SIM] No active floor — activate a floor in Floor Plans first")
        return

    fetched_aps = ap_repository.get_all(active_floor.building_id, active_floor.id)
    if len(fetched_aps) < 2:
        print("[SIM] Need at least 2 APs on the active floor")
        return

    # Build AP lookup by ID
    ap_by_id = {ap.id: ap for ap in fetched_aps}

    # Use admin-configured patrol route if available
    if active_floor.patrol_enabled and active_floor.patrol_route:
        ordered_aps = []
        for ap_id in active_floor.patrol_route:
            ap = ap_by_id.get(ap_id)
            if ap:
                ordered_aps.append(ap)
        if len(ordered_aps) >= 2:
            _floor_aps = [{"id": ap.id, "mac": ap.mac, "name": ap.name,
                           "x_m": ap.x_m, "y_m": ap.y_m} for ap in ordered_aps]
            print(f"[SIM] Using configured patrol route ({len(_floor_aps)} APs)")
        else:
            print("[SIM] WARNING: patrol_route has < 2 valid APs — falling back to coordinate sort")
            _floor_aps = [{"id": ap.id, "mac": ap.mac, "name": ap.name,
                           "x_m": ap.x_m, "y_m": ap.y_m} for ap in fetched_aps]
            _floor_aps.sort(key=lambda a: (a["x_m"], a["y_m"]))
    else:
        print("[SIM] No patrol route configured — using coordinate sort")
        _floor_aps = [{"id": ap.id, "mac": ap.mac, "name": ap.name,
                       "x_m": ap.x_m, "y_m": ap.y_m} for ap in fetched_aps]
        _floor_aps.sort(key=lambda a: (a["x_m"], a["y_m"]))
    print(f"[SIM] Loaded {len(_floor_aps)} AP(s) from floor '{active_floor.name}':")
    for ap in _floor_aps:
        print(f"[SIM]   {ap['name']:20s}  {ap['mac']}  ({ap['x_m']:.1f}m, {ap['y_m']:.1f}m)")

    PADDING = 2.0
    all_x = [ap["x_m"] for ap in _floor_aps]
    all_y = [ap["y_m"] for ap in _floor_aps]
    _BOUNDARY = {
        "x_min": max(0.0, min(all_x) - PADDING),
        "x_max": max(all_x) + PADDING,
        "y_min": max(0.0, min(all_y) - PADDING),
        "y_max": max(all_y) + PADDING,
    }
    print(f"[SIM] Boundary: x={_BOUNDARY['x_min']:.1f}–{_BOUNDARY['x_max']:.1f}m  "
          f"y={_BOUNDARY['y_min']:.1f}–{_BOUNDARY['y_max']:.1f}m")

    n = len(_floor_aps)

    # Both guards follow the configured route in order.
    # Guard Beta starts mid-route so they are offset and don't overlap.
    mid = n // 2

    # Starting AP index per guard
    start_indices = [0, mid]
    start_aps     = [_floor_aps[0], _floor_aps[mid]]

    for i, beacon in enumerate(SIMULATED_BEACONS):
        beacon["ap_order"]        = list(range(n))
        beacon["current_ap_idx"]  = start_indices[i]
        beacon["x_m"]             = start_aps[i]["x_m"]
        beacon["y_m"]             = start_aps[i]["y_m"]
        beacon["vx"]              = 0.0
        beacon["vy"]              = 0.0
        beacon["state"]           = "moving"
        beacon["wander_ticks"]    = 0
        beacon["wander_target"]   = None
        beacon["shift_id"]             = f"shift-{uuid.uuid4().hex[:8]}"
        beacon["loops_completed"]      = 0
        # A guard starting at mid-route has already "skipped" start_indices[i] APs.
        # Pre-fill checkpoints_this_loop so loop completion fires correctly.
        beacon["checkpoints_this_loop"] = start_indices[i]

    route_str = " → ".join(_floor_aps[i]["name"] for i in range(n))
    print(f"[SIM] Guard Alpha: {route_str} → loop (start: AP 1)")
    print(f"[SIM] Guard Beta:  {route_str} → loop (start: AP {mid + 1})")

    print(f"[SIM] Pure Patrol simulation started. Ctrl+C to stop.")
    for beacon in SIMULATED_BEACONS:
        print(f"[SIM]   {beacon['label']:12s} initial shift: {beacon['shift_id']}")
    print(f"[SIM] Computed moving speed : {_scale_speed(0.6):.3f} m/tick")
    print(f"[SIM] Computed wander speed : {_scale_speed(0.4):.3f} m/tick")

    token = settings.OMADA_ACCESS_TOKEN
    headers = {"Authorization": f"Bearer {token}"}
    tick = 0

    # Clear stale positions for ALL simulated beacons (guards + worker + forklift)
    # so switching between simulation modes never leaves ghost markers on the map
    ALL_SIMULATED_MACS = [
        "AA:BB:CC:DD:EE:01",  # Guard Alpha
        "AA:BB:CC:DD:EE:04",  # Guard Beta
        "AA:BB:CC:DD:EE:02",  # Worker 1
        "AA:BB:CC:DD:EE:03",  # Forklift 1
    ]
    print("[SIM] Clearing stale RTDB positions…")
    for mac in ALL_SIMULATED_MACS:
        key = mac.replace(":", "_")
        rtdb.reference(f"/positions/{key}").delete()
    print("[SIM] Stale positions cleared.")

    async with httpx.AsyncClient() as client:
        while True:
            _write_heartbeats()

            for beacon in SIMULATED_BEACONS:
                try:
                    _tick_guard(beacon)
                except Exception as e:
                    print(f"[SIM] ERROR in _tick_guard for {beacon['label']}: {e}")
                    beacon["state"] = "moving"
                    beacon["wander_target"] = None

            now_ts = utcnow_iso()
            for beacon in SIMULATED_BEACONS:
                payload = _build_payload(beacon, now_ts)
                n_readings = len(payload["readings"])
                try:
                    resp = await client.post(TELEMETRY_ENDPOINT, json=payload,
                                             headers=headers, timeout=5.0)
                    print(f"[SIM] tick {tick:4d} | {beacon['label']:12s} → {resp.status_code} ({n_readings} APs) | pos=({beacon['x_m']:.2f}m, {beacon['y_m']:.2f}m)")
                except Exception as e:
                    print(f"[SIM] {beacon['label']} send failed: {e}")

            tick += 1
            await asyncio.sleep(TICK_INTERVAL_S)

if __name__ == "__main__":
    asyncio.run(run_simulation())
