"""VIGI camera OpenAPI health probe (Prompt 130, Part C). Read-only.

Logs in once with doAuth (two calls, SHA-256 digest), then calls only "get"
methods: device info and status, time zone and system time (to compare the
camera clock with this PC's UTC clock), stream resolutions and the stream
port. It changes nothing on the camera.

The admin password is read from VIGI_CAMERA_PASSWORD (environment, or
backend/.env). The password, A1, the digest response and the stok token are
never printed. The camera locks its admin account after repeated failed logins
(errCode -10030), so this makes exactly one login attempt and stops on any
failure; it never retries.

Reference: VIGI IPC Open API Document V1.1 (TP-Link), sections 4.1.1, 4.2,
4.3, 4.5, 4.12. HTTPS on port 20443 with a self-signed certificate, so
certificate checks are off for this local probe only. A new connection per
call, as the document requires.

    python openapi_probe.py [--host 192.168.0.101] [--port 20443]
"""
import argparse
import datetime as dt
import hashlib
import http.client
import json
import os
import ssl
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
READ_ONLY_METHODS = [
    "getDeviceInfo", "getDeviceStatus", "getTimeZone",
    "getResolution", "getVideoCapability", "getStreamPort",
]
CLOCK_SAMPLES = 3
SECRET_KEYS = {"stok", "password", "response", "nonce", "token"}


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _load_password() -> str:
    pw = os.environ.get("VIGI_CAMERA_PASSWORD", "")
    if pw:
        return pw
    try:
        from dotenv import dotenv_values
        return (dotenv_values(REPO / "backend" / ".env").get("VIGI_CAMERA_PASSWORD") or "")
    except ImportError:
        return ""


def _redact(value, secrets: list):
    if isinstance(value, dict):
        return {k: ("<redacted>" if k.lower() in SECRET_KEYS else _redact(v, secrets)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, secrets) for v in value]
    if isinstance(value, str):
        for s in secrets:
            if s and s in value:
                value = value.replace(s, "<redacted>")
    return value


class Camera:
    def __init__(self, host: str, port: int, timeout: float = 10.0):
        self.host, self.port, self.timeout = host, port, timeout
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE   # self-signed camera certificate; local probe only
        self.stok = ""

    def post(self, body: dict) -> dict:
        path = f"/stok={self.stok}" if self.stok else "/"
        conn = http.client.HTTPSConnection(self.host, self.port, timeout=self.timeout, context=self.ctx)
        try:
            conn.request("POST", path, body=json.dumps(body), headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            raw = resp.read()
        finally:
            conn.close()
        try:
            return json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            return {"errCode": None, "_http_status": resp.status, "_non_json_bytes": len(raw)}

    def login(self, password: str) -> tuple:
        first = self.post({"method": "doAuth", "params": None})
        auth = first.get("authenticate") or {}
        realm, nonce = auth.get("realm"), auth.get("nonce")
        method, uri = auth.get("method", "POST"), auth.get("uri", "doAuth")
        if not realm or not nonce:
            return False, f"first doAuth returned no challenge (errCode {first.get('errCode')})", auth
        if (auth.get("algorithm") or "SHA-256").upper() != "SHA-256":
            return False, f"unexpected algorithm {auth.get('algorithm')!r}; not attempting login", auth
        a1 = _sha256(f"admin:{realm}:{password}")
        response = _sha256(f"{a1}:{nonce}:{_sha256(f'{method}:{uri}')}")
        second = self.post({"method": "doAuth", "params": {"nonce": nonce, "response": response}})
        del a1, response
        code = second.get("errCode")
        if code == 0 and second.get("stok"):
            self.stok = second["stok"]
            return True, "ok", {"realm": realm, "algorithm": auth.get("algorithm"), "uri": uri, "method": method}
        meaning = {-10021: "authentication failed or wrong password",
                   -10022: "too many clients logged in",
                   -10030: "too many failed attempts; the account is locked"}.get(code, "unknown")
        return False, f"login failed: errCode {code} ({meaning}). Not retrying.", {"realm": realm}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.0.101")
    ap.add_argument("--port", type=int, default=20443)
    args = ap.parse_args()

    password = _load_password()
    if not password:
        print("VIGI_CAMERA_PASSWORD is not set in the environment or backend/.env; skipping (Part C).")
        return 3

    cam = Camera(args.host, args.port)
    report = {"host": args.host, "port": args.port}
    try:
        ok, msg, info = cam.login(password)
    except Exception as e:
        print(json.dumps({"login": f"connection failed: {type(e).__name__}: {e}"}, indent=2))
        return 1
    report["login"] = msg
    report["auth_challenge"] = info
    if not ok:
        print(json.dumps(_redact(report, [password]), indent=2))
        return 1
    secrets = [password, cam.stok]

    for m in READ_ONLY_METHODS:
        try:
            r = cam.post({"method": m})
            report[m] = {"errCode": r.get("errCode"), "result": r.get("result")}
        except Exception as e:
            report[m] = {"error": f"{type(e).__name__}: {e}"}

    # Camera clock against this PC: UTC before and after each getSystemTime
    # call; the camera's whole-second value is compared with the midpoint.
    samples = []
    for _ in range(CLOCK_SAMPLES):
        try:
            t0 = time.time()
            r = cam.post({"method": "getSystemTime"})
            t1 = time.time()
            cam_s = (r.get("result") or {}).get("system_time")
            if isinstance(cam_s, (int, float)):
                samples.append({"camera_utc": dt.datetime.fromtimestamp(cam_s, dt.timezone.utc).isoformat(),
                                "pc_utc_mid": dt.datetime.fromtimestamp((t0 + t1) / 2, dt.timezone.utc).isoformat(timespec="milliseconds"),
                                "camera_minus_pc_s": round(cam_s - (t0 + t1) / 2, 3),
                                "round_trip_s": round(t1 - t0, 3)})
            else:
                samples.append({"errCode": r.get("errCode"), "result": r.get("result")})
        except Exception as e:
            samples.append({"error": f"{type(e).__name__}: {e}"})
        time.sleep(1.3)
    report["getSystemTime"] = samples
    print(json.dumps(_redact(report, secrets), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
