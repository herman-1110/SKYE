"""In-process checks for COR-12, simulator half (Prompt 135): each scripted
event in simulation_events raises exactly its own alert, once.

  1  the ghost-patrol segment (5 ticks) raises one ghost_patrol and no
     patrol_violation
  2  the ghost record has a BLE arrival time, a dwell over the minimum,
     vigi_detected False and is compliant (the tag was there)
  3  the missed-checkpoint event raises one patrol_violation (missed_checkpoint)
     and no ghost_patrol
  4  the missed record has no arrival, no dwell and is not compliant
  5  normal patrol ticks raise nothing and write no patrol log
  6  two whole scripted cycles through run_simulation(): ghost_patrol alerts =
     ghost events, patrol_violation alerts = missed events, and the tick each
     event fired on is reported (the ghost event is fixed at cycle tick 26 of
     37, counting from 0; the missed event depends on how far guard_a is from
     AP0 when its segment starts)

run_simulation()'s httpx client is faked and its endpoint points at a dead
port (localhost:8000 is the live backend); with no backend behind it, the
only alerts are the simulator's own.

usage (Git Bash, repo root):
  "$py" -B tools/harness/cor12_sim_events_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import asyncio
import contextlib
import io
import json
import os
import sys
import types

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

DEAD_ENDPOINT = "http://127.0.0.1:9/telemetry"
CYCLES = 2
results = []


def check(num, name, ok, detail=""):
    results.append({"check": num, "name": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] #{num} {name}" + (f" - {detail}" if detail else ""), flush=True)


class StopSim(Exception):
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend-dir", required=True)
    args = ap.parse_args()
    backend_dir = os.path.abspath(args.backend_dir)
    if os.path.isdir(os.path.join(backend_dir, "venv")) or os.path.exists(os.path.join(backend_dir, "serviceAccountKey.json")):
        print("refusing: --backend-dir must be a git-archive export, never the live backend/")
        return 2
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "cor12_sim_events_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-cor12-default-rtdb.firebaseio.com",
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

    import main  # noqa: F401 - reconfigures stdout to UTF-8; the simulator prints arrows
    from firebase_admin import firestore
    from repositories.alert_repository import alert_repository
    from services import simulation_events as sev
    from services.safety_service import safety_service

    def alerts():
        out = {"ghost_patrol": [], "patrol_violation": []}
        for a in (alert_repository.get_all() or {}).values():
            if a.get("alert_type") in out:
                out[a["alert_type"]].append(a)
        return out

    def counts():
        a = alerts()
        return {k: len(v) for k, v in a.items()}

    def logs(guard="sim-guard-001"):
        return [d.to_dict() for d in firestore.client().collection("patrol_logs").stream()
                if d.to_dict().get("guard_id") == guard]

    def setup_world():
        aps = [{"id": a["id"], "mac": a["mac"], "name": a["doc_name"], "x_m": a["x_m"], "y_m": a["y_m"]} for a in C.APS]
        sev._floor_aps = aps
        xs, ys = [a["x_m"] for a in aps], [a["y_m"] for a in aps]
        pad_x = max((max(xs) - min(xs)) * 0.20, 2.0)
        pad_y = max((max(ys) - min(ys)) * 0.20, 2.0)
        sev._floor_bounds = {
            "x_min": max(0.0, min(xs) - pad_x), "x_max": max(xs) + pad_x,
            "y_min": max(0.0, min(ys) - pad_y), "y_max": max(ys) + pad_y,
            "w": (max(xs) + pad_x) - max(0.0, min(xs) - pad_x),
            "h": (max(ys) + pad_y) - max(0.0, min(ys) - pad_y),
        }
        sev._safety_svc = safety_service
        sev._shift_id = "shift-harness-cor12"
        n, mid = len(aps), len(aps) // 2
        b = sev.SIMULATED_BEACONS
        b[0].update(ap_order=list(range(n)), x_m=aps[0]["x_m"], y_m=aps[0]["y_m"], current_ap_idx=0)
        b[1].update(ap_order=list(range(n)), x_m=aps[mid]["x_m"], y_m=aps[mid]["y_m"], current_ap_idx=mid)
        b[2].update(ap_order=list(range(n)), x_m=aps[0]["x_m"] + 1.0, y_m=aps[0]["y_m"] + 1.0, current_ap_idx=0)
        b[3].update(ap_order=list(range(n - 1, -1, -1)), x_m=aps[-1]["x_m"] - 1.0, y_m=aps[-1]["y_m"] - 1.0,
                    current_ap_idx=0)
        for beacon in b:
            beacon.update(state="moving", wander_ticks=0, wander_target=None)

    quiet = contextlib.redirect_stdout(io.StringIO())
    setup_world()

    # 1 and 2: the ghost segment
    before = counts()
    sev._event_fired = False
    with quiet:
        for t in range(5):
            sev._tick_ghost_patrol(t)
    after = counts()
    ghost_new = after["ghost_patrol"] - before["ghost_patrol"]
    pv_new = after["patrol_violation"] - before["patrol_violation"]
    check(1, "the ghost-patrol segment raises one ghost_patrol and no patrol_violation",
          ghost_new == 1 and pv_new == 0, f"ghost_patrol={ghost_new} patrol_violation={pv_new}")
    ghost_logs = [r for r in logs() if r.get("actual_arrival")]
    rec = ghost_logs[0] if len(ghost_logs) == 1 else {}
    check(2, "the ghost record: BLE arrival time, dwell over the minimum, vigi_detected False, compliant",
          len(ghost_logs) == 1 and rec.get("ble_detected") is True and rec.get("vigi_detected") is False
          and rec.get("compliant") is True and rec.get("dwell_time_seconds", 0) >= rec.get("min_dwell_required", 99),
          f"records={len(ghost_logs)} dwell={rec.get('dwell_time_seconds')} compliant={rec.get('compliant')}")

    # 3 and 4: the missed event (guard_a heading for the AP it must skip)
    sev.SIMULATED_BEACONS[0].update(current_ap_idx=1, state="moving", wander_target=None)
    before = counts()
    sev._event_fired = False
    with quiet:
        for t in range(5):
            sev._tick_missed_checkpoint(t)
    after = counts()
    pv_new = after["patrol_violation"] - before["patrol_violation"]
    ghost_new = after["ghost_patrol"] - before["ghost_patrol"]
    causes = [a.get("cause") for a in alerts()["patrol_violation"]]
    check(3, "the missed event raises one patrol_violation (missed_checkpoint) and no ghost_patrol",
          pv_new == 1 and ghost_new == 0 and causes.count("missed_checkpoint") == 1,
          f"patrol_violation={pv_new} ghost_patrol={ghost_new} causes={causes}")
    missed_logs = [r for r in logs() if not r.get("actual_arrival")]
    rec = missed_logs[0] if len(missed_logs) == 1 else {}
    check(4, "the missed record: no arrival, no dwell, not compliant",
          len(missed_logs) == 1 and rec.get("compliant") is False and rec.get("dwell_time_seconds") == 0,
          f"records={len(missed_logs)} compliant={rec.get('compliant')} dwell={rec.get('dwell_time_seconds')}")

    # 5: normal ticks
    before, before_logs = counts(), len(logs())
    with quiet:
        for _ in range(30):
            sev._tick_normal_patrol()
    check(5, "30 normal patrol ticks raise nothing and write no patrol log",
          counts() == before and len(logs()) == before_logs, f"alerts={counts()} logs={len(logs()) - before_logs}")

    # 6: whole scripted cycles through run_simulation()
    class FakeResponse:
        status_code = 200

    class FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None, timeout=None):
            if url != DEAD_ENDPOINT:
                raise RuntimeError(f"unexpected endpoint {url}")
            return FakeResponse()

    sev.httpx = types.SimpleNamespace(AsyncClient=FakeAsyncClient)
    sev.TELEMETRY_ENDPOINT = DEAD_ENDPOINT
    sev.TICK_INTERVAL_S = 0.0
    cycle_len = sum(d for _, d in sev.SEGMENTS)
    ticks = {"n": 0}
    fired = []
    orig_heartbeats, orig_write = sev._write_heartbeats, sev._write_patrol_log

    def heartbeats():
        if ticks["n"] >= CYCLES * cycle_len:
            raise StopSim()
        ticks["n"] += 1
        orig_heartbeats()

    def write(beacon, cp_id, cp_name, event):
        fired.append({"event": event, "tick": ticks["n"] - 1, "cycle_tick": (ticks["n"] - 1) % cycle_len,
                      "segment_tick": sev._segment_tick})
        orig_write(beacon, cp_id, cp_name, event)

    sev._write_heartbeats, sev._write_patrol_log = heartbeats, write
    before = counts()
    with quiet:
        try:
            asyncio.run(sev.run_simulation())
            stopped = False
        except StopSim:
            stopped = True
    sev._write_heartbeats, sev._write_patrol_log = orig_heartbeats, orig_write
    after = counts()
    n_ghost = sum(1 for f in fired if f["event"] == "ghost")
    n_missed = sum(1 for f in fired if f["event"] == "missed")
    d_ghost = after["ghost_patrol"] - before["ghost_patrol"]
    d_pv = after["patrol_violation"] - before["patrol_violation"]
    ghost_ticks = [f["cycle_tick"] for f in fired if f["event"] == "ghost"]
    missed_ticks = [f["cycle_tick"] for f in fired if f["event"] == "missed"]
    check(6, f"{CYCLES} whole cycles ({CYCLES * cycle_len} ticks): ghost_patrol alerts = ghost events, "
             "patrol_violation alerts = missed events; ghost at cycle tick 26",
          stopped and n_ghost == CYCLES and d_ghost == n_ghost and d_pv == n_missed and ghost_ticks == [26] * CYCLES,
          f"ghost events={n_ghost} at cycle ticks {ghost_ticks}, missed events={n_missed} at cycle ticks "
          f"{missed_ticks}; alerts ghost_patrol={d_ghost} patrol_violation={d_pv}")

    loud = [p for p in ("UNIMPLEMENTED.txt", "TRIPWIRE_HIT.txt") if os.path.exists(os.path.join(run_dir, p))]
    check(0, "fakes: nothing unimplemented, no tripwire", not loud, f"{loud}")
    failed = [x for x in results if not x["ok"]]
    with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump({"passed": len(results) - len(failed), "failed": len(failed), "results": results,
                   "fired": fired}, f, indent=1)
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
