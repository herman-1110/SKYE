"""Prompt 132 in-process checks: live view through go2rtc (VALIDATION 1-4).

  1  POST .../cctvs/{id}/webrtc: 401 without auth, 403 for a non-admin; an
     admin gets the fake go2rtc's canned answer back, and nothing else. The
     fake saw the right stream name (sub by default, main for HD) and the
     offer as sent, and no stream address.
  2  errors: fake go2rtc down -> 503; stream unknown to go2rtc -> 503 with
     its own sentence; go2rtc error (its body holds the test password) ->
     502 with a fixed sentence; go2rtc too slow -> 504; camera offline or
     never seen -> 409; no IP / NVR -> 409; unknown camera -> 404; an offer
     that would send video or audio -> 422
  3  the generated config: written at startup; _sub/_main streams with the
     right paths for each registered camera; ${VIGI_CAMERA_PASSWORD} and
     never the test password; loopback-only settings; rewritten after a
     create, an IP edit and a delete, and NOT rewritten when nothing in it
     changes (a name edit); no temp file left behind
  4  the test password appears in no log line, response body or config
     file (every captured output is searched for it)

usage (Git Bash, repo root):
  "$py" -B tools/harness/vigi_132_inprocess.py --backend-dir "$exp/backend"

No server port, no go2rtc, no LAN traffic: the fake go2rtc is a small HTTP
server on 127.0.0.1, and the cameras are 127.0.0.2x addresses nothing
listens on. The real backend/.env is never read; settings are fake values.
"""
import argparse
import glob
import json
import logging
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

TEST_PASSWORD = "p132-TEST.pw_~Zz9"   # fixed test value; every output is searched for it
ADMIN = {"Authorization": "Bearer harness-token:harness-owner"}
USER = {"Authorization": "Bearer harness-token:harness-user"}
BASE = f"/buildings/{C.BUILDING_ID}/floors/{C.FLOOR_ID}"

CAM_A = {"id": "cam-p132-a", "mac": "AA:BB:CC:13:2A:01", "key": "AA_BB_CC_13_2A_01", "ip": "127.0.0.21",
         "stream": "ipc_AABBCC132A01_1"}
CAM_N = {"id": "cam-p132-nvr", "mac": "AA:BB:CC:13:2A:02", "key": "AA_BB_CC_13_2A_02", "ip": "127.0.0.22"}
CAM_X = {"id": "cam-p132-noip", "mac": "AA:BB:CC:13:2A:03", "key": "AA_BB_CC_13_2A_03"}

OFFER = "\r\n".join([
    "v=0", "o=- 4611731400430051336 2 IN IP4 127.0.0.1", "s=-", "t=0 0", "a=group:BUNDLE 0",
    "m=video 9 UDP/TLS/RTP/SAVPF 102", "c=IN IP4 0.0.0.0", "a=ice-ufrag:abcd", "a=ice-pwd:abcdefghijklmnopqrstuvwx",
    "a=fingerprint:sha-256 " + ":".join(f"{i:02X}" for i in range(32)), "a=setup:actpass", "a=mid:0",
    "a=recvonly", "a=rtcp-mux", "a=rtpmap:102 H264/90000", ""])
ANSWER = "\r\n".join([
    "v=0", "o=- 1 2 IN IP4 127.0.0.1", "s=-", "t=0 0", "m=video 9 UDP/TLS/RTP/SAVPF 102", "c=IN IP4 0.0.0.0",
    "a=candidate:1 1 udp 2130706431 127.0.0.1 8555 typ host", "a=sendonly", "a=rtpmap:102 H264/90000", ""])

results = []
responses = []   # every response body the backend sent in this test (searched in check 4)


def check(num, name, ok, detail=""):
    results.append({"check": num, "name": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] #{num} {name}" + (f" - {detail}" if detail else ""), flush=True)


class FakeGo2rtc:
    """Stands in for go2rtc's POST /api/webrtc?src=<name>. mode: ok | notfound | error | slow."""
    def __init__(self):
        self.mode = "ok"
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):   # quiet: nothing of the fake reaches the captured output
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", "replace")
                url = urlparse(self.path)
                fake.requests.append({"path": url.path, "query": parse_qs(url.query),
                                      "ctype": self.headers.get("Content-Type"), "body": body})
                if fake.mode == "slow":
                    time.sleep(3)
                if fake.mode == "notfound":
                    self._reply(404, b"stream not found\n", "text/plain")
                elif fake.mode == "error":
                    # What go2rtc's unmasked error path could carry: the source address.
                    msg = f"streams: rtsp://admin:{TEST_PASSWORD}@{CAM_A['ip']}:554/stream2: wrong user/pass\n"
                    self._reply(500, msg.encode(), "text/plain")
                else:
                    self._reply(200, json.dumps({"type": "answer", "sdp": ANSWER}).encode(), "application/json")

            def _reply(self, status, data, ctype):
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend-dir", required=True)
    args = ap.parse_args()
    backend_dir = os.path.abspath(args.backend_dir)
    if os.path.isdir(os.path.join(backend_dir, "venv")) or os.path.exists(os.path.join(backend_dir, "serviceAccountKey.json")):
        print("refusing: --backend-dir must be a git-archive export, never the live backend/")
        return 2
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "vigi132_inprocess"))
    config_path = os.path.join(run_dir, "go2rtc", "go2rtc.yaml")
    fake = FakeGo2rtc()
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-p132-default-rtdb.firebaseio.com",
        "GEMINI_API_KEY": "harness-fake-gemini-key",
        "OMADA_ACCESS_TOKEN": "harness-fake-omada-token",
        "LLM_MODEL_NAME": "harness-fake-model",
        "VIGI_ALARM_PATH_SECRET": "p132-INPROC-alarm-secret-0123456789abcdef",
        "VIGI_CAMERA_PASSWORD": TEST_PASSWORD,
        "VIGI_DISCOVERY_INTERVAL_S": "0",
        "VIGI_LIVENESS_INTERVAL_S": "3600",
        "VIGI_OPENAPI_START_DELAY_S": "3600",
        "GO2RTC_API_URL": fake.url,
        "GO2RTC_CONFIG_PATH": config_path,
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
    firestore.client().collection("users").document("harness-user").set({
        "uid": "harness-user", "email": "harness-user@example.invalid", "display_name": "Harness User",
        "role": "user", "status": "approved", "person_id": "", "created_at": "2026-10-06T00:00:00+00:00",
        "email_verified": True})

    import main
    from fastapi.testclient import TestClient
    from models.cctv import CCTV
    from repositories.cctv_repository import cctv_repository
    from services import live_view_service as L

    # Everything the backend logs, as it would reach a log file.
    log_file = os.path.join(run_dir, "backend.log")
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)

    def seed_camera(c, **kw):
        cctv_repository.save(C.BUILDING_ID, C.FLOOR_ID, CCTV(
            id=c["id"], floor_id=C.FLOOR_ID, building_id=C.BUILDING_ID, name=c["id"], x_pct=0.5, y_pct=0.5,
            created_at="2026-10-06T00:00:00+00:00", mac=c["mac"], device_mac=c["mac"], ip=c.get("ip"), **kw))

    def online(c, age_s=0):
        db.reference(f"/cctv_heartbeats/{c['key']}").update({"mac": c["mac"], "last_seen": int(time.time()) - age_s})

    seed_camera(CAM_A)
    seed_camera(CAM_N, source_type="nvr", channel=3)
    seed_camera(CAM_X)

    def config_text():
        try:
            with open(config_path, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def mtime():
        try:
            return os.stat(config_path).st_mtime_ns
        except FileNotFoundError:
            return None

    with TestClient(main.app) as client:
        def post(path, body=None, headers=None):
            r = client.post(path, json=body, headers=headers or {})
            responses.append(r.text)
            return r

        def offer(cam_id, body=None, headers=ADMIN):
            return post(f"{BASE}/cctvs/{cam_id}/webrtc", body if body is not None else {"sdp": OFFER}, headers)

        # 3. written at startup, from the registry
        text = config_text() or ""
        a_sub = f'"{CAM_A["stream"]}_sub": "rtsp://admin:${{VIGI_CAMERA_PASSWORD}}@{CAM_A["ip"]}:554/stream2#media=video"'
        a_main = f'"{CAM_A["stream"]}_main": "rtsp://admin:${{VIGI_CAMERA_PASSWORD}}@{CAM_A["ip"]}:554/stream1#media=video"'
        check(3, "config written at startup: _sub -> stream2 and _main -> stream1, audio excluded",
              a_sub in text and a_main in text, f"exists={bool(text)} sub={a_sub in text} main={a_main in text}")
        check(3, "config holds ${VIGI_CAMERA_PASSWORD} and never the test password",
              "${VIGI_CAMERA_PASSWORD}" in text and TEST_PASSWORD not in text, "")
        settings_ok = all(s in text for s in (
            "modules: [api, rtsp, webrtc]", 'listen: "127.0.0.1:1984"', 'allow_paths: ["/api", "/api/webrtc"]',
            'rtsp:\n  listen: ""', 'listen: "127.0.0.1:8555"', 'candidates: ["127.0.0.1:8555"]', "ice_servers: []"))
        check(3, "config: only api/rtsp/webrtc, API and WebRTC on 127.0.0.1, no RTSP re-server, no ICE servers",
              settings_ok, "")
        check(3, "config: an NVR camera and a camera without an IP get no stream, only a comment",
              "nvr_AABBCC132A02_3" in text and '"nvr_' not in text and "ipc_AABBCC132A03_1: no IP set" in text
              and '"ipc_AABBCC132A03' not in text, "")

        # 1. auth and the happy path
        online(CAM_A)
        r_none = offer(CAM_A["id"], headers={})
        r_user = offer(CAM_A["id"], headers=USER)
        fake.requests.clear()
        r_admin = offer(CAM_A["id"])
        seen = list(fake.requests)
        check(1, "no auth -> 401, non-admin -> 403", r_none.status_code == 401 and r_user.status_code == 403,
              f"none={r_none.status_code} user={r_user.status_code}")
        check(1, "admin -> 200 with the fake's canned answer and nothing else",
              r_admin.status_code == 200 and r_admin.json() == {"type": "answer", "sdp": ANSWER},
              f"status={r_admin.status_code} keys={sorted(r_admin.json()) if r_admin.status_code == 200 else None}")
        fwd = seen[0] if len(seen) == 1 else {}
        fwd_body = json.loads(fwd.get("body") or "{}")
        check(1, "go2rtc got one POST /api/webrtc?src=<camera>_sub with the offer as JSON, and no stream address",
              fwd.get("path") == "/api/webrtc" and fwd.get("query") == {"src": [f"{CAM_A['stream']}_sub"]}
              and (fwd.get("ctype") or "").startswith("application/json")
              and fwd_body == {"type": "offer", "sdp": OFFER} and "rtsp://" not in (fwd.get("body") or ""),
              f"requests={len(seen)} path={fwd.get('path')} query={fwd.get('query')}")
        fake.requests.clear()
        r_hd = offer(CAM_A["id"], {"sdp": OFFER, "quality": "main"})
        r_q = offer(CAM_A["id"], {"sdp": OFFER, "quality": "hd"})
        check(1, "quality main (HD) -> stream <camera>_main; an unknown quality -> 422",
              r_hd.status_code == 200 and [q["query"] for q in fake.requests] == [{"src": [f"{CAM_A['stream']}_main"]}]
              and r_q.status_code == 422, f"hd={r_hd.status_code} bad={r_q.status_code}")

        # 2. errors
        online(CAM_A)
        fake.mode = "notfound"
        r_nf = offer(CAM_A["id"])
        fake.mode = "error"
        r_err = offer(CAM_A["id"])
        fake.mode = "slow"
        L._ANSWER_TIMEOUT_S = 1.0
        r_slow = offer(CAM_A["id"])
        L._ANSWER_TIMEOUT_S = 20.0
        time.sleep(2.5)   # let the slow handler finish before the next mode
        fake.mode = "ok"
        check(2, "go2rtc doesn't know the stream -> 503 'hasn't picked up this camera yet'",
              r_nf.status_code == 503 and r_nf.json().get("detail") == L.NOT_LOADED, f"{r_nf.status_code} {r_nf.json()}")
        check(2, "go2rtc error -> 502 with a fixed sentence; go2rtc's error text (holding the password) not passed on",
              r_err.status_code == 502 and r_err.json().get("detail") == L.STREAM_FAILED
              and TEST_PASSWORD not in r_err.text and "rtsp" not in r_err.text.lower(), f"{r_err.status_code}")
        check(2, "go2rtc too slow -> 504", r_slow.status_code == 504 and r_slow.json().get("detail") == L.TIMED_OUT,
              f"{r_slow.status_code}")
        online(CAM_A, age_s=60)
        r_off = offer(CAM_A["id"])
        db.reference(f"/cctv_heartbeats/{CAM_A['key']}").delete()
        r_never = offer(CAM_A["id"])
        online(CAM_N)
        r_nvr = offer(CAM_N["id"])
        online(CAM_X)
        r_noip = offer(CAM_X["id"])
        r_unknown = offer("no-such-camera")
        check(2, "camera offline (last seen 60 s ago) or never seen -> 409 'offline'",
              r_off.status_code == 409 and r_never.status_code == 409 and r_off.json().get("detail") == L.OFFLINE,
              f"stale={r_off.status_code} never={r_never.status_code}")
        check(2, "NVR camera and camera without an IP -> 409; unknown camera -> 404",
              r_nvr.status_code == 409 and r_noip.status_code == 409 and r_unknown.status_code == 404,
              f"nvr={r_nvr.status_code} noip={r_noip.status_code} unknown={r_unknown.status_code}")
        online(CAM_A)
        fake.requests.clear()
        r_send = offer(CAM_A["id"], {"sdp": OFFER.replace("a=recvonly", "a=sendrecv")})
        r_audio = offer(CAM_A["id"], {"sdp": OFFER + "m=audio 9 UDP/TLS/RTP/SAVPF 8\r\na=recvonly\r\n"})
        r_junk = offer(CAM_A["id"], {"sdp": "hello"})
        check(2, "offers that would send video, ask for audio, or aren't SDP -> 422, never forwarded",
              (r_send.status_code, r_audio.status_code, r_junk.status_code) == (422, 422, 422) and not fake.requests,
              f"send={r_send.status_code} audio={r_audio.status_code} junk={r_junk.status_code} forwarded={len(fake.requests)}")
        fake.close()
        online(CAM_A)
        r_down = offer(CAM_A["id"])
        check(2, "go2rtc not running -> 503 'Live view isn't running on the server'",
              r_down.status_code == 503 and r_down.json().get("detail") == L.NOT_RUNNING, f"{r_down.status_code} {r_down.json()}")

        # 3. rewritten after create / edit / delete, and only when it changes
        m0 = mtime()
        r_c = post(f"{BASE}/cctvs", {"name": "P132 B", "x_pct": 0.3, "y_pct": 0.3, "mac": "aa-bb-cc-13-2a-04",
                                     "ip": "127.0.0.24"}, ADMIN)
        cam_b = r_c.json() if r_c.status_code == 200 else {}
        t_create, m1 = config_text() or "", mtime()
        b_sub = '"ipc_AABBCC132A04_1_sub": "rtsp://admin:${VIGI_CAMERA_PASSWORD}@127.0.0.24:554/stream2#media=video"'
        check(3, "create -> config rewritten with the new camera's streams",
              r_c.status_code == 200 and m1 != m0 and b_sub in t_create and a_sub in t_create, f"create={r_c.status_code}")
        r_n = client.patch(f"{BASE}/cctvs/{cam_b.get('id')}", json={"name": "P132 B renamed"}, headers=ADMIN)
        responses.append(r_n.text)
        m2 = mtime()
        check(3, "name-only edit -> config unchanged and not rewritten (no needless go2rtc relaunch)",
              r_n.status_code == 200 and m2 == m1 and config_text() == t_create, f"patch={r_n.status_code}")
        r_ip = client.patch(f"{BASE}/cctvs/{cam_b.get('id')}", json={"ip": "127.0.0.25"}, headers=ADMIN)
        responses.append(r_ip.text)
        t_ip = config_text() or ""
        check(3, "IP edit -> config rewritten with the new address, the old one gone",
              r_ip.status_code == 200 and mtime() != m2 and "@127.0.0.25:554/stream2" in t_ip and "127.0.0.24" not in t_ip,
              f"patch={r_ip.status_code}")
        r_d = client.delete(f"{BASE}/cctvs/{cam_b.get('id')}", headers=ADMIN)
        responses.append(r_d.text)
        t_del = config_text() or ""
        check(3, "delete -> config rewritten without that camera's streams",
              r_d.status_code == 200 and "ipc_AABBCC132A04" not in t_del and a_sub in t_del, f"delete={r_d.status_code}")
        leftovers = [p for p in os.listdir(os.path.dirname(config_path)) if p != "go2rtc.yaml"]
        check(3, "atomic writes leave no temp file behind", not leftovers, f"{leftovers}")
        check(1, "no API response carries a stream address", not any("rtsp://" in t for t in responses),
              f"responses={len(responses)}")

    # 4. the test password nowhere
    logging.getLogger().removeHandler(handler)
    handler.close()
    files = [p for p in glob.glob(os.path.join(run_dir, "**", "*"), recursive=True) if os.path.isfile(p)]
    files += glob.glob(os.path.join(backend_dir, "logs", "skye-*.log"))
    hits = [os.path.basename(p) for p in files if TEST_PASSWORD.encode() in open(p, "rb").read()]
    resp_hits = sum(TEST_PASSWORD in t for t in responses)
    with open(log_file, encoding="utf-8") as f:
        backend_log = f.read()
    live_lines = backend_log.count("[LIVE]")
    check(1, "each opened stream logs where go2rtc told the browser to connect (here 127.0.0.1:8555 udp)",
          "opened ipc:AABBCC132A01:1 (sub); answer candidates: 127.0.0.1:8555 udp" in backend_log, "")
    check(4, "the test password is in no log line, response body or config file",
          not hits and resp_hits == 0 and live_lines > 0 and len(responses) > 20,
          f"files searched={len(files)} hits={hits} responses={len(responses)} with password={resp_hits} [LIVE] lines={live_lines}")
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
    os._exit(rc)
