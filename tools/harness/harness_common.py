"""Shared constants for the SKYE test harness (launcher, fakes, seed, driver).

Nothing here touches the outside network (port_busy() only connects to
127.0.0.1). The only filesystem write is prepare_run_dir(), which only ever
deletes inside tools/harness/runs/.
Module name is prefixed ``harness_`` so it can never shadow a backend module
(config/, utils/, ...) once the backend dir is put on sys.path.
"""
import math
import os
import shutil
import sys

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))   # <repo>/tools/harness
REPO_ROOT = os.path.dirname(os.path.dirname(HARNESS_DIR))   # <repo>
RUNS_DIR = os.path.join(HARNESS_DIR, "runs")                # git-ignored

# The real .env (read-only). Loaded explicitly because config/settings.py calls
# load_dotenv() with no args, which will not find a .env from an export/worktree.
REAL_ENV_PATH = os.path.join(REPO_ROOT, "backend", ".env")

FORBIDDEN_PORTS = {8000}  # live dev server with real AP traffic - never touch
HOST = "127.0.0.1"


def port_busy(port: int) -> bool:
    """True if something already listens on HOST:port (loopback connect only)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        return s.connect_ex((HOST, port)) == 0
    finally:
        s.close()


def prepare_run_dir(run_dir: str) -> str:
    """Absolute run dir, created empty. A non-empty dir under RUNS_DIR is wiped
    (stale op logs / capture files would otherwise mix into the new run); a
    non-empty dir anywhere else is refused with exit code 2."""
    run_dir = os.path.abspath(run_dir)
    if os.path.exists(run_dir) and os.listdir(run_dir):
        rd, root = os.path.normcase(run_dir), os.path.normcase(RUNS_DIR)
        try:
            under = os.path.commonpath([rd, root]) == root and rd != root
        except ValueError:  # different drives
            under = False
        if not under:
            print(f"run dir {run_dir} is not empty and not under {RUNS_DIR}; aborting", file=sys.stderr)
            raise SystemExit(2)
        shutil.rmtree(run_dir)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


# ── Seed geometry ──────────────────────────────────────────────────────────
BUILDING_ID = "b-t128"
FLOOR_ID = "f-t128"
SCALE_PX_PER_M = 50.0
IMAGE_W_PX = 1000   # -> 20.0 m wide
IMAGE_H_PX = 800    # -> 16.0 m tall

# Firestore stores AP macs colon-separated upper-case (floor_routes APCreateRequest
# validator; ap_repository.get_by_mac_global queries mac.upper() with the
# colon form that omada_ingest_service._format_mac_colons produces).
# Real APs send reporter.mac colon-less upper-case ("A82948C388A0").
APS = [
    {"index": 1, "id": "ap-t128-1", "doc_name": "T128 AP1", "mac": "AA:BB:CC:00:01:01",
     "reporter_name": "EAP770", "hwType": "2.0", "swVersion": "1.4.3", "swBuild": "14057",
     "ipv4": "192.168.0.201", "x_m": 2.0, "y_m": 2.0},
    {"index": 2, "id": "ap-t128-2", "doc_name": "T128 AP2", "mac": "AA:BB:CC:00:01:02",
     "reporter_name": "EAP660 HD", "hwType": "2.0", "swVersion": "1.6.7", "swBuild": "8173",
     "ipv4": "192.168.0.202", "x_m": 14.0, "y_m": 2.0},
    {"index": 3, "id": "ap-t128-3", "doc_name": "T128 AP3", "mac": "AA:BB:CC:00:01:03",
     "reporter_name": "EAP660 HD", "hwType": "2.0", "swVersion": "1.6.7", "swBuild": "8173",
     "ipv4": "192.168.0.203", "x_m": 8.0, "y_m": 12.0},
]
AP_BY_INDEX = {a["index"]: a for a in APS}


def ap_wire_mac(ap: dict) -> str:
    """Reporter mac exactly as real Omada APs send it: colon-less upper-case."""
    return ap["mac"].replace(":", "").upper()


# ── Beacons ────────────────────────────────────────────────────────────────
# Nominal identity from the task: 11111111-2222-3333-4444-555555555555.
# Real Omada payloads carry ibeacon.uuid as 32 lower-case hex chars with NO
# dashes (every one of the 820 iBeacon entries in the 2026-09-22 calibration
# log). make_ibeacon_key() only lower-cases - it does NOT strip dashes - so a
# registration must use the same dash-less form for a real payload to resolve.
# Both the seeded Beacon doc and the driver use the wire form below.
BEACON_UUID_NOMINAL = "11111111-2222-3333-4444-555555555555"
BEACON_UUID_WIRE = BEACON_UUID_NOMINAL.replace("-", "").lower()
BEACON_MAJOR = "0001"

BEACONS = {
    "0001": {"person_id": "test-128-guard", "person_type": "guard", "label": "T128 Guard",
             "tx_power": -59.0, "ble_mac": "C3000071A001", "model": "MWC01"},
    "0002": {"person_id": "test-128-worker", "person_type": "worker", "label": "T128 Worker",
             "tx_power": -59.0, "ble_mac": "C3000071A002", "model": "MWC01"},
}


def beacon_key(minor: str) -> str:
    """Mirror of config.beacon_registry.make_ibeacon_key (uuid lower-cased only)."""
    return f"{BEACON_UUID_WIRE.lower()}:{BEACON_MAJOR}:{minor}"


# Extra seed for the man-down sweeper: a worker whose /positions record is
# 300 s old (inside [MAN_DOWN_STALE_SECONDS=120, MAN_DOWN_STALE_MAX_AGE_S=3600])
# so the first 60 s sweep tick fires one signal_loss alert through the fakes.
# Disable with env HARNESS_SEED_STALE=0 (not an app env var).
STALE_PERSON_ID = "test-128-stale"
STALE_AGE_S = 300

# LDPL model used by the driver (matches settings.PATH_LOSS_EXPONENT default 2.5)
PATH_LOSS_EXPONENT = 2.5
TX_POWER = -59.0


def ldpl_rssi(ap: dict, x: float, y: float, tx_power: float = TX_POWER,
              n: float = PATH_LOSS_EXPONENT) -> float:
    d = max(math.hypot(x - ap["x_m"], y - ap["y_m"]), 0.01)
    return tx_power - 10.0 * n * math.log10(d)
