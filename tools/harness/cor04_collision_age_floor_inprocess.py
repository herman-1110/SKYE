"""In-process checks for COR-04 (Prompt 136): collisions only between fresh
records on the same floor.

  1  a fresh worker and forklift on the same floor, 1 m apart -> one collision
  2  a stale worker (10 s old) next to a fresh forklift, and a fresh worker
     next to a stale forklift -> nothing
  3  the same pair on different floors, or with no floor -> nothing
  4  repeats for one pair are 10 s apart: +5 s nothing, +11 s one more
  5  an unreadable timestamp is skipped, not paired, and logged once; a second
     check doesn't log it again

check_collision() is called directly with PositionRecords; the clock is
driven by patching safety_service.utcnow_iso. On 2975863, checks 2, 3 and 5
fail (every pair within the distance alerts).

usage (Git Bash, repo root):
  "$py" -B tools/harness/cor04_collision_age_floor_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import contextlib
import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

BASE_T = datetime(2026, 10, 20, 2, 0, 0, tzinfo=timezone.utc)
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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "cor04_collision_age_floor_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_", "MAN_DOWN_",
                         "AP_SILENT", "AP_ALIVE", "COLLISION_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-cor04-default-rtdb.firebaseio.com",
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
    harness_fakes.install_fakes(run_dir)

    import services.safety_service as ss
    from models.position import PositionRecord
    from models.safety_settings import SafetySettings

    svc = ss.safety_service
    svc._get_settings = lambda: SafetySettings(man_down_minutes=5, collision_distance_m=2.0)
    clock = {"t": 0.0}
    ss.utcnow_iso = lambda: (BASE_T + timedelta(seconds=clock["t"])).isoformat()

    def iso(t):
        return (BASE_T + timedelta(seconds=t)).isoformat()

    def rec(pid, ptype, x, ts, floor=C.FLOOR_ID, building=C.BUILDING_ID):
        return PositionRecord(beacon_mac=pid, person_id=pid, person_type=ptype, x=x, y=5.0, zone="Z",
                              timestamp=ts, predicted_x=x, predicted_y=5.0, floor_id=floor, building_id=building)

    def run(t, records):
        clock["t"] = t
        return [(a.person_id, a.other_person_id) for a in svc.check_collision(records)]

    # 1
    one = run(100, [rec("test-c04-w1", "worker", 5.0, iso(99)), rec("test-c04-f1", "forklift", 6.0, iso(100))])
    check(1, "fresh worker and forklift on the same floor, 1 m apart -> one collision",
          one == [("test-c04-w1", "test-c04-f1")], f"{one}")

    # 2
    stale_w = run(200, [rec("test-c04-w2", "worker", 5.0, iso(190)), rec("test-c04-f2", "forklift", 6.0, iso(200))])
    stale_f = run(300, [rec("test-c04-w3", "worker", 5.0, iso(300)), rec("test-c04-f3", "forklift", 6.0, iso(290))])
    check(2, "a 10 s old worker or forklift never pairs", stale_w == [] and stale_f == [],
          f"stale_worker={stale_w} stale_forklift={stale_f}")

    # 3
    other_floor = run(400, [rec("test-c04-w4", "worker", 5.0, iso(400)),
                            rec("test-c04-f4", "forklift", 6.0, iso(400), floor="f-other")])
    no_floor = run(500, [rec("test-c04-w5", "worker", 5.0, iso(500), floor="", building=""),
                         rec("test-c04-f5", "forklift", 6.0, iso(500), floor="", building="")])
    check(3, "different floors, or no floor at all -> nothing", other_floor == [] and no_floor == [],
          f"other_floor={other_floor} no_floor={no_floor}")

    # 4: test-c04-w1/f1 alerted at t=100
    plus5 = run(105, [rec("test-c04-w1", "worker", 5.0, iso(105)), rec("test-c04-f1", "forklift", 6.0, iso(105))])
    plus11 = run(111, [rec("test-c04-w1", "worker", 5.0, iso(111)), rec("test-c04-f1", "forklift", 6.0, iso(111))])
    check(4, "repeats for one pair: +5 s nothing, +11 s one more", plus5 == [] and plus11 == [("test-c04-w1", "test-c04-f1")],
          f"+5s={plus5} +11s={plus11}")

    # 5
    def bad_run(t):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            got = run(t, [rec("test-c04-w6", "worker", 5.0, "2026-10-20T02:10:00"),   # naive
                          rec("test-c04-f6", "forklift", 6.0, iso(t))])
        return got, [ln for ln in out.getvalue().splitlines() if "collision check" in ln]
    first, log1 = bad_run(600)
    second, log2 = bad_run(605)
    check(5, "an unreadable timestamp is skipped and logged once",
          first == [] and second == [] and len(log1) == 1 and "test-c04-w6" in log1[0] and log2 == [],
          f"first={first} second={second} logged={len(log1)},{len(log2)}")

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
