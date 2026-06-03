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
from services.safety_service import safety_service
from utils.timestamp_utils import utcnow_iso

# ── Constants ─────────────────────────────────────────────────────────────
TICK_INTERVAL_S  = 2.0
BACKEND_URL      = "http://localhost:8000"
TELEMETRY_ENDPOINT = f"{BACKEND_URL}/telemetry"
WANDER_TICKS_MIN = 8
WANDER_TICKS_MAX = 12
WANDER_RADIUS_M  = 2.5

SIMULATED_CCTVS: List[Dict] = [
    {"mac": "A8:57:4E:3C:11:01", "name": "VIGI C340 (Sim)"},
]

# ── Scenario timeline ──────────────────────────────────────────────────────
# (segment_name, duration_ticks)
SEGMENTS = [
    ("normal_patrol",     90),
    ("man_down",         180),
    ("normal_patrol",     60),
    ("collision_warning", 60),
    ("normal_patrol",     60),
    ("ghost_patrol",      60),
    ("normal_patrol",     60),
    ("missed_checkpoint", 60),
]

# ── Beacons ────────────────────────────────────────────────────────────────
SIMULATED_BEACONS: List[Dict] = [
    {
        "mac": "AA:BB:CC:DD:EE:01", "person_id": "guard-001",
        "person_type": "guard", "label": "Guard Alpha",
        "x_m": 0.0, "y_m": 0.0, "vx": 0.0, "vy": 0.0,
        "ap_order": [], "current_ap_idx": 0, "wander_ticks": 0, "state": "moving",
        "skip_ap_idx": -1,   # for missed_checkpoint: index to skip
        "wander_target": None,
    },
    {
        "mac": "AA:BB:CC:DD:EE:04", "person_id": "guard-002",
        "person_type": "guard", "label": "Guard Beta",
        "x_m": 0.0, "y_m": 0.0, "vx": 0.0, "vy": 0.0,
        "ap_order": [], "current_ap_idx": 0, "wander_ticks": 0, "state": "moving",
        "skip_ap_idx": -1,
        "wander_target": None,
    },
    {
        "mac": "AA:BB:CC:DD:EE:02", "person_id": "worker-001",
        "person_type": "worker", "label": "Worker 1",
        "x_m": 0.0, "y_m": 0.0, "vx": 0.0, "vy": 0.0,
        "ap_order": [], "current_ap_idx": 0, "wander_ticks": 0, "state": "moving",
        "wander_target": None,
    },
    {
        "mac": "AA:BB:CC:DD:EE:03", "person_id": "forklift-001",
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
    if not _floor_aps:
        return base
    xs = [ap["x_m"] for ap in _floor_aps]
    ys = [ap["y_m"] for ap in _floor_aps]
    w = max(xs) - min(xs) + WANDER_RADIUS_M * 2
    h = max(ys) - min(ys) + WANDER_RADIUS_M * 2
    scale = math.sqrt((w * h) / (12.0 * 10.0))
    return min(base * scale, base * 4.0)

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
    arrived = _move_toward(beacon, tx, ty, speed=_scale_speed(0.6))
    if arrived:
        beacon["wander_target"] = None

def _tick_patrol(beacon: Dict, skip_ap_idx: int = -1) -> Optional[str]:
    """
    Patrol state machine. Returns checkpoint name when arriving at an AP zone.
    skip_ap_idx: if set, beacon skips that AP index (missed checkpoint scenario).
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
                               speed=_scale_speed(0.8))
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
        actual_arrival=utcnow_iso(),
        dwell_time_seconds=dwell,
        min_dwell_required=settings.MIN_DWELL_SECONDS,
        ble_detected=True,
        vigi_detected=vigi_detected,
        compliant=compliant,
        shift_id=_shift_id,
    )
    patrol_log_repository.save(record)
    safety_service.check_patrol_compliance(record)
    safety_service.verify_multimodal(record, ble_detected=True, vigi_detected=vigi_detected)

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
    _tick_patrol(worker)
    _tick_patrol(forklift)

def _tick_man_down(tick: int) -> None:
    """
    Worker moves to far corner of floor and stays stationary.
    Guards continue patrol. Forklift moves slowly.
    Man-down alert fires after worker has been stationary for 150 ticks (~5 min).
    """
    global _mandown_seeded
    guard_a, guard_b, worker, forklift = SIMULATED_BEACONS

    danger_x = _floor_bounds["x_max"] - WANDER_RADIUS_M
    danger_y = _floor_bounds["y_max"] - WANDER_RADIUS_M

    if tick < 10:
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
    _move_toward(forklift, _floor_bounds["x_min"] + _floor_bounds["w"] * 0.3,
                 _floor_bounds["y_min"] + _floor_bounds["h"] * 0.5,
                 speed=_scale_speed(0.3))

    if tick == 150 and not _mandown_seeded:
        _mandown_seeded = True
        print(f"[SIM] man_down: seeding backdated position for worker")

def _tick_collision_warning(tick: int) -> None:
    """Forklift and worker converge toward floor centre. Guards continue patrol."""
    guard_a, guard_b, worker, forklift = SIMULATED_BEACONS
    centre_x = _floor_bounds["x_min"] + _floor_bounds["w"] * 0.50
    centre_y = _floor_bounds["y_min"] + _floor_bounds["h"] * 0.45

    _move_toward(forklift, centre_x, centre_y, speed=_scale_speed(0.9))
    _move_toward(worker,   centre_x, centre_y, speed=_scale_speed(0.6))
    _tick_patrol(guard_a)
    _tick_patrol(guard_b)

def _tick_ghost_patrol(tick: int) -> None:
    """Guard Alpha freezes (BLE present, VIGI no confirm). Others keep moving."""
    global _event_fired
    guard_a, guard_b, worker, forklift = SIMULATED_BEACONS

    guard_a["vx"] = 0.0
    guard_a["vy"] = 0.0

    if tick == 10 and not _event_fired:
        _event_fired = True
        fake_cp = {"id": "cp-ghost", "name": "Patrol Zone"}
        _write_patrol_log(guard_a, fake_cp["id"], fake_cp["name"],
                          compliant=False, vigi_detected=False)
        print(f"[SIM] Ghost patrol event fired for {guard_a['label']}")

    _tick_patrol(guard_b)
    _tick_patrol(worker)
    _tick_patrol(forklift)

def _tick_missed_checkpoint(tick: int) -> None:
    """Guard Alpha skips one AP zone. Others patrol normally."""
    global _event_fired
    guard_a, guard_b, worker, forklift = SIMULATED_BEACONS

    result = _tick_patrol(guard_a, skip_ap_idx=1)
    if result and result.startswith("SKIPPED:") and not _event_fired:
        _event_fired = True
        skipped_name = result.replace("SKIPPED:", "")
        _write_patrol_log(guard_a, "cp-missed", skipped_name,
                          compliant=False, vigi_detected=False, dwell_s=0)
        print(f"[SIM] Missed checkpoint event fired: {skipped_name}")

    _tick_patrol(guard_b)
    _tick_patrol(worker)
    _tick_patrol(forklift)

# ── Reset actors between segments ─────────────────────────────────────────
def _reset_actors() -> None:
    """Reset all beacon states for a clean normal_patrol segment."""
    for beacon in SIMULATED_BEACONS:
        beacon["state"] = "moving"
        beacon["wander_ticks"] = 0
        beacon["current_ap_idx"] = 0
        beacon["wander_target"] = None

# ── Main loop ──────────────────────────────────────────────────────────────
async def run_simulation() -> None:
    global _floor_aps, _floor_bounds, _shift_id
    global _segment_idx, _segment_tick, _event_fired, _mandown_seeded

    _init_firebase_if_needed()

    active_floor = floor_repository.get_any_active()
    if not active_floor:
        print("[SIM] No active floor — activate a floor in Floor Plans first")
        return

    fetched_aps = ap_repository.get_all(active_floor.building_id, active_floor.id)
    if len(fetched_aps) < 2:
        print("[SIM] Need at least 2 APs on the active floor")
        return

    _floor_aps = [{"mac": ap.mac, "name": ap.name, "x_m": ap.x_m, "y_m": ap.y_m}
                  for ap in fetched_aps]

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

    n = len(_floor_aps)
    _shift_id = f"shift-{uuid.uuid4().hex[:8]}"

    # Assign AP patrol orders
    SIMULATED_BEACONS[0]["ap_order"] = list(range(n))           # Guard Alpha: forward
    SIMULATED_BEACONS[1]["ap_order"] = list(range(n-1, -1, -1)) # Guard Beta: reverse
    SIMULATED_BEACONS[2]["ap_order"] = list(range(n))           # Worker: forward
    SIMULATED_BEACONS[3]["ap_order"] = list(range(n-1, -1, -1)) # Forklift: reverse

    # Starting positions
    SIMULATED_BEACONS[0]["x_m"] = _floor_aps[0]["x_m"]
    SIMULATED_BEACONS[0]["y_m"] = _floor_aps[0]["y_m"]
    SIMULATED_BEACONS[1]["x_m"] = _floor_aps[n-1]["x_m"]
    SIMULATED_BEACONS[1]["y_m"] = _floor_aps[n-1]["y_m"]
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

            # man_down: send backdated seed payload at tick 150
            if segment == "man_down" and _segment_tick == 150 and _mandown_seeded:
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
                try:
                    resp = await client.post(TELEMETRY_ENDPOINT, json=payload,
                                             headers=headers, timeout=5.0)
                    print(f"[SIM] {segment:20s} tick {_segment_tick:3d} | "
                          f"{beacon['label']:12s} → {resp.status_code} ({n_readings} APs)")
                except Exception as e:
                    print(f"[SIM] {beacon['label']} send failed: {e}")

            _segment_tick += 1
            await asyncio.sleep(TICK_INTERVAL_S)

if __name__ == "__main__":
    asyncio.run(run_simulation())
