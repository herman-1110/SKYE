"""In-process checks for the man-down stillness latch (Open #1, 9 Oct):
one stillness alert per stillness episode instead of one every 30 s.

  1  still past the threshold -> exactly one stillness alert
  2  staying still for another hour -> no further alert
  3  moving past the epsilon ends the episode; still past the threshold
     again -> a second alert
  4  an approximate -> exact upgrade re-seeds the anchor and starts a new
     episode; an exact -> approximate reading does not
  5  a beacon that went dark (signal-loss latch set) and comes back still at
     the same anchor: the signal-loss latch clears, no second stillness alert;
     forklifts never alert

The clock is driven by patching safety_service.utcnow_iso; man_down_minutes
is patched to 1. Run against HEAD without the latch, checks 2 to 5 fail.

usage (Git Bash, repo root):
  "$py" -B tools/harness/man_down_latch_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

BASE_T = datetime(2026, 10, 9, 2, 0, 0, tzinfo=timezone.utc)
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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "man_down_latch_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_", "MAN_DOWN_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-mdlatch-default-rtdb.firebaseio.com",
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
    from repositories.alert_repository import alert_repository

    svc = ss.safety_service
    svc._get_settings = lambda: SafetySettings(man_down_minutes=1, collision_distance_m=2.0)
    clock = {"t": 0.0}
    ss.utcnow_iso = lambda: (BASE_T + timedelta(seconds=clock["t"])).isoformat()
    eps = ss.settings.MAN_DOWN_MOVEMENT_EPSILON_M

    def pos(pid, x, y, approx=False, ptype="worker"):
        return PositionRecord(beacon_mac="AA:00:00:00:00:01", person_id=pid, person_type=ptype,
                              x=x, y=y, zone="Z", timestamp=ss.utcnow_iso(), is_approximate=approx)

    def at(t, pid, x, y, approx=False, ptype="worker"):
        clock["t"] = t
        return svc.check_man_down(pos(pid, x, y, approx, ptype))

    def saved(pid):
        return sorted((a for a in alert_repository.get_all().values() if a.get("person_id") == pid),
                      key=lambda a: a["timestamp"])

    # 1: seed, still for 30 s (nothing), still past 60 s (one alert)
    P = "test-latch-worker"
    fired = [at(0, P, 5.0, 5.0), at(30, P, 5.1, 5.0), at(61, P, 5.0, 5.1)]
    a = saved(P)
    check(1, "still past man_down_minutes -> one stillness alert",
          fired[0] is None and fired[1] is None and fired[2] is not None
          and len(a) == 1 and a[0]["cause"] == "stillness" and a[0]["alert_type"] == "man_down",
          f"fired={[f is not None for f in fired]} saved={len(a)}")

    # 2: another hour of stillness, polled every 31 s (each one past the old 30 s gate)
    later = [at(61 + 31 * i, P, 5.0 + (0.1 if i % 2 else 0.0), 5.0) for i in range(1, 117)]
    a = saved(P)
    check(2, "still for another hour (116 readings, 31 s apart) -> no further alert",
          all(f is None for f in later) and len(a) == 1,
          f"extra alerts returned={sum(f is not None for f in later)} saved={len(a)}")

    # 3: move past epsilon, then still past the threshold again
    t = clock["t"]
    moved = at(t + 5, P, 5.0 + eps + 0.5, 5.0)
    early = at(t + 35, P, 5.0 + eps + 0.5, 5.0)
    again = at(t + 70, P, 5.0 + eps + 0.6, 5.0)
    after = at(t + 101, P, 5.0 + eps + 0.5, 5.0)
    a = saved(P)
    check(3, "moving past the epsilon starts a new episode -> exactly one more alert",
          moved is None and early is None and again is not None and after is None and len(a) == 2,
          f"move={moved is not None} early={early is not None} again={again is not None} after={after is not None} saved={len(a)}")

    # 4: approximate anchor alerts; exact solve upgrades -> new episode; downgrade doesn't reset
    Q = "test-latch-guard"
    q = [at(0, Q, 1.0, 1.0, approx=True, ptype="guard"), at(61, Q, 1.0, 1.0, approx=True, ptype="guard"),
         at(92, Q, 1.0, 1.0, approx=True, ptype="guard")]
    up = [at(100, Q, 3.0, 3.0, ptype="guard"), at(161, Q, 3.1, 3.0, ptype="guard"),
          at(192, Q, 3.0, 3.0, ptype="guard")]
    down = [at(230, Q, 1.0, 1.0, approx=True, ptype="guard"), at(262, Q, 3.0, 3.1, ptype="guard")]
    a = saved(Q)
    check(4, "approximate alert once; exact upgrade -> one new alert; exact->approximate doesn't reset",
          q[0] is None and q[1] is not None and q[1].approximate and q[2] is None
          and up[0] is None and up[1] is not None and not up[1].approximate and up[2] is None
          and all(f is None for f in down) and len(a) == 2,
          f"approx={[f is not None for f in q]} upgrade={[f is not None for f in up]} "
          f"downgrade={[f is not None for f in down]} saved={len(a)}")

    # 5: P's stillness alert is latched (check 3). The beacon goes dark (signal-loss
    # latch set), then comes back still at the same anchor: same episode.
    ss._stale_alerted.add(P)
    back = at(clock["t"] + 300, P, 5.0 + eps + 0.5, 5.0)
    F = "test-latch-forklift"
    fk = [at(0, F, 2.0, 2.0, ptype="forklift"), at(61, F, 2.0, 2.0, ptype="forklift"),
          at(3600, F, 2.0, 2.0, ptype="forklift")]
    check(5, "back from dark, still at the same anchor: signal-loss latch cleared, no second "
             "stillness alert; a still forklift never alerts",
          back is None and len(saved(P)) == 2 and P not in ss._stale_alerted
          and all(f is None for f in fk) and not saved(F),
          f"back={back is not None} saved={len(saved(P))} stale_latched={P in ss._stale_alerted} "
          f"forklift_alerts={len(saved(F))}")

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
