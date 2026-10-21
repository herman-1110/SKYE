"""In-process checks for Prompt 142, D1.7: inactive floors raise nothing in
the signal-loss sweep, and "placed APs" means APs placed on an active floor.

The seeded floor (T128 Level, active, AP1-AP3) plus Backup (inactive), which
also holds AP4, an AP no active floor has. Heartbeats go through the Omada
ingest's own writer for longer than the 30 s grace, so the APs are alive and
136's hold rule (REL-01) doesn't apply; position records are written
straight into the fake RTDB, with heard_by, as the position writers leave
them.

  1  a stale worker on Backup (inactive): no signal-loss
  2  a stale worker on T128 Level (active): one signal-loss, as under 136
  3  a stale worker with an empty floor_id: still checked, one signal-loss
  4  AP1-AP3 go silent while AP4 (placed only on Backup) keeps reporting:
     one positioning_offline, since AP4 isn't placed on an active floor
  5  no floor active at all: a new stale worker on T128 Level raises nothing
  6  a stale worker whose floor can't be found is still checked (fail open)

On the base (3ab8adc) the sweep ignores floor state: the Backup worker and
the no-active-floor worker alert, and AP4's reports suppress the
positioning_offline.

usage (Git Bash, repo root):
  "$py" -B tools/harness/f142_sweep_inactive_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import contextlib
import io
import json
import os
import sys
import time as _real_time
import types
from datetime import datetime, timezone

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

UNIX0 = 1_790_000_000
BACKUP = "f-142-backup"
AP4_MAC = "AA:BB:CC:00:14:04"
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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "f142_sweep_inactive_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_", "MAN_DOWN_",
                         "AP_SILENT", "AP_ALIVE", "COLLISION_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-f142s-default-rtdb.firebaseio.com",
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

    import services.omada_ingest_service as OIS
    import services.safety_service as ss
    from firebase_admin import db, firestore
    from models.position import PositionRecord
    from repositories.alert_repository import alert_repository

    clock = {"t": 0}
    fake_time = types.SimpleNamespace(**{k: getattr(_real_time, k) for k in dir(_real_time) if not k.startswith("__")})
    fake_time.time = lambda: float(UNIX0 + clock["t"])
    OIS.time = fake_time

    def iso(t):
        return datetime.fromtimestamp(UNIX0 + t, timezone.utc).isoformat()
    ss.utcnow_iso = lambda: iso(clock["t"])
    svc = ss.safety_service
    writer = OIS.omada_ingest_service
    fs = firestore.client()
    B1, F1 = C.BUILDING_ID, C.FLOOR_ID
    AP1, AP2, AP3 = (a["mac"] for a in C.APS)

    def floor_ref(f):
        return fs.collection("buildings").document(B1).collection("floors").document(f)

    seeded_floor = floor_ref(F1).get().to_dict()
    floor_ref(BACKUP).set(dict(seeded_floor, id=BACKUP, name="T142 Backup", is_active=False,
                               storage_path="", url="harness://backup.png"))
    floor_ref(BACKUP).collection("access_points").document("ap-142-b4").set({
        "id": "ap-142-b4", "floor_id": BACKUP, "building_id": B1, "name": "Backup AP4", "mac": AP4_MAC,
        "x_pct": 0.5, "y_pct": 0.5, "created_at": seeded_floor["uploaded_at"], "x_m": 10.0, "y_m": 8.0})

    def report(aps, t0, t1):
        """Each AP in aps reports once a second from t0 to t1 inclusive."""
        for t in range(t0, t1 + 1):
            clock["t"] = t
            for m in aps:
                writer._write_ap_heartbeat(m, "T142")

    has_heard_by = "heard_by" in PositionRecord.__dataclass_fields__

    def position(pid, t, floor_id, heard_by):
        v = {"beacon_mac": pid, "person_id": pid, "person_type": "worker", "x": 8.0, "y": 6.0, "zone": "Z",
             "timestamp": iso(t), "floor_id": floor_id, "building_id": B1 if floor_id else ""}
        if has_heard_by:
            v["heard_by"] = heard_by
        db.reference(f"/positions/{pid}").set(v)

    def sweep(t):
        clock["t"] = t
        with contextlib.redirect_stdout(io.StringIO()):
            fired = svc.check_man_down_stale()
        return sorted((a.alert_type, a.person_id) for a in fired)

    def saved(kind):
        return [a for a in alert_repository.get_all().values()
                if (a.get("cause") == "signal_loss" if kind == "signal_loss" else a.get("alert_type") == kind)]

    W_BACKUP, W_ACTIVE, W_NOFLOOR, W_ALLOFF, W_UNKNOWN = (f"test-f142-w{i}" for i in range(1, 6))

    # 1-3: one sweep, all APs alive
    report([AP1, AP2, AP3, AP4_MAC], 0, 100)
    position(W_BACKUP, 100, BACKUP, [AP1, AP2, AP3])
    position(W_ACTIVE, 100, F1, [AP1, AP2, AP3])
    position(W_NOFLOOR, 100, "", [AP1, AP2, AP3])
    report([AP1, AP2, AP3, AP4_MAC], 101, 250)
    fired = sweep(250)
    people = [p for kind, p in fired if kind == "man_down"]
    check(1, "a stale worker on Backup (inactive): no signal-loss", W_BACKUP not in people, f"fired={fired}")
    check(2, "a stale worker on T128 Level (active): one signal-loss", people.count(W_ACTIVE) == 1, f"fired={fired}")
    check(3, "a stale worker with an empty floor_id is still checked", people.count(W_NOFLOOR) == 1, f"fired={fired}")

    # 4: AP1-AP3 silent from 251; AP4 (Backup only) keeps reporting
    report([AP4_MAC], 251, 400)
    fired4 = sweep(400)
    check(4, "AP1-AP3 silent, AP4 (placed only on Backup) reporting: one positioning_offline",
          fired4 == [("positioning_offline", "")] and len(saved("positioning_offline")) == 1,
          f"fired={fired4}")

    # 5: no floor active
    floor_ref(F1).update({"is_active": False})
    report([AP1, AP2, AP3, AP4_MAC], 401, 500)
    position(W_ALLOFF, 500, F1, [AP1, AP2, AP3])
    report([AP1, AP2, AP3, AP4_MAC], 501, 650)
    fired5 = sweep(650)
    check(5, "no floor active: a new stale worker on T128 Level raises nothing", fired5 == [], f"fired={fired5}")

    # 6: a floor that can't be found
    position(W_UNKNOWN, 650, "f-142-no-such-floor", [AP4_MAC])
    report([AP1, AP2, AP3, AP4_MAC], 651, 800)
    fired6 = sweep(800)
    check(6, "a stale worker whose floor can't be found is still checked",
          [p for kind, p in fired6 if kind == "man_down"] == [W_UNKNOWN], f"fired={fired6}")

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
