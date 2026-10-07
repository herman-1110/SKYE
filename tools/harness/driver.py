"""p128 harness driver: POST real-shaped Omada payloads to /telemetry/omada.

Library:
    import driver as D
    D.configure(port)                       # default port for post()
    D.wait_ready(port)                      # polls GET /openapi.json (unauthenticated)
    D.entry("0001", -70)                    # guard beacon, rssi {"avg": -70}
    D.entry("0001", None)                   # real-style null  -> "rssi": {}
    D.entry("0001", "JSONNULL")             # crash shape      -> "rssi": null
    status, body = D.post(1, [D.entry(...)])  # AP index 1..3
    D.rssi_for_point(8, 6)                  # {1: -80, 2: -80, 3: -78} (LDPL n=2.5, tx -59)

CLI:
    python driver.py <port> <scenario> <out_json>
    scenarios: solve | rssinull | holdfallback | all

Payload shape is taken from the real captures (backend/payload.json and the
'[OMADA] {' raw-JSON lines of skye-calib-eap770-postupgrade-20260922-135717.log):
  top-level keys meta/reporter/reported; reporter.mac colon-less upper-case;
  reporter.time and reported[].lastseen are unix-seconds STRINGS; rssi.avg an
  int (or {} when the AP has no average); ibeacon uuid 32 lower-case hex with
  no dashes, major/minor 4-digit strings, power int; deviceClass/model/sensors
  as sent by the Minew MWC01 tags.
The access token is read from the real .env and never printed or recorded.
"""
import http.client
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True
HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
if HARNESS_DIR not in sys.path:
    sys.path.append(HARNESS_DIR)

import harness_common as C  # noqa: E402

_PORT: Optional[int] = None
_TOKEN: Optional[str] = None
_RECORD: List[Dict[str, Any]] = []
_CTX = {"scenario": None, "phase": None}
_BATTERY = {"0001": 85, "0002": 59}


def configure(port: int) -> None:
    global _PORT
    if int(port) in C.FORBIDDEN_PORTS:
        raise SystemExit(f"refusing port {port} (live dev server)")
    _PORT = int(port)


def _token() -> str:
    global _TOKEN
    if _TOKEN is None:
        from dotenv import dotenv_values
        _TOKEN = dotenv_values(C.REAL_ENV_PATH).get("OMADA_ACCESS_TOKEN") or ""
        if not _TOKEN:
            raise SystemExit("OMADA_ACCESS_TOKEN missing from the real .env")
    return _TOKEN


# ── payload builders ─────────────────────────────────────────────────────────
def entry(beacon_minor: str, rssi: Any, lastseen: Optional[int] = None) -> Dict[str, Any]:
    """One reported[] item. rssi: number -> {"avg": int(round(n))};
    None -> {} (real null shape); "JSONNULL" -> null (the crash shape)."""
    b = C.BEACONS[beacon_minor]
    if rssi is None:
        rssi_block: Any = {}
    elif isinstance(rssi, str) and rssi == "JSONNULL":
        rssi_block = None
    else:
        rssi_block = {"avg": int(round(float(rssi)))}
    return {
        "mac": b["ble_mac"],
        "deviceClass": ["Minew", "iBeacon", "Eddystone"],
        "model": b["model"],
        "lastseen": str(int(lastseen if lastseen is not None else time.time())),
        "rssi": rssi_block,
        "ibeacon": {"uuid": C.BEACON_UUID_WIRE, "major": C.BEACON_MAJOR, "minor": beacon_minor,
                    "power": int(b["tx_power"])},
        "sensors": {"battery": _BATTERY.get(beacon_minor, 80), "temperature": 26},
    }


def payload(ap_index: int, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    ap = C.AP_BY_INDEX[ap_index]
    return {
        "meta": {"access_token": _token(), "clientId": "test", "nbTopic": "telemetry"},
        "reporter": {"name": ap["reporter_name"], "mac": C.ap_wire_mac(ap), "hwType": ap["hwType"],
                     "swVersion": ap["swVersion"], "swBuild": ap["swBuild"], "ipv4": ap["ipv4"],
                     "time": str(int(time.time()))},
        "reported": entries,
    }


def rssi_for_point(x: float, y: float, aps=(1, 2, 3)) -> Dict[int, float]:
    """LDPL rssi = -59 - 25*log10(d) per AP (float; entry() rounds to int like real APs)."""
    return {i: C.ldpl_rssi(C.AP_BY_INDEX[i], x, y) for i in aps}


# ── HTTP ───────────────────────────────────────────────────────────────────
def _request(method: str, path: str, body: Optional[bytes], port: int, timeout: float = 15.0):
    conn = http.client.HTTPConnection(C.HOST, port, timeout=timeout)
    try:
        headers = {"Content-Type": "application/json"} if body is not None else {}
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        try:
            data = json.loads(raw.decode("utf-8")) if raw else None
        except Exception:
            data = {"_non_json": raw[:500].decode("utf-8", "replace")}
        return resp.status, data
    finally:
        conn.close()


def post(ap_index: int, entries: List[Dict[str, Any]], port: Optional[int] = None,
         note: str = "") -> Tuple[int, Any]:
    port = port or _PORT
    if port is None:
        raise RuntimeError("driver.configure(port) first, or pass port=")
    if int(port) in C.FORBIDDEN_PORTS:
        raise SystemExit(f"refusing port {port}")
    body = json.dumps(payload(ap_index, entries), separators=(",", ":")).encode("utf-8")
    t0 = time.time()
    try:
        status, data = _request("POST", "/telemetry/omada", body, port)
        err = None
    except Exception as e:
        status, data, err = -1, None, f"{type(e).__name__}: {e}"
    t1 = time.time()
    _RECORD.append({
        "t": round(t0, 4), "t_end": round(t1, 4),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t0)) + f".{int((t0 % 1) * 1000):03d}Z",
        "scenario": _CTX["scenario"], "phase": _CTX["phase"], "note": note,
        "ap_index": ap_index, "ap_mac": C.AP_BY_INDEX[ap_index]["mac"],
        "entries": [{"minor": e["ibeacon"]["minor"], "rssi": e["rssi"]} for e in entries],
        "status": status, "json": data, "error": err, "elapsed_ms": round((t1 - t0) * 1000, 1),
    })
    return status, data


def wait_ready(port: int, timeout: float = 60.0, proc=None) -> bool:
    """Poll GET /openapi.json (no auth, no Firebase) until 200."""
    if int(port) in C.FORBIDDEN_PORTS:
        raise SystemExit(f"refusing port {port}")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            return False
        try:
            status, _ = _request("GET", "/openapi.json", None, port, timeout=2.0)
            if status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


# ── scheduling helpers ───────────────────────────────────────────────────────
_MARKS: List[Dict[str, Any]] = []


def _phase(scenario: str, phase: str) -> None:
    now = time.time()
    if _MARKS and _MARKS[-1]["t_end"] is None:
        _MARKS[-1]["t_end"] = round(now, 4)
    _CTX["scenario"], _CTX["phase"] = scenario, phase
    _MARKS.append({"scenario": scenario, "phase": phase, "t_start": round(now, 4), "t_end": None})


def _end_phase() -> None:
    if _MARKS and _MARKS[-1]["t_end"] is None:
        _MARKS[-1]["t_end"] = round(time.time(), 4)


def _sleep_until(t: float) -> None:
    d = t - time.time()
    if d > 0:
        time.sleep(d)


def _run_schedule(t0: float, sched: List[Tuple[float, int, List[Tuple[str, Any]]]], note: str = "") -> None:
    """sched items: (offset_s, ap_index, [(beacon_minor, rssi), ...]); entries are
    built at send time so lastseen/reporter.time are current, like a real AP."""
    for offset, ap_index, specs in sched:
        _sleep_until(t0 + offset)
        post(ap_index, [entry(m, rv) for m, rv in specs], note=note)


GUARD, WORKER = "0001", "0002"
SOLVE_POINT = (8.0, 6.0)


def _full_cycles(n: int, x: float, y: float, start: float = 0.0, period: float = 1.0,
                 stagger: float = 0.35, aps=(1, 2, 3)):
    r = rssi_for_point(x, y, aps)
    sched = []
    for c in range(n):
        for k, i in enumerate(aps):
            sched.append((start + c * period + k * stagger, i, [(GUARD, r[i])]))
    return sched


# ── scenarios ──────────────────────────────────────────────────────────────
def scenario_solve() -> None:
    _phase("solve", "full3")
    _run_schedule(time.time(), _full_cycles(4, *SOLVE_POINT))
    _end_phase()


def scenario_rssinull() -> None:
    _phase("rssinull", "single_post")
    post(1, [entry(GUARD, "JSONNULL"), entry(WORKER, -65)], note="guard rssi=null, worker -65")
    _end_phase()


def scenario_holdfallback() -> None:
    x, y = SOLVE_POINT
    r = rssi_for_point(x, y)
    # 1) 3 full cycles -> exact solve
    _phase("holdfallback", "full3")
    _run_schedule(time.time(), _full_cycles(3, x, y))
    # 2) AP1+AP2 only, 6 s at 1 Hz each -> <3 fresh -> hold (after AP3's
    #    last reading ages out of BUFFER_WINDOW_S=2.0)
    _phase("holdfallback", "ap12_hold")
    t0 = time.time()
    _run_schedule(t0, [(c * 1.0 + k * 0.35, i, [(GUARD, r[i])])
                       for c in range(6) for k, i in enumerate((1, 2))])
    _sleep_until(t0 + 6.0)
    # 3) AP1 only, 8 s -> crosses POSITION_EXACT_HOLD_SECONDS=10 -> fallback at AP1
    _phase("holdfallback", "ap1_fallback")
    t0 = time.time()
    _run_schedule(t0, [(c * 1.0, 1, [(GUARD, r[1])]) for c in range(8)])
    _sleep_until(t0 + 8.0)
    # 4) AP1 at -95 dBm, 4 s -> below PROXIMITY_RSSI_FLOOR=-90 -> no write
    _phase("holdfallback", "ap1_weak_-95")
    t0 = time.time()
    _run_schedule(t0, [(c * 1.0, 1, [(GUARD, -95)]) for c in range(4)])
    _sleep_until(t0 + 4.0)
    _end_phase()


SCENARIOS = {
    "solve": [scenario_solve],
    "rssinull": [scenario_rssinull],
    "holdfallback": [scenario_holdfallback],
    "all": [scenario_solve, scenario_rssinull, scenario_holdfallback],
}


def run(port: int, scenario: str, out_json: str) -> Dict[str, Any]:
    configure(port)
    if scenario not in SCENARIOS:
        raise SystemExit(f"unknown scenario {scenario!r}; choose from {sorted(SCENARIOS)}")
    started = time.time()
    fns = SCENARIOS[scenario]
    for i, fn in enumerate(fns):
        if i:
            time.sleep(1.0)
        fn()
    result = {
        "port": port, "scenario": scenario, "started": started, "finished": time.time(),
        "constants": {"guard_point": SOLVE_POINT, "rssi_at_guard_point": rssi_for_point(*SOLVE_POINT),
                      "aps": [{k: a[k] for k in ("index", "mac", "x_m", "y_m")} for a in C.APS],
                      "beacon_uuid_wire": C.BEACON_UUID_WIRE,
                      "beacons": {m: b["person_id"] for m, b in C.BEACONS.items()}},
        "phases": _MARKS,
        "requests": _RECORD,
    }
    tmp = out_json + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    os.replace(tmp, out_json)
    return result


def main(argv) -> int:
    if len(argv) != 4:
        print("usage: python driver.py <port> <scenario> <out_json>", file=sys.stderr)
        return 2
    res = run(int(argv[1]), argv[2], os.path.abspath(argv[3]))
    by = {}
    for r in res["requests"]:
        k = f"{r['scenario']}/{r['phase']}"
        by.setdefault(k, {}).setdefault(str(r["status"]), 0)
        by[k][str(r["status"])] += 1
    # ASCII only
    for k, v in by.items():
        print(f"[DRIVER] {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
