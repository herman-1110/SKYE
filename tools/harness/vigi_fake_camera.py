"""Fake VIGI camera for the Prompt 131 tests (tools/harness/vigi_131_test.py).

- tcp_listener(host): accepts and closes connections on host:554, standing in
  for the camera's RTSP port (what TCP liveness probes).
- OpenApiServer(host, state, cert, key): HTTPS on host:20443 speaking the
  subset of the VIGI IPC Open API (doc V1.1 §4.1.1) the backend uses:
  doAuth (challenge, then the SHA-256 digest response, which it really
  checks against state.password), getDeviceStatus, getSystemTime,
  getTimeZone, getPeopleDetectionSwitch. Any other method gets -10004.

FakeCameraState.logins counts password-bearing doAuth requests - the number
the real camera's lockout counts. mode "reject" answers every login with
-10021; tz and people_enabled are what getTimeZone / getPeopleDetectionSwitch
return. Bind to 127.0.0.x (not 127.0.0.1) so nothing collides with real
local services. Test-only; never point the backend at a real camera with it.
"""
import collections
import hashlib
import json
import os
import shutil
import socket
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REALM = "TP-LINK IP-Camera"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_self_signed_cert(out_dir: str):
    """(cert_path, key_path) via openssl (Git for Windows ships it)."""
    openssl = shutil.which("openssl")
    if not openssl:
        raise RuntimeError("openssl not found on PATH (run from Git Bash)")
    cert, key = os.path.join(out_dir, "fake-camera-cert.pem"), os.path.join(out_dir, "fake-camera-key.pem")
    subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", cert,
                    "-days", "1", "-subj", "/CN=fake-vigi-camera"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return cert, key


class FakeCameraState:
    def __init__(self, password: str, mode: str = "ok", tz: str = "UTC+07:00", people_enabled: str = "on") -> None:
        self.lock = threading.Lock()
        self.password = password
        self.mode = mode                  # "ok" | "reject"
        self.tz = tz
        self.people_enabled = people_enabled
        self.challenges = 0
        self.logins = 0                   # password-bearing doAuth requests
        self.calls = collections.Counter()
        self._nonce = None
        self._stok = None

    def snapshot(self) -> dict:
        with self.lock:
            return {"challenges": self.challenges, "logins": self.logins, "calls": dict(self.calls),
                    "mode": self.mode, "people_enabled": self.people_enabled}

    def handle(self, path: str, body: dict) -> dict:
        method = body.get("method")
        with self.lock:
            if method == "doAuth" and body.get("params") is None:
                self.challenges += 1
                self._nonce = os.urandom(16).hex()
                return {"method": "doAuth", "errCode": -10020,
                        "authenticate": {"realm": REALM, "nonce": self._nonce, "algorithm": "SHA-256",
                                         "uri": "doAuth", "method": "POST"}}
            if method == "doAuth":
                self.logins += 1
                params = body.get("params") or {}
                a1 = _sha256(f"admin:{REALM}:{self.password}")
                expected = _sha256(f"{a1}:{self._nonce}:{_sha256('POST:doAuth')}")
                if self.mode == "reject" or params.get("nonce") != self._nonce or params.get("response") != expected:
                    return {"method": "doAuth", "errCode": -10021}
                self._stok = os.urandom(16).hex()
                return {"method": "doAuth", "stok": self._stok, "errCode": 0}
            stok = path[len("/stok="):] if path.startswith("/stok=") else None
            if not self._stok or stok != self._stok:
                return {"method": method, "errCode": -10003}
            self.calls[method] += 1
            if method == "getDeviceStatus":
                return {"method": method, "errCode": 0,
                        "result": {"device_model": "InSight S445 (fake)", "dev_alias": "fake", "ip": "",
                                   "mac": "98-ba-5f-8b-10-03", "link_status": 1, "uptime": 1234}}
            if method == "getSystemTime":
                return {"method": method, "errCode": 0, "result": {"system_time": int(time.time())}}
            if method == "getTimeZone":
                return {"method": method, "errCode": 0, "result": {"timezone": self.tz, "area": "Asia/Jakarta"}}
            if method == "getPeopleDetectionSwitch":
                return {"method": method, "errCode": 0,
                        "result": {"enabled": self.people_enabled, "sensitivity": 50, "sound_alarm_enabled": "off",
                                   "light_alarm_enabled": "off", "msg_push_enabled": "on", "record_enabled": "on"}}
            return {"method": method, "errCode": -10004}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            body = {}
        data = json.dumps(self.server.state.handle(self.path, body)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True


class OpenApiServer:
    def __init__(self, host: str, state: FakeCameraState, cert: str, key: str, port: int = 20443) -> None:
        self.httpd = ThreadingHTTPServer((host, port), _Handler)
        self.httpd.daemon_threads = True
        self.httpd.state = state
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        self.httpd.socket = ctx.wrap_socket(self.httpd.socket, server_side=True)
        threading.Thread(target=self.httpd.serve_forever, name=f"fake-openapi-{host}", daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def tcp_listener(host: str, port: int = 554) -> socket.socket:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind((host, port))
    srv.listen(16)

    def loop():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            conn.close()

    threading.Thread(target=loop, name=f"fake-rtsp-{host}", daemon=True).start()
    return srv
