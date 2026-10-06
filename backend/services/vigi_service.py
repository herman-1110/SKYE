"""VIGI camera alarm ingest (Prompt 131 T4, docs/vigi-integration-design.md §3).

The camera's Alarm Server posts to /vigi/alarm/<VIGI_ALARM_PATH_SECRET>
(routes/vigi_routes.py checks the secret and calls handle_alarm() in a worker
thread). This module never sees the path, and never takes
positioning_service.pipeline_lock: camera events must not queue behind
position solves.

Who's accepted:
- a registered camera posting from its registered ip: its detections go to
  the in-memory buffer and its heartbeat's last_event_at is updated;
- a registered MAC from any other address: nothing is recorded, one warning
  per camera every 10 minutes;
- an unregistered MAC: only its heartbeat is written (online, not placed on
  any floor), logged once per device every 10 minutes - as APs are.

Replaces the old /vigi/detection heartbeat writer (removed in 131 T6; nothing
called it).
"""
import hmac
import json
import logging
import re
import threading
import time
from datetime import datetime
from typing import Optional

from config.settings import VIGI_ALARM_PATH_SECRET_MIN_LEN, settings
from repositories.cctv_repository import cctv_repository
from services.camera_detection_buffer import detection_buffer
from services.cctv_service import cctv_service
from services.vigi_alarm_parser import parse_ipc_alarm
from utils.mac_utils import InvalidMacError, normalize_mac

log = logging.getLogger(__name__)

_LOG_EVERY_S = 600.0
_MAX_LOG_KEYS = 1000


def _json_or_none(data: bytes):
    try:
        return json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return None


def _multipart_json(raw: bytes, content_type: str):
    """The first JSON part of a multipart body; image parts are dropped
    unread. The camera's multipart form (attached image on) is documented by
    TP-Link but was never captured here - images stay off."""
    m = re.search(r'boundary="?([^";]+)"?', content_type, re.IGNORECASE)
    if not m:
        return None
    delimiter = b"--" + m.group(1).strip().encode("latin-1", "replace")
    for segment in raw.split(delimiter)[1:]:
        if segment.startswith(b"--"):
            break
        if segment.startswith(b"\r\n"):
            segment = segment[2:]
        elif segment.startswith(b"\n"):
            segment = segment[1:]
        split, gap = segment.find(b"\r\n\r\n"), 4
        if split == -1:
            split, gap = segment.find(b"\n\n"), 2
        if split == -1:
            continue
        headers = segment[:split].decode("latin-1").lower()
        content = segment[split + gap:]
        if content.endswith(b"\r\n"):
            content = content[:-2]
        if "content-type: image/" in headers or content[:2] == b"\xff\xd8" or content[:4] == b"\x89PNG":
            continue
        obj = _json_or_none(content)
        if isinstance(obj, dict):
            return obj
    return None


class VigiService:
    def __init__(self) -> None:
        self._log_lock = threading.Lock()
        self._last_logged: dict = {}

    # ── the path secret ──────────────────────────────────────────────────────
    @staticmethod
    def secret_configured() -> bool:
        return len(settings.VIGI_ALARM_PATH_SECRET) >= VIGI_ALARM_PATH_SECRET_MIN_LEN

    def path_secret_ok(self, path_secret: str) -> bool:
        """Constant-time check. Bytes, because compare_digest refuses non-ASCII
        str and a percent-decoded path segment can be anything."""
        if not self.secret_configured():
            return False
        return hmac.compare_digest(path_secret.encode("utf-8", "surrogatepass"),
                                   settings.VIGI_ALARM_PATH_SECRET.encode("utf-8"))

    # ── logging, at most once per key every 10 minutes ───────────────────────
    def _log_limited(self, key, level: int, msg: str, *args, **kwargs) -> None:
        now = time.monotonic()
        with self._log_lock:
            last = self._last_logged.get(key)
            if last is not None and now - last < _LOG_EVERY_S:
                return
            if len(self._last_logged) >= _MAX_LOG_KEYS:
                self._last_logged.clear()
            self._last_logged[key] = now
        log.log(level, msg, *args, **kwargs)

    # ── ingest ───────────────────────────────────────────────────────────────
    @staticmethod
    def extract_json(raw: bytes, content_type: str) -> Optional[dict]:
        ctype = (content_type or "").lower()
        if ctype.startswith("application/json"):
            obj = _json_or_none(raw)
        elif ctype.startswith("multipart/form-data"):
            obj = _multipart_json(raw, content_type)
        else:
            return None
        return obj if isinstance(obj, dict) else None

    def handle_alarm(self, raw: bytes, content_type: str, source_ip: str, received_at: datetime) -> str:
        """Process one push. Returns the outcome (for tests and logs); the
        route answers 200 whatever it is, so the camera never retries."""
        try:
            body = self.extract_json(raw, content_type)
            if body is None:
                self._log_limited(("unsupported", source_ip), logging.WARNING,
                                  "[VIGI] ignored an alarm push from %s: unsupported or unreadable body (%s, %d bytes)",
                                  source_ip, (content_type or "no content-type").split(";")[0], len(raw))
                return "unsupported"
            if settings.VIGI_RAW_DUMP_ENABLED:
                print(f"[VIGI] raw alarm from {source_ip}: {json.dumps(body, ensure_ascii=False)}", flush=True)

            try:
                device_mac = normalize_mac(body.get("mac"))
            except InvalidMacError:
                self._log_limited(("no_mac", source_ip), logging.WARNING,
                                  "[VIGI] ignored an alarm push from %s: no valid camera MAC in the body", source_ip)
                return "no_mac"
            device_name = body.get("device_name")
            device_name = device_name[:80] if isinstance(device_name, str) else None
            now_s = int(time.time())

            cameras = cctv_service.cameras_for_device(device_mac)
            if not cameras:
                cctv_repository.update_heartbeat(device_mac, {"last_seen": now_s, "device_name": device_name})
                self._log_limited(("unregistered", device_mac), logging.INFO,
                                  "[VIGI] alarm from unregistered camera %s at %s: online but not placed on any floor - heartbeat written",
                                  device_mac, source_ip)
                return "unregistered"

            accepted = [c for c in cameras if c.ip and c.ip == source_ip]
            if not accepted:
                self._log_limited(("wrong_ip", device_mac), logging.WARNING,
                                  "[VIGI] WARNING: alarm for registered camera %s came from %s, not its registered IP %s - ignored",
                                  device_mac, source_ip, cameras[0].ip or "(none set)")
                return "wrong_ip"

            stats: dict = {}
            detections = parse_ipc_alarm(body, source_ip, received_at,
                                         camera_timezone=accepted[0].timezone, stats=stats)
            keys = {c.camera_key for c in accepted}
            kept = [d for d in detections if d.camera_key in keys]
            detection_buffer.add_many(kept)
            cctv_repository.update_heartbeat(device_mac, {"last_event_at": now_s, "device_name": device_name})
            if stats.get("skipped") or len(kept) < len(detections):
                self._log_limited(("skipped", device_mac), logging.WARNING,
                                  "[VIGI] alarm from %s: %d malformed event(s) skipped, %d event(s) on an unregistered channel",
                                  device_mac, stats.get("skipped", 0), len(detections) - len(kept))
            return "accepted"
        except Exception:
            self._log_limited(("error", source_ip), logging.ERROR,
                              "[VIGI] alarm push from %s failed; it was answered 200 and dropped", source_ip,
                              exc_info=True)
            return "error"


vigi_service = VigiService()
