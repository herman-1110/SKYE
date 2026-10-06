"""Camera health: TCP liveness and the OpenAPI check (Prompt 131 T8).

Both loops start in main.py's lifespan, next to _man_down_stale_loop, and
write /cctv_heartbeats/{AA_BB_CC_DD_EE_FF} through
cctv_repository.update_heartbeat (partial updates, shared with alarm ingest):

  last_seen      unix s of the last successful TCP connect to ip:554
  last_event_at  unix s of the last accepted alarm push (vigi_service)
  device_name    as the camera names itself
  probe          "ok" | "auth_error" | "no_credentials" | "unreachable" | "error"
  probe_ok_at    unix s of the last probe == "ok"; absent until the first one,
                 which is how the dashboard tells "never verified" apart
  alarm_config   "mismatch" | "unknown" - see _alarm_config()

Liveness: every VIGI_LIVENESS_INTERVAL_S (5 s, Herman's decision 5) an async
TCP connect with a 2 s timeout to each registered camera's ip:554. A success
writes last_seen; a failure writes nothing, so the hook's 10 s threshold turns
the camera offline. No credentials are involved.

OpenAPI: first run VIGI_OPENAPI_START_DELAY_S after startup, then every
VIGI_OPENAPI_INTERVAL_S, one camera at a time, through the shared,
lockout-guarded client in vigi_openapi_client.

Per-process, like _man_down_stale_loop: under more than one worker each
would probe on its own.
"""
import asyncio
import logging
import time
from typing import Dict

from config.settings import settings
from models.cctv import CCTV
from repositories.cctv_repository import cctv_repository
from services.cctv_service import cctv_service
from services.vigi_openapi_client import (
    OpenApiAuthBlocked, OpenApiAuthFailed, OpenApiError, OpenApiNoCredentials, OpenApiUnreachable,
    openapi_clients,
)

log = logging.getLogger(__name__)

RTSP_PORT = 554
TCP_TIMEOUT_S = 2.0
CLOCK_DRIFT_WARN_S = 10.0
_LOOP_ERROR_LOG_EVERY_S = 600.0


class CameraHealthService:
    def __init__(self) -> None:
        self._last_logged: Dict[str, float] = {}

    def _log_limited(self, key: str, every_s: float, level: int, msg: str, *args, **kwargs) -> None:
        now = time.monotonic()
        last = self._last_logged.get(key)
        if last is not None and now - last < every_s:
            return
        self._last_logged[key] = now
        log.log(level, msg, *args, **kwargs)

    @staticmethod
    def _devices() -> Dict[str, CCTV]:
        """One registered camera per reporting device that has an IP."""
        devices: Dict[str, CCTV] = {}
        for cam in cctv_service.all_cameras():
            if cam.device_mac and cam.ip and cam.device_mac not in devices:
                devices[cam.device_mac] = cam
        return devices

    # ── TCP liveness ─────────────────────────────────────────────────────────
    @staticmethod
    async def _tcp_ok(ip: str) -> bool:
        try:
            _reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, RTSP_PORT), TCP_TIMEOUT_S)
        except (OSError, asyncio.TimeoutError):
            return False
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), 1.0)
        except Exception:
            pass
        return True

    async def liveness_once(self) -> Dict[str, bool]:
        devices = await asyncio.to_thread(self._devices)
        if not devices:
            return {}
        results = await asyncio.gather(*(self._tcp_ok(cam.ip) for cam in devices.values()))
        now_s = int(time.time())
        for mac, ok in zip(devices, results):
            if ok:
                await asyncio.to_thread(cctv_repository.update_heartbeat, mac, {"last_seen": now_s})
        return dict(zip(devices, results))

    async def liveness_loop(self) -> None:
        while True:
            try:
                await self.liveness_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                self._log_limited("liveness", _LOOP_ERROR_LOG_EVERY_S, logging.ERROR,
                                  "[VIGI] camera liveness sweep failed, will retry", exc_info=True)
            await asyncio.sleep(settings.VIGI_LIVENESS_INTERVAL_S)

    # ── OpenAPI ──────────────────────────────────────────────────────────────
    @staticmethod
    def _alarm_config(client) -> str:
        """A2. "ok" would need the camera's Alarm Server entry (path, port 8000,
        this machine's address) plus human detection set to "Send to Alarm
        Server". The VIGI IPC Open API Document V1.1 has no method that reads
        the Alarm Server settings or a processing mode (Prompt 131 D3), so "ok"
        can't be proven and is never returned. What can be read is
        getPeopleDetectionSwitch: human detection switched off means a broken
        setup -> "mismatch". Anything else -> "unknown"."""
        try:
            reply = client.call("getPeopleDetectionSwitch")
        except OpenApiUnreachable:
            return "unknown"
        if reply.get("errCode") != 0:
            return "unknown"
        enabled = (reply.get("result") or {}).get("enabled")
        return "mismatch" if enabled == "off" else "unknown"

    def openapi_check(self, cam: CCTV) -> dict:
        """One health check for one camera. Returns the heartbeat fields written."""
        values: dict = {}
        if not settings.VIGI_CAMERA_PASSWORD:
            values["probe"] = "no_credentials"
        else:
            client = openapi_clients.get(cam.camera_key, cam.ip)
            try:
                status = client.call("getDeviceStatus")
                if status.get("errCode") == 0:
                    values["probe"] = "ok"
                    values["probe_ok_at"] = int(time.time())
                else:
                    values["probe"] = "error"
                    self._log_limited(f"status:{cam.camera_key}", _LOOP_ERROR_LOG_EVERY_S, logging.WARNING,
                                      "[VIGI] getDeviceStatus for %s returned errCode %s",
                                      cam.camera_key, status.get("errCode"))
                t0 = time.time()
                clock = client.call("getSystemTime")
                t1 = time.time()
                camera_s = (clock.get("result") or {}).get("system_time")
                if isinstance(camera_s, (int, float)) and not isinstance(camera_s, bool):
                    drift = camera_s - (t0 + t1) / 2
                    if abs(drift) > CLOCK_DRIFT_WARN_S:
                        log.warning("[VIGI] camera %s clock is %+.0f s off this server", cam.camera_key, drift)
                values["alarm_config"] = self._alarm_config(client)
            except (OpenApiAuthFailed, OpenApiAuthBlocked) as e:
                values["probe"] = "auth_error"
                self._log_limited(f"auth:{cam.camera_key}", 3600.0, logging.WARNING,
                                  "[VIGI] OpenAPI checks for %s stopped: %s. Fix VIGI_CAMERA_PASSWORD in "
                                  "backend/.env (saving the file allows one new attempt).", cam.camera_key, e)
            except OpenApiNoCredentials:
                values["probe"] = "no_credentials"
            except OpenApiUnreachable as e:
                values["probe"] = "unreachable"
                self._log_limited(f"unreach:{cam.camera_key}", _LOOP_ERROR_LOG_EVERY_S, logging.INFO,
                                  "[VIGI] OpenAPI check for %s: %s", cam.camera_key, e)
            except OpenApiError as e:
                values["probe"] = "error"
                self._log_limited(f"err:{cam.camera_key}", _LOOP_ERROR_LOG_EVERY_S, logging.WARNING,
                                  "[VIGI] OpenAPI check for %s failed: %s", cam.camera_key, e)
        cctv_repository.update_heartbeat(cam.device_mac, values)
        return values

    def check_now(self, cam: CCTV) -> None:
        """One OpenAPI check right after a camera is registered or its ip/MAC
        changes, so the dashboard doesn't wait up to VIGI_OPENAPI_INTERVAL_S
        for its first status. Run as a background task after the response.
        Reuses the stok the registration's getTimeZone call just obtained, so
        it costs no extra login."""
        if not (cam.camera_key and cam.ip and cam.device_mac):
            return
        try:
            self.openapi_check(cam)
        except Exception:
            self._log_limited(f"now:{cam.camera_key}", _LOOP_ERROR_LOG_EVERY_S, logging.ERROR,
                              "[VIGI] first OpenAPI check for %s failed", cam.camera_key, exc_info=True)

    async def openapi_loop(self) -> None:
        await asyncio.sleep(settings.VIGI_OPENAPI_START_DELAY_S)
        if not settings.VIGI_CAMERA_PASSWORD:
            log.info("[VIGI] VIGI_CAMERA_PASSWORD is not set: OpenAPI health checks are off (TCP liveness still runs)")
        while True:
            try:
                devices = await asyncio.to_thread(self._devices)
                for cam in devices.values():
                    await asyncio.to_thread(self.openapi_check, cam)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._log_limited("openapi", _LOOP_ERROR_LOG_EVERY_S, logging.ERROR,
                                  "[VIGI] camera OpenAPI sweep failed, will retry", exc_info=True)
            await asyncio.sleep(settings.VIGI_OPENAPI_INTERVAL_S)


camera_health_service = CameraHealthService()
