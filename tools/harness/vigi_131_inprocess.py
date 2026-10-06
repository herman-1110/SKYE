"""Prompt 131 in-process checks (no server, no port), the part of VALIDATION
that needs to reach inside the process:

  12  alarm ingest never takes positioning_service.pipeline_lock: the lock is
      held by another thread while an alarm is posted through FastAPI's
      TestClient; the push must still complete and land in the buffer.
  8   the detection buffer stops at 15 minutes.
  2,3 the parser on every fixture in fixtures/vigi/.

usage (Git Bash, repo root):
  "$py" -B tools/harness/vigi_131_inprocess.py --backend-dir "$exp/backend"

Like ab_run.py it installs the tripwire and fakes in-process. It never loads
the real backend/.env: every setting comes from fake values set below.
"""
import argparse
import glob
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

TEST_SECRET = "p131-INPROC-alarm-secret-0123456789abcdef"
FAKE_ENV = {
    "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
    "FIREBASE_RTDB_URL": "https://harness-fake-p131-default-rtdb.firebaseio.com",
    "GEMINI_API_KEY": "harness-fake-gemini-key",
    "OMADA_ACCESS_TOKEN": "harness-fake-omada-token",
    "LLM_MODEL_NAME": "harness-fake-model",
    "VIGI_ALARM_PATH_SECRET": TEST_SECRET,
    "VIGI_CAMERA_PASSWORD": "",
}
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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "vigi131_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_")):
            del os.environ[k]
    os.environ.update(FAKE_ENV)
    os.environ["HARNESS_SEED_STALE"] = "0"
    fixtures = sorted(glob.glob(os.path.join(HARNESS, "fixtures", "vigi", "*.json")))

    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)
    import harness_fakes
    harness_fakes.install_tripwire(run_dir)
    store = harness_fakes.install_fakes(run_dir)
    import harness_seed
    harness_seed.seed(store)

    # 12. static: no camera module mentions pipeline_lock
    modules = ["routes/vigi_routes.py", "services/vigi_service.py", "services/vigi_alarm_parser.py",
               "services/camera_detection_buffer.py", "services/camera_health_service.py",
               "services/cctv_service.py", "services/vigi_openapi_client.py"]
    import ast
    text_mentions, code_refs = {}, {}
    for m in modules:
        src = open(os.path.join(backend_dir, m), encoding="utf-8").read()
        text_mentions[m] = src.count("pipeline_lock")
        code_refs[m] = sum(1 for node in ast.walk(ast.parse(src))
                           if (isinstance(node, ast.Attribute) and node.attr == "pipeline_lock")
                           or (isinstance(node, ast.Name) and node.id == "pipeline_lock"))
    check(12, "no camera module references pipeline_lock in code (comments/docstrings only)",
          all(v == 0 for v in code_refs.values()),
          f"code refs={sum(code_refs.values())}, text mentions={ {k.split('/')[-1]: v for k, v in text_mentions.items() if v} }")

    import main  # noqa: F401  (builds the app against the fakes, installs the capture tee into the export)
    from fastapi.testclient import TestClient
    from models.cctv import CCTV
    from repositories.cctv_repository import cctv_repository
    from services.camera_detection_buffer import DetectionBuffer, detection_buffer
    from services.cctv_service import cctv_service
    from services.positioning_service import positioning_service
    from services.vigi_alarm_parser import parse_ipc_alarm
    from models.camera_detection import CameraDetection

    # A camera registered at TestClient's own client address ("testclient"), written directly
    # (the API would refuse a non-IPv4 address).
    cam = CCTV(id="cam-inproc", floor_id=C.FLOOR_ID, building_id=C.BUILDING_ID, name="inproc", x_pct=0.5, y_pct=0.5,
               created_at=datetime.now(timezone.utc).isoformat(), mac="98:BA:5F:8B:10:03", device_mac="98:BA:5F:8B:10:03",
               ip="testclient", timezone="UTC+08:00")
    cctv_repository.save(C.BUILDING_ID, C.FLOOR_ID, cam)
    cctv_service.invalidate()
    client = TestClient(main.app)   # no context manager: no lifespan, so no background loops
    with open(os.path.join(HARNESS, "fixtures", "vigi", "legacy_motion_people.json"), encoding="utf-8") as f:
        body = json.load(f)["body"]

    holder_has_lock, release = threading.Event(), threading.Event()

    def hold_lock():
        with positioning_service.pipeline_lock:
            holder_has_lock.set()
            release.wait(30)

    t_hold = threading.Thread(target=hold_lock, daemon=True)
    t_hold.start()
    holder_has_lock.wait(5)
    outcome = {}

    def post():
        t0 = time.perf_counter()
        r = client.post(f"/vigi/alarm/{TEST_SECRET}", json=body)
        outcome.update(status=r.status_code, seconds=time.perf_counter() - t0)

    t_post = threading.Thread(target=post, daemon=True)
    t_post.start()
    t_post.join(10)
    still_held = positioning_service.pipeline_lock.locked()
    recorded = detection_buffer.recent(cam.camera_key)
    release.set()
    t_hold.join(5)
    check(12, "an alarm push completes while pipeline_lock is held by another thread",
          not t_post.is_alive() and outcome.get("status") == 200 and still_held and len(recorded) == 2,
          f"status={outcome.get('status')} took={outcome.get('seconds', -1):.3f}s lock_held_throughout={still_held} "
          f"recorded={[(r['event_type'], r['is_human']) for r in recorded]}")

    # 8. 15-minute cutoff, newest first
    buf = DetectionBuffer()
    now = datetime.now(timezone.utc)

    def det(age_s, event):
        return CameraDetection(camera_key="ipc:X:1", source_type="ipc", device_mac="AA:AA:AA:AA:AA:AA", channel=1,
                               event_type=event, is_human=event == "PEOPLE", obj_num=None, regions=None, boxes=None,
                               camera_time_raw=None, camera_time_utc=None, received_at=now - timedelta(seconds=age_s),
                               source_ip="x", payload_format="legacy")

    buf.add_many([det(16 * 60, "MOTION"), det(14 * 60, "PEOPLE"), det(60, "MOTION"), det(1, "PEOPLE")])
    rows = buf.recent("ipc:X:1")
    ages = [round((now - datetime.fromisoformat(r["received_at"])).total_seconds()) for r in rows]
    check(8, "buffer keeps the last 15 minutes only, newest first", ages == [1, 60, 840], f"ages(s)={ages}")

    # 2, 3. parser on every fixture
    summary = {}
    for path in fixtures:
        with open(path, encoding="utf-8") as f:
            b = json.load(f)["body"]
        st = {}
        dets = parse_ipc_alarm(b, "192.168.0.101", now, camera_timezone="UTC+08:00", stats=st)
        summary[os.path.basename(path)] = [(d.event_type, d.is_human, d.obj_num) for d in dets] + [st]
    human_only_people = all(d[1] == (d[0] == "PEOPLE") for v in summary.values() for d in v if isinstance(d, tuple))
    check(2, "parser: is_human only for PEOPLE across every fixture; nothing skipped",
          human_only_people and all(v[-1]["skipped"] == 0 for v in summary.values()), json.dumps(summary))
    loud = [p for p in ("UNIMPLEMENTED.txt", "TRIPWIRE_HIT.txt") if os.path.exists(os.path.join(run_dir, p))]
    check(0, "fakes: nothing unimplemented, no tripwire", not loud, f"{loud}")

    failed = [r for r in results if not r["ok"]]
    with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump({"passed": len(results) - len(failed), "failed": len(failed), "results": results}, f, indent=1)
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)   # skip interpreter teardown of the fakes' and the tee's threads
