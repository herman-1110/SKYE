"""VIGI camera RTSP stream probe (Prompt 130, Part E1). Read-only.

For each candidate path it sends RTSP DESCRIBE (Digest auth, user admin) and
reads the SDP: codec, payload type and anything the camera states about size
or frame rate. With --sample N it also plays the stream over TCP for N seconds
and measures the frame rate from the RTP timestamps, then tears it down.
Nothing is decoded, recorded or saved.

Uses no third-party tools (ffprobe isn't installed). The admin password is
read from VIGI_CAMERA_PASSWORD (environment, or backend/.env). It never goes
into a URL, and the password, digest values and session ids are never
printed. A rejected login stops the whole probe, because the camera locks the
account after repeated failures.

    python rtsp_probe.py [--host 192.168.0.101] [--paths stream1 stream2] [--sample 4]
"""
import argparse
import hashlib
import os
import re
import secrets
import socket
import struct
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
USER = "admin"


def _load_password() -> str:
    pw = os.environ.get("VIGI_CAMERA_PASSWORD", "")
    if pw:
        return pw
    try:
        from dotenv import dotenv_values
        return dotenv_values(REPO / "backend" / ".env").get("VIGI_CAMERA_PASSWORD") or ""
    except ImportError:
        return ""


class AuthRejected(Exception):
    pass


class Rtsp:
    def __init__(self, host: str, port: int, password: str):
        self.host, self.port, self.password = host, port, password
        self.sock = socket.create_connection((host, port), timeout=8)
        self.buf = b""
        self.cseq = 0
        self.challenge = None   # parsed WWW-Authenticate
        self.session = None

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass

    def _readline(self) -> bytes:
        while b"\r\n" not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("camera closed the connection")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\r\n", 1)
        return line

    def _readn(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("camera closed the connection")
            self.buf += chunk
        data, self.buf = self.buf[:n], self.buf[n:]
        return data

    def _digest(self, method: str, uri: str) -> str:
        c = self.challenge
        alg = (c.get("algorithm") or "MD5").upper()
        h = (lambda s: hashlib.sha256(s.encode()).hexdigest()) if "SHA-256" in alg else \
            (lambda s: hashlib.md5(s.encode()).hexdigest())
        ha1 = h(f"{USER}:{c['realm']}:{self.password}")
        ha2 = h(f"{method}:{uri}")
        if "auth" in (c.get("qop") or ""):
            cnonce, nc = secrets.token_hex(8), "00000001"
            resp = h(f"{ha1}:{c['nonce']}:{nc}:{cnonce}:auth:{ha2}")
            return (f'Digest username="{USER}", realm="{c["realm"]}", nonce="{c["nonce"]}", uri="{uri}", '
                    f'response="{resp}", algorithm="{c.get("algorithm") or "MD5"}", qop=auth, nc={nc}, cnonce="{cnonce}"')
        resp = h(f"{ha1}:{c['nonce']}:{ha2}")
        return f'Digest username="{USER}", realm="{c["realm"]}", nonce="{c["nonce"]}", uri="{uri}", response="{resp}"'

    def request(self, method: str, uri: str, headers: dict = None, auth: bool = True):
        self.cseq += 1
        lines = [f"{method} {uri} RTSP/1.0", f"CSeq: {self.cseq}", "User-Agent: skye-rtsp-probe"]
        for k, v in (headers or {}).items():
            lines.append(f"{k}: {v}")
        if self.session:
            lines.append(f"Session: {self.session}")
        if auth and self.challenge:
            lines.append(f"Authorization: {self._digest(method, uri)}")
        self.sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        status_line = self._readline().decode("latin-1")
        while status_line.startswith("$") or not status_line.startswith("RTSP/"):
            status_line = self._readline().decode("latin-1")   # skip stray interleaved data
        hdrs = {}
        while True:
            line = self._readline().decode("latin-1")
            if not line:
                break
            k, _, v = line.partition(":")
            hdrs.setdefault(k.strip().lower(), []).append(v.strip())
        body = b""
        n = int((hdrs.get("content-length") or ["0"])[0])
        if n:
            body = self._readn(n)
        code = int(status_line.split()[1])
        return code, hdrs, body

    def authed(self, method: str, uri: str, headers: dict = None):
        code, hdrs, body = self.request(method, uri, headers, auth=True)
        if code == 401:
            if self.challenge is not None:
                raise AuthRejected(f"{method} rejected the credentials (401)")
            self.challenge = _parse_challenge(hdrs.get("www-authenticate", []))
            if not self.challenge:
                raise AuthRejected("401 without a usable Digest challenge")
            code, hdrs, body = self.request(method, uri, headers, auth=True)
            if code == 401:
                raise AuthRejected(f"{method} rejected the credentials (401)")
        return code, hdrs, body


def _parse_challenge(values: list):
    for v in values:
        if v.lower().startswith("digest"):
            return dict(re.findall(r'(\w+)="?([^",]*)"?', v[6:]))
    return None


def _sdp_summary(sdp: str) -> list:
    out, media = [], None
    for line in sdp.splitlines():
        if line.startswith("m="):
            media = {"m": line[2:], "rtpmap": [], "fmtp_keys": [], "control": None, "other": []}
            out.append(media)
        elif media is not None and line.startswith("a=rtpmap:"):
            media["rtpmap"].append(line[9:])
        elif media is not None and line.startswith("a=fmtp:"):
            # parameter names only: sprop-* values are long base64 blobs
            media["fmtp_keys"] = [kv.split("=")[0].strip() for kv in line.split(" ", 1)[-1].split(";") if kv.strip()]
            media["fmtp_profile"] = re.findall(r"(profile-level-id|profile-id|level-id|tier-flag)=([^;]+)", line)
        elif media is not None and line.startswith("a=control:"):
            media["control"] = line[10:]
        elif media is not None and re.match(r"a=(framerate|x-framerate|x-dimensions|cliprect|framesize|range)", line):
            media["other"].append(line[2:])
    return out


def _sample_fps(cam: Rtsp, base_uri: str, video: dict, seconds: float) -> dict:
    ctrl = video.get("control") or ""
    track = ctrl if ctrl.startswith("rtsp://") else base_uri.rstrip("/") + "/" + ctrl
    code, hdrs, _ = cam.authed("SETUP", track, {"Transport": "RTP/AVP/TCP;unicast;interleaved=0-1"})
    if code != 200:
        return {"setup": code}
    cam.session = (hdrs.get("session") or [""])[0].split(";")[0]
    code, _, _ = cam.authed("PLAY", base_uri, {"Range": "npt=0.000-"})
    if code != 200:
        return {"play": code}
    ts_seen, packets, nbytes, markers = [], 0, 0, 0
    end = time.time() + seconds
    cam.sock.settimeout(3)
    while time.time() < end:
        head = cam._readn(1)
        if head != b"$":
            cam._readline()          # an RTSP message (e.g. a keep-alive reply); skip it
            continue
        chan, length = struct.unpack(">BH", cam._readn(3))
        pkt = cam._readn(length)
        if chan != 0 or length < 12:
            continue
        packets += 1
        nbytes += length
        marker = pkt[1] & 0x80
        ts = struct.unpack(">I", pkt[4:8])[0]
        if marker:
            markers += 1
        if not ts_seen or ts != ts_seen[-1]:
            ts_seen.append(ts)
    try:
        cam.authed("TEARDOWN", base_uri)
    except Exception:
        pass
    span = ((ts_seen[-1] - ts_seen[0]) & 0xFFFFFFFF) / 90000.0 if len(ts_seen) > 1 else 0
    return {"seconds": seconds, "rtp_packets": packets, "kbit_per_s": round(nbytes * 8 / seconds / 1000),
            "frames": len(ts_seen), "fps_from_rtp_timestamps": round((len(ts_seen) - 1) / span, 2) if span else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.0.101")
    ap.add_argument("--port", type=int, default=554)
    ap.add_argument("--paths", nargs="+", default=["stream1", "stream2", "stream3"])
    ap.add_argument("--sample", type=float, default=0, help="seconds of RTP to sample per stream (0 = DESCRIBE only)")
    args = ap.parse_args()
    password = _load_password()
    if not password:
        print("VIGI_CAMERA_PASSWORD is not set; skipping.")
        return 3
    for path in args.paths:
        uri = f"rtsp://{args.host}:{args.port}/{path}"
        print(f"== /{path}")
        cam = Rtsp(args.host, args.port, password)
        try:
            code, hdrs, body = cam.authed("DESCRIBE", uri, {"Accept": "application/sdp"})
            print(f"   DESCRIBE -> {code}   auth: Digest {cam.challenge.get('algorithm') or 'MD5'}"
                  f"{', qop=' + cam.challenge['qop'] if cam.challenge and cam.challenge.get('qop') else ''}"
                  if cam.challenge else f"   DESCRIBE -> {code}   (no auth asked)")
            if code != 200:
                continue
            sdp = body.decode("utf-8", "replace")
            for k in ("s=", "i="):
                for line in sdp.splitlines():
                    if line.startswith(k):
                        print(f"   {line}")
            media = _sdp_summary(sdp)
            for m in media:
                print(f"   m={m['m']}  rtpmap={m['rtpmap']}  fmtp params={m['fmtp_keys']}"
                      + (f"  profile={m.get('fmtp_profile')}" if m.get("fmtp_profile") else "")
                      + (f"  {m['other']}" if m["other"] else ""))
            video = next((m for m in media if m["m"].startswith("video")), None)
            if video and args.sample > 0:
                print(f"   sample: {_sample_fps(cam, uri, video, args.sample)}")
        except AuthRejected as e:
            print(f"   STOP: {e}. Not trying further paths (the account locks after repeated failures).")
            return 1
        except Exception as e:
            print(f"   error: {type(e).__name__}: {e}")
        finally:
            cam.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
