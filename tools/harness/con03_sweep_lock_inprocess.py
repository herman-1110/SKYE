"""In-process checks for CON-03 (Prompt 136): the signal-loss sweep and the
ingest pipeline no longer race.

  1  a fresh position for a person arrives after the sweep has read their
     stale record (forced by running check_man_down() from inside the
     sweep's /positions read): no signal-loss alert, no latch
  2  the alert save runs with positioning_service.pipeline_lock held; the
     /positions read runs without it
  3  while another thread holds pipeline_lock, the sweep still finishes its
     read, but its save waits until the lock is released
  4  someone whose last fresh position came before the sweep's read still
     gets their signal-loss alert

Records are written straight into the fake RTDB with real timestamps (stale
= 200 s old). On 2975863, checks 1 to 3 fail.

usage (Git Bash, repo root):
  "$py" -B tools/harness/con03_sweep_lock_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "con03_sweep_lock_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_", "MAN_DOWN_",
                         "AP_SILENT", "AP_ALIVE", "COLLISION_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-con03-default-rtdb.firebaseio.com",
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
    from firebase_admin import db
    from models.position import PositionRecord
    from models.safety_settings import SafetySettings
    from repositories.alert_repository import alert_repository
    from repositories.position_repository import position_repository
    from services.positioning_service import positioning_service

    svc = ss.safety_service
    svc._get_settings = lambda: SafetySettings(man_down_minutes=60, collision_distance_m=2.0)
    lock = positioning_service.pipeline_lock

    def iso(age_s):
        return (datetime.now(timezone.utc) - timedelta(seconds=age_s)).isoformat()

    def raw(pid, age_s):
        return {"beacon_mac": pid, "person_id": pid, "person_type": "worker", "x": 5.0, "y": 5.0,
                "zone": "Z", "timestamp": iso(age_s), "floor_id": C.FLOOR_ID, "building_id": C.BUILDING_ID}

    def fresh(pid):
        return PositionRecord(**raw(pid, 0))

    def signal_loss(pid):
        return [a for a in alert_repository.get_all().values()
                if a.get("person_id") == pid and a.get("cause") == "signal_loss"]

    real_get_all = position_repository.get_all
    real_save = alert_repository.save

    # 1: P reappears while the sweep is reading
    P = "test-con03-back"
    db.reference("/positions").set({P: raw(P, 200)})

    def get_all_then_p_returns():
        snapshot = real_get_all()
        svc.check_man_down(fresh(P))          # the fresh position lands after the read
        return snapshot
    position_repository.get_all = get_all_then_p_returns
    fired = svc.check_man_down_stale()
    position_repository.get_all = real_get_all
    check(1, "a fresh position after the sweep's read: no signal-loss, no latch",
          fired == [] and not signal_loss(P) and P not in ss._stale_alerted,
          f"fired={[a.person_id for a in fired]} saved={len(signal_loss(P))} latched={P in ss._stale_alerted}")

    # 2: where the lock is held
    Q = "test-con03-held"
    db.reference("/positions").set({Q: raw(Q, 200)})
    seen = {}

    def get_all_noting():
        seen["read_locked"] = lock.locked()
        return real_get_all()

    def save_noting(record):
        seen["save_locked"] = lock.locked()
        return real_save(record)
    position_repository.get_all = get_all_noting
    alert_repository.save = save_noting
    fired = svc.check_man_down_stale()
    position_repository.get_all = real_get_all
    alert_repository.save = real_save
    check(2, "the alert save holds pipeline_lock; the /positions read doesn't",
          [a.person_id for a in fired] == [Q] and seen.get("save_locked") is True
          and seen.get("read_locked") is False, f"{seen}")

    # 3: lock held elsewhere: the read completes, the save waits
    R = "test-con03-wait"
    db.reference("/positions").set({R: raw(R, 200)})
    read_done = threading.Event()

    def get_all_signalling():
        out = real_get_all()
        read_done.set()
        return out
    position_repository.get_all = get_all_signalling
    out = {}
    lock.acquire()
    try:
        t = threading.Thread(target=lambda: out.setdefault("fired", svc.check_man_down_stale()), daemon=True)
        t.start()
        read_ok = read_done.wait(5.0)
        time.sleep(0.5)
        saved_while_held = len(signal_loss(R))
    finally:
        lock.release()
    t.join(5.0)
    position_repository.get_all = real_get_all
    check(3, "with pipeline_lock held elsewhere the read finishes but the save waits",
          read_ok and saved_while_held == 0 and len(signal_loss(R)) == 1 and not t.is_alive(),
          f"read_done={read_ok} saved_while_held={saved_while_held} saved_after={len(signal_loss(R))}")

    # 4: seen before the read, still stale in /positions -> alerts as before
    S = "test-con03-before"
    svc.check_man_down(fresh(S))
    time.sleep(0.05)
    db.reference("/positions").set({S: raw(S, 200)})
    fired = svc.check_man_down_stale()
    check(4, "last seen before the sweep's read -> the signal-loss alert still fires",
          [a.person_id for a in fired] == [S] and len(signal_loss(S)) == 1, f"fired={[a.person_id for a in fired]}")

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
