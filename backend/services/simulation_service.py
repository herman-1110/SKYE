"""
SKYE simulation engine — emits BLE telemetry in Omada Controller format.

Run with:  python services/simulation_service.py
           (from the backend/ directory, with .env loaded)

Each tick sends one POST per AP to /telemetry, exactly mirroring real hardware.
"""
from __future__ import annotations

import asyncio
import math
import os
import random
import sys
import time
from typing import Dict, List, Tuple

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from config.settings import settings

# ---------------------------------------------------------------------------
# AP definitions — mirrors physical deployment on the warehouse floor
# ---------------------------------------------------------------------------
SIMULATED_APS: List[Dict] = [
    {
        "name": "EAP725-Outdoor",
        "mac": "CC:BA:BD:81:9D:CD",
        "hwType": "1.0",
        "swVersion": "1.0.5",
        "swBuild": "37537",
        "ipv4": "192.168.0.6",
        "x_m": 0.0,
        "y_m": 0.0,
    },
    {
        "name": "EAP660 HD",
        "mac": "40:AE:30:9D:34:5A",
        "hwType": "2.0",
        "swVersion": "1.4.3",
        "swBuild": "64055",
        "ipv4": "192.168.0.3",
        "x_m": 10.0,
        "y_m": 0.0,
    },
    {
        "name": "EAP673",
        "mac": "24:2F:D0:38:55:B0",
        "hwType": "1.0",
        "swVersion": "1.3.0",
        "swBuild": "35129",
        "ipv4": "192.168.0.4",
        "x_m": 5.0,
        "y_m": 8.0,
    },
]

# ---------------------------------------------------------------------------
# Beacon definitions — each represents a person/asset wearing a Minew tag
# ---------------------------------------------------------------------------
SIMULATED_BEACONS: List[Dict] = [
    {"mac": "AA:BB:CC:DD:EE:01", "label": "Guard-1",    "x_m": 3.0, "y_m": 4.0},
    {"mac": "AA:BB:CC:DD:EE:02", "label": "Worker-1",   "x_m": 7.0, "y_m": 2.0},
    {"mac": "AA:BB:CC:DD:EE:03", "label": "Forklift-1", "x_m": 5.0, "y_m": 5.0},
]

# Waypoints per beacon label: [(x, y, dwell_seconds), ...]
_WAYPOINTS: Dict[str, List[Tuple[float, float, int]]] = {
    "Guard-1":    [(3.0, 4.0, 20), (8.0, 7.0, 30), (2.0, 7.0, 25), (5.0, 1.0, 20)],
    "Worker-1":   [(7.0, 2.0, 30), (9.0, 6.0, 40), (3.0, 6.0, 30)],
    "Forklift-1": [(5.0, 5.0, 15), (9.0, 5.0, 15), (5.0, 5.0, 15), (1.0, 5.0, 15)],
}

# ---------------------------------------------------------------------------
# RSSI model
# ---------------------------------------------------------------------------
TELEMETRY_URL = "http://localhost:8000/telemetry"
TX_POWER = settings.TX_POWER_DEFAULT        # dBm at 1 m
PATH_LOSS_N = settings.PATH_LOSS_EXPONENT
RSSI_NOISE_STD = settings.RSSI_NOISE_STD


def _rssi_from_distance(distance_m: float) -> int:
    if distance_m < 0.1:
        distance_m = 0.1
    rssi = TX_POWER - 10 * PATH_LOSS_N * math.log10(distance_m)
    return int(round(rssi + random.gauss(0, RSSI_NOISE_STD)))


# ---------------------------------------------------------------------------
# Waypoint interpolation
# ---------------------------------------------------------------------------

def _lerp(a: Tuple[float, float], b: Tuple[float, float], t: float) -> Tuple[float, float]:
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


def _position_at_tick(label: str, tick: int) -> Tuple[float, float]:
    waypoints = _WAYPOINTS[label]
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


def update_beacon_positions(beacons: List[Dict], tick: int) -> None:
    """Update x_m/y_m of each beacon according to its waypoint path."""
    for beacon in beacons:
        label = beacon["label"]
        if label in _WAYPOINTS:
            x, y = _position_at_tick(label, tick)
            beacon["x_m"] = round(x, 3)
            beacon["y_m"] = round(y, 3)


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------

def build_telemetry_payload(ap: Dict, beacons: List[Dict]) -> Dict:
    """Build one Omada-format telemetry payload for one AP."""
    now_str = str(int(time.time()))
    reported = []
    for beacon in beacons:
        dx = beacon["x_m"] - ap["x_m"]
        dy = beacon["y_m"] - ap["y_m"]
        distance = math.sqrt(dx ** 2 + dy ** 2)
        rssi = _rssi_from_distance(distance)
        reported.append({
            "mac": beacon["mac"],
            "rssi": rssi,
            "timestamp": int(time.time()),
        })
    return {
        "meta": {
            "access_token": settings.OMADA_ACCESS_TOKEN,
            "clientId": "sim",
            "nbTopic": "telemetry",
        },
        "reporter": {
            "name": ap["name"],
            "mac": ap["mac"],
            "hwType": ap["hwType"],
            "swVersion": ap["swVersion"],
            "swBuild": ap["swBuild"],
            "ipv4": ap["ipv4"],
            "time": now_str,
        },
        "reported": reported,
    }


# ---------------------------------------------------------------------------
# HTTP send
# ---------------------------------------------------------------------------

async def send_telemetry_tick(beacons: List[Dict]) -> None:
    """Send one POST per AP — mirrors real Omada Controller behaviour."""
    async with httpx.AsyncClient() as client:
        for ap in SIMULATED_APS:
            payload = build_telemetry_payload(ap, beacons)
            try:
                resp = await client.post(
                    TELEMETRY_URL,
                    json=payload,
                    headers={"Authorization": f"Bearer {settings.OMADA_ACCESS_TOKEN}"},
                    timeout=5.0,
                )
                print(f"[SIM] AP {ap['name']} → {resp.status_code}")
            except Exception as exc:
                print(f"[SIM] AP {ap['name']} failed: {exc}")


# ---------------------------------------------------------------------------
# AP position registration (call once at startup so positioning_service knows
# where each AP sits on the floor)
# ---------------------------------------------------------------------------

def register_ap_positions() -> None:
    """Seed the positioning service with each AP's physical location."""
    from services.positioning_service import positioning_service
    for ap in SIMULATED_APS:
        positioning_service.register_ap(ap["mac"], ap["x_m"], ap["y_m"])
    print(f"[SIM] Registered {len(SIMULATED_APS)} APs with positioning service")


# ---------------------------------------------------------------------------
# Main simulation loop
# ---------------------------------------------------------------------------

async def run_simulation(ticks: int = 0, tick_interval_s: float = 2.0) -> None:
    """
    Run the simulation loop.  ticks=0 means run indefinitely.
    Registers AP positions first, then sends telemetry every tick_interval_s seconds.
    """
    register_ap_positions()
    beacons = [dict(b) for b in SIMULATED_BEACONS]
    tick = 0
    print(f"[SIM] Starting — {len(SIMULATED_APS)} APs, {len(beacons)} beacons, "
          f"interval={tick_interval_s}s")
    while ticks == 0 or tick < ticks:
        update_beacon_positions(beacons, tick)
        await send_telemetry_tick(beacons)
        tick += 1
        await asyncio.sleep(tick_interval_s)


if __name__ == "__main__":
    asyncio.run(run_simulation())
