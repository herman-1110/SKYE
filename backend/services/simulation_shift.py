"""
SKYE Simulation — Shift Change (File 3)

Outgoing shift (Guards 1 & 2) patrol one full loop back to their starting AP,
then freeze in place. Incoming shift (Guards 3 & 4) wait at AP[0] during the
outgoing patrol, then begin their own patrol when the shift triggers.

Run: venv/Scripts/python.exe services/simulation_shift.py
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

WANDER_TICKS_MIN = 1
WANDER_TICKS_MAX = 1
WANDER_RADIUS_M  = 1.0

SIMULATED_CCTVS: List[Dict] = [
    {"mac": "A8:57:4E:3C:11:01", "name": "VIGI C340 (Sim)"},
]

# ── Mutable state ─────────────────────────────────────────────────────────
_floor_aps: List[Dict] = []
_BOUNDARY: Dict[str, float] = {"x_min": 0.0, "x_max": 12.0, "y_min": 0.0, "y_max": 10.0}

# shift_complete[i] = True when outgoing guard i has finished their loop
_shift_complete = [False, False]
_shift_triggered = False   # set to True when both outgoing guards finish

OUTGOING_BEACONS: List[Dict] = [
    {
        "mac": "AA:BB:CC:DD:EE:01", "person_id": "guard-001",
        "person_type": "guard", "label": "Guard Alpha",
        "x_m": 0.0, "y_m": 0.0, "vx": 0.0, "vy": 0.0,
        "ap_order": [], "current_ap_idx": 0, "start_ap_idx": 0,
        "wander_ticks": 0, "state": "moving", "wander_target": None,
        "shift_id": "", "loops_completed": 0, "checkpoints_this_loop": 0,
        "frozen": False,
    },
    {
        "mac": "AA:BB:CC:DD:EE:04", "person_id": "guard-002",
        "person_type": "guard", "label": "Guard Beta",
        "x_m": 0.0, "y_m": 0.0, "vx": 0.0, "vy": 0.0,
        "ap_order": [], "current_ap_idx": 0, "start_ap_idx": 0,
        "wander_ticks": 0, "state": "moving", "wander_target": None,
        "shift_id": "", "loops_completed": 0, "checkpoints_this_loop": 0,
        "frozen": False,
    },
]

INCOMING_BEACONS: List[Dict] = [
    {
        "mac": "AA:BB:CC:DD:EE:05", "person_id": "guard-003",
        "person_type": "guard", "label": "Guard Gamma",
        "x_m": 0.0, "y_m": 0.0, "vx": 0.0, "vy": 0.0,
        "ap_order": [], "current_ap_idx": 0, "start_ap_idx": 0,
        "wander_ticks": 0, "state": "moving", "wander_target": None,
        "shift_id": "", "loops_completed": 0, "checkpoints_this_loop": 0,
    },
    {
        "mac": "AA:BB:CC:DD:EE:06", "person_id": "guard-004",
        "person_type": "guard", "label": "Guard Delta",
        "x_m": 0.0, "y_m": 0.0, "vx": 0.0, "vy": 0.0,
        "ap_order": [], "current_ap_idx": 0, "start_ap_idx": 0,
        "wander_ticks": 0, "state": "moving", "wander_target": None,
        "shift_id": "", "loops_completed": 0, "checkpoints_this_loop": 0,
    },
]

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
    if len(_floor_aps) < 2:
        return base
    xs = [ap["x_m"] for ap in _floor_aps]
    ys = [ap["y_m"] for ap in _floor_aps]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    spread = math.sqrt(w * w + h * h)
    if spread < 1.0:
        return base
    natural_speed = spread / 10.0
    return max(base, min(natural_speed, base * 2.0))

def _wander_within_ap(beacon: Dict, ap: Dict) -> None:
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

# ── Shift rotation ────────────────────────────────────────────────────────
def _rotate_shift(beacon: Dict) -> None:
    old = beacon["shift_id"]
    beacon["shift_id"] = f"shift-{uuid.uuid4().hex[:8]}"
    print(f"[SIM] ── {beacon['label']} loop complete ──────────────────────────────")
    print(f"[SIM]    Closed : {old}")
    print(f"[SIM]    New    : {beacon['shift_id']}")
    print(f"[SIM] ───────────────────────────────────────────────────────────────")

# ── Guard patrol tick (shared by outgoing and incoming) ───────────────────
def _tick_guard(beacon: Dict) -> None:
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
                print(f"[SIM] WARNING: patrol log failed for {beacon['label']} "
                      f"at {current_ap['name']}: {e}")
            print(f"[SIM] {beacon['label']:12s} arrived at {current_ap['name']} "
                  f"— wandering for {beacon['wander_ticks']} ticks")

    elif beacon["state"] == "wandering":
        _wander_within_ap(beacon, current_ap)
        beacon["wander_ticks"] -= 1
        if beacon["wander_ticks"] <= 0:
            beacon["checkpoints_this_loop"] += 1
            n_aps = len(beacon["ap_order"])
            next_idx = (beacon["current_ap_idx"] + 1) % n_aps

            returning_to_start = (next_idx == beacon["start_ap_idx"])
            loop_complete = (
                beacon["checkpoints_this_loop"] >= n_aps and returning_to_start
            )

            if loop_complete:
                beacon["loops_completed"] += 1
                beacon["checkpoints_this_loop"] = 0
                beacon["current_ap_idx"] = next_idx
                try:
                    _rotate_shift(beacon)
                except Exception as e:
                    print(f"[SIM] WARNING: shift rotation failed for {beacon['label']}: {e}")
                    beacon["shift_id"] = f"shift-{uuid.uuid4().hex[:8]}"
            else:
                beacon["current_ap_idx"] = next_idx

            beacon["state"] = "moving"
            beacon["wander_target"] = None

            next_ap = _floor_aps[beacon["ap_order"][beacon["current_ap_idx"]]]
            suffix = ""
            if loop_complete:
                suffix = " ← LOOP COMPLETE"
            elif returning_to_start:
                suffix = " ← RETURN TO START"
            print(f"[SIM] {beacon['label']:12s} moving to {next_ap['name']}{suffix}")

# ── Outgoing guard tick — freezes beacon after one full loop ──────────────
def _tick_outgoing(beacon: Dict, guard_idx: int) -> None:
    global _shift_triggered

    if beacon["frozen"]:
        return

    prev_loops = beacon["loops_completed"]
    _tick_guard(beacon)

    if beacon["loops_completed"] > prev_loops:
        beacon["frozen"] = True
        _shift_complete[guard_idx] = True
        print(
            f"[SIM] ══ {beacon['label']} SHIFT COMPLETE — freezing at "
            f"({beacon['x_m']:.2f}m, {beacon['y_m']:.2f}m) ══"
        )
        if all(_shift_complete):
            _shift_triggered = True
            print("[SIM] ══════════════════════════════════════════════")
            print("[SIM]   SHIFT CHANGE — incoming guards now active   ")
            print("[SIM] ══════════════════════════════════════════════")

# ── Main loop ─────────────────────────────────────────────────────────────
async def run_simulation() -> None:
    global _floor_aps, _BOUNDARY, _shift_triggered

    _init_firebase_if_needed()

    active_floor = floor_repository.get_any_active()
    if not active_floor:
        print("[SIM] No active floor — activate a floor in Floor Plans first")
        return

    fetched_aps = ap_repository.get_all(active_floor.building_id, active_floor.id)
    if len(fetched_aps) < 2:
        print("[SIM] Need at least 2 APs on the active floor")
        return

    ap_by_id = {ap.id: ap for ap in fetched_aps}

    if active_floor.patrol_enabled and active_floor.patrol_route:
        ordered_aps = [ap_by_id[ap_id] for ap_id in active_floor.patrol_route if ap_id in ap_by_id]
        if len(ordered_aps) >= 2:
            _floor_aps = [{"id": ap.id, "mac": ap.mac, "name": ap.name,
                           "x_m": ap.x_m, "y_m": ap.y_m} for ap in ordered_aps]
            print(f"[SIM] Using configured patrol route ({len(_floor_aps)} APs)")
        else:
            _floor_aps = [{"id": ap.id, "mac": ap.mac, "name": ap.name,
                           "x_m": ap.x_m, "y_m": ap.y_m} for ap in fetched_aps]
            _floor_aps.sort(key=lambda a: (a["x_m"], a["y_m"]))
    else:
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

    n = len(_floor_aps)
    mid = n // 2

    # Initialise outgoing guards
    outgoing_starts = [0, mid]
    for i, beacon in enumerate(OUTGOING_BEACONS):
        beacon["ap_order"]              = list(range(n))
        beacon["current_ap_idx"]        = outgoing_starts[i]
        beacon["start_ap_idx"]          = outgoing_starts[i]
        beacon["x_m"]                   = _floor_aps[outgoing_starts[i]]["x_m"]
        beacon["y_m"]                   = _floor_aps[outgoing_starts[i]]["y_m"]
        beacon["vx"]                    = 0.0
        beacon["vy"]                    = 0.0
        beacon["state"]                 = "moving"
        beacon["wander_ticks"]          = 0
        beacon["wander_target"]         = None
        beacon["shift_id"]              = f"shift-{uuid.uuid4().hex[:8]}"
        beacon["loops_completed"]       = 0
        beacon["checkpoints_this_loop"] = 0
        beacon["frozen"]                = False

    # Initialise incoming guards — Gamma waits at AP[0], Delta at AP[mid]
    incoming_starts = [0, mid]
    for i, beacon in enumerate(INCOMING_BEACONS):
        beacon["ap_order"]              = list(range(n))
        beacon["current_ap_idx"]        = incoming_starts[i]
        beacon["start_ap_idx"]          = incoming_starts[i]
        beacon["x_m"]                   = _floor_aps[incoming_starts[i]]["x_m"]
        beacon["y_m"]                   = _floor_aps[incoming_starts[i]]["y_m"]
        beacon["vx"]                    = 0.0
        beacon["vy"]                    = 0.0
        beacon["state"]                 = "moving"
        beacon["wander_ticks"]          = 0
        beacon["wander_target"]         = None
        beacon["shift_id"]              = f"shift-{uuid.uuid4().hex[:8]}"
        beacon["loops_completed"]       = 0
        beacon["checkpoints_this_loop"] = 0

    # Reset module-level shift state (important when restarting without process exit)
    _shift_complete[0] = False
    _shift_complete[1] = False
    _shift_triggered = False

    # Clear stale RTDB positions for all 6 guards + other sim MACs
    ALL_MACS = [b["mac"] for b in OUTGOING_BEACONS + INCOMING_BEACONS] + [
        "AA:BB:CC:DD:EE:02",  # Worker 1 (from simulation_events)
        "AA:BB:CC:DD:EE:03",  # Forklift 1 (from simulation_events)
    ]
    print("[SIM] Clearing stale RTDB positions…")
    for mac in ALL_MACS:
        key = mac.replace(":", "_")
        rtdb.reference(f"/positions/{key}").delete()
    print("[SIM] Stale positions cleared.")

    route_str = " → ".join(ap["name"] for ap in _floor_aps)
    print(f"[SIM] Patrol route: {route_str} → loop")
    print(f"[SIM] Outgoing: Guard Alpha (start AP[0]) | Guard Beta (start AP[{mid}])")
    print(f"[SIM] Incoming: Guard Gamma waiting at AP[0] | Guard Delta at AP[{mid}]")
    print(f"[SIM] Shift change triggers when BOTH outgoing guards complete one full loop.")
    print(f"[SIM] Shift Change simulation started. Ctrl+C to stop.")

    token = settings.OMADA_ACCESS_TOKEN
    headers = {"Authorization": f"Bearer {token}"}
    tick = 0

    async with httpx.AsyncClient() as client:
        while True:
            _write_heartbeats()

            for i, beacon in enumerate(OUTGOING_BEACONS):
                try:
                    _tick_outgoing(beacon, i)
                except Exception as e:
                    print(f"[SIM] ERROR in _tick_outgoing for {beacon['label']}: {e}")
                    beacon["state"] = "moving"
                    beacon["wander_target"] = None

            if _shift_triggered:
                for beacon in INCOMING_BEACONS:
                    try:
                        _tick_guard(beacon)
                    except Exception as e:
                        print(f"[SIM] ERROR in _tick_guard for {beacon['label']}: {e}")
                        beacon["state"] = "moving"
                        beacon["wander_target"] = None

            now_ts = utcnow_iso()
            for beacon in OUTGOING_BEACONS + INCOMING_BEACONS:
                payload = _build_payload(beacon, now_ts)
                n_readings = len(payload["readings"])
                key = beacon["mac"].replace(":", "_")
                pos_data = rtdb.reference(f"/positions/{key}").get() or {}
                pred_x   = pos_data.get("predicted_x")
                smooth_x = pos_data.get("x")
                pred_y   = pos_data.get("predicted_y")
                smooth_y = pos_data.get("y")
                kal_str = (
                    f" | smooth=({smooth_x:.2f}m, {smooth_y:.2f}m)"
                    f" predicted=({pred_x:.2f}m, {pred_y:.2f}m)"
                    if pred_x is not None and smooth_x is not None else ""
                )
                frozen_str  = " [FROZEN]"  if beacon.get("frozen") else ""
                waiting_str = " [WAITING]" if not _shift_triggered and beacon in INCOMING_BEACONS else ""
                try:
                    resp = await client.post(TELEMETRY_ENDPOINT, json=payload,
                                             headers=headers, timeout=5.0)
                    print(
                        f"[SIM] tick {tick:4d} | {beacon['label']:12s} → {resp.status_code} "
                        f"({n_readings} APs) | pos=({beacon['x_m']:.2f}m, {beacon['y_m']:.2f}m)"
                        f"{frozen_str}{waiting_str}{kal_str}"
                    )
                except Exception as e:
                    print(f"[SIM] {beacon['label']} send failed: {e}")

            tick += 1
            await asyncio.sleep(TICK_INTERVAL_S)


if __name__ == "__main__":
    asyncio.run(run_simulation())
