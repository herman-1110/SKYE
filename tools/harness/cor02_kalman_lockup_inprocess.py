"""In-process checks for COR-02 (Prompt 136): the Kalman filter can no longer
lock onto an old position.

  1  a person settled at one spot jumps more than the 8 m outlier threshold:
     the output follows within 3 measurements
  2  a rejected measurement doesn't refresh _last_seen (only an accepted or
     initialising one does)
  3  isolated outliers are still rejected: two in a row, then a good fix,
     then two more, never move the output or reset the filter
  4  invalidate_scale_cache() drops every Kalman filter

positioning_service.compute_position() runs against the seeded test floor
(20 x 16 m, 3 APs) with noiseless RSSI, on a fake clock (time.time and
time.monotonic patched in positioning_service and kalman_service).
On 2975863, checks 1, 2 and 4 fail.

usage (Git Bash, repo root):
  "$py" -B tools/harness/cor02_kalman_lockup_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import json
import os
import sys
import time as _real_time
import types

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

results = []


def check(num, name, ok, detail=""):
    results.append({"check": num, "name": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] #{num} {name}" + (f" - {detail}" if detail else ""), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend-dir", required=True)
    args = ap.parse_args()
    backend_dir = os.path.abspath(args.backend_dir)
    if os.path.isdir(os.path.join(backend_dir, "venv")) or os.path.exists(os.path.join(backend_dir, "serviceAccountKey.json")):
        print("refusing: --backend-dir must be a git-archive export, never the live backend/")
        return 2
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "cor02_kalman_lockup_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_", "MAN_DOWN_",
                         "AP_SILENT", "AP_ALIVE", "COLLISION_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-cor02-default-rtdb.firebaseio.com",
        "GEMINI_API_KEY": "harness-fake-gemini-key",
        "OMADA_ACCESS_TOKEN": "harness-fake-omada-token",
        "LLM_MODEL_NAME": "harness-fake-model",
        "VIGI_DISCOVERY_INTERVAL_S": "0",
        "GO2RTC_CONFIG_PATH": os.path.join(run_dir, "go2rtc.yaml"),
        "HARNESS_SEED_STALE": "0",
    })
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)
    import harness_fakes
    harness_fakes.install_tripwire(run_dir)
    store = harness_fakes.install_fakes(run_dir)
    import harness_seed
    harness_seed.seed(store)

    import services.kalman_service as KS
    import services.positioning_service as PS
    from models.telemetry import APRssiReading, OmadaTelemetryPayload

    clock = {"t": 1000.0}
    fake_time = types.SimpleNamespace(**{k: getattr(_real_time, k) for k in dir(_real_time) if not k.startswith("__")})
    fake_time.monotonic = lambda: clock["t"]
    fake_time.time = lambda: 1_790_000_000.0 + clock["t"]
    KS.time = fake_time
    PS.time = fake_time
    svc = PS.positioning_service

    def solve(pid, x, y):
        readings = [APRssiReading(ap_mac=a["mac"], rssi=C.ldpl_rssi(a, x, y), ap_x=a["x_m"], ap_y=a["y_m"])
                    for a in C.APS]
        payload = OmadaTelemetryPayload(reporter_mac=pid, timestamp="2026-10-20T02:00:00+00:00",
                                        readings=readings, person_id=pid, person_type="worker")
        rec = svc.compute_position(payload, floor_id=C.FLOOR_ID, building_id=C.BUILDING_ID)
        return (round(rec.x, 2), round(rec.y, 2)) if rec else None

    def at(t, pid, x, y):
        clock["t"] = t
        return solve(pid, x, y)

    # 1: settle at (4, 4), then jump to (15, 12) (about 13.6 m away)
    P = "test-cor02-jump"
    settle = [at(1000 + 2 * i, P, 4.0, 4.0) for i in range(6)]
    jump = [at(1012 + 2 * i, P, 15.0, 12.0) for i in range(3)]
    followed = jump[-1] is not None and abs(jump[-1][0] - 15.0) < 0.5 and abs(jump[-1][1] - 12.0) < 0.5
    check(1, "a jump of more than 8 m is followed within 3 measurements",
          settle[-1] is not None and abs(settle[-1][0] - 4.0) < 0.5 and followed,
          f"settled={settle[-1]} after_jump={jump}")

    # 2: one accepted fix, then one rejected one: _last_seen stays at the accepted time
    Q = "test-cor02-seen"
    at(2000, Q, 4.0, 4.0)
    at(2002, Q, 4.2, 4.0)
    accepted_at = svc._last_seen.get(Q)
    at(2004, Q, 15.0, 12.0)                     # rejected (first in a row)
    after_reject = svc._last_seen.get(Q)
    check(2, "a rejected measurement doesn't refresh _last_seen",
          accepted_at is not None and after_reject == accepted_at,
          f"accepted_at={accepted_at} after_reject={after_reject}")

    # 3: isolated outliers: 2 bad, 1 good, 2 bad -> output stays near (4, 4) throughout
    R = "test-cor02-isolated"
    for i in range(4):
        at(3000 + 2 * i, R, 4.0, 4.0)
    seq = [at(3008, R, 15.0, 12.0), at(3010, R, 15.0, 12.0), at(3012, R, 4.1, 4.0),
           at(3014, R, 15.0, 12.0), at(3016, R, 15.0, 12.0)]
    check(3, "isolated outliers (2 bad, 1 good, 2 bad) are still rejected",
          all(s is not None and abs(s[0] - 4.0) < 1.0 and abs(s[1] - 4.0) < 1.0 for s in seq),
          f"outputs={seq}")

    # 4: invalidate_scale_cache() drops the filters
    before = len(svc._filters)
    svc.invalidate_scale_cache()
    check(4, "invalidate_scale_cache() clears the Kalman filters",
          before > 0 and len(svc._filters) == 0, f"filters before={before} after={len(svc._filters)}")

    loud = [p for p in ("UNIMPLEMENTED.txt", "TRIPWIRE_HIT.txt") if os.path.exists(os.path.join(run_dir, p))]
    check(0, "fakes: nothing unimplemented, no tripwire", not loud, f"{loud}")
    failed = [x for x in results if not x["ok"]]
    with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump({"passed": len(results) - len(failed), "failed": len(failed), "results": results}, f, indent=1)
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
