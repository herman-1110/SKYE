"""
SKYE Simulation — Patrol + Safety Events (File 2)

2 guards, 1 worker, 1 forklift move between AP zones.
Safety events (man_down, collision, ghost_patrol, missed_checkpoint)
fire at spaced intervals with normal patrol in between.

Run: venv/Scripts/python.exe services/simulation_events.py
"""
from __future__ import annotations
import asyncio
import math
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

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
TICK_INTERVAL_S  = 1.0
BACKEND_URL      = "http://localhost:8000"
TELEMETRY_ENDPOINT = f"{BACKEND_URL}/telemetry"
WANDER_TICKS_MIN = 1
WANDER_TICKS_MAX = 1
WANDER_RADIUS_M  = 1.0

SIMULATED_CCTVS: List[Dict] = [
    {"mac": "A8:57:4E:3C:11:01", "name": "VIGI C340 (Sim)"},
]

# ── Scenario timeline ──────────────────────────────────────────────────────
# (segment_name, duration_ticks)
SEGMENTS = [
    ("normal_patrol",     3),   # 3s  — establish baseline
    ("man_down",          10),   # 10s  — worker stationary, alert fires at tick 5
    ("normal_patrol",     3),   # 3s
    ("collision_warning", 5),   # 5s  — forklift + worker converge
    ("normal_patrol",     3),   # 3s
    ("ghost_patrol",      5),   # 5s  — BLE no VIGI, fires at tick 2
    ("normal_patrol",     3),   # 3s
    ("missed_checkpoint", 5),   # 5s  — guard skips AP, fires almost immediately
]

# ── Beacons ────────────────────────────────────────────────────────────────
SIMULATED_BEACONS: List[Dict] = [
    {
        "mac": "AA:BB:CC:DD:EE:01", "person_id": "sim-guard-001",
        "person_type": "guard", "label": "Guard Alpha",
        "x_m": 0.0, "y_m": 0.0, "vx": 0.0, "vy": 0.0,
        "ap_order": [], "current_ap_idx": 0, "wander_ticks": 0, "state": "moving",
        "skip_ap_idx": -1,   # for missed_checkpoint: index to skip
        "wander_target": None,
    },
    {
        "mac": "AA:BB:CC:DD:EE:04", "person_id": "sim-guard-002",
        "person_type": "guard", "label": "Guard Beta",
        "x_m": 0.0, "y_m": 0.0, "vx": 0.0, "vy": 0.0,
        "ap_order": [], "current_ap_idx": 0, "wander_ticks": 0, "state": "moving",
        "skip_ap_idx": -1,
        "wander_target": None,
    },
    {
        "mac": "AA:BB:CC:DD:EE:02", "person_id": "sim-worker-001",
        "person_type": "worker", "label": "Worker 1",
        "x_m": 0.0, "y_m": 0.0, "vx": 0.0, "vy": 0.0,
        "ap_order": [], "current_ap_idx": 0, "wander_ticks": 0, "state": "moving",
        "wander_target": None,
    },
    {
        "mac": "AA:BB:CC:DD:EE:03", "person_id": "sim-forklift-001",
        "person_type": "forklift", "label": "Forklift 1",
        "x_m": 0.0, "y_m": 0.0, "vx": 0.0, "vy": 0.0,
        "ap_order": [], "current_ap_idx": 0, "wander_ticks": 0, "state": "moving",
        "wander_target": None,
    },
]

# ── Mutable global state ───────────────────────────────────────────────────
_floor_aps: List[Dict] = []
_floor_bounds: Dict[str, float] = {}
_shift_id: str = ""
_segment_idx: int = 0
_segment_tick: int = 0
_event_fired: bool = False       # reset each segment
_mandown_seeded: bool = False
_safety_svc = None

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

# ── Firebase init ──────────────────────────────────────────────────────────
def _init_firebase_if_needed() -> None:
    if not firebase_admin._apps:
        cred = credentials.Certificate(settings.FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred, {"databaseURL": settings.FIREBASE_RTDB_URL})

# ── Heartbeats ─────────────────────────────────────────────────────────────
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

# ── Movement helpers ───────────────────────────────────────────────────────
def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)

def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))

def _clamp_position(x: float, y: float) -> tuple[float, float]:
    return (
        _clamp(x, _floor_bounds["x_min"], _floor_bounds["x_max"]),
        _clamp(y, _floor_bounds["y_min"], _floor_bounds["y_max"]),
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
    A new target is only chosen once the beacon arrives at the current one.
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

def _tick_patrol(beacon: Dict, skip_ap_idx: int = -1, move_speed: float = 0.6) -> Optional[str]:
    """
    Patrol state machine. Returns checkpoint name when arriving at an AP zone.
    skip_ap_idx: if set, beacon skips that AP index (missed checkpoint scenario).
    move_speed: base speed passed to _scale_speed; guards use 0.6, worker/forklift use 0.4.
    """
    ap_order = beacon["ap_order"]
    if not ap_order:
        return None

    # Find next non-skipped AP
    idx = beacon["current_ap_idx"] % len(ap_order)
    actual_ap_idx = ap_order[idx]

    if skip_ap_idx >= 0 and actual_ap_idx == skip_ap_idx:
        # Skip this AP — log the miss then advance
        skipped_ap = _floor_aps[actual_ap_idx]
        beacon["current_ap_idx"] += 1
        print(f"[SIM] {beacon['label']:12s} SKIPPED {skipped_ap['name']}")
        return f"SKIPPED:{skipped_ap['name']}"

    current_ap = _floor_aps[actual_ap_idx]

    if beacon["state"] == "moving":
        arrived = _move_toward(beacon, current_ap["x_m"], current_ap["y_m"],
                               speed=_scale_speed(move_speed))
        if arrived:
            beacon["state"] = "wandering"
            beacon["wander_ticks"] = random.randint(WANDER_TICKS_MIN, WANDER_TICKS_MAX)
            print(f"[SIM] {beacon['label']:12s} arrived at {current_ap['name']}")
            return current_ap["name"]

    elif beacon["state"] == "wandering":
        _wander_within_ap(beacon, current_ap)
        beacon["wander_ticks"] -= 1
        if beacon["wander_ticks"] <= 0:
            beacon["current_ap_idx"] += 1
            beacon["state"] = "moving"
            beacon["wander_target"] = None

    return None

# ── Patrol log writer ──────────────────────────────────────────────────────
def _write_patrol_log(beacon: Dict, cp_id: str, cp_name: str,
                       compliant: bool, vigi_detected: bool,
                       dwell_s: Optional[int] = None) -> None:
    dwell = dwell_s if dwell_s is not None else random.randint(settings.MIN_DWELL_SECONDS, 60)
    record = PatrolLogRecord(
        log_id=str(uuid.uuid4()),
        guard_id=beacon["person_id"],
        checkpoint_id=cp_id,
        checkpoint_name=cp_name,
        expected_arrival=utcnow_iso(),
        actual_arrival=utcnow_iso() if compliant else None,
        dwell_time_seconds=dwell,
        min_dwell_required=settings.MIN_DWELL_SECONDS,
        ble_detected=True,
        vigi_detected=vigi_detected,
        compliant=compliant,
        shift_id=_shift_id,
    )
    patrol_log_repository.save(record)
    if _safety_svc:
        _safety_svc.check_patrol_compliance(record)
        _safety_svc.verify_multimodal(record, ble_detected=True, vigi_detected=vigi_detected)

# ── RSSI / payload ─────────────────────────────────────────────────────────
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

# ── Segment tick handlers ──────────────────────────────────────────────────
def _tick_normal_patrol() -> None:
    """All actors do normal AP-zone patrol."""
    guard_a, guard_b, worker, forklift = SIMULATED_BEACONS
    _tick_patrol(guard_a)
    _tick_patrol(guard_b)
    _tick_patrol(worker, move_speed=0.4)
    _tick_patrol(forklift, move_speed=0.4)

def _tick_man_down(tick: int) -> None:
    global _mandown_seeded
    guard_a, guard_b, worker, forklift = SIMULATED_BEACONS

    danger_x = _floor_bounds["x_max"] - WANDER_RADIUS_M
    danger_y = _floor_bounds["y_max"] - WANDER_RADIUS_M

    if tick < 3:
        _move_toward(worker, danger_x, danger_y, speed=_scale_speed(1.0))
    else:
        worker["vx"] = 0.0
        worker["vy"] = 0.0
        worker["x_m"] += random.gauss(0, 0.05)
        worker["y_m"] += random.gauss(0, 0.05)
        worker["x_m"] = _clamp(worker["x_m"], danger_x - 1.5, danger_x + 1.5)
        worker["y_m"] = _clamp(worker["y_m"], danger_y - 1.5, danger_y + 1.5)

    _tick_patrol(guard_a)
    _tick_patrol(guard_b)
    _move_toward(forklift,
                 _floor_bounds["x_min"] + _floor_bounds["w"] * 0.3,
                 _floor_bounds["y_min"] + _floor_bounds["h"] * 0.5,
                 speed=_scale_speed(0.3))

    if tick == 5 and not _mandown_seeded:
        _mandown_seeded = True
        print(f"[SIM] man_down: seeding backdated position for worker")

def _tick_collision_warning(tick: int) -> None:
    """Forklift and worker converge toward floor centre. Collision alert via Kalman backend."""
    guard_a, guard_b, worker, forklift = SIMULATED_BEACONS
    centre_x = _floor_bounds["x_min"] + _floor_bounds["w"] * 0.50
    centre_y = _floor_bounds["y_min"] + _floor_bounds["h"] * 0.45

    _move_toward(forklift, centre_x, centre_y, speed=_scale_speed(0.9))
    _move_toward(worker,   centre_x, centre_y, speed=_scale_speed(0.6))
    _tick_patrol(guard_a)
    _tick_patrol(guard_b)

    dist = _dist(worker["x_m"], worker["y_m"], forklift["x_m"], forklift["y_m"])
    print(
        f"[SIM] collision_warning tick {tick:3d} | "
        f"{worker['label']} ↔ {forklift['label']} dist={dist:.2f}m "
        f"(backend collision check via Kalman)"
    )

def _tick_ghost_patrol(tick: int) -> None:
    """Guard Alpha freezes (BLE present, VIGI no confirm). Others keep moving."""
    global _event_fired
    guard_a, guard_b, worker, forklift = SIMULATED_BEACONS

    guard_a["vx"] = 0.0
    guard_a["vy"] = 0.0

    if tick == 2 and not _event_fired:
        _event_fired = True
        cp_ap = _floor_aps[0]
        _write_patrol_log(
            guard_a,
            cp_id=cp_ap["mac"],
            cp_name=cp_ap["name"],
            compliant=False,
            vigi_detected=False,
        )
        print(f"[SIM] Ghost patrol event fired for {guard_a['label']} at {cp_ap['name']}")

    _tick_patrol(guard_b)
    _tick_patrol(worker, move_speed=0.4)
    _tick_patrol(forklift, move_speed=0.4)

def _tick_missed_checkpoint(tick: int) -> None:
    """Guard Alpha skips one AP zone. Others patrol normally."""
    global _event_fired
    guard_a, guard_b, worker, forklift = SIMULATED_BEACONS

    result = _tick_patrol(guard_a, skip_ap_idx=1)
    if result and result.startswith("SKIPPED:") and not _event_fired:
        _event_fired = True
        skipped_name = result.replace("SKIPPED:", "")
        skipped_ap = _floor_aps[1] if len(_floor_aps) > 1 else _floor_aps[0]
        _write_patrol_log(
            guard_a,
            cp_id=skipped_ap["mac"],
            cp_name=skipped_name,
            compliant=False,
            vigi_detected=False,
            dwell_s=0,
        )
        print(f"[SIM] Missed checkpoint event fired: {skipped_name}")

    _tick_patrol(guard_b)
    _tick_patrol(worker, move_speed=0.4)
    _tick_patrol(forklift, move_speed=0.4)

# ── Reset actors between segments ─────────────────────────────────────────
def _reset_actors() -> None:
    """Reset all beacon states for a clean normal_patrol segment."""
    n = len(_floor_aps)
    mid = n // 2
    for i, beacon in enumerate(SIMULATED_BEACONS):
        beacon["state"] = "moving"
        beacon["wander_ticks"] = 0
        beacon["wander_target"] = None
        # Guard Beta (index 1) restarts at mid-route to stay offset from Guard Alpha
        beacon["current_ap_idx"] = mid if i == 1 else 0

# ── Main loop ──────────────────────────────────────────────────────────────
async def run_simulation() -> None:
    global _floor_aps, _floor_bounds, _shift_id
    global _segment_idx, _segment_tick, _event_fired, _mandown_seeded

    _init_firebase_if_needed()

    # Import after Firebase is initialized to avoid early DB call failures
    from services.safety_service import safety_service as _safety_service
    global _safety_svc
    _safety_svc = _safety_service

    active_floor = floor_repository.get_any_active()
    if not active_floor:
        print("[SIM] No active floor — activate a floor in Floor Plans first")
        return

    fetched_aps = ap_repository.get_all(active_floor.building_id, active_floor.id)
    if len(fetched_aps) < 3:
        print("[SIM] Need at least 3 APs on the active floor for positioning to work")
        return

    ap_by_id = {ap.id: ap for ap in fetched_aps}

    if active_floor.patrol_enabled and active_floor.patrol_route:
        ordered_aps = []
        for ap_id in active_floor.patrol_route:
            ap = ap_by_id.get(ap_id)
            if ap:
                ordered_aps.append(ap)
        if len(ordered_aps) >= 3:
            _floor_aps = [{"id": ap.id, "mac": ap.mac, "name": ap.name,
                           "x_m": ap.x_m, "y_m": ap.y_m} for ap in ordered_aps]
            print(f"[SIM] Using configured patrol route ({len(_floor_aps)} APs)")
        else:
            print("[SIM] WARNING: patrol_route has < 3 valid APs — falling back to coordinate sort")
            _floor_aps = [{"id": ap.id, "mac": ap.mac, "name": ap.name,
                           "x_m": ap.x_m, "y_m": ap.y_m} for ap in fetched_aps]
            _floor_aps.sort(key=lambda a: (a["x_m"], a["y_m"]))
    else:
        print("[SIM] No patrol route configured — using coordinate sort")
        _floor_aps = [{"id": ap.id, "mac": ap.mac, "name": ap.name,
                       "x_m": ap.x_m, "y_m": ap.y_m} for ap in fetched_aps]
        _floor_aps.sort(key=lambda a: (a["x_m"], a["y_m"]))

    xs = [ap["x_m"] for ap in _floor_aps]
    ys = [ap["y_m"] for ap in _floor_aps]
    pad_x = max((max(xs) - min(xs)) * 0.20, 2.0)
    pad_y = max((max(ys) - min(ys)) * 0.20, 2.0)
    _floor_bounds = {
        "x_min": max(0.0, min(xs) - pad_x), "x_max": max(xs) + pad_x,
        "y_min": max(0.0, min(ys) - pad_y), "y_max": max(ys) + pad_y,
        "w": (max(xs) + pad_x) - max(0.0, min(xs) - pad_x),
        "h": (max(ys) + pad_y) - max(0.0, min(ys) - pad_y),
    }

    print(f"[SIM] Loaded {len(_floor_aps)} AP(s) from floor '{active_floor.name}':")
    for ap in _floor_aps:
        print(f"[SIM]   {ap['name']:20s}  {ap['mac']}  ({ap['x_m']:.1f}m, {ap['y_m']:.1f}m)")
    print(f"[SIM] Floor bounds: x={_floor_bounds['x_min']:.1f}–{_floor_bounds['x_max']:.1f}m  "
          f"y={_floor_bounds['y_min']:.1f}–{_floor_bounds['y_max']:.1f}m")
    print(f"[SIM] Computed moving speed : {_scale_speed(0.6):.3f} m/tick")
    print(f"[SIM] Computed wander speed : {_scale_speed(0.4):.3f} m/tick")

    n = len(_floor_aps)
    _shift_id = f"shift-{uuid.uuid4().hex[:8]}"

    mid = n // 2

    # Guards follow the configured patrol route in order
    SIMULATED_BEACONS[0]["ap_order"] = list(range(n))   # Guard Alpha: route order
    SIMULATED_BEACONS[0]["x_m"] = _floor_aps[0]["x_m"]
    SIMULATED_BEACONS[0]["y_m"] = _floor_aps[0]["y_m"]
    SIMULATED_BEACONS[0]["current_ap_idx"] = 0

    SIMULATED_BEACONS[1]["ap_order"] = list(range(n))   # Guard Beta: same route, offset start
    SIMULATED_BEACONS[1]["x_m"] = _floor_aps[mid]["x_m"]
    SIMULATED_BEACONS[1]["y_m"] = _floor_aps[mid]["y_m"]
    SIMULATED_BEACONS[1]["current_ap_idx"] = mid

    # Worker and forklift are not on patrol — move freely between all APs
    SIMULATED_BEACONS[2]["ap_order"] = list(range(n))           # Worker: forward
    SIMULATED_BEACONS[3]["ap_order"] = list(range(n-1, -1, -1)) # Forklift: reverse

    SIMULATED_BEACONS[2]["x_m"], SIMULATED_BEACONS[2]["y_m"] = _clamp_position(
        _floor_aps[0]["x_m"] + WANDER_RADIUS_M,
        _floor_aps[0]["y_m"] + WANDER_RADIUS_M,
    )
    SIMULATED_BEACONS[3]["x_m"], SIMULATED_BEACONS[3]["y_m"] = _clamp_position(
        _floor_aps[n-1]["x_m"] - WANDER_RADIUS_M,
        _floor_aps[n-1]["y_m"] - WANDER_RADIUS_M,
    )

    print(f"[SIM] Patrol + Events simulation started  shift={_shift_id}")
    print(f"[SIM] Segments: {[s for s, _ in SEGMENTS]}")

    token = settings.OMADA_ACCESS_TOKEN
    headers = {"Authorization": f"Bearer {token}"}
    _segment_idx = 0
    _segment_tick = 0
    _event_fired = False
    _mandown_seeded = False

    # Clear stale positions for all sim beacon MACs — RTDB is keyed by beacon_mac
    # (the reporter_mac sent to /telemetry), matching what compute_position() writes.
    sim_macs = [b["mac"].replace(":", "_") for b in SIMULATED_BEACONS]
    print("[SIM] Clearing stale RTDB positions…")
    for mac_key in sim_macs:
        rtdb.reference(f"/positions/{mac_key}").delete()
    print("[SIM] Stale positions cleared.")

    async with httpx.AsyncClient() as client:
        while True:
            segment, max_ticks = SEGMENTS[_segment_idx % len(SEGMENTS)]

            if _segment_tick >= max_ticks:
                print(f"[SIM] '{segment}' complete → next segment")
                _segment_idx += 1
                _segment_tick = 0
                _event_fired = False
                _mandown_seeded = False
                _reset_actors()
                segment, max_ticks = SEGMENTS[_segment_idx % len(SEGMENTS)]
                print(f"[SIM] Starting '{segment}' ({max_ticks} ticks)")

            _write_heartbeats()

            if segment == "normal_patrol":
                _tick_normal_patrol()
            elif segment == "man_down":
                _tick_man_down(_segment_tick)
            elif segment == "collision_warning":
                _tick_collision_warning(_segment_tick)
            elif segment == "ghost_patrol":
                _tick_ghost_patrol(_segment_tick)
            elif segment == "missed_checkpoint":
                _tick_missed_checkpoint(_segment_tick)

            # man_down: send backdated seed payload at tick 5
            if segment == "man_down" and _segment_tick == 5 and _mandown_seeded:
                worker = SIMULATED_BEACONS[2]
                seed_ts = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
                seed_payload = _build_payload(worker, seed_ts)
                if len(seed_payload["readings"]) >= 3:
                    try:
                        await client.post(TELEMETRY_ENDPOINT, json=seed_payload,
                                          headers=headers, timeout=5.0)
                        print(f"[SIM] man_down backdated seed sent")
                    except Exception as e:
                        print(f"[SIM] man_down seed failed: {e}")

            now_ts = utcnow_iso()
            for beacon in SIMULATED_BEACONS:
                payload = _build_payload(beacon, now_ts)
                n_readings = len(payload["readings"])
                pos_data = rtdb.reference(f"/positions/{beacon['mac'].replace(':', '_')}").get() or {}
                pred_x = pos_data.get("predicted_x")
                pred_y = pos_data.get("predicted_y")
                smooth_x = pos_data.get("x")
                smooth_y = pos_data.get("y")
                kal_str = (
                    f" | smooth=({smooth_x:.2f}m, {smooth_y:.2f}m)"
                    f" predicted=({pred_x:.2f}m, {pred_y:.2f}m)"
                    if pred_x is not None and smooth_x is not None else ""
                )
                try:
                    resp = await client.post(TELEMETRY_ENDPOINT, json=payload,
                                             headers=headers, timeout=5.0)
                    print(f"[SIM] {segment:20s} tick {_segment_tick:3d} | "
                          f"{beacon['label']:12s} → {resp.status_code} ({n_readings} APs)"
                          f" | pos=({beacon['x_m']:.2f}m, {beacon['y_m']:.2f}m)"
                          f"{kal_str}")
                except Exception as e:
                    print(f"[SIM] {beacon['label']} send failed: {e}")

            _segment_tick += 1
            await asyncio.sleep(TICK_INTERVAL_S)

if __name__ == "__main__":
    asyncio.run(run_simulation())
