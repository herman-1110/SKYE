"""In-process checks for Prompt 142, D1.1-D1.5: several floors active at once,
each AP (by MAC) on at most one of them.

The seeded floor (T128 Level, active, AP1-AP3) plus five more, all inactive
to start: Backup (same building), Annex (a second building), Empty (no APs,
not calibrated), Spare (calibrated, no APs) and Annex 2 (second building).

  1  a floor with no APs and no calibration activates; T128 Level stays active
  2  AP1 can be placed on Backup (inactive), although T128 Level holds it
  3  activating Backup -> 409; the body lists T128 Level, its building and
     AP1 as {name, mac}; Backup stays inactive
  4  across buildings: AP2 placed on Annex; activating Annex -> 409 listing
     T128 Level (building T128 Test Building) and AP2 only
  5  placing on an active floor that clashes -> 409, one sentence naming the
     other floor and its building; nothing saved
  6  two conflicts at once: the 409 lists both floors, the sentence says 2
  7  deactivate T128 Level, then activate Backup -> 200; Empty and Spare stay
     active (several active floors)
  8  one placement per floor, as before: the same MAC twice on Backup -> 409
  9  activating an active floor is a no-op (200); an unknown floor -> 404
 10  swap back: deactivate Backup, activate T128 Level; no MAC is on two
     active floors at the end

On the base (3ab8adc) activation switches the building's other floors off and
a second placement of a MAC gets 409, so most checks fail.

usage (Git Bash, repo root):
  "$py" -B tools/harness/f142_active_floors_inprocess.py --backend-dir "$exp/backend"

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
results = []

B2 = "b-142-second"
BACKUP, ANNEX, EMPTY, SPARE, ANNEX2 = "f-142-backup", "f-142-annex", "f-142-empty", "f-142-spare", "f-142-annex2"
X_MAC = "AA:BB:CC:00:14:2A"


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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "f142_active_floors_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-f142a-default-rtdb.firebaseio.com",
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

    # A server error comes back as a 500 rather than raising here, so the base
    # (where activating an unknown floor is a 500) still reports every check.
    client = TestClient(main.app, raise_server_exceptions=False)
    fs = firestore.client()
    seeded_floor = (fs.collection("buildings").document(C.BUILDING_ID)
                    .collection("floors").document(C.FLOOR_ID).get().to_dict())
    fs.collection("buildings").document(B2).set({
        "id": B2, "name": "T142 Second Building", "description": "", "user_id": "harness-owner",
        "created_at": seeded_floor["uploaded_at"]})

    def floor_ref(b, f):
        return fs.collection("buildings").document(b).collection("floors").document(f)

    def add_floor(b, f, name, calibrated=True):
        # The seeded floor's full shape (FloorRecord's fields), inactive.
        doc = dict(seeded_floor, id=f, building_id=b, name=name, is_active=False,
                   storage_path="", url=f"harness://{f}.png")
        if not calibrated:
            doc["scale_pixels_per_meter"] = None
        floor_ref(b, f).set(doc)

    add_floor(C.BUILDING_ID, BACKUP, "T142 Backup")
    add_floor(B2, ANNEX, "T142 Annex")
    add_floor(C.BUILDING_ID, EMPTY, "T142 Empty", calibrated=False)
    add_floor(C.BUILDING_ID, SPARE, "T142 Spare")
    add_floor(B2, ANNEX2, "T142 Annex 2")

    def active(b, f):
        return bool((floor_ref(b, f).get().to_dict() or {}).get("is_active"))

    def activate(b, f):
        return client.patch(f"/buildings/{b}/floors/{f}/activate", headers=ADMIN)

    def deactivate(b, f):
        return client.patch(f"/buildings/{b}/floors/{f}/deactivate", headers=ADMIN)

    def place(b, f, mac, name="AP"):
        return client.post(f"/buildings/{b}/floors/{f}/aps", headers=ADMIN,
                           json={"name": name, "mac": mac, "x_pct": 0.3, "y_pct": 0.4})

    def macs_on(b, f):
        return sorted(d.to_dict()["mac"] for d in floor_ref(b, f).collection("access_points").stream())

    def detail(r):
        try:
            return r.json().get("detail")
        except Exception:
            return r.text[:200]

    AP1, AP2, AP3 = (C.AP_BY_INDEX[i] for i in (1, 2, 3))
    B1, F1 = C.BUILDING_ID, C.FLOOR_ID

    # 1
    r = activate(B1, EMPTY)
    check(1, "a floor with no APs and no calibration activates; T128 Level stays active",
          r.status_code == 200 and active(B1, EMPTY) and active(B1, F1),
          f"status={r.status_code} empty_active={active(B1, EMPTY)} t128_active={active(B1, F1)}")

    # 2
    r = place(B1, BACKUP, AP1["mac"], "Backup AP1")
    check(2, "AP1 can be placed on Backup (inactive) although T128 Level holds it",
          r.status_code == 200 and macs_on(B1, BACKUP) == [AP1["mac"]],
          f"status={r.status_code} detail={detail(r) if r.status_code != 200 else ''} backup={macs_on(B1, BACKUP)}")

    # 3
    r = activate(B1, BACKUP)
    d = detail(r)
    want = [{"floor_id": F1, "floor_name": "T128 Level", "building_id": B1, "building_name": "T128 Test Building",
             "aps": [{"name": AP1["doc_name"], "mac": AP1["mac"]}]}]
    ok = (r.status_code == 409 and isinstance(d, dict) and isinstance(d.get("message"), str)
          and "T128 Level" in d["message"] and d.get("conflicts") == want)
    check(3, "activating Backup -> 409 listing T128 Level, its building and AP1; Backup stays inactive",
          ok and not active(B1, BACKUP) and active(B1, F1),
          f"status={r.status_code} detail={d} backup_active={active(B1, BACKUP)}")

    # 4
    r_place = place(B2, ANNEX, AP2["mac"], "Annex AP2")
    r = activate(B2, ANNEX)
    d = detail(r)
    want = [{"floor_id": F1, "floor_name": "T128 Level", "building_id": B1, "building_name": "T128 Test Building",
             "aps": [{"name": AP2["doc_name"], "mac": AP2["mac"]}]}]
    check(4, "across buildings: AP2 placed on Annex; activating Annex -> 409 listing T128 Level and AP2 only",
          r_place.status_code == 200 and r.status_code == 409 and isinstance(d, dict)
          and d.get("conflicts") == want and not active(B2, ANNEX),
          f"place={r_place.status_code} activate={r.status_code} detail={d}")

    # 5
    r_act = activate(B1, SPARE)
    r = place(B1, SPARE, AP3["mac"], "Spare AP3")
    d = detail(r)
    check(5, "placing on an active floor that clashes -> 409, one sentence naming the floor and its building",
          r_act.status_code == 200 and r.status_code == 409 and isinstance(d, str)
          and "T128 Level" in d and "T128 Test Building" in d and macs_on(B1, SPARE) == [],
          f"activate={r_act.status_code} place={r.status_code} detail={d!r} spare={macs_on(B1, SPARE)}")

    # 6
    steps = [place(B2, ANNEX2, AP1["mac"], "Annex2 AP1").status_code,
             place(B1, SPARE, X_MAC, "Spare X").status_code,
             place(B2, ANNEX2, X_MAC, "Annex2 X").status_code]
    r = activate(B2, ANNEX2)
    d = detail(r)
    conflicts = d.get("conflicts") if isinstance(d, dict) else None
    got = sorted((c["floor_id"], tuple(a["mac"] for a in c["aps"])) for c in conflicts or [])
    check(6, "two conflicts at once: the 409 lists both floors; the sentence says 2",
          steps == [200, 200, 200] and r.status_code == 409
          and got == sorted([(F1, (AP1["mac"],)), (SPARE, (X_MAC,))])
          and "2 active floors" in (d.get("message") or ""),
          f"placements={steps} status={r.status_code} conflicts={got} message={(d or {}).get('message') if isinstance(d, dict) else d}")

    # 7
    r_off = deactivate(B1, F1)
    r = activate(B1, BACKUP)
    check(7, "deactivate T128 Level, then activate Backup -> 200; Empty and Spare stay active",
          r_off.status_code == 200 and r.status_code == 200 and active(B1, BACKUP) and not active(B1, F1)
          and active(B1, EMPTY) and active(B1, SPARE),
          f"deactivate={r_off.status_code} activate={r.status_code} detail={detail(r) if r.status_code != 200 else ''} "
          f"backup={active(B1, BACKUP)} t128={active(B1, F1)} empty={active(B1, EMPTY)} spare={active(B1, SPARE)}")

    # 8
    r = place(B1, BACKUP, AP1["mac"], "Backup AP1 again")
    d = detail(r)
    check(8, "one placement per floor: the same MAC twice on Backup -> 409 (already on this floor)",
          r.status_code == 409 and isinstance(d, str) and "already exists on this floor" in d
          and macs_on(B1, BACKUP) == [AP1["mac"]],
          f"status={r.status_code} detail={d!r}")

    # 9
    r_again = activate(B1, BACKUP)
    r_unknown = activate(B1, "no-such-floor")
    check(9, "activating an active floor is a no-op (200); an unknown floor -> 404",
          r_again.status_code == 200 and active(B1, BACKUP) and r_unknown.status_code == 404,
          f"again={r_again.status_code} unknown={r_unknown.status_code}")

    # 10
    r_off = deactivate(B1, BACKUP)
    r_on = activate(B1, F1)
    everywhere = {}
    for b in (B1, B2):
        for f_doc in fs.collection("buildings").document(b).collection("floors").stream():
            fd = f_doc.to_dict()
            if fd.get("is_active"):
                for m in macs_on(b, fd["id"]):
                    everywhere.setdefault(m, []).append(fd["id"])
    doubled = {m: fl for m, fl in everywhere.items() if len(fl) > 1}
    check(10, "swap back: T128 Level active, Backup inactive; no MAC on two active floors",
          r_off.status_code == 200 and r_on.status_code == 200 and active(B1, F1) and not active(B1, BACKUP)
          and not doubled,
          f"deactivate={r_off.status_code} activate={r_on.status_code} doubled={doubled}")

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
