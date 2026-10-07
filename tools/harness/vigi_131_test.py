"""Prompt 131 validation (VIGI camera events) through the harness.

Covers VALIDATION 1-11; 12 (pipeline_lock), the 15-minute buffer cutoff and
the parser-on-fixtures checks are in vigi_131_inprocess.py.

usage (Git Bash, repo root; the backend dir must be a git-archive export):
  py=backend/venv/Scripts/python.exe
  "$py" -B tools/harness/vigi_131_test.py --backend-dir "$exp/backend" [--port 8003]

Secrets: the test writes <backend-dir>/.env with FAKE values only and points
the launcher at it (HARNESS_ENV_PATH), so the real backend/.env - camera
password, alarm path secret - is never loaded. The alarm path secret here is a
fixed test value; check 6 greps every log for it.

Fake cameras (tools/harness/vigi_fake_camera.py), all on loopback:
  127.0.0.2  camera A: RTSP-port listener + OpenAPI that accepts the test password
  127.0.0.3  camera B: nothing listening (offline)
  127.0.0.4  camera C: OpenAPI that rejects every login (-10021)
Two server runs (the second is a restart: the in-memory fakes start empty, the
lockout marker in <backend-dir>/logs/ persists). Writes
tools/harness/runs/vigi131/{run1,run2}/ and result.json. Exit 0 = all passed.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time
import http.client

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402
import vigi_fake_camera as FC  # noqa: E402

TEST_SECRET = "p131-TEST-alarm-secret-0123456789abcdef"     # fixed test value, not a real secret
WRONG_SECRET = "p131-WRONG-alarm-secret-0123456789abcdef"
TEST_PASSWORD = "harnessfake131"
ADMIN = {"Authorization": "Bearer harness-token:harness-owner"}
BASE = f"/buildings/{C.BUILDING_ID}/floors/{C.FLOOR_ID}"
FIXTURES = os.path.join(HARNESS, "fixtures", "vigi")

CAM_A = {"ip": "127.0.0.2", "mac_dashed": "98-ba-5f-8b-10-03", "key": "98_BA_5F_8B_10_03", "norm": "98:BA:5F:8B:10:03"}
CAM_B = {"ip": "127.0.0.3", "mac": "AA-BB-CC-00-00-0B", "key": "AA_BB_CC_00_00_0B"}
CAM_C = {"ip": "127.0.0.4", "mac": "CC-CC-CC-00-00-0C", "key": "CC_CC_CC_00_00_0C", "camera_key": "ipc:CCCCCC00000C:1"}
UNREGISTERED_MAC, UNREGISTERED_KEY = "11-22-33-44-55-66", "11_22_33_44_55_66"

results = []


def check(num, name, ok, detail=""):
    results.append({"check": num, "name": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] #{num} {name}" + (f" - {detail}" if detail else ""), flush=True)


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)["body"]


def call(port, method, path, *, body=None, raw=None, ctype=None, headers=None, source=None):
    conn = http.client.HTTPConnection(C.HOST, port, timeout=20, source_address=(source, 0) if source else None)
    hdrs = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    elif raw is not None:
        data = raw
    if ctype:
        hdrs["Content-Type"] = ctype
    try:
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        text = resp.read().decode("utf-8", "replace")
        headers_out = {k.lower(): v for k, v in resp.getheaders()}
        status = resp.status
    finally:
        conn.close()
    try:
        js = json.loads(text)
    except ValueError:
        js = None
    return status, headers_out, js


def state(run_dir):
    for _ in range(40):
        try:
            with open(os.path.join(run_dir, "state.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            time.sleep(0.1)
    return {}


def heartbeat(run_dir, key):
    time.sleep(0.7)   # the launcher dumps state every 0.5 s
    return ((state(run_dir).get("rtdb") or {}).get("cctv_heartbeats") or {}).get(key)


def write_test_env(backend_dir, dump: bool):
    path = os.path.join(backend_dir, ".env")
    lines = [
        "# Prompt 131 harness test .env - FAKE values only (vigi_131_test.py)",
        "FIREBASE_KEY_PATH=./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL=https://harness-fake-p131-default-rtdb.firebaseio.com",
        "GEMINI_API_KEY=harness-fake-gemini-key",
        "OMADA_ACCESS_TOKEN=harness-fake-omada-token",
        "LLM_PROVIDER=gemini",
        "LLM_MODEL_NAME=harness-fake-model",
        "OMADA_RAW_DUMP_ENABLED=false",
        f"VIGI_ALARM_PATH_SECRET={TEST_SECRET}",
        f"VIGI_CAMERA_PASSWORD={TEST_PASSWORD}",
        f"VIGI_RAW_DUMP_ENABLED={'true' if dump else 'false'}",
        "VIGI_LIVENESS_INTERVAL_S=1",
        "VIGI_OPENAPI_INTERVAL_S=2",
        "VIGI_OPENAPI_START_DELAY_S=1",
        "VIGI_DISCOVERY_INTERVAL_S=0",   # 131b: never multicast on the real LAN from a test
    ]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return path


def touch_env(env_path):
    """Move .env's mtime forward (what an edit by Herman does), content unchanged."""
    before = os.stat(env_path).st_mtime_ns
    t = time.time() + 2
    os.utime(env_path, (t, t))
    return before, os.stat(env_path).st_mtime_ns


def start_server(backend_dir, port, run_dir, env_path, extra_env=None):
    C.prepare_run_dir(run_dir)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_"))}
    env.update({"HARNESS_ENV_PATH": env_path, "HARNESS_FAKE_AUTH": "1", "HARNESS_SEED_STALE": "0",
                "PYTHONUNBUFFERED": "1"})
    env.update(extra_env or {})   # wins over the .env file (the launcher loads it with override=False)
    out = open(os.path.join(run_dir, "server.stdout.txt"), "wb")
    err = open(os.path.join(run_dir, "server.stderr.txt"), "wb")
    proc = subprocess.Popen([sys.executable, "-B", os.path.join(HARNESS, "launcher.py"), backend_dir, str(port), run_dir],
                            stdout=out, stderr=err, env=env, cwd=C.REPO_ROOT)
    deadline = time.time() + 120
    while time.time() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"server exited early with {proc.returncode}; see {run_dir}")
        try:
            status, _, _ = call(port, "GET", "/no-such-route")
            if status == 404:
                return proc, out, err
        except OSError:
            pass
        time.sleep(0.5)
    raise SystemExit("server never became ready")


def stop_server(proc, run_dir, out, err):
    open(os.path.join(run_dir, "STOP"), "w").close()
    try:
        proc.wait(40)
    except subprocess.TimeoutExpired:
        try:
            pid = open(os.path.join(run_dir, "pid.txt")).read().strip()
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
        finally:
            proc.wait(15)
    out.close()
    err.close()


def wait_until(pred, timeout, step=0.5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(step)
    return pred()


def multipart_body(json_body):
    boundary = "ReportEventBoundary"
    jpeg = b"\xff\xd8\xff\xe0" + os.urandom(300) + b"\xff\xd9"
    raw = (f"--{boundary}\r\nContent-Type: application/json\r\n\r\n".encode() + json.dumps(json_body).encode()
           + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"snap.jpg\"\r\n"
             f"Content-Type: image/jpeg\r\n\r\n".encode() + jpeg + f"\r\n--{boundary}--\r\n".encode())
    return raw, f"multipart/form-data; boundary={boundary}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend-dir", required=True)
    ap.add_argument("--port", type=int, default=8003)
    args = ap.parse_args()
    backend_dir = os.path.abspath(args.backend_dir)
    # The live backend has a venv and the service-account key; a git-archive export has neither.
    if os.path.isdir(os.path.join(backend_dir, "venv")) or \
            os.path.exists(os.path.join(backend_dir, "serviceAccountKey.json")):
        print("refusing: --backend-dir must be a git-archive export, never the live backend/")
        return 2
    if args.port in C.FORBIDDEN_PORTS or C.port_busy(args.port):
        print(f"refusing port {args.port} (forbidden or busy)")
        return 2
    root = os.path.join(C.RUNS_DIR, "vigi131")
    os.makedirs(root, exist_ok=True)
    marker_dir = os.path.join(backend_dir, "logs")
    for old in glob.glob(os.path.join(marker_dir, "vigi-openapi-lockout-*.json")):
        os.remove(old)

    cert, key = FC.make_self_signed_cert(root)
    cam_a = FC.FakeCameraState(TEST_PASSWORD, mode="ok", tz="UTC+07:00", people_enabled="on")
    cam_c = FC.FakeCameraState(TEST_PASSWORD, mode="reject")
    servers = [FC.OpenApiServer(CAM_A["ip"], cam_a, cert, key), FC.OpenApiServer(CAM_C["ip"], cam_c, cert, key)]
    listeners = [FC.tcp_listener(CAM_A["ip"])]

    # ── run 1 ──────────────────────────────────────────────────────────────────
    env_path = write_test_env(backend_dir, dump=False)
    run1 = os.path.join(root, "run1")
    proc, out, err = start_server(backend_dir, args.port, run1, env_path)
    port = args.port
    try:
        # 11. /vigi/detection is gone
        s, _, _ = call(port, "POST", "/vigi/detection", body={"MAC": CAM_A["norm"]})
        check(11, "/vigi/detection returns 404", s == 404, f"status {s}")

        # 1. secret check
        s_unknown, h_unknown, j_unknown = call(port, "POST", "/no-such-route", body={})
        s_wrong, h_wrong, j_wrong = call(port, "POST", f"/vigi/alarm/{WRONG_SECRET}", body=fixture("legacy_people.json"))
        s_empty, _, j_empty = call(port, "POST", "/vigi/alarm/", body={})
        unreg = dict(fixture("legacy_people.json"), mac=UNREGISTERED_MAC)
        s_ok, h_ok, j_ok = call(port, "POST", f"/vigi/alarm/{TEST_SECRET}", body=unreg, source="127.0.0.5")
        check(1, "wrong secret -> 404, same body as an unknown route",
              s_wrong == 404 and j_wrong == j_unknown and h_wrong.get("content-type") == h_unknown.get("content-type"),
              f"wrong={s_wrong} {j_wrong} unknown={s_unknown} {j_unknown}")
        check(1, "missing secret -> 404", s_empty == 404, f"status {s_empty} {j_empty}")
        check(1, "right secret -> 200 {ok: true} with Connection: close",
              s_ok == 200 and j_ok == {"ok": True} and h_ok.get("connection", "").lower() == "close",
              f"status {s_ok} {j_ok} connection={h_ok.get('connection')}")

        # 5b. unregistered MAC -> heartbeat only
        hb_u = heartbeat(run1, UNREGISTERED_KEY)
        check(5, "unregistered MAC writes only the heartbeat (online, not placed)",
              bool(hb_u) and isinstance(hb_u.get("last_seen"), int) and hb_u.get("mac") == "11:22:33:44:55:66",
              f"node={hb_u}")

        # 7. registry
        s, _, a = call(port, "POST", f"{BASE}/cctvs", headers=ADMIN, body={
            "name": "P131 Cam A", "x_pct": 0.5, "y_pct": 0.5, "mac": CAM_A["mac_dashed"], "ip": CAM_A["ip"]})
        check(7, "create camera A with a dashed MAC -> normalised colon form",
              s == 200 and a and a.get("device_mac") == CAM_A["norm"] and a.get("mac") == CAM_A["norm"]
              and a.get("camera_key") == "ipc:98BA5F8B1003:1", f"status {s} device_mac={a and a.get('device_mac')}")
        check(7, "time zone read from the camera at registration (decision 11)",
              a and a.get("timezone") == "UTC+07:00", f"timezone={a and a.get('timezone')}")
        cam_a_id = a["id"] if a else None
        s, _, j = call(port, "POST", f"{BASE}/cctvs", headers=ADMIN, body={
            "name": "dup", "x_pct": 0.1, "y_pct": 0.1, "mac": "98:ba:5f:8b:10:03", "ip": "127.0.0.9"})
        check(7, "duplicate (device_mac, channel) in another MAC spelling -> 409 with a sentence",
              s == 409 and isinstance(j and j.get("detail"), str), f"status {s} {j}")
        s1, _, j1 = call(port, "POST", f"{BASE}/cctvs", headers=ADMIN, body={"name": "x", "x_pct": 0, "y_pct": 0, "mac": "98-ba:5f-8b-10-03"})
        s2, _, j2 = call(port, "POST", f"{BASE}/cctvs", headers=ADMIN, body={"name": "x", "x_pct": 0, "y_pct": 0, "mac": "AA-00-00-00-00-01", "ip": "192.168.0.300"})
        s3, _, j3 = call(port, "POST", f"{BASE}/cctvs", headers=ADMIN, body={"name": "x", "x_pct": 0, "y_pct": 0, "mac": "AA-00-00-00-00-02", "checkpoint_ap_id": "no-such-ap"})
        check(7, "bad MAC / bad IP / foreign checkpoint -> 422 with a plain sentence",
              (s1, s2, s3) == (422, 422, 422) and all(isinstance(j and j.get("detail"), str) for j in (j1, j2, j3)),
              f"{s1} {j1 and j1.get('detail')!r} | {s2} {j2 and j2.get('detail')!r} | {s3} {j3 and j3.get('detail')!r}")
        s, _, b = call(port, "POST", f"{BASE}/cctvs", headers=ADMIN, body={
            "name": "P131 Cam B", "x_pct": 0.2, "y_pct": 0.2, "mac": CAM_B["mac"], "ip": CAM_B["ip"]})
        check(7, "camera B (unreachable) registers with the UTC+08:00 fallback",
              s == 200 and b and b.get("timezone") == "UTC+08:00", f"status {s} tz={b and b.get('timezone')}")
        cam_b_id = b["id"] if b else None
        s, _, pa = call(port, "PATCH", f"{BASE}/cctvs/{cam_a_id}", headers=ADMIN,
                        body={"name": "P131 Cam A2", "checkpoint_ap_id": "ap-t128-1"})
        s_ch, _, j_ch = call(port, "PATCH", f"{BASE}/cctvs/{cam_a_id}", headers=ADMIN, body={"channel": 0})
        s_dup, _, j_dup = call(port, "PATCH", f"{BASE}/cctvs/{cam_a_id}", headers=ADMIN, body={"mac": "aa:bb:cc:00:00:0b"})
        check(7, "PATCH edits name and checkpoint; bad channel 422; taking B's MAC 409",
              s == 200 and pa and pa.get("name") == "P131 Cam A2" and pa.get("checkpoint_ap_id") == "ap-t128-1"
              and s_ch == 422 and s_dup == 409, f"patch={s} ch={s_ch} dup={s_dup}")
        s, _, c = call(port, "POST", f"{BASE}/cctvs", headers=ADMIN, body={
            "name": "P131 Cam C", "x_pct": 0.8, "y_pct": 0.8, "mac": CAM_C["mac"], "ip": CAM_C["ip"]})
        marker = os.path.join(marker_dir, "vigi-openapi-lockout-ipc_CCCCCC00000C_1.json")
        marker_keys = sorted(json.load(open(marker)).keys()) if os.path.exists(marker) else None
        check(9, "rejected login: exactly one attempt, marker written (camera_key + .env mtime only), probe auth_error",
              s == 200 and cam_c.snapshot()["logins"] == 1 and marker_keys == ["camera_key", "env_mtime_ns"]
              and (heartbeat(run1, CAM_C["key"]) or {}).get("probe") == "auth_error"
              and (c or {}).get("timezone") == "UTC+08:00",
              f"create={s} logins={cam_c.snapshot()['logins']} marker_keys={marker_keys} "
              f"probe={(heartbeat(run1, CAM_C['key']) or {}).get('probe')}")

        # 2-5. alarms from camera A's own address
        for name in ("legacy_motion_people.json", "enhanced_people_two_persons.json", "enhanced_motion_only.json"):
            s, _, _ = call(port, "POST", f"/vigi/alarm/{TEST_SECRET}", body=fixture(name), source=CAM_A["ip"])
            assert s == 200, (name, s)
        raw, ctype = multipart_body(fixture("legacy_people.json"))
        s_mp, _, _ = call(port, "POST", f"/vigi/alarm/{TEST_SECRET}", raw=raw, ctype=ctype, source=CAM_A["ip"])
        s_txt, _, j_txt = call(port, "POST", f"/vigi/alarm/{TEST_SECRET}", raw=b"hello", ctype="text/plain", source=CAM_A["ip"])
        s_wip, _, _ = call(port, "POST", f"/vigi/alarm/{TEST_SECRET}", body=fixture("legacy_people.json"), source="127.0.0.1")
        s_no, _, j_no = call(port, "GET", f"{BASE}/cctvs/{cam_a_id}/detections")
        s_bad, _, _ = call(port, "GET", f"{BASE}/cctvs/{cam_a_id}/detections", headers={"Authorization": "Bearer nope"})
        s_det, _, det = call(port, "GET", f"{BASE}/cctvs/{cam_a_id}/detections", headers=ADMIN)
        rows = (det or {}).get("detections") or []
        seq = [(r["event_type"], r["is_human"], r["obj_num"], r["payload_format"]) for r in reversed(rows)]
        check(2, "legacy MOTION+PEOPLE -> two records, only PEOPLE is human",
              seq[:2] == [("MOTION", False, None, "legacy"), ("PEOPLE", True, None, "legacy")], f"oldest-first={seq}")
        check(3, "enhanced two people -> obj_num 2; MOTION alone -> not human",
              seq[2:4] == [("PEOPLE", True, 2, "enhanced"), ("MOTION", False, 1, "enhanced")], f"{seq[2:4]}")
        check(4, "multipart: JSON part parsed, image part dropped",
              s_mp == 200 and seq[4:5] == [("PEOPLE", True, None, "legacy")], f"status {s_mp} {seq[4:5]}")
        check(4, "other content types -> 200, nothing recorded", s_txt == 200 and j_txt == {"ok": True} and len(seq) == 5,
              f"status {s_txt}, records {len(seq)}")
        check(5, "registered MAC from the wrong IP records nothing", s_wip == 200 and len(seq) == 5, f"records {len(seq)}")
        times = [r["received_at"] for r in rows]
        check(8, "detections GET: 401 without/with a bad token; newest first; process_started_at given",
              s_no == 401 and s_bad == 401 and s_det == 200 and times == sorted(times, reverse=True)
              and bool((det or {}).get("process_started_at")) and (det or {}).get("window_s") == 900,
              f"no-auth={s_no} bad={s_bad} ok={s_det} n={len(rows)}")
        hb_a = heartbeat(run1, CAM_A["key"]) or {}
        check(5, "accepted alarm updates last_event_at", isinstance(hb_a.get("last_event_at"), int), f"{hb_a}")

        # 10. liveness
        ok_live = wait_until(lambda: isinstance((heartbeat(run1, CAM_A["key"]) or {}).get("last_seen"), int), 10)
        hb_b = heartbeat(run1, CAM_B["key"]) or {}
        check(10, "liveness: listener on A:554 -> last_seen written; nothing on B:554 -> no write",
              ok_live and "last_seen" not in hb_b, f"A={heartbeat(run1, CAM_A['key'])} B={hb_b}")

        # 9. OpenAPI success path
        ok_probe = wait_until(lambda: (heartbeat(run1, CAM_A["key"]) or {}).get("probe") == "ok", 15)
        hb_a = heartbeat(run1, CAM_A["key"]) or {}
        check(9, "success path: probe ok, probe_ok_at set, alarm_config unknown (no Alarm Server read exists)",
              ok_probe and isinstance(hb_a.get("probe_ok_at"), int) and hb_a.get("alarm_config") == "unknown", f"{hb_a}")
        with cam_a.lock:
            cam_a.people_enabled = "off"
        ok_mm = wait_until(lambda: (heartbeat(run1, CAM_A["key"]) or {}).get("alarm_config") == "mismatch", 15)
        check(9, "human detection switched off on the camera -> alarm_config mismatch", ok_mm,
              f"{heartbeat(run1, CAM_A['key'])}")
        time.sleep(4)
        snap_a, snap_c = cam_a.snapshot(), cam_c.snapshot()
        check(9, "one shared client: camera A logged in once across registration and every probe",
              snap_a["logins"] == 1 and snap_a["calls"].get("getDeviceStatus", 0) >= 2, f"{snap_a}")
        check(9, "rejected camera C: still exactly one login attempt after several cycles",
              snap_c["logins"] == 1, f"{snap_c}")
        hb_b = heartbeat(run1, CAM_B["key"]) or {}
        check(9, "unreachable camera B: probe unreachable", hb_b.get("probe") == "unreachable", f"{hb_b}")

        # 7. delete one camera removes its heartbeat; deleting a linked AP unlinks the camera
        had_b = bool(heartbeat(run1, CAM_B["key"]))
        s, _, _ = call(port, "DELETE", f"{BASE}/cctvs/{cam_b_id}", headers=ADMIN)
        gone_b = wait_until(lambda: heartbeat(run1, CAM_B["key"]) is None, 5)
        check(7, "deleting one camera removes its /cctv_heartbeats node", s == 200 and had_b and gone_b,
              f"delete={s} existed_before={had_b} gone_after={gone_b}")
        s, _, _ = call(port, "DELETE", f"{BASE}/aps/ap-t128-1", headers=ADMIN)
        s_l, _, cams = call(port, "GET", f"{BASE}/cctvs", headers=ADMIN)
        a_now = next((x for x in (cams or []) if x.get("id") == cam_a_id), {})
        check(7, "deleting a linked AP sets checkpoint_ap_id to null",
              s == 200 and s_l == 200 and a_now.get("checkpoint_ap_id") is None, f"ap delete={s} cam={a_now.get('checkpoint_ap_id')!r}")

        # 6 (part): trip slowapi's limit on a wrong-secret path so its "exceeded at endpoint" warning is logged
        codes = {}
        conn = http.client.HTTPConnection(C.HOST, port, timeout=20)
        for _ in range(605):
            conn.request("POST", f"/vigi/alarm/{WRONG_SECRET}", body=b"{}", headers={"Content-Type": "application/json"})
            r = conn.getresponse()
            r.read()
            codes[r.status] = codes.get(r.status, 0) + 1
            if r.getheader("connection", "").lower() == "close":
                conn.close()
                conn = http.client.HTTPConnection(C.HOST, port, timeout=20)
        conn.close()
        check(6, "rate limit trips on the alarm route (so slowapi logs its endpoint line)", codes.get(429, 0) >= 1, f"{codes}")
    finally:
        stop_server(proc, run1, out, err)

    # ── run 2: restart, .env untouched (the raw dump comes from the environment) ──
    marker = os.path.join(marker_dir, "vigi-openapi-lockout-ipc_CCCCCC00000C_1.json")
    run2 = os.path.join(root, "run2")
    proc, out, err = start_server(backend_dir, args.port, run2, env_path, extra_env={"VIGI_RAW_DUMP_ENABLED": "true"})
    try:
        before = cam_c.snapshot()["logins"]
        s, _, c2 = call(port, "POST", f"{BASE}/cctvs", headers=ADMIN, body={
            "name": "P131 Cam C", "x_pct": 0.8, "y_pct": 0.8, "mac": CAM_C["mac"], "ip": CAM_C["ip"]})
        time.sleep(6)   # registration plus several OpenAPI cycles
        after = cam_c.snapshot()["logins"]
        check(9, "after a restart, with .env unchanged: no login attempt (registration or probes)",
              s == 200 and after == before and (heartbeat(run2, CAM_C["key"]) or {}).get("probe") == "auth_error",
              f"logins {before}->{after} probe={(heartbeat(run2, CAM_C['key']) or {}).get('probe')}")
        m0, m1 = touch_env(env_path)
        ok1 = wait_until(lambda: cam_c.snapshot()["logins"] == before + 1, 10)
        time.sleep(6)
        after_touch = cam_c.snapshot()["logins"]
        rec = json.load(open(marker)) if os.path.exists(marker) else {}
        check(9, ".env mtime changed: exactly one retry, then stopped again (marker re-armed with the new mtime)",
              ok1 and after_touch == before + 1 and rec.get("env_mtime_ns") == m1, f"logins {before}->{after_touch}")
        with cam_c.lock:
            cam_c.mode = "ok"
        touch_env(env_path)
        ok2 = wait_until(lambda: (heartbeat(run2, CAM_C["key"]) or {}).get("probe") == "ok", 15)
        check(9, "fixed password + .env saved: one login succeeds, marker removed, probe ok",
              ok2 and cam_c.snapshot()["logins"] == before + 2 and not os.path.exists(marker),
              f"logins={cam_c.snapshot()['logins']} marker_exists={os.path.exists(marker)}")
        s, _, _ = call(port, "POST", f"/vigi/alarm/{TEST_SECRET}", body=dict(fixture("legacy_people.json"), mac=UNREGISTERED_MAC), source="127.0.0.5")
        time.sleep(1)
    finally:
        stop_server(proc, run2, out, err)

    # 6. no secret anywhere (fixed test secret, the wrong-secret probes, the test password)
    files = [p for d in (run1, run2) for p in glob.glob(os.path.join(d, "*")) if os.path.isfile(p)]
    files += glob.glob(os.path.join(backend_dir, "logs", "skye-*.log"))
    hits, redacted_lines = {}, 0
    for p in files:
        data = open(p, "rb").read().decode("utf-8", "replace")
        for needle in (TEST_SECRET, WRONG_SECRET, TEST_PASSWORD):
            if needle in data:
                hits.setdefault(os.path.basename(p), []).append(needle[:9] + "...")
        redacted_lines += data.count("/vigi/alarm/***")
    raw_dump = sum(open(p, "rb").read().count(b"[VIGI] raw alarm from") for p in files if "run2" in p and "stdout" in p)
    check(6, "redaction: no captured log line holds the test secret, the probe secret or the test password",
          not hits and redacted_lines > 0, f"files={len(files)} hits={hits} redacted lines seen={redacted_lines}")
    check(6, "raw dump (run 2) logs the body with [VIGI] and never the path", raw_dump >= 1, f"[VIGI] raw lines={raw_dump}")
    loud = [p for d in (run1, run2) for p in ("UNIMPLEMENTED.txt", "TRIPWIRE_HIT.txt") if os.path.exists(os.path.join(d, p))]
    check(0, "fakes: nothing unimplemented, no tripwire", not loud, f"{loud}")

    for s_ in servers:
        s_.close()
    for l_ in listeners:
        l_.close()
    failed = [r for r in results if not r["ok"]]
    with open(os.path.join(root, "result.json"), "w", encoding="utf-8") as f:
        json.dump({"passed": len(results) - len(failed), "failed": len(failed), "results": results,
                   "fake_camera_a": cam_a.snapshot(), "fake_camera_c": cam_c.snapshot()}, f, indent=1)
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
