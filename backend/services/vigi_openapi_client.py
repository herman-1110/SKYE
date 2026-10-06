"""Read-only VIGI camera OpenAPI client with a lockout guard (Prompt 131 T8).

Protocol (VIGI IPC Open API Document V1.1 §4.1.1, confirmed on the real
InSight S445 on 5 Oct): HTTPS on port 20443 with a self-signed certificate; a
new connection per call; doAuth twice (a challenge, then a SHA-256 digest
response) returns a stok that the camera ages out after 30 minutes; every
other call is POST /stok=<stok> {"method": ...}.

The camera locks its admin account after repeated failed logins (errCode
-10030), so logins are rationed:

- One shared client per camera_key: the registry's getTimeZone call and the
  health loop reuse the same stok, so registering a camera and then probing it
  costs one login.
- Before the password-bearing doAuth is sent, a marker file is written under
  backend/logs/ holding only the camera_key and backend/.env's modification
  time. A confirmed success deletes it. While it exists and .env hasn't
  changed, no login is attempted, across restarts. When .env's mtime moves,
  exactly one attempt is allowed (the marker is rewritten with the new mtime
  first). So a wrong or unconfirmed login happens at most once per change to
  .env, even if the process dies mid-attempt.

Never logged: the password, A1 (which answers any nonce), the digest
response, the nonce, the stok, or a URL containing the stok.
"""
import hashlib
import http.client
import json
import logging
import os
import ssl
import threading
import time
from pathlib import Path
from typing import Optional

from config.settings import settings

log = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = _BACKEND_DIR / ".env"
MARKER_DIR = _BACKEND_DIR / "logs"

OPENAPI_PORT = 20443
STOK_TTL_S = 25 * 60          # the camera ages a stok out after 30 min (doc §4.1.1)
DEFAULT_TIMEOUT_S = 5.0

ERR_UNAUTHORIZED = -10003     # stok missing or expired
_LOGIN_ERRORS = {
    -10021: "authentication failed or wrong password",
    -10022: "too many clients logged in",
    -10030: "too many failed attempts; the account is locked",
}


class OpenApiError(Exception):
    """Base class. Messages never contain secrets."""


class OpenApiNoCredentials(OpenApiError):
    pass


class OpenApiAuthBlocked(OpenApiError):
    """A previous login failed (or was never confirmed) and backend/.env hasn't changed since."""


class OpenApiAuthFailed(OpenApiError):
    """The camera rejected the login, or the reply never came. The marker stays."""


class OpenApiUnreachable(OpenApiError):
    """Network or TLS failure, or a reply that wasn't JSON. No password was sent."""


def _env_mtime_ns() -> Optional[int]:
    try:
        return ENV_PATH.stat().st_mtime_ns
    except OSError:
        return None


class LockoutGuard:
    def _path(self, camera_key: str) -> Path:
        safe = "".join(ch if ch.isalnum() else "_" for ch in camera_key)
        return MARKER_DIR / f"vigi-openapi-lockout-{safe}.json"

    def blocked(self, camera_key: str) -> bool:
        """True while a marker exists and .env is unchanged since it was written."""
        path = self._path(camera_key)
        if not path.exists():
            return False
        current = _env_mtime_ns()
        try:
            recorded = json.loads(path.read_text(encoding="utf-8")).get("env_mtime_ns")
        except (OSError, ValueError):
            # Unreadable marker: unblock only if .env changed after it was written.
            try:
                return current is None or current <= path.stat().st_mtime_ns
            except OSError:
                return True
        return recorded == current

    def arm(self, camera_key: str) -> None:
        """Written before every password-bearing doAuth."""
        MARKER_DIR.mkdir(parents=True, exist_ok=True)
        self._path(camera_key).write_text(
            json.dumps({"camera_key": camera_key, "env_mtime_ns": _env_mtime_ns()}), encoding="utf-8")

    def clear(self, camera_key: str) -> None:
        try:
            self._path(camera_key).unlink()
        except FileNotFoundError:
            pass

    def marker_exists(self, camera_key: str) -> bool:
        return self._path(camera_key).exists()


lockout_guard = LockoutGuard()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class VigiOpenApiClient:
    def __init__(self, camera_key: str, host: str, port: int = OPENAPI_PORT) -> None:
        self.camera_key = camera_key
        self.host = host
        self.port = port
        self._lock = threading.Lock()
        self._stok: Optional[str] = None
        self._stok_at = 0.0
        self.logins_attempted = 0   # password-bearing doAuth requests sent by this client

    def _post(self, body: dict, with_stok: bool, timeout: float) -> dict:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE    # the camera's certificate is self-signed; this client only
        path = f"/stok={self._stok}" if with_stok and self._stok else "/"
        conn = http.client.HTTPSConnection(self.host, self.port, timeout=timeout, context=ctx)
        try:
            conn.request("POST", path, body=json.dumps(body), headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            raw = resp.read()
        except (OSError, http.client.HTTPException) as e:
            raise OpenApiUnreachable(f"{type(e).__name__} talking to {self.host}:{self.port}") from None
        finally:
            conn.close()
        try:
            reply = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            raise OpenApiUnreachable(f"non-JSON reply from {self.host}:{self.port} (HTTP {resp.status})") from None
        if not isinstance(reply, dict):
            raise OpenApiUnreachable(f"unexpected reply shape from {self.host}:{self.port}")
        return reply

    def _login(self, timeout: float) -> None:
        password = settings.VIGI_CAMERA_PASSWORD
        if not password:
            raise OpenApiNoCredentials("VIGI_CAMERA_PASSWORD is not set")
        if lockout_guard.blocked(self.camera_key):
            raise OpenApiAuthBlocked(
                f"a previous OpenAPI login for {self.camera_key} failed; waiting for backend/.env to change")

        challenge = self._post({"method": "doAuth", "params": None}, with_stok=False, timeout=timeout)
        auth = challenge.get("authenticate") or {}
        realm, nonce = auth.get("realm"), auth.get("nonce")
        method, uri = auth.get("method") or "POST", auth.get("uri") or "doAuth"
        if not realm or not nonce:
            raise OpenApiUnreachable(f"doAuth returned no challenge (errCode {challenge.get('errCode')})")
        if (auth.get("algorithm") or "SHA-256").upper() != "SHA-256":
            raise OpenApiUnreachable(f"unexpected doAuth algorithm {auth.get('algorithm')!r}")

        lockout_guard.arm(self.camera_key)
        self.logins_attempted += 1
        log.info("[VIGI] OpenAPI login for %s", self.camera_key)
        a1 = _sha256(f"admin:{realm}:{password}")
        response = _sha256(f"{a1}:{nonce}:{_sha256(f'{method}:{uri}')}")
        try:
            reply = self._post({"method": "doAuth", "params": {"nonce": nonce, "response": response}},
                               with_stok=False, timeout=timeout)
        except OpenApiUnreachable:
            log.warning("[VIGI] OpenAPI login for %s unconfirmed (no reply); no retry until backend/.env changes",
                        self.camera_key)
            raise OpenApiAuthFailed("login unconfirmed: the camera never replied") from None
        finally:
            del a1, response
        code = reply.get("errCode")
        stok = reply.get("stok")
        if code == 0 and isinstance(stok, str) and stok:
            self._stok = stok
            self._stok_at = time.monotonic()
            lockout_guard.clear(self.camera_key)
            return
        meaning = _LOGIN_ERRORS.get(code, "login rejected")
        log.warning("[VIGI] OpenAPI login for %s failed: errCode %s (%s); no retry until backend/.env changes",
                    self.camera_key, code, meaning)
        raise OpenApiAuthFailed(f"errCode {code} ({meaning})")

    def call(self, method: str, timeout: float = DEFAULT_TIMEOUT_S) -> dict:
        """One read-only call. Logs in first when there's no valid stok, and at
        most once per call."""
        with self._lock:
            logged_in_now = False
            if not self._stok or time.monotonic() - self._stok_at > STOK_TTL_S:
                self._stok = None
                self._login(timeout)
                logged_in_now = True
            reply = self._post({"method": method}, with_stok=True, timeout=timeout)
            if reply.get("errCode") == ERR_UNAUTHORIZED and not logged_in_now:
                # The camera dropped our stok (reboot, or aged out early).
                self._stok = None
                self._login(timeout)
                reply = self._post({"method": method}, with_stok=True, timeout=timeout)
            return reply


class _ClientRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clients: dict[str, VigiOpenApiClient] = {}

    def get(self, camera_key: str, host: str) -> VigiOpenApiClient:
        with self._lock:
            client = self._clients.get(camera_key)
            if client is None or client.host != host:
                client = VigiOpenApiClient(camera_key, host)
                self._clients[camera_key] = client
            return client

    def drop(self, camera_key: Optional[str]) -> None:
        if not camera_key:
            return
        with self._lock:
            self._clients.pop(camera_key, None)


openapi_clients = _ClientRegistry()
