"""In-process checks for Prompt 142, D3: Recalibrate remembers the last
calibration, and zones stay where they're drawn.

The seeded floor (T128 Level, 50 px/m, 1000 x 800 px, AP1-AP3) with two
zones, plus Fresh, a floor never calibrated, with one zone.

  1  a scale sent with the two points and the distance -> 200; the floor
     stores {a, b, distance_m, calibrated_at}
  2  the zones' metres are multiplied by old / new px/m (50 / 40), so each
     zone's rectangle on the image (metres x px/m) doesn't move
  3  the APs are re-derived from their image fractions, as before
  4  a bad calibration -> 422 with one sentence, and nothing changes: a
     point off the image, A equal to B, a distance of 0, a distance over
     10,000 m, the points without the distance
  5  a scale sent alone -> the stored calibration is cleared (and the zones
     follow the new scale, 40 / 45)
  6  a first calibration (Fresh, no old scale) leaves its zone alone
  7  saving the same scale again leaves the zones alone; a 10,000 m distance
     is accepted

On the base (3ab8adc) the scale request ignores the points and the
distance, so nothing is stored or checked, and the zones never change.

usage (Git Bash, repo root):
  "$py" -B tools/harness/f142_calibration_inprocess.py --backend-dir "$exp/backend"

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
FRESH = "f-142-fresh"
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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "f142_calibration_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-f142c-default-rtdb.firebaseio.com",
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
    from firebase_admin import firestore

    client = TestClient(main.app, raise_server_exceptions=False)
    fs = firestore.client()
    B1, F1 = C.BUILDING_ID, C.FLOOR_ID

    def floor_ref(f):
        return fs.collection("buildings").document(B1).collection("floors").document(f)

    seeded_floor = floor_ref(F1).get().to_dict()
    floor_ref(FRESH).set(dict(seeded_floor, id=FRESH, name="T142 Fresh", is_active=False, storage_path="",
                              url="harness://fresh.png", scale_pixels_per_meter=None))

    def add_zone(f, zone_id, x_min, x_max, y_min, y_max):
        floor_ref(f).collection("zones").document(zone_id).set({
            "id": zone_id, "floor_id": f, "name": zone_id, "color": "#ef444433", "is_high_risk": False,
            "x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max,
            "created_at": seeded_floor["uploaded_at"], "created_by": "harness-owner", "risk_level": "moderate"})

    add_zone(F1, "zone-142-a", 2.0, 6.0, 1.0, 4.0)
    add_zone(F1, "zone-142-b", 10.5, 18.25, 7.0, 15.5)
    add_zone(FRESH, "zone-142-fresh", 3.0, 5.0, 3.0, 5.0)

    def zones(f):
        return {d.id: {k: d.to_dict()[k] for k in ("x_min", "x_max", "y_min", "y_max")}
                for d in floor_ref(f).collection("zones").stream()}

    def floor(f):
        return floor_ref(f).get().to_dict() or {}

    def scale(f, px_per_m, calibration=None):
        body = {"scale_pixels_per_meter": px_per_m}
        if calibration is not None:
            body["calibration"] = calibration
        return client.patch(f"/buildings/{B1}/floors/{f}/scale", headers=ADMIN, json=body)

    def detail(r):
        try:
            return r.json().get("detail")
        except Exception:
            return r.text[:200]

    def pixels(z, px_per_m):
        return {k: round(v * px_per_m, 6) for k, v in z.items()}

    CAL = {"a": {"x_pct": 0.1, "y_pct": 0.2}, "b": {"x_pct": 0.6, "y_pct": 0.2}, "distance_m": 12.5}
    zones_before = zones(F1)

    # 1
    r = scale(F1, 40.0, CAL)
    f1 = floor(F1)
    cal = f1.get("calibration") or {}
    check(1, "a scale sent with the points and the distance -> 200; the floor stores them",
          r.status_code == 200 and f1.get("scale_pixels_per_meter") == 40.0
          and cal.get("a") == CAL["a"] and cal.get("b") == CAL["b"] and cal.get("distance_m") == 12.5
          and isinstance(cal.get("calibrated_at"), str),
          f"status={r.status_code} scale={f1.get('scale_pixels_per_meter')} calibration={f1.get('calibration')}")

    # 2
    zones_after = zones(F1)
    want = {zid: {k: round(v * (50.0 / 40.0), 4) for k, v in z.items()} for zid, z in zones_before.items()}
    same_pixels = all(pixels(zones_after[zid], 40.0) == pixels(zones_before[zid], 50.0) for zid in zones_before)
    check(2, "zones multiplied by old / new (50 / 40): each stays on the same spot of the image",
          zones_after == want and same_pixels, f"before={zones_before} after={zones_after}")

    # 3
    aps = {d.id: d.to_dict() for d in floor_ref(F1).collection("access_points").stream()}
    rederived = all(abs(a["x_m"] - a["x_pct"] * C.IMAGE_W_PX / 40.0) < 1e-3
                    and abs(a["y_m"] - a["y_pct"] * C.IMAGE_H_PX / 40.0) < 1e-3 for a in aps.values())
    check(3, "the APs are re-derived from their image fractions, as before", len(aps) == 3 and rederived,
          f"{[(a['x_m'], a['y_m']) for a in aps.values()]}")

    # 4
    bad = {
        "a point off the image": {**CAL, "b": {"x_pct": 1.2, "y_pct": 0.2}},
        "A equal to B": {**CAL, "b": dict(CAL["a"])},
        "a distance of 0": {**CAL, "distance_m": 0},
        "a distance over 10,000 m": {**CAL, "distance_m": 10000.5},
        "the points without the distance": {"a": CAL["a"], "b": CAL["b"]},
    }
    snapshot = (floor(F1), zones(F1))
    outcomes = {}
    for label, body in bad.items():
        r = scale(F1, 33.0, body)
        d = detail(r)
        outcomes[label] = (r.status_code, d if isinstance(d, str) else repr(d))
    one_sentence = all(st == 422 and isinstance(d, str) and d.endswith(".") and d.count(". ") == 0
                       for st, d in outcomes.values())
    check(4, "a bad calibration -> 422 with one sentence, and nothing changes",
          one_sentence and (floor(F1), zones(F1)) == snapshot, f"{outcomes}")

    # 5
    before5 = zones(F1)
    r = scale(F1, 45.0)
    f5 = floor(F1)
    want5 = {zid: {k: round(v * (40.0 / 45.0), 4) for k, v in z.items()} for zid, z in before5.items()}
    check(5, "a scale sent alone clears the stored calibration (zones follow 40 / 45)",
          r.status_code == 200 and f5.get("scale_pixels_per_meter") == 45.0 and f5.get("calibration") is None
          and zones(F1) == want5,
          f"status={r.status_code} calibration={f5.get('calibration')} zones={zones(F1)}")

    # 6
    fresh_before = zones(FRESH)
    r = scale(FRESH, 50.0, CAL)
    check(6, "a first calibration (no old scale) leaves the zones alone",
          r.status_code == 200 and zones(FRESH) == fresh_before and floor(FRESH).get("scale_pixels_per_meter") == 50.0,
          f"status={r.status_code} zones={zones(FRESH)}")

    # 7
    before7 = zones(F1)
    r = scale(F1, 45.0, {**CAL, "distance_m": 10000})
    f7 = floor(F1)
    check(7, "the same scale again leaves the zones alone; a 10,000 m distance is accepted",
          r.status_code == 200 and zones(F1) == before7 and (f7.get("calibration") or {}).get("distance_m") == 10000,
          f"status={r.status_code} detail={detail(r) if r.status_code != 200 else ''} zones_same={zones(F1) == before7}")

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
