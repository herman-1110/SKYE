"""In-process checks for Prompt 143, D2.1-D2.2: which way a camera faces.

Cameras gain facing_deg (0 to under 360, clockwise from up on the floor plan,
None = not set) and fov_deg (10-360, 90 when a facing is set without it).
Each check reads the stored Firestore document as well as the response,
because the dashboard's maps read Firestore.

  1  create without a facing: both fields None, in the response and stored
  2  create with a facing and no field of view: the field of view is 90
  3  create with both: both kept
  4  set a facing on a camera that had none: the field of view becomes 90,
     and nothing else in the record changes
  5  change the facing of a camera with a field of view of 120: it stays 120
  6  change only the field of view: the facing stays
  7  fov_deg null on a camera with a facing: back to 90
  8  facing_deg null clears both, in the response and stored
  9  judgement calls: facing_deg null with a field of view still clears both;
     a field of view sent to a camera with no facing is ignored (stays None)
 10  out-of-range values get a 422 with one sentence, on create and update,
     and nothing is written
 11  NaN and Infinity (raw JSON bodies) get the same 422, and nothing is written
 12  GET .../cctvs (to_dict) returns both fields for every camera, including a
     record written before 143 (None, None)
 13  a direction-only edit leaves live view and health alone: go2rtc's config
     isn't rewritten and no health check is queued (an IP edit still queues one)

usage (Git Bash, repo root):
  "$py" -B tools/harness/f143_camera_direction_inprocess.py --backend-dir "$exp/backend"

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
JSON_ADMIN = {**ADMIN, "Content-Type": "application/json"}
BASE = f"/buildings/{C.BUILDING_ID}/floors/{C.FLOOR_ID}/cctvs"
OTHER_FIELDS = ("id", "name", "mac", "device_mac", "ip", "channel", "source_type", "checkpoint_ap_id",
                "x_pct", "y_pct", "created_at", "timezone", "floor_id", "building_id")
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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "f143_camera_direction_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_")):
            del os.environ[k]
    config_path = os.path.join(run_dir, "go2rtc.yaml")
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-f143cam-default-rtdb.firebaseio.com",
        "GEMINI_API_KEY": "harness-fake-gemini-key",
        "OMADA_ACCESS_TOKEN": "harness-fake-omada-token",
        "LLM_MODEL_NAME": "harness-fake-model",
        "VIGI_DISCOVERY_INTERVAL_S": "0",
        "GO2RTC_CONFIG_PATH": config_path,
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
    from firebase_admin import firestore

    import main
    from fastapi.testclient import TestClient
    import routes.floor_routes as floor_routes
    client = TestClient(main.app)

    # Count the health checks the routes queue, without running any.
    queued = []
    floor_routes.camera_health_service.check_now = lambda cam: queued.append(cam.id)

    col = firestore.client().collection("buildings").document(C.BUILDING_ID).collection("floors") \
        .document(C.FLOOR_ID).collection("cctvs")

    def stored(cam_id):
        return col.document(cam_id).get().to_dict() or {}

    def count():
        return len(list(col.stream()))

    def pair(d):
        return (d.get("facing_deg", "absent"), d.get("fov_deg", "absent"))

    def create(n, **extra):
        body = {"name": f"P143 cam {n}", "x_pct": 0.1 * n, "y_pct": 0.2, "mac": f"AA:BB:CC:14:3C:0{n}",
                "ip": f"127.0.0.3{n}", **extra}
        r = client.post(BASE, json=body, headers=ADMIN)
        return r, (r.json() if r.status_code == 200 else {})

    def patch(cam_id, body):
        r = client.patch(f"{BASE}/{cam_id}", json=body, headers=ADMIN)
        return r, (r.json() if r.status_code == 200 else {})

    def sentence(r):
        d = r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else None
        return isinstance(d, str) and d.endswith(".") and "\n" not in d

    # 1
    r1, b1 = create(1)
    cam1 = b1.get("id", "missing")
    check(1, "create without a facing: facing_deg and fov_deg None in the response and stored",
          r1.status_code == 200 and pair(b1) == (None, None) and pair(stored(cam1)) == (None, None),
          f"status={r1.status_code} response={pair(b1)} stored={pair(stored(cam1))}")

    # 2
    r2, b2 = create(2, facing_deg=135)
    cam2 = b2.get("id", "missing")
    check(2, "create with facing 135 and no field of view: 135 and 90",
          r2.status_code == 200 and pair(b2) == (135.0, 90.0) and pair(stored(cam2)) == (135.0, 90.0),
          f"status={r2.status_code} response={pair(b2)} stored={pair(stored(cam2))}")

    # 3
    r3, b3 = create(3, facing_deg=45, fov_deg=120)
    cam3 = b3.get("id", "missing")
    check(3, "create with facing 45 and field of view 120: both kept",
          r3.status_code == 200 and pair(b3) == (45.0, 120.0) and pair(stored(cam3)) == (45.0, 120.0),
          f"status={r3.status_code} response={pair(b3)} stored={pair(stored(cam3))}")

    # 4
    before1 = stored(cam1)
    r4, b4 = patch(cam1, {"facing_deg": 270})
    after1 = stored(cam1)
    same = [k for k in OTHER_FIELDS if after1.get(k) != before1.get(k)]
    check(4, "set facing 270 on a camera with none: field of view 90; nothing else in the record changes",
          r4.status_code == 200 and pair(b4) == (270.0, 90.0) and pair(after1) == (270.0, 90.0) and not same
          and before1.get("ip") == "127.0.0.31",
          f"status={r4.status_code} response={pair(b4)} stored={pair(after1)} changed={same}")

    # 5
    r5, b5 = patch(cam3, {"facing_deg": 300})
    check(5, "change the facing of a camera with field of view 120: it stays 120",
          r5.status_code == 200 and pair(b5) == (300.0, 120.0) and pair(stored(cam3)) == (300.0, 120.0),
          f"status={r5.status_code} response={pair(b5)} stored={pair(stored(cam3))}")

    # 6
    r6, b6 = patch(cam3, {"fov_deg": 60})
    check(6, "change only the field of view: the facing stays",
          r6.status_code == 200 and pair(b6) == (300.0, 60.0) and pair(stored(cam3)) == (300.0, 60.0),
          f"status={r6.status_code} response={pair(b6)} stored={pair(stored(cam3))}")

    # 7
    r7, b7 = patch(cam3, {"fov_deg": None})
    check(7, "fov_deg null on a camera with a facing: back to 90",
          r7.status_code == 200 and pair(b7) == (300.0, 90.0) and pair(stored(cam3)) == (300.0, 90.0),
          f"status={r7.status_code} response={pair(b7)} stored={pair(stored(cam3))}")

    # 8
    r8, b8 = patch(cam2, {"facing_deg": None})
    s8 = stored(cam2)
    check(8, "facing_deg null clears both, in the response and stored",
          r8.status_code == 200 and pair(b8) == (None, None) and pair(s8) == (None, None)
          and "facing_deg" in s8 and "fov_deg" in s8,
          f"status={r8.status_code} response={pair(b8)} stored={pair(s8)}")

    # 9
    r9a, b9a = patch(cam3, {"facing_deg": None, "fov_deg": 120})
    r9b, b9b = patch(cam2, {"fov_deg": 60})
    check(9, "judgement calls: facing null with a field of view clears both; a field of view alone, "
             "with no facing, is ignored",
          r9a.status_code == 200 and pair(b9a) == (None, None) and pair(stored(cam3)) == (None, None)
          and r9b.status_code == 200 and pair(b9b) == (None, None) and pair(stored(cam2)) == (None, None),
          f"a={r9a.status_code} {pair(stored(cam3))} b={r9b.status_code} {pair(stored(cam2))}")

    # 10
    patch(cam1, {"facing_deg": 10, "fov_deg": 45})
    n_before = count()
    keep1 = stored(cam1)
    bad_creates = [{"facing_deg": 360}, {"facing_deg": -1}, {"facing_deg": 720},
                   {"facing_deg": 90, "fov_deg": 9}, {"facing_deg": 90, "fov_deg": 361}, {"facing_deg": 90, "fov_deg": 0},
                   {"fov_deg": 400}]
    bad_updates = [{"facing_deg": 360.0}, {"facing_deg": -0.5}, {"fov_deg": 9.99}, {"fov_deg": 400},
                   {"facing_deg": 100, "fov_deg": 5}]
    rc = [create(4, **b)[0] for b in bad_creates]
    ru = [patch(cam1, b)[0] for b in bad_updates]
    codes = [r.status_code for r in rc + ru]
    details = sorted({r.json().get("detail") for r in rc + ru if sentence(r)})
    check(10, "out-of-range values: 422 with one sentence on create and update; nothing written",
          all(c == 422 for c in codes) and all(sentence(r) for r in rc + ru)
          and count() == n_before and stored(cam1) == keep1,
          f"codes={codes} sentences={details} cameras {n_before}->{count()}")

    # 11
    raw = []
    for text in ('NaN', 'Infinity', '-Infinity'):
        raw.append(client.post(BASE, content=(
            '{"name": "P143 nan", "x_pct": 0.5, "y_pct": 0.5, "facing_deg": %s}' % text).encode(), headers=JSON_ADMIN))
        raw.append(client.patch(f"{BASE}/{cam1}", content=('{"facing_deg": %s}' % text).encode(), headers=JSON_ADMIN))
        raw.append(client.patch(f"{BASE}/{cam1}", content=('{"fov_deg": %s}' % text).encode(), headers=JSON_ADMIN))
    check(11, "NaN and +/-Infinity in a raw JSON body: the same 422 sentence; nothing written",
          all(r.status_code == 422 and sentence(r) for r in raw) and count() == n_before and stored(cam1) == keep1,
          f"codes={[r.status_code for r in raw]} cameras {n_before}->{count()}")

    # 12
    col.document("cam-p143-old").set({
        "id": "cam-p143-old", "floor_id": C.FLOOR_ID, "building_id": C.BUILDING_ID, "name": "Before 143",
        "x_pct": 0.9, "y_pct": 0.9, "created_at": "2026-10-01T00:00:00+00:00", "mac": "AA:BB:CC:14:3C:09"})
    r12 = client.get(BASE, headers=ADMIN)
    listed = r12.json() if r12.status_code == 200 else []
    by_id = {c.get("id"): c for c in listed}
    check(12, "GET .../cctvs returns both fields for every camera, None for a record written before 143",
          r12.status_code == 200 and listed and all("facing_deg" in c and "fov_deg" in c for c in listed)
          and pair(by_id.get("cam-p143-old", {})) == (None, None) and pair(by_id.get(cam1, {})) == (10.0, 45.0),
          f"status={r12.status_code} cameras={len(listed)} old={pair(by_id.get('cam-p143-old', {}))} "
          f"cam1={pair(by_id.get(cam1, {}))}")

    # 13
    def config():
        try:
            with open(config_path, encoding="utf-8") as f:
                text = f.read()
            return text, os.stat(config_path).st_mtime_ns
        except FileNotFoundError:
            return None, None
    # Check 12 wrote a camera straight into Firestore, so bring the file up to
    # date with the registry first; from then on only a live-view change may
    # rewrite it.
    from services import live_view_service
    live_view_service.refresh_config()
    cfg_before = config()
    queued.clear()
    r13a, _ = patch(cam1, {"facing_deg": 200})
    r13b, _ = patch(cam1, {"fov_deg": 30})
    r13c, _ = patch(cam1, {"facing_deg": None})
    cfg_after = config()
    queued_direction = list(queued)
    r13d, _ = patch(cam1, {"ip": "127.0.0.39"})
    cfg_ip = config()
    check(13, "direction-only edits: go2rtc's config not rewritten, no health check queued; "
              "an IP edit still rewrites it and queues one",
          all(r.status_code == 200 for r in (r13a, r13b, r13c, r13d)) and cfg_before[0] is not None
          and cfg_after == cfg_before and queued_direction == [] and queued == [cam1]
          and cfg_ip[0] != cfg_before[0] and "127.0.0.39" in (cfg_ip[0] or ""),
          f"config same={cfg_after == cfg_before} queued by direction={queued_direction} after ip={len(queued)} "
          f"ip edit rewrote it={cfg_ip[0] != cfg_before[0]}")

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
