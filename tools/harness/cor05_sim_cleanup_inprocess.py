"""In-process checks for COR-05 and CON-04 (Prompt 135): simulated people
never outlive their simulation in RTDB /positions.

  1  simulation_events cancelled mid-run -> its four records are removed; a
     real person's record is untouched
  2  simulation_events failing mid-run (an exception in a tick) -> removed too
  3  simulation_patrol started and stopped through the API -> its records go
  4  simulation_shift running when the app shuts down -> the lifespan cancels
     it and its records go
  5  startup removes leftovers from all three simulators (a hard kill), and
     nothing else
  6  a clean-up that hangs is waited for at most CLEANUP_TIMEOUT_S, logged,
     and doesn't hold up the cancel
  7  every simulated telemetry post went to the fake client, never a socket

Each simulator's httpx client is replaced by a fake whose post() writes the
position record the backend would have written; TELEMETRY_ENDPOINT also points
at a dead port as a backstop (the tripwire doesn't cover localhost, and
localhost:8000 is the live backend).

usage (Git Bash, repo root):
  "$py" -B tools/harness/cor05_sim_cleanup_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import asyncio
import contextlib
import io
import json
import logging
import os
import sys
import time
import types

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

ADMIN = {"Authorization": "Bearer harness-token:harness-owner"}
DEAD_ENDPOINT = "http://127.0.0.1:9/telemetry"
REAL_KEY = "test-cor05-real-guard"
results = []


def check(num, name, ok, detail=""):
    results.append({"check": num, "name": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] #{num} {name}" + (f" - {detail}" if detail else ""), flush=True)


class Collect(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend-dir", required=True)
    args = ap.parse_args()
    backend_dir = os.path.abspath(args.backend_dir)
    if os.path.isdir(os.path.join(backend_dir, "venv")) or os.path.exists(os.path.join(backend_dir, "serviceAccountKey.json")):
        print("refusing: --backend-dir must be a git-archive export, never the live backend/")
        return 2
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "cor05_sim_cleanup_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-cor05-default-rtdb.firebaseio.com",
        "GEMINI_API_KEY": "harness-fake-gemini-key",
        "OMADA_ACCESS_TOKEN": "harness-fake-omada-token",
        "LLM_MODEL_NAME": "harness-fake-model",
        "VIGI_DISCOVERY_INTERVAL_S": "0",
        "GO2RTC_CONFIG_PATH": os.path.join(run_dir, "go2rtc.yaml"),
        "GO2RTC_API_URL": "http://127.0.0.1:9",
        "HARNESS_FAKE_AUTH": "1",
        "HARNESS_SEED_STALE": "0",
    })
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)
    import harness_fakes
    harness_fakes.install_tripwire(run_dir)
    store = harness_fakes.install_fakes(run_dir)
    import harness_seed
    harness_seed.seed(store)

    import main  # reconfigures stdout to UTF-8; the simulators print arrows
    from fastapi.testclient import TestClient
    from firebase_admin import db
    from routes import simulation_routes as sroutes
    from services import simulation_cleanup as scl
    from services import simulation_events as sev
    from services import simulation_patrol as spa
    from services import simulation_shift as ssh

    posts = []

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
            posts.append(url)
            key = json["reporter_mac"].replace(":", "_")
            db.reference(f"/positions/{key}").set({
                "beacon_mac": json["reporter_mac"], "person_id": json["person_id"],
                "person_type": json["person_type"], "x": 1.0, "y": 1.0, "zone": "unknown",
                "timestamp": json["timestamp"]})
            return FakeResponse()

    for m in (sev, spa, ssh):
        m.httpx = types.SimpleNamespace(AsyncClient=FakeAsyncClient)
        m.TELEMETRY_ENDPOINT = DEAD_ENDPOINT
        m.TICK_INTERVAL_S = 0.02

    EVENTS = scl.position_keys(sev.SIMULATED_BEACONS)
    PATROL = scl.position_keys(spa.SIMULATED_BEACONS)
    SHIFT = scl.position_keys(ssh.OUTGOING_BEACONS + ssh.INCOMING_BEACONS)
    ALL = scl.all_simulated_position_keys()

    def present(keys):
        pos = db.reference("/positions").get() or {}
        return [k for k in keys if k in pos]

    def put_real():
        db.reference(f"/positions/{REAL_KEY}").set({
            "beacon_mac": REAL_KEY, "person_id": REAL_KEY, "person_type": "guard", "x": 3.0, "y": 3.0,
            "zone": "unknown", "timestamp": "2026-10-12T02:00:00+00:00"})

    def real_present():
        return db.reference(f"/positions/{REAL_KEY}").get() is not None

    def wait_until(pred, timeout=8.0):
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if pred():
                return True
            time.sleep(0.02)
        return pred()

    quiet = contextlib.redirect_stdout(io.StringIO())

    # 1: cancel mid-run
    async def run_and_cancel():
        task = asyncio.create_task(sev.run_simulation())
        t0 = time.monotonic()
        while len(present(EVENTS)) < len(EVENTS) and time.monotonic() - t0 < 8:
            await asyncio.sleep(0.02)
        seen = present(EVENTS)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=8)
        return seen, bool(done)

    put_real()
    with quiet:
        seen, finished = asyncio.run(run_and_cancel())
    check(1, "simulation_events cancelled mid-run -> its records are removed, a real record stays",
          len(seen) == len(EVENTS) == 4 and finished and not present(EVENTS) and real_present(),
          f"seen={len(seen)} finished={finished} left={present(EVENTS)} real={real_present()}")

    # 2: fails mid-run
    orig_heartbeats = sev._write_heartbeats
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] > 3:
            raise RuntimeError("harness: simulated failure in a tick")
        orig_heartbeats()

    sev._write_heartbeats = flaky

    async def run_until_error():
        task = asyncio.create_task(sev.run_simulation())
        done, _ = await asyncio.wait({task}, timeout=10)
        return task if done else None

    with quiet:
        task = asyncio.run(run_until_error())
    sev._write_heartbeats = orig_heartbeats
    err = task.exception() if task is not None and not task.cancelled() else None
    check(2, "simulation_events failing mid-run -> its records are removed too",
          isinstance(err, RuntimeError) and calls["n"] > 3 and not present(EVENTS) and real_present(),
          f"error={type(err).__name__ if err else None} ticks={calls['n']} left={present(EVENTS)}")

    # 3: start and stop through the API
    with quiet:
        with TestClient(main.app) as client:
            r_start = client.post("/simulation/start?mode=patrol", headers=ADMIN)
            appeared = wait_until(lambda: len(present(PATROL)) == len(PATROL))
            r_stop = client.post("/simulation/stop", headers=ADMIN)
            left = present(PATROL)
    check(3, "simulation_patrol started and stopped through the API -> its records are removed",
          r_start.status_code == 200 and appeared and r_stop.status_code == 200 and not left and real_present(),
          f"start={r_start.status_code} appeared={appeared} stop={r_stop.status_code} left={left}")

    # 4: shutdown while running
    with quiet:
        with TestClient(main.app) as client:
            r_shift = client.post("/simulation/start?mode=shift", headers=ADMIN)
            appeared = wait_until(lambda: len(present(SHIFT)) == len(SHIFT))
    check(4, "simulation_shift running at shutdown -> the lifespan cancels it and its records go",
          r_shift.status_code == 200 and appeared and sroutes._task is None and not present(SHIFT) and real_present(),
          f"start={r_shift.status_code} appeared={appeared} task_cleared={sroutes._task is None} left={present(SHIFT)}")

    # 5: startup removes leftovers from a hard kill
    for k in ALL:
        db.reference(f"/positions/{k}").set({"beacon_mac": k, "person_id": "sim-leftover", "person_type": "worker",
                                             "x": 1.0, "y": 1.0, "zone": "unknown",
                                             "timestamp": "2026-10-12T01:00:00+00:00"})
    put_real()
    before = present(ALL)
    with quiet:
        with TestClient(main.app):
            after_startup = present(ALL)
            real_after = real_present()
    check(5, "startup removes every simulator's leftovers (six keys) and keeps the real record",
          len(before) == len(ALL) == 6 and not after_startup and real_after,
          f"before={len(before)} after={after_startup} real={real_after}")

    # 6: a hanging clean-up doesn't hold up the cancel
    collect = Collect()
    logging.getLogger("services.simulation_cleanup").addHandler(collect)
    orig_delete = scl.delete_positions
    scl.CLEANUP_TIMEOUT_S = 0.5

    def hanging_delete(keys):
        time.sleep(2.5)
        return orig_delete(keys)

    scl.delete_positions = hanging_delete

    async def cancel_timed():
        task = asyncio.create_task(sev.run_simulation())
        await asyncio.sleep(0.2)
        t0 = time.monotonic()
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=8)
        return time.monotonic() - t0, bool(done)

    with quiet:
        elapsed, finished = asyncio.run(cancel_timed())
    scl.delete_positions = orig_delete
    scl.CLEANUP_TIMEOUT_S = 5.0
    logging.getLogger("services.simulation_cleanup").removeHandler(collect)
    warned = [m for m in collect.messages if "took longer" in m]
    check(6, "a hanging clean-up is waited for at most CLEANUP_TIMEOUT_S and logged",
          finished and elapsed < 2.0 and len(warned) == 1, f"elapsed={elapsed:.2f}s warned={len(warned)}")

    # 7
    check(7, "every simulated telemetry post went to the fake client (dead-port endpoint), none to a socket",
          posts and set(posts) == {DEAD_ENDPOINT}, f"posts={len(posts)} endpoints={sorted(set(posts))}")

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
