"""In-process checks for Prompt 142, D1.6, D1.8 and D1.9: the Omada ingest
resolves an AP to its placement on an active floor; deleting one placement of
an AP that another floor still holds keeps its heartbeat and leaves the
simulators alone.

The seeded floor (T128 Level, f-t128, active, AP1-AP3) plus Backup
(f-142-backup, inactive: its id sorts before f-t128) holding AP1-AP3 at other
spots and AP4, which no other floor has. The ingest's monotonic clock is
frozen, so its 30 s cache never expires by itself: only the invalidation can
make a change show.

  1  AP1 (on T128 Level and Backup) resolves to T128 Level, the active one
  2  AP4, placed only on Backup (inactive), is "online, not placed"
  3  activation takes effect without the 30 s wait, both ways: Backup on ->
     AP1 resolves there and AP4 is placed; T128 Level back -> AP1 there
     again and AP4 not placed
  4  moving an AP takes effect at once (its new metres)
  5  placing an AP takes effect at once (AP5, reporting unplaced, then placed)
  6  deleting Backup's AP2 keeps AP2's heartbeat; AP2 still resolves
  7  deleting Backup's AP3 leaves the simulators' AP lists alone
  8  deleting AP4, its last placement, removes its heartbeat
  9  deleting a floor keeps the heartbeat of an AP another floor still
     holds, and removes the one only it held
 10  deleting T128 Level's AP3 takes it out of the simulators (by id)

On the base (3ab8adc) the ingest takes the lowest floor_id whatever its
state, every delete removes the MAC's heartbeat, and the simulators match by
MAC.

usage (Git Bash, repo root):
  "$py" -B tools/harness/f142_ap_resolution_inprocess.py --backend-dir "$exp/backend"

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

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

ADMIN = {"Authorization": "Bearer harness-token:harness-owner"}
BACKUP = "f-142-backup"
GONE = "f-142-gone"
AP4_MAC, AP5_MAC, AP6_MAC = "AA:BB:CC:00:14:04", "AA:BB:CC:00:14:05", "AA:BB:CC:00:14:06"
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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "f142_ap_resolution_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-f142r-default-rtdb.firebaseio.com",
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
    import services.omada_ingest_service as OIS
    from fastapi.testclient import TestClient
    from firebase_admin import db, firestore
    from services import simulation_events as sev
    from services import simulation_patrol as spa

    # Frozen monotonic clock: the ingest's 30 s TTLs never run out here.
    fake_time = types.SimpleNamespace(**{k: getattr(_real_time, k) for k in dir(_real_time) if not k.startswith("__")})
    fake_time.monotonic = lambda: 1000.0
    OIS.time = fake_time
    ingest = OIS.omada_ingest_service

    client = TestClient(main.app)
    fs = firestore.client()
    B1, F1 = C.BUILDING_ID, C.FLOOR_ID
    AP1, AP2, AP3 = (C.AP_BY_INDEX[i] for i in (1, 2, 3))

    def floor_ref(f):
        return fs.collection("buildings").document(B1).collection("floors").document(f)

    seeded_floor = floor_ref(F1).get().to_dict()

    def add_floor(f, name):
        floor_ref(f).set(dict(seeded_floor, id=f, name=name, is_active=False, storage_path="", url=f"harness://{f}.png"))

    def add_ap(f, ap_id, mac, x_m, y_m, name):
        floor_ref(f).collection("access_points").document(ap_id).set({
            "id": ap_id, "floor_id": f, "building_id": B1, "name": name, "mac": mac,
            "x_pct": x_m * C.SCALE_PX_PER_M / C.IMAGE_W_PX, "y_pct": y_m * C.SCALE_PX_PER_M / C.IMAGE_H_PX,
            "created_at": seeded_floor["uploaded_at"], "x_m": x_m, "y_m": y_m})

    # Backup: the same three APs at other spots, plus AP4 (only here).
    add_floor(BACKUP, "T142 Backup")
    for i, a in enumerate((AP1, AP2, AP3), start=1):
        add_ap(BACKUP, f"ap-142-b{i}", a["mac"], a["x_m"] + 1.0, a["y_m"] + 1.0, f"Backup AP{i}")
    add_ap(BACKUP, "ap-142-b4", AP4_MAC, 10.0, 10.0, "Backup AP4")

    def hb_key(mac):
        return f"/ap_heartbeats/{mac.replace(':', '_')}"

    for mac in (AP1["mac"], AP2["mac"], AP3["mac"], AP4_MAC):
        db.reference(hb_key(mac)).set({"mac": mac, "last_seen": int(_real_time.time())})

    def report(mac):
        """One AP report through the real ingest (no beacons heard)."""
        with contextlib.redirect_stdout(io.StringIO()):
            return ingest.ingest({"reporter": {"mac": mac.replace(":", ""), "name": "T142"}, "reported": []})

    def where(mac):
        got = ingest._get_ap_coords(mac)
        return (got[2], round(got[0], 3), round(got[1], 3)) if got else None

    def activate(f):
        return client.patch(f"/buildings/{B1}/floors/{f}/activate", headers=ADMIN).status_code

    def deactivate(f):
        return client.patch(f"/buildings/{B1}/floors/{f}/deactivate", headers=ADMIN).status_code

    def delete_ap(f, ap_id):
        return client.delete(f"/buildings/{B1}/floors/{f}/aps/{ap_id}", headers=ADMIN).status_code

    # 1
    w1 = where(AP1["mac"])
    check(1, "AP1 (on T128 Level and Backup) resolves to T128 Level, the active one",
          w1 == (F1, AP1["x_m"], AP1["y_m"]), f"resolved={w1}")

    # 2
    r2 = report(AP4_MAC)
    check(2, "AP4, placed only on Backup (inactive), is online, not placed",
          r2.get("status") == "online_unregistered" and db.reference(hb_key(AP4_MAC)).get() is not None,
          f"response={r2}")

    # 3
    steps = [deactivate(F1), activate(BACKUP)]
    w_b, r_b = where(AP1["mac"]), report(AP4_MAC)
    steps += [deactivate(BACKUP), activate(F1)]
    w_f, r_f = where(AP1["mac"]), report(AP4_MAC)
    check(3, "activation takes effect at once, both ways (frozen 30 s cache)",
          steps == [200, 200, 200, 200] and w_b == (BACKUP, AP1["x_m"] + 1.0, AP1["y_m"] + 1.0)
          and r_b.get("status") == "ok" and w_f == (F1, AP1["x_m"], AP1["y_m"])
          and r_f.get("status") == "online_unregistered",
          f"steps={steps} backup_on={w_b},{r_b.get('status')} t128_back={w_f},{r_f.get('status')}")

    # 4
    r4 = client.patch(f"/buildings/{B1}/floors/{F1}/aps/{AP1['id']}/position", headers=ADMIN,
                      json={"x_pct": 0.5, "y_pct": 0.5})
    w4 = where(AP1["mac"])
    want4 = (F1, 0.5 * C.IMAGE_W_PX / C.SCALE_PX_PER_M, 0.5 * C.IMAGE_H_PX / C.SCALE_PX_PER_M)
    check(4, "moving an AP takes effect at once", r4.status_code == 200 and w4 == want4,
          f"status={r4.status_code} resolved={w4} want={want4}")

    # 5
    before = report(AP5_MAC)
    r5 = client.post(f"/buildings/{B1}/floors/{F1}/aps", headers=ADMIN,
                     json={"name": "T142 AP5", "mac": AP5_MAC, "x_pct": 0.2, "y_pct": 0.2})
    after = report(AP5_MAC)
    check(5, "placing an AP takes effect at once",
          before.get("status") == "online_unregistered" and r5.status_code == 200 and after.get("status") == "ok",
          f"before={before.get('status')} place={r5.status_code} after={after.get('status')}")

    # 6
    s6 = delete_ap(BACKUP, "ap-142-b2")
    hb6 = db.reference(hb_key(AP2["mac"])).get()
    w6 = where(AP2["mac"])
    check(6, "deleting Backup's AP2 keeps AP2's heartbeat; AP2 still resolves to T128 Level",
          s6 == 200 and hb6 is not None and w6 is not None and w6[0] == F1,
          f"status={s6} heartbeat={hb6} resolved={w6}")

    # 7: the simulators as a run on T128 Level would have loaded them
    loaded = [{"id": a["id"], "mac": a["mac"], "name": a["doc_name"], "x_m": a["x_m"], "y_m": a["y_m"]}
              for a in (AP1, AP2, AP3)]
    spa._floor_aps = [dict(a) for a in loaded]
    sev._floor_aps = [dict(a) for a in loaded]
    for m in (spa, sev):
        for beacon in m.SIMULATED_BEACONS:
            beacon["ap_order"] = [0, 1, 2]
    s7 = delete_ap(BACKUP, "ap-142-b3")
    ids = [[a["id"] for a in m._floor_aps] for m in (spa, sev)]
    want7 = [a["id"] for a in loaded]
    check(7, "deleting Backup's AP3 leaves the simulators' AP lists alone",
          s7 == 200 and ids == [want7, want7] and db.reference(hb_key(AP3["mac"])).get() is not None,
          f"status={s7} patrol={ids[0]} events={ids[1]}")

    # 8
    s8 = delete_ap(BACKUP, "ap-142-b4")
    check(8, "deleting AP4, its last placement, removes its heartbeat",
          s8 == 200 and db.reference(hb_key(AP4_MAC)).get() is None, f"status={s8}")

    # 9
    add_floor(GONE, "T142 To Delete")
    add_ap(GONE, "ap-142-g1", AP1["mac"], 3.0, 3.0, "Gone AP1")
    add_ap(GONE, "ap-142-g6", AP6_MAC, 4.0, 4.0, "Gone AP6")
    db.reference(hb_key(AP6_MAC)).set({"mac": AP6_MAC, "last_seen": int(_real_time.time())})
    s9 = client.delete(f"/buildings/{B1}/floors/{GONE}", headers=ADMIN).status_code
    hb_ap1, hb_ap6 = db.reference(hb_key(AP1["mac"])).get(), db.reference(hb_key(AP6_MAC)).get()
    check(9, "deleting a floor keeps the heartbeat of an AP another floor holds, removes the one only it held",
          s9 == 200 and hb_ap1 is not None and hb_ap6 is None and not floor_ref(GONE).get().exists,
          f"status={s9} ap1_heartbeat={hb_ap1 is not None} ap6_heartbeat={hb_ap6 is not None}")

    # 10
    s10 = delete_ap(F1, AP3["id"])
    ids = [[a["id"] for a in m._floor_aps] for m in (spa, sev)]
    want10 = [AP1["id"], AP2["id"]]
    check(10, "deleting T128 Level's AP3 takes it out of the simulators (by id)",
          s10 == 200 and ids == [want10, want10], f"status={s10} patrol={ids[0]} events={ids[1]}")

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
