"""In-process checks for REL-01 (Prompt 136): an AP outage no longer raises a
signal-loss man-down for everyone who is still there.

One timeline on the seeded floor (3 APs). The APs' heartbeats are written by
the Omada ingest's own writer; position records are written straight into the
fake RTDB, as the position writers would leave them.

  1  all three APs go silent with W1, W2 (no heard_by, an older record) and
     W3 on the floor: no signal-loss, one positioning_offline
  2  a minute later, still silent: nothing new (positioning_offline latched)
  3  the APs come back; W1 and W2 refresh; a sweep inside the 30 s grace:
     nothing (W3, still missing, is held because the APs aren't alive yet)
  4  past the grace: one signal-loss, for W3 only
  5  one AP silent: W4 (heard by all three) went dark, so one signal-loss;
     W5, heard only by the silent AP, is held, logged once; no
     positioning_offline. W5's AP comes back: still held inside the grace,
     one signal-loss after it
  6  the Omada heartbeat writer keeps up_since: a run of 1 s reports keeps
     it, a silence longer than AP_SILENT_AFTER_S starts a new run

The clock: time.time in omada_ingest_service and safety_service.utcnow_iso.
On 2975863 the records carry no heard_by (its writers never set one, and its
PositionRecord would reject it), and every check fails: signal-loss for
everyone at once, no positioning_offline, no up_since.

usage (Git Bash, repo root):
  "$py" -B tools/harness/rel01_ap_outage_inprocess.py --backend-dir "$exp/backend"

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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "rel01_ap_outage_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_", "MAN_DOWN_",
                         "AP_SILENT", "AP_ALIVE", "COLLISION_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-rel01-default-rtdb.firebaseio.com",
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
    from firebase_admin import db
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
    AP1, AP2, AP3 = (a["mac"] for a in C.APS)

    def report(aps, t0, t1):
        """Each AP in aps reports once a second from t0 to t1 inclusive."""
        for t in range(t0, t1 + 1):
            clock["t"] = t
            for m in aps:
                writer._write_ap_heartbeat(m, "T136")

    has_heard_by = "heard_by" in PositionRecord.__dataclass_fields__

    def position(pid, t, heard_by):
        v = {"beacon_mac": pid, "person_id": pid, "person_type": "worker", "x": 8.0, "y": 6.0, "zone": "Z",
             "timestamp": iso(t), "floor_id": C.FLOOR_ID, "building_id": C.BUILDING_ID}
        if heard_by is not None and has_heard_by:   # 2975863's writers never set it
            v["heard_by"] = heard_by
        db.reference(f"/positions/{pid}").set(v)

    def sweep(t):
        clock["t"] = t
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            fired = svc.check_man_down_stale()
        held_lines = [ln for ln in out.getvalue().splitlines() if "holding the signal-loss alert" in ln]
        return sorted((a.alert_type, a.person_id) for a in fired), held_lines

    def saved(kind, pid=None):
        return [a for a in alert_repository.get_all().values()
                if (a.get("cause") == "signal_loss" if kind == "signal_loss" else a.get("alert_type") == kind)
                and (pid is None or a.get("person_id") == pid)]

    W1, W2, W3, W4, W5 = (f"test-rel01-w{i}" for i in range(1, 6))

    # 1 and 2: whole outage
    report([AP1, AP2, AP3], 0, 100)
    position(W1, 100, [AP1, AP2, AP3])
    position(W2, 100, None)                      # written before 136: no heard_by
    position(W3, 100, [AP1, AP2, AP3])
    f1, _ = sweep(250)
    check(1, "all APs silent: no signal-loss, one positioning_offline",
          f1 == [("positioning_offline", "")] and not saved("signal_loss"), f"fired={f1}")
    f2, _ = sweep(310)
    check(2, "still silent a minute later: nothing new (latched)",
          f2 == [] and len(saved("positioning_offline")) == 1 and not saved("signal_loss"), f"fired={f2}")

    # 3 and 4: the APs come back; W1 and W2 refresh, W3 doesn't
    report([AP1, AP2, AP3], 320, 325)
    position(W1, 325, [AP1, AP2, AP3])
    position(W2, 325, [AP1, AP2, AP3])
    report([AP1, AP2, AP3], 326, 335)
    f3, _ = sweep(335)
    check(3, "APs back, sweep inside the grace: nothing (W1, W2 refreshed; W3 held)",
          f3 == [] and not saved("signal_loss"), f"fired={f3}")
    report([AP1, AP2, AP3], 336, 360)
    f4, _ = sweep(360)
    check(4, "past the grace: one signal-loss, for W3 only",
          f4 == [("man_down", W3)] and len(saved("signal_loss")) == 1 and len(saved("positioning_offline")) == 1,
          f"fired={f4} signal_loss_people={sorted(a['person_id'] for a in saved('signal_loss'))}")

    # 5: W1 to W3 leave the floor. AP3 silent from 361; W4 (heard by all) and
    # W5 (heard by AP3 only) go dark at 360
    for pid in (W1, W2, W3):
        db.reference(f"/positions/{pid}").delete()
    position(W4, 360, [AP1, AP2, AP3])
    position(W5, 360, [AP3])
    report([AP1, AP2], 361, 500)
    f5a, held_a = sweep(500)
    report([AP1, AP2], 501, 560)
    f5b, held_b = sweep(560)
    report([AP1, AP2], 561, 569)
    report([AP1, AP2, AP3], 570, 590)
    f5c, held_c = sweep(590)
    report([AP1, AP2, AP3], 591, 605)
    f5d, _ = sweep(605)
    w5_logs = [ln for ln in held_a + held_b + held_c if W5 in ln]
    check(5, "one AP silent: W4 alerts, W5 (only that AP) held and logged once; "
             "after its AP is back, held inside the grace, then one signal-loss",
          f5a == [("man_down", W4)] and f5b == [] and f5c == [] and f5d == [("man_down", W5)]
          and len(w5_logs) == 1 and len(saved("positioning_offline")) == 1,
          f"500={f5a} 560={f5b} 590={f5c} 605={f5d} w5_log_lines={len(w5_logs)}")

    # 6: up_since as the writer keeps it
    hb1 = db.reference(f"/ap_heartbeats/{AP1.replace(':', '_')}").get() or {}
    hb3 = db.reference(f"/ap_heartbeats/{AP3.replace(':', '_')}").get() or {}
    check(6, "up_since: kept through 1 s reports, restarted after a silence",
          hb1.get("up_since") == UNIX0 + 320 and hb3.get("up_since") == UNIX0 + 570
          and hb3.get("last_seen") == UNIX0 + 605,
          f"AP1 up_since={hb1.get('up_since')} AP3 up_since={hb3.get('up_since')} last_seen={hb3.get('last_seen')}")

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
