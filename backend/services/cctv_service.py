"""Camera registry rules (Prompt 131 T2, docs/vigi-integration-design.md §1).

Cameras stay in the existing buildings/{b}/floors/{f}/cctvs collection; this
service adds the rules around it:
- MACs go through utils.mac_utils.normalize_mac (dashes, colons or none);
- (device_mac, channel) is unique across all floors (409);
- checkpoint_ap_id must be an AP on the camera's own floor (422);
- on create, and whenever ip changes, the camera's time zone is read once
  through the shared OpenAPI client (same lockout rules as the health loop),
  falling back to UTC+08:00 (Herman's decision 11);
- deleting a camera removes its /cctv_heartbeats node unless another camera
  still reports through the same device.

Errors are CameraError(status, plain-English message) so the dashboard can
show them as they are. A short-lived cache of all cameras serves the alarm
endpoint and the health loops without a Firestore read per push.
"""
import dataclasses
import ipaddress
import logging
import re
import threading
import time
import uuid
from typing import List, Optional

from models.cctv import CCTV, DEFAULT_CAMERA_TIMEZONE
from repositories.ap_repository import ap_repository
from repositories.cctv_repository import cctv_repository
from services.camera_detection_buffer import detection_buffer
from services.vigi_openapi_client import (
    OpenApiAuthBlocked, OpenApiAuthFailed, OpenApiError, openapi_clients,
)
from utils.mac_utils import InvalidMacError, normalize_mac
from utils.timestamp_utils import utcnow_iso

log = logging.getLogger(__name__)

SOURCE_TYPES = ("ipc", "nvr")
_TZ_FORMAT = re.compile(r"^UTC[+-]\d{2}:\d{2}$")
_REGISTRATION_TIMEOUT_S = 3.0   # an admin is waiting on this request


class CameraError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class CCTVService:
    _CACHE_TTL_S = 30.0

    def __init__(self) -> None:
        self._cache_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._cache: Optional[List[CCTV]] = None
        self._cache_at = 0.0

    # ── reads ────────────────────────────────────────────────────────────────
    def all_cameras(self) -> List[CCTV]:
        with self._cache_lock:
            if self._cache is not None and time.monotonic() - self._cache_at < self._CACHE_TTL_S:
                return list(self._cache)
        cameras = cctv_repository.get_all_global()
        with self._cache_lock:
            self._cache = cameras
            self._cache_at = time.monotonic()
        return list(cameras)

    def invalidate(self) -> None:
        with self._cache_lock:
            self._cache = None

    def cameras_for_device(self, device_mac: str) -> List[CCTV]:
        return [c for c in self.all_cameras() if c.device_mac == device_mac]

    # ── validation ───────────────────────────────────────────────────────────
    @staticmethod
    def _clean_mac(value) -> Optional[str]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        try:
            return normalize_mac(value)
        except InvalidMacError as e:
            raise CameraError(422, str(e)) from None

    @staticmethod
    def _clean_ip(value) -> Optional[str]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        try:
            return str(ipaddress.IPv4Address(str(value).strip()))
        except ValueError:
            raise CameraError(422, "Invalid IP address: use the camera's IPv4 address, e.g. 192.168.0.101.") from None

    @staticmethod
    def _clean_channel(value) -> int:
        if value is None:
            return 1
        try:
            channel = int(value)
        except (TypeError, ValueError):
            channel = 0
        if isinstance(value, bool) or not 1 <= channel <= 256:
            raise CameraError(422, "Invalid channel: use a whole number from 1 to 256.")
        return channel

    @staticmethod
    def _clean_checkpoint(building_id: str, floor_id: str, ap_id) -> Optional[str]:
        if ap_id is None or (isinstance(ap_id, str) and not ap_id.strip()):
            return None
        ap_id = str(ap_id).strip()
        if ap_id not in {ap.id for ap in ap_repository.get_all(building_id, floor_id)}:
            raise CameraError(422, "That checkpoint isn't an access point on this floor.")
        return ap_id

    @staticmethod
    def _check_unique(device_mac: Optional[str], channel: int, exclude_id: Optional[str] = None) -> None:
        if not device_mac:
            return
        for cam in cctv_repository.get_all_global():     # fresh read, not the cache
            if cam.id != exclude_id and cam.device_mac == device_mac and cam.channel == channel:
                raise CameraError(
                    409,
                    f"A camera with MAC {device_mac} (channel {channel}) is already registered "
                    f"({cam.name!r} on floor {cam.floor_id}). Each camera can be registered once.")

    # ── time zone (decision 11) ──────────────────────────────────────────────
    def _read_timezone(self, cam: CCTV) -> str:
        if not cam.camera_key or not cam.ip:
            return DEFAULT_CAMERA_TIMEZONE
        try:
            client = openapi_clients.get(cam.camera_key, cam.ip)
            reply = client.call("getTimeZone", timeout=_REGISTRATION_TIMEOUT_S)
            tz = (reply.get("result") or {}).get("timezone")
            if reply.get("errCode") == 0 and isinstance(tz, str) and _TZ_FORMAT.match(tz):
                return tz
            log.info("[VIGI] getTimeZone for %s returned errCode %s; using %s",
                     cam.camera_key, reply.get("errCode"), DEFAULT_CAMERA_TIMEZONE)
        except (OpenApiAuthFailed, OpenApiAuthBlocked) as e:
            log.warning("[VIGI] time zone for %s not read (%s); using %s", cam.camera_key, e, DEFAULT_CAMERA_TIMEZONE)
            try:
                cctv_repository.update_heartbeat(cam.device_mac, {"probe": "auth_error"})
            except Exception:
                pass
        except OpenApiError as e:
            log.info("[VIGI] time zone for %s not read (%s); using %s", cam.camera_key, e, DEFAULT_CAMERA_TIMEZONE)
        except Exception:
            log.exception("[VIGI] time zone read for %s failed unexpectedly; using %s",
                          cam.camera_key, DEFAULT_CAMERA_TIMEZONE)
        return DEFAULT_CAMERA_TIMEZONE

    # ── writes ───────────────────────────────────────────────────────────────
    def create(self, building_id: str, floor_id: str, *, name: str, x_pct: float, y_pct: float,
               mac=None, ip=None, checkpoint_ap_id=None, channel=None, source_type=None) -> CCTV:
        source_type = (source_type or "ipc").strip().lower()
        if source_type not in SOURCE_TYPES:
            raise CameraError(422, "Invalid source type: use ipc (or nvr, later).")
        mac = self._clean_mac(mac)
        cam = CCTV(
            id=str(uuid.uuid4()),
            floor_id=floor_id,
            building_id=building_id,
            name=(name or "").strip() or "CCTV",
            x_pct=x_pct,
            y_pct=y_pct,
            created_at=utcnow_iso(),
            mac=mac,
            source_type=source_type,
            device_mac=mac,
            channel=self._clean_channel(channel),
            ip=self._clean_ip(ip),
            checkpoint_ap_id=self._clean_checkpoint(building_id, floor_id, checkpoint_ap_id),
        )
        with self._write_lock:
            self._check_unique(cam.device_mac, cam.channel)
            cctv_repository.save(building_id, floor_id, cam)
        self.invalidate()
        # Outside the write lock: this can take a few seconds on an unreachable camera.
        cam.timezone = self._read_timezone(cam)
        cctv_repository.update_fields(building_id, floor_id, cam.id, {"timezone": cam.timezone})
        self.invalidate()
        return cam

    def update(self, building_id: str, floor_id: str, cctv_id: str, changes: dict) -> CCTV:
        old = cctv_repository.get_by_id(building_id, floor_id, cctv_id)
        if old is None:
            raise CameraError(404, "Camera not found.")
        new = dataclasses.replace(old)
        if "name" in changes:
            new.name = (changes["name"] or "").strip() or "CCTV"
        if "mac" in changes:
            new.mac = self._clean_mac(changes["mac"])
            new.device_mac = new.mac
        if "channel" in changes:
            new.channel = self._clean_channel(changes["channel"])
        if "ip" in changes:
            new.ip = self._clean_ip(changes["ip"])
        if "checkpoint_ap_id" in changes:
            new.checkpoint_ap_id = self._clean_checkpoint(building_id, floor_id, changes["checkpoint_ap_id"])

        fields = ("name", "mac", "device_mac", "channel", "ip", "checkpoint_ap_id")
        with self._write_lock:
            if (new.device_mac, new.channel) != (old.device_mac, old.channel):
                self._check_unique(new.device_mac, new.channel, exclude_id=old.id)
            diff = {f: getattr(new, f) for f in fields if getattr(new, f) != getattr(old, f)}
            if diff:
                cctv_repository.update_fields(building_id, floor_id, cctv_id, diff)
        self.invalidate()

        if old.camera_key != new.camera_key:
            detection_buffer.drop(old.camera_key)
        if old.camera_key != new.camera_key or old.ip != new.ip:
            openapi_clients.drop(old.camera_key)
        if old.device_mac and old.device_mac != new.device_mac:
            self._drop_heartbeat_if_unused(old.device_mac, exclude_id=old.id)
        if new.ip != old.ip and new.device_mac:
            # The registered IP was just edited: drop discovery's ip_mismatch
            # warning now rather than at the next round (Prompt 131b).
            try:
                cctv_repository.update_heartbeat(new.device_mac, {}, remove=["ip_mismatch"])
            except Exception:
                log.warning("[VIGI] couldn't clear ip_mismatch for %s", new.device_mac)
        if new.ip != old.ip:
            new.timezone = self._read_timezone(new) if new.ip else (old.timezone or DEFAULT_CAMERA_TIMEZONE)
            if new.timezone != old.timezone:
                cctv_repository.update_fields(building_id, floor_id, cctv_id, {"timezone": new.timezone})
                self.invalidate()
        return new

    def delete(self, building_id: str, floor_id: str, cctv_id: str) -> None:
        cam = cctv_repository.get_by_id(building_id, floor_id, cctv_id)
        cctv_repository.delete(building_id, floor_id, cctv_id)
        self.invalidate()
        if cam is None:
            return
        detection_buffer.drop(cam.camera_key)
        openapi_clients.drop(cam.camera_key)
        if cam.device_mac:
            self._drop_heartbeat_if_unused(cam.device_mac, exclude_id=cam.id)

    def unlink_ap(self, building_id: str, floor_id: str, ap_id: str) -> int:
        """Called when an AP is deleted: cameras that covered it cover nothing."""
        unlinked = 0
        for cam in cctv_repository.get_all(building_id, floor_id):
            if cam.checkpoint_ap_id == ap_id:
                cctv_repository.update_fields(building_id, floor_id, cam.id, {"checkpoint_ap_id": None})
                unlinked += 1
        if unlinked:
            self.invalidate()
        return unlinked

    @staticmethod
    def _drop_heartbeat_if_unused(device_mac: str, exclude_id: str) -> None:
        if any(c.device_mac == device_mac and c.id != exclude_id for c in cctv_repository.get_all_global()):
            return
        cctv_repository.delete_cctv_heartbeat(device_mac)


cctv_service = CCTVService()
