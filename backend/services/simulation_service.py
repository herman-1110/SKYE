"""
SKYE Simulation Engine — full-pipeline scenario driver.

Sends HTTP POST /telemetry once per beacon per tick so the complete stack
(Positioning → Kalman Filter → Safety Detection → LLM Audit) receives
live synthetic data with realistic RSSI values.

Payload format matches the actual TelemetryRequest schema:
    reporter_mac  = beacon MAC (not AP MAC)
    readings[]    = one entry per AP that detected the beacon
    person_id     = actor identifier
    person_type   = guard | worker | forklift

Ghost patrol and patrol compliance are triggered via direct service/repo
calls since no HTTP endpoints exist for those flows.

Run standalone:  python services/simulation_service.py
Run via API:     POST /simulation/start   (see simulation_routes.py)
"""
from __future__ import annotations

import asyncio
import math
import os
import random
import sys
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import httpx
import firebase_admin
from firebase_admin import credentials

from config.settings import settings
from models.patrol_log import PatrolLogRecord
from repositories.patrol_log_repository import patrol_log_repository
from services.safety_service import safety_service
from utils.timestamp_utils import utcnow_iso

# ── AP positions (metres) ────────────────────────────────────────────────
# IMPORTANT: these MACs must match what the admin registers in
# Floor Plans → Add AP.  When the simulation runs, those APs will show
# the green online dot on the map; stopping it makes them go red.
SIMULATED_APS: List[Dict] = [
    {"name": "EAP725-Outdoor", "mac": "CC:BA:BD:81:9D:CD", "x_m": 0.0,  "y_m": 0.0},
    {"name": "EAP660 HD",      "mac": "40:AE:30:9D:34:5A", "x_m": 10.0, "y_m": 0.0},
    {"name": "EAP673",         "mac": "24:2F:D0:38:55:B0", "x_m": 5.0,  "y_m": 8.0},
]

# ── Beacon actors — positions mutated each tick ───────────────────────────
SIMULATED_BEACONS: List[Dict] = [
    {
        "mac": "AA:BB:CC:DD:EE:01", "person_id": "guard-001",
        "person_type": "guard",    "label": "Guard Alpha",
        "x_m": 2.0, "y_m": 2.0, "vx": 0.0, "vy": 0.0,
    },
    {
        "mac": "AA:BB:CC:DD:EE:02", "person_id": "worker-001",
        "person_type": "worker",   "label": "Worker 1",
        "x_m": 7.0, "y_m": 3.0, "vx": 0.0, "vy": 0.0,
    },
    {
        "mac": "AA:BB:CC:DD:EE:03", "person_id": "forklift-001",
        "person_type": "forklift", "label": "Forklift 1",
        "x_m": 8.0, "y_m": 7.0, "vx": 0.0, "vy": 0.0,
    },
]

FLOOR_W_M = 12.0
FLOOR_H_M = 10.0

TICK_INTERVAL_S    = 2.0
BACKEND_URL        = "http://localhost:8000"
TELEMETRY_ENDPOINT = f"{BACKEND_URL}/telemetry"

# ── Patrol route — guard visits these checkpoints in order ────────────────
PATROL_CHECKPOINTS: List[Dict] = [
    {"id": "cp-01", "name": "Gate A",         "x_m": 1.0, "y_m": 1.0},
    {"id": "cp-02", "name": "Warehouse Zone", "x_m": 5.0, "y_m": 2.0},
    {"id": "cp-03", "name": "Machinery Bay",  "x_m": 9.0, "y_m": 4.0},
    {"id": "cp-04", "name": "Exit Corridor",  "x_m": 6.0, "y_m": 8.0},
    {"id": "cp-01", "name": "Gate A",         "x_m": 1.0, "y_m": 1.0},  # return
]

# ── Scenario order and durations ──────────────────────────────────────────
SCENARIOS = [
    ("normal_patrol",    60),   # 60 ticks  = ~2 min
    ("man_down",        150),   # 150 ticks = ~5 min — worker stationary in high-risk zone
    ("collision_warning", 30),  # 30 ticks  = ~1 min — forklift converges on worker
    ("ghost_patrol",     20),   # 20 ticks  = ~40 s  — BLE present, VIGI no human
    ("missed_checkpoint", 30),  # 30 ticks  = ~1 min — guard skips Machinery Bay
]

# ── Mutable scenario state ────────────────────────────────────────────────
_scenario_index = 0
_scenario_tick  = 0
_patrol_cp_idx  = 0
_shift_id       = ""
_ghost_logged   = False
_missed_logged  = False
_mandown_seeded = False  # True once we have written the back-dated position seed


# ── LDPL helpers ──────────────────────────────────────────────────────────

def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def _rssi_from_distance(d: float) -> int:
    """LDPL + Gaussian noise, using settings constants to match the backend."""
    d = max(d, 0.1)
    rssi = settings.TX_POWER_DEFAULT - 10.0 * settings.PATH_LOSS_EXPONENT * math.log10(d)
    return int(round(rssi + random.gauss(0, settings.RSSI_NOISE_STD)))


# ── Movement helpers ──────────────────────────────────────────────────────

def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def _move_toward(beacon: Dict, tx: float, ty: float, speed: float = 0.4) -> bool:
    """Advance beacon toward (tx, ty) at speed m/tick. Returns True when arrived."""
    dx = tx - beacon["x_m"]
    dy = ty - beacon["y_m"]
    d = math.sqrt(dx * dx + dy * dy)
    if d < 0.3:
        beacon["vx"] = 0.0
        beacon["vy"] = 0.0
        return True
    step = min(speed, d)
    beacon["x_m"] += (dx / d) * step
    beacon["y_m"] += (dy / d) * step
    beacon["vx"] = (dx / d) * speed
    beacon["vy"] = (dy / d) * speed
    return False


# ── Scenario tick — mutates beacon positions ──────────────────────────────

def _tick_scenario(scenario: str, tick: int) -> None:
    global _patrol_cp_idx

    guard    = SIMULATED_BEACONS[0]
    worker   = SIMULATED_BEACONS[1]
    forklift = SIMULATED_BEACONS[2]

    if scenario == "normal_patrol":
        cp = PATROL_CHECKPOINTS[_patrol_cp_idx % len(PATROL_CHECKPOINTS)]
        if _move_toward(guard, cp["x_m"], cp["y_m"], speed=0.5):
            _write_patrol_log(guard, cp, compliant=True, vigi_detected=True)
            _patrol_cp_idx += 1

        worker["x_m"] = _clamp(worker["x_m"] + random.uniform(-0.3, 0.3), 0.5, 7.0)
        worker["y_m"] = _clamp(worker["y_m"] + random.uniform(-0.3, 0.3), 0.5, 4.5)
        worker["vx"]  = random.uniform(-0.3, 0.3)
        worker["vy"]  = random.uniform(-0.3, 0.3)

        forklift_targets = [(9.0, 1.0), (9.0, 8.0), (2.0, 8.0), (2.0, 1.0)]
        ft = forklift_targets[(tick // 15) % len(forklift_targets)]
        _move_toward(forklift, ft[0], ft[1], speed=0.6)

    elif scenario == "man_down":
        if tick < 5:
            _move_toward(worker, 9.5, 7.0, speed=0.8)
        else:
            worker["vx"] = 0.0
            worker["vy"] = 0.0
            worker["x_m"] += random.gauss(0, 0.04)
            worker["y_m"] += random.gauss(0, 0.04)
            worker["x_m"] = _clamp(worker["x_m"], 8.5, 10.5)
            worker["y_m"] = _clamp(worker["y_m"], 6.0, 8.5)

        cp = PATROL_CHECKPOINTS[_patrol_cp_idx % len(PATROL_CHECKPOINTS)]
        if _move_toward(guard, cp["x_m"], cp["y_m"], speed=0.4):
            _write_patrol_log(guard, cp, compliant=True, vigi_detected=True)
            _patrol_cp_idx += 1

        _move_toward(forklift, 3.0, 5.0, speed=0.3)

    elif scenario == "collision_warning":
        _move_toward(forklift, 5.0, 4.0, speed=0.8)
        _move_toward(worker,   5.0, 4.0, speed=0.5)
        _move_toward(guard,    1.0, 1.0, speed=0.3)

    elif scenario == "ghost_patrol":
        guard["vx"] = 0.0
        guard["vy"] = 0.0

        worker["x_m"] = _clamp(worker["x_m"] + random.uniform(-0.2, 0.2), 0.5, 7.0)
        worker["y_m"] = _clamp(worker["y_m"] + random.uniform(-0.2, 0.2), 0.5, 4.5)
        _move_toward(forklift, 8.0, 2.0, speed=0.4)

    elif scenario == "missed_checkpoint":
        if tick < 15:
            _move_toward(guard, 5.0, 2.0, speed=0.5)  # Warehouse Zone
        else:
            _move_toward(guard, 6.0, 8.0, speed=0.5)  # Exit Corridor (skips Machinery Bay)

        worker["x_m"] = _clamp(worker["x_m"] + random.uniform(-0.2, 0.2), 0.5, 7.0)
        worker["y_m"] = _clamp(worker["y_m"] + random.uniform(-0.2, 0.2), 0.5, 4.5)
        _move_toward(forklift, 2.0, 5.0, speed=0.3)


# ── Patrol log writer ─────────────────────────────────────────────────────

def _write_patrol_log(
    beacon: Dict,
    checkpoint: Dict,
    compliant: bool,
    vigi_detected: bool,
    dwell_s: Optional[int] = None,
    actual_arrival: Optional[str] = None,
) -> None:
    """Write a PatrolLogRecord to Firestore and run compliance + ghost-patrol checks."""
    dwell = dwell_s if dwell_s is not None else random.randint(settings.MIN_DWELL_SECONDS, 60)
    record = PatrolLogRecord(
        log_id=str(uuid.uuid4()),
        guard_id=beacon["person_id"],
        checkpoint_id=checkpoint["id"],
        checkpoint_name=checkpoint["name"],
        expected_arrival=utcnow_iso(),
        actual_arrival=actual_arrival if actual_arrival is not None else utcnow_iso(),
        dwell_time_seconds=dwell,
        min_dwell_required=settings.MIN_DWELL_SECONDS,
        ble_detected=True,
        vigi_detected=vigi_detected,
        compliant=compliant,
        shift_id=_shift_id,
    )
    patrol_log_repository.save(record)
    print(f"[SIM] Patrol log: {beacon['label']} → {checkpoint['name']}  vigi={vigi_detected}  compliant={compliant}")

    safety_service.check_patrol_compliance(record)
    safety_service.verify_multimodal(record, ble_detected=True, vigi_detected=vigi_detected)


# ── Side-effect events per scenario ──────────────────────────────────────

def _side_effects(scenario: str, tick: int) -> None:
    """Trigger patrol compliance / ghost-patrol at the right moment of each scenario."""
    global _ghost_logged, _missed_logged

    if scenario == "ghost_patrol" and tick == 5 and not _ghost_logged:
        _ghost_logged = True
        guard = SIMULATED_BEACONS[0]
        fake_cp = {"id": "cp-ghost", "name": "Patrol Area"}
        _write_patrol_log(guard, fake_cp, compliant=False, vigi_detected=False)

    if scenario == "missed_checkpoint" and tick == 20 and not _missed_logged:
        _missed_logged = True
        guard = SIMULATED_BEACONS[0]
        missed_cp = {"id": "cp-03", "name": "Machinery Bay"}
        # actual_arrival=None means the guard never arrived
        _write_patrol_log(
            guard, missed_cp,
            compliant=False, vigi_detected=False,
            dwell_s=0, actual_arrival=None,
        )


# ── Telemetry payload builder ─────────────────────────────────────────────

def _build_payload(beacon: Dict, timestamp: str) -> Dict:
    """
    Build TelemetryRequest-compatible dict:
        reporter_mac  = beacon MAC
        readings[]    = one entry per AP, with AP position and computed RSSI
    Only APs where RSSI > -90 dBm are included (beacon is in range).
    """
    readings = []
    for ap in SIMULATED_APS:
        d = _dist(ap["x_m"], ap["y_m"], beacon["x_m"], beacon["y_m"])
        rssi = _rssi_from_distance(d)
        if rssi < -90:
            continue
        readings.append({
            "ap_mac": ap["mac"],
            "rssi":   rssi,
            "ap_x":   ap["x_m"],
            "ap_y":   ap["y_m"],
        })
    return {
        "reporter_mac": beacon["mac"],
        "timestamp":    timestamp,
        "readings":     readings,
        "person_id":    beacon["person_id"],
        "person_type":  beacon["person_type"],
    }


# ── Firebase initialisation (standalone mode only) ────────────────────────

def _init_firebase_if_needed() -> None:
    if not firebase_admin._apps:
        cred = credentials.Certificate(settings.FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred, {"databaseURL": settings.FIREBASE_RTDB_URL})


# ── Main async loop ───────────────────────────────────────────────────────

async def run_simulation() -> None:
    """
    Cycle through scenarios, POST /telemetry once per beacon per tick,
    and trigger safety events at the right moments.
    """
    global _scenario_index, _scenario_tick, _shift_id
    global _ghost_logged, _missed_logged, _mandown_seeded

    _init_firebase_if_needed()

    _shift_id       = f"shift-{uuid.uuid4().hex[:8]}"
    _scenario_index = 0
    _scenario_tick  = 0
    _ghost_logged   = False
    _missed_logged  = False
    _mandown_seeded = False

    token = settings.OMADA_ACCESS_TOKEN
    headers = {"Authorization": f"Bearer {token}"}

    print(f"[SIM] Starting SKYE simulation  shift={_shift_id}")
    print(f"[SIM] Scenarios: {[s for s, _ in SCENARIOS]}")
    print(f"[SIM] Tick interval: {TICK_INTERVAL_S}s")

    async with httpx.AsyncClient() as client:
        while True:
            scenario, max_ticks = SCENARIOS[_scenario_index % len(SCENARIOS)]

            if _scenario_tick >= max_ticks:
                print(f"[SIM] '{scenario}' complete → next scenario")
                _scenario_index += 1
                _scenario_tick  = 0
                _ghost_logged   = False
                _missed_logged  = False
                _mandown_seeded = False
                scenario, max_ticks = SCENARIOS[_scenario_index % len(SCENARIOS)]
                print(f"[SIM] Starting '{scenario}'")

            _tick_scenario(scenario, _scenario_tick)
            _side_effects(scenario, _scenario_tick)

            # ── man_down: seed a back-dated first position so the safety
            # service sees >5 min elapsed on the next tick ─────────────────
            if scenario == "man_down" and _scenario_tick == 5 and not _mandown_seeded:
                _mandown_seeded = True
                seed_ts = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
                worker = SIMULATED_BEACONS[1]
                seed_payload = _build_payload(worker, seed_ts)
                if len(seed_payload["readings"]) >= 3:
                    try:
                        await client.post(TELEMETRY_ENDPOINT, json=seed_payload,
                                          headers=headers, timeout=5.0)
                        print(f"[SIM] man_down seed posted (ts={seed_ts[:19]})")
                    except Exception as e:
                        print(f"[SIM] man_down seed failed: {e}")

            # ── Send one POST per beacon ───────────────────────────────────
            now_ts = utcnow_iso()
            for beacon in SIMULATED_BEACONS:
                payload = _build_payload(beacon, now_ts)
                n = len(payload["readings"])
                try:
                    resp = await client.post(TELEMETRY_ENDPOINT, json=payload,
                                             headers=headers, timeout=5.0)
                    print(f"[SIM] {scenario:20s} tick {_scenario_tick:3d} | "
                          f"{beacon['label']:12s} → {resp.status_code} "
                          f"({n} APs in readings[])")
                except Exception as e:
                    print(f"[SIM] {beacon['label']} send failed: {e}")

            _scenario_tick += 1
            await asyncio.sleep(TICK_INTERVAL_S)


if __name__ == "__main__":
    asyncio.run(run_simulation())
