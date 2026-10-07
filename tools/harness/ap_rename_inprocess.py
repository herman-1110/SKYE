"""In-process checks for renaming an AP (PATCH /buildings/{b}/floors/{f}/aps/{id}).

  1  refused without auth and for a non-admin
  2  an admin renames a seeded AP: 200 with the new (trimmed) name, Firestore
     updated, MAC and coordinates unchanged
  3  a blank or over-long name -> 422 with a plain sentence; unknown AP -> 404;
     nothing written

usage (Git Bash, repo root):
  "$py" -B tools/harness/ap_rename_inprocess.py --backend-dir "$exp/backend"

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
USER = {"Authorization": "Bearer harness-token:harness-user"}
BASE = f"/buildings/{C.BUILDING_ID}/floors/{C.FLOOR_ID}/aps"
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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "ap_rename_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-aprename-default-rtdb.firebaseio.com",
        "GEMINI_API_KEY": "harness-fake-gemini-key",
        "OMADA_ACCESS_TOKEN": "harness-fake-omada-token",
        "LLM_MODEL_NAME": "harness-fake-model",
        "VIGI_DISCOVERY_INTERVAL_S": "0",
        "GO2RTC_CONFIG_PATH": os.path.join(run_dir, "go2rtc.yaml"),
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
    firestore.client().collection("users").document("harness-user").set({
        "uid": "harness-user", "email": "harness-user@example.invalid", "display_name": "Harness User",
        "role": "user", "status": "approved", "person_id": "", "created_at": "2026-10-07T00:00:00+00:00",
        "email_verified": True})

    import main
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    ap_id = C.APS[0]["id"]

    def doc(i):
        return firestore.client().collection("buildings").document(C.BUILDING_ID).collection("floors") \
            .document(C.FLOOR_ID).collection("access_points").document(i).get().to_dict() or {}

    before = doc(ap_id)

    # 1
    r_none = client.patch(f"{BASE}/{ap_id}", json={"name": "x"})
    r_user = client.patch(f"{BASE}/{ap_id}", json={"name": "x"}, headers=USER)
    check(1, "refused without auth and for a non-admin; nothing written",
          r_none.status_code in (401, 422) and r_user.status_code == 403 and doc(ap_id).get("name") == before.get("name"),
          f"none={r_none.status_code} user={r_user.status_code}")

    # 2
    r = client.patch(f"{BASE}/{ap_id}", json={"name": "  Lobby entrance  "}, headers=ADMIN)
    after = doc(ap_id)
    body = r.json() if r.status_code == 200 else {}
    check(2, "admin rename -> 200 with the trimmed name; Firestore updated; MAC and position unchanged",
          r.status_code == 200 and body.get("name") == "Lobby entrance" and after.get("name") == "Lobby entrance"
          and all(after.get(k) == before.get(k) for k in ("mac", "x_pct", "y_pct", "x_m", "y_m", "id")),
          f"status={r.status_code} name={after.get('name')!r}")

    # 3
    r_blank = client.patch(f"{BASE}/{ap_id}", json={"name": "   "}, headers=ADMIN)
    r_long = client.patch(f"{BASE}/{ap_id}", json={"name": "x" * 65}, headers=ADMIN)
    r_unknown = client.patch(f"{BASE}/no-such-ap", json={"name": "y"}, headers=ADMIN)
    check(3, "blank or too long -> 422 with a sentence; unknown AP -> 404; the name stays",
          r_blank.status_code == 422 and isinstance(r_blank.json().get("detail"), str)
          and r_long.status_code == 422 and isinstance(r_long.json().get("detail"), str)
          and r_unknown.status_code == 404 and doc(ap_id).get("name") == "Lobby entrance"
          and doc("no-such-ap") == {},
          f"blank={r_blank.status_code} {r_blank.json().get('detail')!r} long={r_long.status_code} unknown={r_unknown.status_code}")

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
