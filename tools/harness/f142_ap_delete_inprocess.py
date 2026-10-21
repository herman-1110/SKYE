"""In-process checks for Prompt 142, D4: removing an AP never reports a
failure for a removal that happened.

delete_ap runs the patrol route, the camera unlink and the AP delete first;
the clean-up after it (heartbeat, simulators, ingest cache) can't fail the
request. Every AP here is placed through POST .../aps first.

  1  the heartbeat clean-up fails after the delete -> 200, the AP is gone,
     one log line naming the AP id
  2  the simulator clean-up fails after the delete -> 200, one log line
  3  deleting twice -> 200 both times
  4  the order: route update, then camera unlink, then the AP's delete
     (read from the fake Firestore's op log)
  5  a failure before the delete (the camera unlink) -> 500, and the AP is
     still there
  6  DIAGNOSE 8's cases, each deleted with its clean-up checked: on the
     patrol route; covered by a camera; loaded by a running simulation
     (patrol, then events); no heartbeat node

On the base (3ab8adc) a clean-up failure after the delete is a 500 for an AP
that is already gone, and the camera unlink runs after the delete.

usage (Git Bash, repo root):
  "$py" -B tools/harness/f142_ap_delete_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import contextlib
import io
import json
import os
import sys
import time
import types

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

ADMIN = {"Authorization": "Bearer harness-token:harness-owner"}
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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "f142_ap_delete_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-f142d-default-rtdb.firebaseio.com",
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

    import main
    from fastapi.testclient import TestClient
    from firebase_admin import db, firestore
    from repositories.position_repository import position_repository
    from routes import simulation_routes as sroutes
    from services import simulation_events as sev
    from services import simulation_patrol as spa
    from services.cctv_service import cctv_service

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
            return FakeResponse()

    for m in (sev, spa):
        m.httpx = types.SimpleNamespace(AsyncClient=FakeAsyncClient)
        m.TELEMETRY_ENDPOINT = "http://127.0.0.1:9/telemetry"
        m.TICK_INTERVAL_S = 0.05

    fs = firestore.client()
    B1, F1 = C.BUILDING_ID, C.FLOOR_ID
    BASE = f"/buildings/{B1}/floors/{F1}"
    floor_ref = fs.collection("buildings").document(B1).collection("floors").document(F1)
    aps_col = floor_ref.collection("access_points")
    seeded = [a["id"] for a in C.APS]
    ops_path = os.path.join(run_dir, "firestore_ops.jsonl")
    floor_path = floor_ref.path if isinstance(floor_ref.path, str) else "/".join(floor_ref.path)
    n = {"i": 0}

    def ops_count():
        with open(ops_path, encoding="utf-8") as f:
            return len(f.read().splitlines())

    def ops_since(mark):
        with open(ops_path, encoding="utf-8") as f:
            return [json.loads(ln) for ln in f.read().splitlines()[mark:] if ln.strip()]

    def hb_key(mac):
        return f"/ap_heartbeats/{mac.replace(':', '_')}"

    def wait_until(pred, timeout=8.0):
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if pred():
                return True
            time.sleep(0.02)
        return pred()

    with TestClient(main.app, raise_server_exceptions=False) as client:
        def place(heartbeat=True):
            n["i"] += 1
            mac = f"AA:BB:CC:00:4D:{n['i']:02X}"
            r = client.post(f"{BASE}/aps", headers=ADMIN,
                            json={"name": f"T142 Del {n['i']}", "mac": mac, "x_pct": 0.2 + 0.02 * n["i"], "y_pct": 0.6})
            assert r.status_code == 200, r.text
            if heartbeat:
                db.reference(hb_key(mac)).set({"mac": mac, "last_seen": int(time.time())})
            return r.json()["id"], mac

        def delete(ap_id):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                r = client.delete(f"{BASE}/aps/{ap_id}", headers=ADMIN)
            return r, [ln for ln in out.getvalue().splitlines() if "[AP] WARNING" in ln]

        def add_camera(cam_id, ap_id):
            floor_ref.collection("cctvs").document(cam_id).set({
                "id": cam_id, "floor_id": F1, "building_id": B1, "name": cam_id, "x_pct": 0.5, "y_pct": 0.5,
                "created_at": "2026-10-22T00:00:00+00:00", "checkpoint_ap_id": ap_id})

        def camera_link(cam_id):
            return (floor_ref.collection("cctvs").document(cam_id).get().to_dict() or {}).get("checkpoint_ap_id")

        # 1
        ap_id, mac = place()
        real = position_repository.delete_ap_heartbeat

        def broken(_mac):
            raise RuntimeError("harness: RTDB unreachable")
        position_repository.delete_ap_heartbeat = broken
        r, lines = delete(ap_id)
        position_repository.delete_ap_heartbeat = real
        check(1, "the heartbeat clean-up fails after the delete -> 200, AP gone, one log line naming it",
              r.status_code == 200 and not aps_col.document(ap_id).get().exists
              and len(lines) == 1 and ap_id in lines[0],
              f"status={r.status_code} gone={not aps_col.document(ap_id).get().exists} lines={lines}")

        # 2
        ap_id, mac = place()
        real_patrol = spa.remove_ap

        def broken_sim(_ap_id):
            raise RuntimeError("harness: simulator state")
        spa.remove_ap = broken_sim
        r, lines = delete(ap_id)
        spa.remove_ap = real_patrol
        check(2, "the simulator clean-up fails after the delete -> 200, one log line",
              r.status_code == 200 and not aps_col.document(ap_id).get().exists and len(lines) == 1 and ap_id in lines[0],
              f"status={r.status_code} lines={lines}")

        # 3
        ap_id, mac = place()
        r1, _ = delete(ap_id)
        r2, _ = delete(ap_id)
        check(3, "deleting twice -> 200 both times", r1.status_code == 200 and r2.status_code == 200,
              f"first={r1.status_code} second={r2.status_code}")

        # 4
        ap_id, mac = place()
        floor_ref.update({"patrol_enabled": True, "patrol_route": seeded + [ap_id]})
        add_camera("cam-142-order", ap_id)
        mark = ops_count()
        r, _ = delete(ap_id)
        ops = ops_since(mark)

        def first(pred):
            return next((i for i, o in enumerate(ops) if pred(o)), None)
        i_route = first(lambda o: o.get("op") == "doc.update" and o.get("path") == floor_path)
        i_cam = first(lambda o: o.get("op") == "doc.update" and str(o.get("path", "")).endswith("cctvs/cam-142-order"))
        i_del = first(lambda o: o.get("op") == "doc.delete" and str(o.get("path", "")).endswith(f"access_points/{ap_id}"))
        check(4, "the order: route update, then camera unlink, then the AP's delete",
              r.status_code == 200 and None not in (i_route, i_cam, i_del) and i_route < i_cam < i_del,
              f"status={r.status_code} route={i_route} camera={i_cam} delete={i_del}")
        floor_ref.update({"patrol_enabled": False, "patrol_route": []})

        # 5
        ap_id, mac = place()
        real_unlink = cctv_service.unlink_ap

        def broken_unlink(*a, **kw):
            raise RuntimeError("harness: Firestore unavailable")
        cctv_service.unlink_ap = broken_unlink
        r, _ = delete(ap_id)
        cctv_service.unlink_ap = real_unlink
        still = aps_col.document(ap_id).get().exists
        check(5, "a failure before the delete (the camera unlink) -> 500, and the AP is still there",
              r.status_code == 500 and still, f"status={r.status_code} ap_still_there={still}")
        delete(ap_id)

        # 6: DIAGNOSE 8's cases
        outcomes = {}

        ap_id, mac = place()
        floor_ref.update({"patrol_enabled": True, "patrol_route": seeded + [ap_id]})
        r, lines = delete(ap_id)
        outcomes["route"] = (r.status_code, (floor_ref.get().to_dict() or {}).get("patrol_route") == seeded
                             and db.reference(hb_key(mac)).get() is None, lines)
        floor_ref.update({"patrol_enabled": False, "patrol_route": []})

        ap_id, mac = place()
        add_camera("cam-142-case", ap_id)
        r, lines = delete(ap_id)
        outcomes["camera"] = (r.status_code, camera_link("cam-142-case") is None
                              and db.reference(hb_key(mac)).get() is None, lines)

        for mode, mod in (("patrol", spa), ("events", sev)):
            ap_id, mac = place()
            with contextlib.redirect_stdout(io.StringIO()):
                started = client.post(f"/simulation/start?mode={mode}", headers=ADMIN).status_code
                loaded = wait_until(lambda: any(a.get("id") == ap_id for a in mod._floor_aps))
                time.sleep(0.2)
                r, lines = delete(ap_id)
                time.sleep(0.2)
                dropped = not any(a.get("id") == ap_id for a in mod._floor_aps)
                task = sroutes._task
                alive = task is not None and not task.done()
                stopped = client.post("/simulation/stop", headers=ADMIN).status_code
            outcomes[f"simulation ({mode})"] = (r.status_code, started == 200 and loaded and dropped and alive
                                                and stopped == 200 and not aps_col.document(ap_id).get().exists,
                                                lines)

        ap_id, mac = place(heartbeat=False)
        r, lines = delete(ap_id)
        outcomes["no heartbeat"] = (r.status_code, not aps_col.document(ap_id).get().exists, lines)

        check(6, "DIAGNOSE 8's cases: route, camera, running simulation (patrol, events), no heartbeat",
              all(st == 200 and ok and not lines for st, ok, lines in outcomes.values()), f"{outcomes}")

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
