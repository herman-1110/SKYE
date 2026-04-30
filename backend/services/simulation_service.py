"""
Standalone synthetic shift generator.
Run with:  python services/simulation_service.py
"""
from __future__ import annotations

import math
import os
import random
import sys
import time
import uuid
from typing import Dict, List, Optional, Tuple

# Allow importing from backend/ when executed directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from config.settings import settings  # noqa: E402  (must come after path fix + load_dotenv)
from models.patrol_log import PatrolLogRecord
from models.position import PositionRecord
from repositories.patrol_log_repository import patrol_log_repository
from repositories.position_repository import position_repository
from utils.rssi_utils import distance_to_rssi, rssi_to_distance
from utils.zone_utils import coordinate_to_zone
from utils.timestamp_utils import utcnow_iso

import firebase_admin
from firebase_admin import credentials

# ---------------------------------------------------------------------------
# Floor layout — 7 APs at known (x, y) positions in metres
# ---------------------------------------------------------------------------
AP_LAYOUT: List[Tuple[str, float, float]] = [
    ("aa:bb:cc:01", 10.0,  5.0),
    ("aa:bb:cc:02", 30.0,  5.0),
    ("aa:bb:cc:03", 50.0,  5.0),
    ("aa:bb:cc:04", 70.0,  5.0),
    ("aa:bb:cc:05", 10.0, 25.0),
    ("aa:bb:cc:06", 40.0, 25.0),
    ("aa:bb:cc:07", 70.0, 25.0),
]

# Waypoints: person_id → [(x, y, dwell_seconds), ...]
WORKER_WAYPOINTS: Dict[str, List[Tuple[float, float, int]]] = {
    "worker-001": [(5.0, 5.0, 30), (25.0, 15.0, 60), (45.0, 10.0, 45), (65.0, 8.0, 30)],
    "worker-002": [(15.0, 20.0, 45), (35.0, 25.0, 30), (55.0, 20.0, 60)],
    "guard-001":  [(2.0, 35.0, 20), (20.0, 35.0, 30), (50.0, 35.0, 30), (75.0, 35.0, 20)],
}

FORKLIFT_PATH: List[Tuple[float, float]] = [
    (5.0, 12.0), (20.0, 12.0), (35.0, 12.0), (20.0, 12.0),
]

# Guard checkpoints: (cp_id, name, x, y)
PATROL_CHECKPOINTS: List[Tuple[str, str, float, float]] = [
    ("cp-01", "Loading Bay Entrance",  2.0, 35.0),
    ("cp-02", "Assembly Floor North", 20.0, 35.0),
    ("cp-03", "Storage Rack A",       50.0, 35.0),
    ("cp-04", "Exit Corridor End",    75.0, 35.0),
]

VIGI_RADIUS = 3.0  # metres — deterministic presence threshold for VIGI camera


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _init_firebase() -> None:
    if not firebase_admin._apps:
        cred = credentials.Certificate(settings.FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred, {"databaseURL": settings.FIREBASE_RTDB_URL})


def _synthetic_rssi(beacon_xy: Tuple[float, float], ap_xy: Tuple[float, float]) -> float:
    """
    Compute simulated RSSI using inverse LDPL + Gaussian noise.

    True distance → inverse LDPL → theoretical RSSI → add N(0, σ) noise.
    σ = settings.RSSI_NOISE_STD models multipath / obstacle attenuation per LR1/LR2.
    RSSI values are never hardcoded.
    """
    dist = math.hypot(beacon_xy[0] - ap_xy[0], beacon_xy[1] - ap_xy[1])
    ideal = distance_to_rssi(max(dist, 0.1), settings.TX_POWER_DEFAULT, settings.PATH_LOSS_EXPONENT)
    return ideal + random.gauss(0.0, settings.RSSI_NOISE_STD)


def _lerp(a: Tuple[float, float], b: Tuple[float, float], t: float) -> Tuple[float, float]:
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


def _person_position(person_id: str, tick: int) -> Tuple[float, float]:
    """Interpolate position along waypoints at a given tick (1 tick = 1 second)."""
    waypoints = WORKER_WAYPOINTS[person_id]
    total = sum(w[2] for w in waypoints)
    t_cyc = tick % total
    elapsed = 0
    for i, (wx, wy, dwell) in enumerate(waypoints):
        if t_cyc < elapsed + dwell:
            frac = (t_cyc - elapsed) / dwell
            if i < len(waypoints) - 1:
                return _lerp((wx, wy), (waypoints[i + 1][0], waypoints[i + 1][1]), frac)
            return wx, wy
        elapsed += dwell
    return waypoints[-1][0], waypoints[-1][1]


def _forklift_position(tick: int) -> Tuple[float, float]:
    path = FORKLIFT_PATH
    idx = tick % len(path)
    nxt = (idx + 1) % len(path)
    return _lerp(path[idx], path[nxt], (tick % 1))


def _vigi_detected(beacon_xy: Tuple[float, float], cp_xy: Tuple[float, float]) -> bool:
    """Deterministic VIGI output: True iff beacon is within VIGI_RADIUS of checkpoint camera."""
    return math.hypot(beacon_xy[0] - cp_xy[0], beacon_xy[1] - cp_xy[1]) <= VIGI_RADIUS


# ---------------------------------------------------------------------------
# Public simulation entry point
# ---------------------------------------------------------------------------

def run_simulation(ticks: int = 120, tick_interval_s: float = 0.5) -> None:
    """Generate one synthetic shift and write all data to Firebase via repositories."""
    _init_firebase()
    shift_id = f"shift-{uuid.uuid4().hex[:8]}"
    print(f"[SKYE Simulation] shift={shift_id}  ticks={ticks}")

    for tick in range(ticks):
        for person_id in WORKER_WAYPOINTS:
            xy = _person_position(person_id, tick)
            person_type = "guard" if person_id.startswith("guard") else "worker"

            record = PositionRecord(
                beacon_mac=f"beacon-{person_id}",
                person_id=person_id,
                person_type=person_type,
                x=round(xy[0], 2),
                y=round(xy[1], 2),
                zone=coordinate_to_zone(xy[0], xy[1]),
                timestamp=utcnow_iso(),
            )
            position_repository.save(record)

        # Forklift position
        fxy = _forklift_position(tick)
        position_repository.save(PositionRecord(
            beacon_mac="beacon-forklift-01",
            person_id="forklift-01",
            person_type="forklift",
            x=round(fxy[0], 2),
            y=round(fxy[1], 2),
            zone=coordinate_to_zone(fxy[0], fxy[1]),
            timestamp=utcnow_iso(),
        ))

        time.sleep(tick_interval_s)
        if tick % 20 == 0:
            print(f"  tick {tick}/{ticks}")

    # Write patrol log for guard-001
    guard_pos_at_tick: Dict[str, Tuple[float, float]] = {
        cp_id: _person_position("guard-001", i * (ticks // len(PATROL_CHECKPOINTS)))
        for i, (cp_id, _, _, _) in enumerate(PATROL_CHECKPOINTS)
    }
    for cp_id, cp_name, cp_x, cp_y in PATROL_CHECKPOINTS:
        gxy = guard_pos_at_tick[cp_id]
        dwell = random.randint(20, 60)
        patrol_log_repository.save(PatrolLogRecord(
            log_id=str(uuid.uuid4()),
            guard_id="guard-001",
            checkpoint_id=cp_id,
            checkpoint_name=cp_name,
            expected_arrival=utcnow_iso(),
            actual_arrival=utcnow_iso(),
            dwell_time_seconds=dwell,
            min_dwell_required=settings.MIN_DWELL_SECONDS,
            ble_detected=True,
            vigi_detected=_vigi_detected(gxy, (cp_x, cp_y)),
            compliant=dwell >= settings.MIN_DWELL_SECONDS,
            shift_id=shift_id,
        ))

    print(f"[SKYE Simulation] Done. Shift {shift_id} written to Firebase.")


if __name__ == "__main__":
    run_simulation(ticks=120, tick_interval_s=0.5)
