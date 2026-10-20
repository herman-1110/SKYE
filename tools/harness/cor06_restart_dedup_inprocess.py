"""In-process checks for COR-06 (Prompt 136): a backend restart doesn't repeat
an alert the previous process already raised for the same episode.

A "restart" clears every piece of in-memory state the sweep and the Omada
heartbeat writer keep; /alerts and /positions (the fake RTDB) survive, as
they do on real Firebase.

  1  a signal-loss alert, then a restart: the next sweep doesn't repeat it,
     and latches the person
  2  once that alert is resolved, a restart and a sweep alert again
  3  a new episode (the person came back after the alert, then went dark
     again) alerts after a restart even though the old alert is unresolved
  4  a positioning_offline, then a restart: not repeated during the same
     outage
  5  after a new outage (the APs reported in between), a restart and a sweep
     raise a new positioning_offline

The clock: time.time in omada_ingest_service and safety_service.utcnow_iso.
On 2975863 every check fails: each restart repeats the signal-loss alerts
(checks 2 and 3 then fail on the extra copies), and there is no
positioning_offline.

usage (Git Bash, repo root):
  "$py" -B tools/harness/cor06_restart_dedup_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "cor06_restart_dedup_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_", "MAN_DOWN_",
                         "AP_SILENT", "AP_ALIVE", "COLLISION_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-cor06-default-rtdb.firebaseio.com",
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
    APS = [a["mac"] for a in C.APS]

    def report(t0, t1):
        for t in range(t0, t1 + 1):
            clock["t"] = t
            for m in APS:
                writer._write_ap_heartbeat(m, "T136")

    def position(pid, t):
        db.reference(f"/positions/{pid}").set({
            "beacon_mac": pid, "person_id": pid, "person_type": "worker", "x": 8.0, "y": 6.0, "zone": "Z",
            "timestamp": iso(t), "floor_id": C.FLOOR_ID, "building_id": C.BUILDING_ID})

    def restart():
        for name in ("_stale_alerted", "_last_man_down", "_still_alerted", "_man_down_tracker",
                     "_approx_runs", "_last_fresh_mono", "_held_logged"):
            if hasattr(ss, name):
                getattr(ss, name).clear()
        svc._positioning_offline_latched = False
        for name in ("_ap_last_report", "_ap_up_since"):
            if hasattr(writer, name):
                getattr(writer, name).clear()

    def sweep(t):
        clock["t"] = t
        return sorted((a.alert_type, a.person_id) for a in svc.check_man_down_stale())

    def saved(kind, pid=""):
        out = [(k, a) for k, a in alert_repository.get_all().items()
               if (a.get("cause") == "signal_loss" if kind == "signal_loss" else a.get("alert_type") == kind)
               and (a.get("person_id") or "") == pid]
        return sorted(out, key=lambda ka: ka[1]["timestamp"])

    P1, P2 = "test-cor06-p1", "test-cor06-p2"

    # 1: P1 goes dark at 10; alerted at 200; restart; the APs keep reporting
    report(0, 200)
    position(P1, 10)
    first = sweep(200)
    restart()
    report(201, 260)                             # past the 30 s grace after the restart
    again = sweep(260)
    check(1, "unresolved signal-loss, then a restart: not repeated, person latched",
          first == [("man_down", P1)] and again == [] and len(saved("signal_loss", P1)) == 1
          and P1 in ss._stale_alerted,
          f"first={first} after_restart={again} saved={len(saved('signal_loss', P1))}")

    # 2: resolve it; restart; alert again
    alert_repository.mark_resolved(saved("signal_loss", P1)[0][0])
    restart()
    report(261, 300)
    resolved = sweep(300)
    check(2, "once resolved, a restart and a sweep alert again",
          resolved == [("man_down", P1)] and len(saved("signal_loss", P1)) == 2, f"fired={resolved}")

    # 3: P2: alerted at 200-something, came back at 400, dark again; restart
    position(P2, 100)
    report(301, 320)
    p2_first = sweep(320)
    report(321, 400)
    position(P2, 400)                            # back, after the alert
    report(401, 540)
    restart()
    report(541, 580)
    p2_new = sweep(580)
    check(3, "a new episode after the old (unresolved) alert: alerts after a restart",
          p2_first == [("man_down", P2)] and p2_new == [("man_down", P2)] and len(saved("signal_loss", P2)) == 2,
          f"first={p2_first} new_episode={p2_new}")

    # 4: whole outage after 600; positioning_offline; restart; not repeated
    for pid in (P1, P2):
        db.reference(f"/positions/{pid}").delete()
    report(581, 600)
    off1 = sweep(700)
    restart()
    off2 = sweep(760)
    check(4, "positioning_offline, then a restart during the same outage: not repeated",
          off1 == [("positioning_offline", "")] and off2 == [] and len(saved("positioning_offline")) == 1,
          f"first={off1} after_restart={off2} saved={len(saved('positioning_offline'))}")

    # 5: the APs report 800-850 (a sweep sees them), silent again; restart; a new one
    report(800, 850)
    back = sweep(850)
    restart()
    off3 = sweep(950)
    check(5, "a new outage after the APs reported again: a new positioning_offline after a restart",
          back == [] and off3 == [("positioning_offline", "")] and len(saved("positioning_offline")) == 2,
          f"while_back={back} new_outage={off3} saved={len(saved('positioning_offline'))}")

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
