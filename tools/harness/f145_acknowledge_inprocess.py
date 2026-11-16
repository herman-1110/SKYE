"""In-process checks for Prompt 145, D1: POST /alerts/{id}/acknowledge.

  1  refused without auth, and 403 for a user; nothing written
  2  an admin acknowledges: 200 with the three fields; acknowledged_by is the
     admin's display name, acknowledged_by_uid their uid, acknowledged_at an
     ISO 8601 time in UTC; /alerts holds the same three; every other field is
     unchanged and resolved stays false
  3  the owner can acknowledge too
  4  a second acknowledge, by someone else, changes nothing and returns the
     first one's values
  5  an unknown alert -> 404 "Alert not found"; nothing created
  6  an admin with an empty display name is recorded as "admin"
  0  the fakes: nothing unimplemented, no tripwire

On the base (9f28798) the route doesn't exist: every request is a 404 with
FastAPI's own "Not Found", so checks 1-6 fail.

usage (Git Bash, repo root):
  "$py" -B tools/harness/f145_acknowledge_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

OWNER = {"Authorization": "Bearer harness-token:harness-owner"}
ADMIN = {"Authorization": "Bearer harness-token:harness-admin"}
BLANK = {"Authorization": "Bearer harness-token:harness-admin-blank"}
USER = {"Authorization": "Bearer harness-token:harness-user"}
ACK = ("acknowledged_at", "acknowledged_by", "acknowledged_by_uid")
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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "f145_acknowledge_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-f145ack-default-rtdb.firebaseio.com",
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
    from firebase_admin import db, firestore
    for uid, name, role in (("harness-admin", "Harness Admin", "admin"),
                            ("harness-admin-blank", "   ", "admin"),
                            ("harness-user", "Harness User", "user")):
        firestore.client().collection("users").document(uid).set({
            "uid": uid, "email": f"{uid}@example.invalid", "display_name": name, "role": role,
            "status": "approved", "person_id": "", "created_at": "2026-11-16T00:00:00+00:00",
            "email_verified": True})

    def alert(alert_id, alert_type="man_down"):
        db.reference(f"/alerts/{alert_id}").set({
            "alert_id": alert_id, "alert_type": alert_type, "person_id": "test-f145", "zone": "Z",
            "timestamp": "2026-11-16T01:00:00+00:00", "resolved": False, "approximate": False,
            "cause": "stillness"})

    def stored(alert_id):
        return db.reference(f"/alerts/{alert_id}").get()

    for i in ("a1", "a2", "a3"):
        alert(i)
    alert("a3", "possible_man_down")

    import main
    from fastapi.testclient import TestClient
    client = TestClient(main.app)

    def post(alert_id, headers=None):
        return client.post(f"/alerts/{alert_id}/acknowledge", headers=headers or {})

    # 1
    before = stored("a1")
    r_none = post("a1")
    r_user = post("a1", USER)
    check(1, "refused without auth and for a user (403); nothing written",
          r_none.status_code in (401, 422) and r_user.status_code == 403 and stored("a1") == before,
          f"none={r_none.status_code} user={r_user.status_code}")

    # 2
    r = post("a1", ADMIN)
    body = r.json() if r.status_code == 200 else {}
    after = stored("a1") or {}
    when = None
    try:
        when = datetime.fromisoformat(body.get("acknowledged_at", ""))
    except Exception:
        pass
    others_same = {k: v for k, v in after.items() if k not in ACK} == before
    check(2, "admin -> 200 with name, uid and a UTC time; /alerts holds the same three; nothing else changes",
          r.status_code == 200 and body.get("alert_id") == "a1"
          and body.get("acknowledged_by") == "Harness Admin" and body.get("acknowledged_by_uid") == "harness-admin"
          and when is not None and when.utcoffset() == timedelta(0)
          and all(after.get(k) == body.get(k) for k in ACK) and others_same and after.get("resolved") is False,
          f"status={r.status_code} body={body} resolved={after.get('resolved')} others_same={others_same}")

    # 3
    r3 = post("a2", OWNER)
    b3 = r3.json() if r3.status_code == 200 else {}
    check(3, "the owner can acknowledge",
          r3.status_code == 200 and b3.get("acknowledged_by") == "Harness Owner"
          and b3.get("acknowledged_by_uid") == "harness-owner"
          and (stored("a2") or {}).get("acknowledged_by_uid") == "harness-owner",
          f"status={r3.status_code} body={b3}")

    # 4
    first = stored("a1")
    r4 = post("a1", OWNER)
    b4 = r4.json() if r4.status_code == 200 else {}
    check(4, "a second acknowledge (by the owner) changes nothing and returns the admin's values",
          r4.status_code == 200 and stored("a1") == first and all(b4.get(k) == first.get(k) for k in ACK)
          and b4.get("acknowledged_by") == "Harness Admin",
          f"status={r4.status_code} body={b4}")

    # 5
    r5 = post("no-such-alert", ADMIN)
    detail5 = r5.json().get("detail") if r5.headers.get("content-type", "").startswith("application/json") else None
    check(5, "an unknown alert -> 404 'Alert not found'; nothing created",
          r5.status_code == 404 and detail5 == "Alert not found" and stored("no-such-alert") is None,
          f"status={r5.status_code} detail={detail5!r}")

    # 6
    r6 = post("a3", BLANK)
    b6 = r6.json() if r6.status_code == 200 else {}
    check(6, "an admin with an empty display name is recorded as 'admin'",
          r6.status_code == 200 and b6.get("acknowledged_by") == "admin"
          and (stored("a3") or {}).get("acknowledged_by") == "admin"
          and (stored("a3") or {}).get("resolved") is False,
          f"status={r6.status_code} body={b6}")

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
