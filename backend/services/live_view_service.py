"""Live view through go2rtc (Prompt 132, docs/vigi-integration-design.md §8).

go2rtc runs as its own process (tools/go2rtc/start.ps1, in Herman's own
terminal). The backend never starts, stops or restarts it; it does two things.

The config file (T2). The backend writes go2rtc's config from the camera
registry at startup and after every camera create, edit or delete, to
settings.GO2RTC_CONFIG_PATH. It writes only when the content changes, and
atomically, because start.ps1 relaunches go2rtc whenever the file changes.
go2rtc's own POST /api/restart does nothing on Windows (it re-executes itself
with syscall.Exec, which Go doesn't support there; checked on v1.9.14).
The camera password is never in the file: each stream address holds the
variable VIGI_CAMERA_PASSWORD, which go2rtc fills in from its environment
when it loads the file and masks as *** in its own logs.

Each registered camera gets two streams, <camera_key>_sub (stream2,
848x480) and <camera_key>_main (stream1, 2688x1520), with the key's ':'
replaced by '_' so the name is a plain YAML key.

Why ffmpeg sits in front (Herman's option 2, 7 Oct). The InSight S445 ends
every frame with a small SEI NAL that carries the RTP marker bit, and go2rtc
1.9.14's H.264 depacketizer (pkg/h264/rtp.go:45-48) drops a marked SEI under
128 bytes without completing the frame - so go2rtc's own RTSP reader never
emits a frame from this camera (measured on 6 Oct; unchanged on go2rtc
master). Each stream is therefore an exec: source: ffmpeg reads the camera
over RTSP, copies the video (no re-encoding), strips SEI NALs
(filter_units=remove_types=6), drops audio (Herman's decision 7) and pipes
MPEG-TS to go2rtc, which never runs its RTP depacketizer on a pipe. ffmpeg
logs nothing (-loglevel quiet), so its error text - which would contain the
camera address - can't reach go2rtc's log or its API. The password is on
ffmpeg's command line while it runs (Herman accepted that, 7 Oct).

Where WebRTC listens. go2rtc's API stays on 127.0.0.1:1984, but its WebRTC
media port (8555) listens on this laptop's LAN address (Herman's option A,
6 Oct): Windows refuses packets from a socket bound to the LAN address to
127.0.0.1 (WSAEADDRNOTAVAIL), and a browser's WebRTC sockets are bound to the
LAN address, so a loopback-only go2rtc can never be reached (measured in the
132 live check). The address comes from GO2RTC_WEBRTC_HOST, else from the
route to the registered camera, and is re-checked before every viewing, so a
DHCP change rewrites the config and start.ps1 relaunches go2rtc. The
laptop's own browser reaches that address without leaving the machine; other
devices are kept out by Windows Firewall's inbound rules for go2rtc.

Signaling (T3). open_stream() forwards the browser's SDP offer to go2rtc's
POST /api/webrtc?src=<stream name> and returns the answer. go2rtc's error
bodies are never passed on or logged: they aren't masked like its logs and
can carry RTSP error text. Every failure becomes one fixed sentence.
"""
import ipaddress
import logging
import os
import re
import socket
import tempfile
import threading
import time
from typing import Iterable, Optional

import httpx

from config.settings import settings
from models.cctv import CCTV
from repositories.cctv_repository import cctv_repository

log = logging.getLogger(__name__)

QUALITIES = {"sub": "stream2", "main": "stream1"}   # sub is the default; main is the HD option
RTSP_PORT = 554
WEBRTC_PORT = 8555
ONLINE_THRESHOLD_S = 10.0      # same rule as the dashboard (useCCTVHeartbeats.ts ONLINE_THRESHOLD_MS)
MAX_OFFER_BYTES = 64 * 1024    # a browser's video-only offer is a few KB
_CONNECT_TIMEOUT_S = 2.0
_ANSWER_TIMEOUT_S = 20.0       # go2rtc dials the camera before answering; an unreachable one fails after ~10 s

# ffmpeg per stream: read the camera, copy the video, strip SEI (NAL type 6),
# no audio, MPEG-TS to stdout. Silent, so no error text carries the address.
FFMPEG_ARGS = ("-hide_banner -loglevel quiet -nostdin -fflags nobuffer -rtsp_transport tcp -i {camera} "
               "-map 0:v:0 -c:v copy -bsf:v filter_units=remove_types=6 -an "
               "-f mpegts -muxdelay 0 -muxpreload 0 -")

NOT_RUNNING = "Live view isn't running on the server"
NOT_LOADED = "Live view hasn't picked up this camera yet. Try again in a few seconds."
STREAM_FAILED = ("The camera's video couldn't be started. Check that the camera is online and that "
                 "VIGI_CAMERA_PASSWORD in backend/.env is right.")
TIMED_OUT = "The camera's video didn't start in time. Try again."
OFFLINE = "The camera is offline, so there's no live view."
NO_MAC = "This camera has no MAC address set, so it has no live view."
NO_IP = "This camera has no IP address set, so it has no live view."
NVR_LATER = "Live view for cameras behind an NVR isn't supported yet."
NOT_FOUND = "Camera not found."
BAD_OFFER = "The live-view request wasn't a video-only WebRTC offer."
NO_FFMPEG = "Live view isn't fully installed on the server: ffmpeg is missing from tools/go2rtc/bin."


class LiveViewError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# ── stream names and addresses ───────────────────────────────────────────────
def stream_name(cam: CCTV, quality: str) -> str:
    """"ipc_98BA5F8B1003_1_sub" for camera_key "ipc:98BA5F8B1003:1"."""
    return f"{cam.camera_key.replace(':', '_')}_{quality}"


def ffmpeg_path() -> str:
    """settings.GO2RTC_FFMPEG_PATH with forward slashes: it goes into YAML
    double-quoted strings, where a backslash would be an escape."""
    return settings.GO2RTC_FFMPEG_PATH.replace("\\", "/")


def source_url(cam: CCTV, quality: str) -> str:
    """The one place a stream source is built: go2rtc's exec: running ffmpeg
    on the camera's RTSP address. That address holds the password only as
    go2rtc's ${VIGI_CAMERA_PASSWORD} variable, and the source only ever goes
    into the config file - never into a response, a log line or the browser."""
    if cam.source_type == "nvr":
        # An NVR's per-channel RTSP path is UNCONFIRMED (design §8).
        raise NotImplementedError("NVR streams are not supported yet")
    if cam.source_type != "ipc":
        raise ValueError(f"unknown source type {cam.source_type!r}")
    if not cam.ip:
        raise ValueError("camera has no IP")
    camera = f"rtsp://admin:${{VIGI_CAMERA_PASSWORD}}@{cam.ip}:{RTSP_PORT}/{QUALITIES[quality]}"
    return f"exec:{ffmpeg_path()} " + FFMPEG_ARGS.format(camera=camera)


# ── the config file (T2) ─────────────────────────────────────────────────────
_HEADER = """\
# go2rtc config for SKYE live view (Prompt 132). GENERATED by the backend
# (services/live_view_service.py) from the camera registry - don't edit it:
# it's rewritten after every camera create, edit or delete, and
# tools/go2rtc/start.ps1 relaunches go2rtc whenever it changes.
# The camera password is never written here. Each stream address holds the
# variable VIGI_CAMERA_PASSWORD, which go2rtc fills in from its environment
# (start.ps1 reads it from backend/.env).

app:
  modules: [api, webrtc, exec]   # nothing else loads: no RTSP server, no HomeKit SRTP on :8443

api:
  listen: "127.0.0.1:1984"
  allow_paths: ["/api", "/api/webrtc"]   # no web UI, no stream/config/log API, so no new streams

log:
  output: "file:go2rtc.log"      # next to this file: start.ps1 runs go2rtc in this folder
  format: text
  level: info
"""

_EXEC_BLOCK = """\
exec:
  allow_paths: ["{ffmpeg}"]   # exec: may run this ffmpeg and nothing else
"""

_WEBRTC_BLOCK = """\
webrtc:
  listen: "{host}:{port}"   # media only; the API above stays on loopback
  candidates: ["{host}:{port}"]
  ice_servers: []                # no STUN or TURN
  filters:
{loopback}    candidates: ["{host}"]
    networks: [udp4, tcp4]
  # This laptop's own browser reaches that address without leaving the
  # machine. Other devices are kept out by Windows Firewall's inbound Block
  # rules for go2rtc (made when its network prompt was refused). Viewing from
  # other devices (later; not built) is an inbound Allow rule for TCP and
  # UDP 8555 instead, which Herman adds himself.
"""


def _ipv4(value) -> Optional[str]:
    try:
        return str(ipaddress.IPv4Address(str(value).strip()))
    except ValueError:
        return None


def _route_source(ip: str) -> Optional[str]:
    """The local address this machine uses to reach ip. A UDP connect only
    looks up the route; nothing is sent."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((ip, RTSP_PORT))
            return _ipv4(s.getsockname()[0])
    except OSError:
        return None


def webrtc_host(cameras: Iterable[CCTV]) -> str:
    """Where go2rtc's WebRTC media listens: GO2RTC_WEBRTC_HOST if set, else
    this laptop's address towards the registered camera (its LAN address),
    else 127.0.0.1 (no camera, nothing to stream)."""
    configured = settings.GO2RTC_WEBRTC_HOST
    if configured:
        host = _ipv4(configured)
        if host:
            return host
        log.warning("[LIVE] GO2RTC_WEBRTC_HOST=%r isn't an IPv4 address; using the LAN address instead", configured)
    for cam in sorted((c for c in cameras if c.ip), key=lambda c: c.camera_key or ""):
        host = _route_source(cam.ip)
        if host and host != "0.0.0.0":
            return host
    return "127.0.0.1"


def render_config(cameras: Iterable[CCTV], host: Optional[str] = None) -> str:
    """The whole config file for these cameras, with WebRTC on host (default
    webrtc_host()). Deterministic (sorted by camera_key), so an unchanged
    registry and address render byte-identical text."""
    cameras = list(cameras)
    host = host or webrtc_host(cameras)
    lines = []
    for cam in sorted((c for c in cameras if c.camera_key), key=lambda c: c.camera_key):
        if not cam.ip:
            lines.append(f"  # {stream_name(cam, 'sub')[:-4]}: no IP set, no live view")
            continue
        try:
            sources = {q: source_url(cam, q) for q in QUALITIES}
        except (NotImplementedError, ValueError) as e:
            lines.append(f"  # {stream_name(cam, 'sub')[:-4]}: {e}")
            continue
        for quality, url in sources.items():
            lines.append(f'  "{stream_name(cam, quality)}": "{url}"')
    streams = "streams:\n" + "\n".join(lines) + "\n" if lines else "streams: {}\n"
    webrtc = _WEBRTC_BLOCK.format(host=host, port=WEBRTC_PORT,
                                  loopback="    loopback: true\n" if host.startswith("127.") else "")
    return _HEADER + "\n" + _EXEC_BLOCK.format(ffmpeg=ffmpeg_path()) + "\n" + webrtc + "\n" + streams


_write_lock = threading.Lock()


def _replace(tmp: str, path: str) -> None:
    # os.replace can hit a sharing violation on Windows while another process
    # (go2rtc loading the file) has it open; that lasts milliseconds.
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.1)


def write_config() -> bool:
    """Render the config from a fresh registry read; write it, atomically,
    only if it differs from what's on disk. True when the file was written."""
    cameras = cctv_repository.get_all_global()   # fresh read, not cctv_service's 30 s cache
    host = webrtc_host(cameras)
    data = render_config(cameras, host).encode("utf-8")
    path = settings.GO2RTC_CONFIG_PATH
    with _write_lock:
        try:
            with open(path, "rb") as f:
                if f.read() == data:
                    return False
        except FileNotFoundError:
            pass
        folder = os.path.dirname(path)
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=folder)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            _replace(tmp, path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
    streams = data.count(b'": "exec:')
    log.info("[LIVE] go2rtc config written: %d stream(s), WebRTC on %s:%d, %s", streams, host, WEBRTC_PORT, path)
    return True


def refresh_config() -> None:
    """write_config() for the hooks (startup, camera create/edit/delete): a
    failure is logged and never fails the camera change itself."""
    try:
        write_config()
    except Exception:
        log.exception("[LIVE] couldn't write the go2rtc config to %s", settings.GO2RTC_CONFIG_PATH)


# ── signaling (T3) ───────────────────────────────────────────────────────────
_DIRECTIONS = ("a=sendrecv", "a=sendonly", "a=recvonly", "a=inactive")
_CANDIDATE = re.compile(r"^a=candidate:\S+ \d+ (\w+) \d+ (\S+) (\d+) typ", re.M)


def answer_candidates(sdp: str) -> str:
    """"127.0.0.1:8555 tcp, 127.0.0.1:8555 udp": where go2rtc told the browser
    to connect. Logged per connection, so the live check can show that only
    loopback was offered (addresses and ports, nothing secret)."""
    found = sorted({f"{host}:{port} {proto.lower()}" for proto, host, port in _CANDIDATE.findall(sdp)})
    return ", ".join(found) or "none"


def check_offer(sdp) -> None:
    """Only a video-only, receive-only offer is forwarded. go2rtc treats an
    offer that sends video as a publisher pushing into the stream, so an
    offer with any other direction or media is refused here (422)."""
    if not isinstance(sdp, str) or not sdp.startswith("v=0") or len(sdp.encode("utf-8")) > MAX_OFFER_BYTES:
        raise LiveViewError(422, BAD_OFFER)
    sections = []
    for line in sdp.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if line.startswith("m="):
            sections.append({"media": line, "dirs": set()})
        elif sections and line in _DIRECTIONS:
            sections[-1]["dirs"].add(line)
    if not sections:
        raise LiveViewError(422, BAD_OFFER)
    for sec in sections:
        if not sec["media"].startswith("m=video ") or sec["dirs"] != {"a=recvonly"}:
            raise LiveViewError(422, BAD_OFFER)


def camera_online(cam: CCTV, now: Optional[float] = None) -> bool:
    """The dashboard's rule: the camera's RTSP port answered TCP liveness in
    the last ONLINE_THRESHOLD_S seconds."""
    hb = cctv_repository.get_heartbeat(cam.device_mac) or {}
    last_seen = hb.get("last_seen")
    if not isinstance(last_seen, (int, float)) or isinstance(last_seen, bool):
        return False
    return (now if now is not None else time.time()) - last_seen < ONLINE_THRESHOLD_S


def _exchange(cam: CCTV, quality: str, sdp: str) -> str:
    name = stream_name(cam, quality)
    timeout = httpx.Timeout(_ANSWER_TIMEOUT_S, connect=_CONNECT_TIMEOUT_S)
    try:
        # trust_env=False: no system proxy may sit between the backend and a loopback go2rtc.
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(f"{settings.GO2RTC_API_URL}/api/webrtc", params={"src": name},
                               json={"type": "offer", "sdp": sdp})
    except (httpx.ConnectError, httpx.ConnectTimeout):
        log.info("[LIVE] %s %s: go2rtc isn't answering at %s", cam.camera_key, quality, settings.GO2RTC_API_URL)
        raise LiveViewError(503, NOT_RUNNING) from None
    except httpx.TimeoutException:
        log.info("[LIVE] %s %s: go2rtc didn't answer within %.0f s", cam.camera_key, quality, _ANSWER_TIMEOUT_S)
        raise LiveViewError(504, TIMED_OUT) from None
    except httpx.HTTPError as e:
        log.info("[LIVE] %s %s: go2rtc connection failed (%s)", cam.camera_key, quality, type(e).__name__)
        raise LiveViewError(503, NOT_RUNNING) from None

    if resp.status_code == 404:
        # The running go2rtc doesn't know this stream: start.ps1 is relaunching
        # it, or the config predates the camera. Rewriting is a no-op if current.
        log.info("[LIVE] %s %s: go2rtc doesn't have stream %s yet", cam.camera_key, quality, name)
        refresh_config()
        raise LiveViewError(503, NOT_LOADED)
    if resp.status_code != 200:
        # The body is go2rtc's error text: never passed on, never logged.
        log.info("[LIVE] %s %s: go2rtc answered %d (%d-byte body, not logged)",
                 cam.camera_key, quality, resp.status_code, len(resp.content))
        raise LiveViewError(502, STREAM_FAILED)
    try:
        answer = resp.json()
    except ValueError:
        answer = None
    sdp_answer = answer.get("sdp") if isinstance(answer, dict) and answer.get("type") == "answer" else None
    if not isinstance(sdp_answer, str) or not sdp_answer.startswith("v=0") or "rtsp://" in sdp_answer:
        log.info("[LIVE] %s %s: go2rtc's reply wasn't an SDP answer", cam.camera_key, quality)
        raise LiveViewError(502, STREAM_FAILED)
    return sdp_answer


def open_stream(building_id: str, floor_id: str, cctv_id: str, sdp, quality: str, user_id: str = "") -> dict:
    """One live-view connection: look up the camera, check it can stream,
    forward the browser's offer to go2rtc, return go2rtc's answer. The reply
    is the SDP answer only - never a stream address."""
    if quality not in QUALITIES:
        raise LiveViewError(422, "quality must be sub or main.")
    cam = cctv_repository.get_by_id(building_id, floor_id, cctv_id)
    if cam is None:
        raise LiveViewError(404, NOT_FOUND)
    check_offer(sdp)
    if cam.source_type == "nvr":
        raise LiveViewError(409, NVR_LATER)
    if not cam.camera_key:
        raise LiveViewError(409, NO_MAC)
    if not cam.ip:
        raise LiveViewError(409, NO_IP)
    if not camera_online(cam):
        raise LiveViewError(409, OFFLINE)
    # A no-op unless this laptop's LAN address changed since the last write
    # (DHCP); then start.ps1 relaunches go2rtc on the new one.
    refresh_config()
    if not os.path.isfile(settings.GO2RTC_FFMPEG_PATH):
        log.info("[LIVE] %s %s: ffmpeg isn't at %s", cam.camera_key, quality, settings.GO2RTC_FFMPEG_PATH)
        raise LiveViewError(503, NO_FFMPEG)
    answer = _exchange(cam, quality, sdp)
    log.info("[LIVE] %s opened %s (%s); answer candidates: %s",
             user_id or "an admin", cam.camera_key, quality, answer_candidates(answer))
    return {"type": "answer", "sdp": answer}
