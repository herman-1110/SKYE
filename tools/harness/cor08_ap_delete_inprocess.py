"""In-process checks for COR-08 (Prompt 135): deleting an AP that is on the
patrol route works.

  1  DELETE a route AP -> 200; the AP is gone; the route loses only that AP;
     patrol_enabled and patrol_interval_minutes are unchanged
  2  the route update touches only patrol_route and happens before the AP is
     deleted (read from the fake Firestore's op log)
  3  the existing clean-up still runs: the AP's heartbeat is removed and a
     camera covering it is unlinked
  4  deleting an AP that isn't on the route leaves the floor document alone
  5  an unknown AP id -> 200 and nothing changes (unchanged behaviour)

usage (Git Bash, repo root):
  "$py" -B tools/harness/cor08_ap_delete_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import json
import os
import sys

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

ADMIN = {"Authorization": "Bearer harness-token:harness-owner"}
BASE = f"/buildings/{C.BUILDING_ID}/floors/{C.FLOOR_ID}"
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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "cor08_ap_delete_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-cor08-default-rtdb.firebaseio.com",
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

    client = TestClient(main.app)
    fs = firestore.client()
    floor_ref = fs.collection("buildings").document(C.BUILDING_ID).collection("floors").document(C.FLOOR_ID)
    aps_col = floor_ref.collection("access_points")
    ap1, ap2, ap3 = (a["id"] for a in C.APS)
    ap2_mac = C.AP_BY_INDEX[2]["mac"]
    floor_ref.update({"patrol_enabled": True, "patrol_route": [ap1, ap2, ap3], "patrol_interval_minutes": 7})
    db.reference(f"/ap_heartbeats/{ap2_mac.replace(':', '_')}").set({"mac": ap2_mac, "last_seen": 1})
    floor_ref.collection("cctvs").document("cam-cor08").set({
        "id": "cam-cor08", "floor_id": C.FLOOR_ID, "building_id": C.BUILDING_ID, "name": "Cam", "x_pct": 0.5,
        "y_pct": 0.5, "created_at": "2026-10-12T00:00:00+00:00", "checkpoint_ap_id": ap2})
    ops_path = os.path.join(run_dir, "firestore_ops.jsonl")

    def ops_since(mark):
        with open(ops_path, encoding="utf-8") as f:
            return [json.loads(ln) for ln in f.read().splitlines()[mark:] if ln.strip()]

    def ops_count():
        with open(ops_path, encoding="utf-8") as f:
            return len(f.read().splitlines())

    floor_path = floor_ref.path if isinstance(floor_ref.path, str) else "/".join(floor_ref.path)

    # 1
    mark = ops_count()
    r = client.delete(f"{BASE}/aps/{ap2}", headers=ADMIN)
    floor = floor_ref.get().to_dict() or {}
    gone = not aps_col.document(ap2).get().exists
    check(1, "DELETE a route AP -> 200; the AP is gone; route loses only it; other patrol fields unchanged",
          r.status_code == 200 and gone and floor.get("patrol_route") == [ap1, ap3]
          and floor.get("patrol_enabled") is True and floor.get("patrol_interval_minutes") == 7,
          f"status={r.status_code} gone={gone} route={floor.get('patrol_route')} enabled={floor.get('patrol_enabled')} "
          f"interval={floor.get('patrol_interval_minutes')}")

    # 2
    ops = ops_since(mark)
    floor_updates = [i for i, o in enumerate(ops) if o.get("op") == "doc.update" and o.get("path") == floor_path]
    ap_deletes = [i for i, o in enumerate(ops) if o.get("op") == "doc.delete" and str(o.get("path", "")).endswith(f"access_points/{ap2}")]
    only_route = len(floor_updates) == 1 and set(ops[floor_updates[0]].get("value", {})) == {"patrol_route"}
    check(2, "the route update touches only patrol_route and comes before the AP's delete",
          only_route and ap_deletes and floor_updates[0] < ap_deletes[0],
          f"floor_updates={[ops[i].get('value') for i in floor_updates]} order={floor_updates}<{ap_deletes}")

    # 3
    hb = db.reference(f"/ap_heartbeats/{ap2_mac.replace(':', '_')}").get()
    cam = floor_ref.collection("cctvs").document("cam-cor08").get().to_dict() or {}
    check(3, "existing clean-up still runs: heartbeat removed, covering camera unlinked",
          hb is None and cam.get("checkpoint_ap_id") is None, f"heartbeat={hb} camera_checkpoint={cam.get('checkpoint_ap_id')}")

    # 4
    aps_col.document("ap-cor08-extra").set({
        "id": "ap-cor08-extra", "floor_id": C.FLOOR_ID, "building_id": C.BUILDING_ID, "name": "Extra",
        "mac": "AA:BB:CC:00:08:01", "x_pct": 0.1, "y_pct": 0.1, "created_at": "2026-10-12T00:00:00+00:00",
        "x_m": 2.0, "y_m": 1.6})
    mark = ops_count()
    r4 = client.delete(f"{BASE}/aps/ap-cor08-extra", headers=ADMIN)
    touched = [o for o in ops_since(mark) if o.get("op") in ("doc.update", "doc.set") and o.get("path") == floor_path]
    floor = floor_ref.get().to_dict() or {}
    check(4, "deleting an AP that isn't on the route leaves the floor document alone",
          r4.status_code == 200 and not touched and floor.get("patrol_route") == [ap1, ap3]
          and not aps_col.document("ap-cor08-extra").get().exists,
          f"status={r4.status_code} floor_writes={len(touched)} route={floor.get('patrol_route')}")

    # 5
    r5 = client.delete(f"{BASE}/aps/no-such-ap", headers=ADMIN)
    floor = floor_ref.get().to_dict() or {}
    check(5, "an unknown AP id -> 200 and nothing changes",
          r5.status_code == 200 and floor.get("patrol_route") == [ap1, ap3] and aps_col.document(ap1).get().exists,
          f"status={r5.status_code} route={floor.get('patrol_route')}")

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
