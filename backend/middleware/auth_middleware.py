import ipaddress
import logging
import time
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request

import firebase_admin.auth
import hmac
from config.settings import settings
from models.user import UserRecord
from repositories.user_repository import user_repository

log = logging.getLogger(__name__)

# Fixed sentences for the ingest source checks (Prompt 135, SEC-01).
LOOPBACK_ONLY = "This endpoint only accepts requests from this machine."
SOURCE_NOT_ALLOWED = "This address isn't allowed to send AP reports."
_REJECT_LOG_EVERY_S = 600.0
_rejected_logged: dict = {}   # source address -> monotonic time of its last "rejected source" line


def _client_ip(request: Request):
    """The caller's address as an ipaddress object, or None when the host
    isn't an IP address at all (Starlette's TestClient reports "testclient").
    An IPv4-mapped IPv6 address (::ffff:a.b.c.d) is read as the IPv4 one, so a
    future dual-stack bind doesn't change the answers below."""
    host = request.client.host if request.client else ""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip


async def require_loopback(request: Request) -> None:
    """/telemetry is the simulators' and the harness's route, and they only
    ever call it on this machine (Prompt 135, SEC-01). Any 127.0.0.0/8 address
    or ::1 is accepted. Everything else - including a host that isn't an IP
    address - gets 403 with a fixed sentence, before the token is looked at."""
    ip = _client_ip(request)
    if ip is None or not ip.is_loopback:
        raise HTTPException(status_code=403, detail=LOOPBACK_ONLY)


async def verify_omada_source(request: Request) -> None:
    """/telemetry/omada: when OMADA_INGEST_ALLOWED_IPS is set, only those
    addresses may post AP reports (Prompt 135, SEC-01). Runs before the token
    check, so an unlisted address learns nothing about the token. Each rejected
    address is logged at most once every 10 minutes. Unset: no restriction
    (main.py's lifespan warns once at startup)."""
    allowed = settings.OMADA_INGEST_ALLOWED_IPS
    if not allowed:
        return
    ip = _client_ip(request)
    if ip is not None and str(ip) in allowed:
        return
    source = str(ip) if ip is not None else ((request.client.host if request.client else "") or "unknown")
    now = time.monotonic()
    last = _rejected_logged.get(source)
    if last is None or now - last >= _REJECT_LOG_EVERY_S:
        if len(_rejected_logged) >= 1000:
            _rejected_logged.clear()
        _rejected_logged[source] = now
        log.warning("[OMADA] rejected source %s: not in OMADA_INGEST_ALLOWED_IPS", source)
    raise HTTPException(status_code=403, detail=SOURCE_NOT_ALLOWED)


async def verify_omada_token(authorization: str = Header(..., alias="Authorization")) -> None:
    """FastAPI dependency that validates the Omada Bearer token on /telemetry."""
    if not hmac.compare_digest(authorization, f"Bearer {settings.OMADA_ACCESS_TOKEN}"):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def verify_omada_body_token(request: Request) -> None:
    """Validate Omada token from JSON body meta.access_token (real AP payloads don't send a header)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=401, detail="Missing or invalid JSON body")
    token = (body.get("meta") or {}).get("access_token", "")
    if not hmac.compare_digest(token, settings.OMADA_ACCESS_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def require_auth(authorization: str = Header(..., alias="Authorization")) -> UserRecord:
    """Verify Firebase ID token. Returns UserRecord. Raises 401/403 if invalid or suspended."""
    try:
        token = authorization.removeprefix("Bearer ").strip()
        decoded = firebase_admin.auth.verify_id_token(token, clock_skew_seconds=60)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = user_repository.get_by_uid(decoded["uid"])
    if user is None:
        raise HTTPException(status_code=401, detail="User record not found")
    if user.status == "pending":
        raise HTTPException(status_code=403, detail="Account pending approval")
    if user.status == "suspended":
        raise HTTPException(status_code=403, detail="Account suspended")
    return user


async def require_auth_strict(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> UserRecord:
    """require_auth, but a missing Authorization header is a 401 rather than
    FastAPI's 422 for a missing required header (Prompt 131: the camera
    detections route must answer 401 without auth). Existing routes keep
    require_auth unchanged."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await require_auth(authorization)


async def require_admin(user: UserRecord = Depends(require_auth)) -> UserRecord:
    """Calls require_auth then asserts role is admin or owner (owner is a superset of
    admin). Raises 403 if not."""
    if user.role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_admin_strict(user: UserRecord = Depends(require_auth_strict)) -> UserRecord:
    """require_admin, but a missing Authorization header is a 401 rather than a
    422 (Prompt 132: the live-view signaling route must answer 401 without
    auth). Existing routes keep require_admin unchanged."""
    if user.role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_owner(user: UserRecord = Depends(require_auth)) -> UserRecord:
    """Calls require_auth then asserts role == owner. Raises 403 if not. Reserved for
    owner-only actions like switching another user's role between admin and user."""
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")
    return user
