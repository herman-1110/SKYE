from fastapi import Depends, Header, HTTPException

import firebase_admin.auth
import hmac
from config.settings import settings
from models.user import UserRecord
from repositories.user_repository import user_repository


async def verify_omada_token(authorization: str = Header(..., alias="Authorization")) -> None:
    """FastAPI dependency that validates the Omada Bearer token on /telemetry."""
    if not hmac.compare_digest(authorization, f"Bearer {settings.OMADA_ACCESS_TOKEN}"):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def require_auth(authorization: str = Header(..., alias="Authorization")) -> UserRecord:
    """Verify Firebase ID token. Returns UserRecord. Raises 401/403 if invalid or suspended."""
    try:
        token = authorization.removeprefix("Bearer ").strip()
        decoded = firebase_admin.auth.verify_id_token(token)
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


async def require_admin(user: UserRecord = Depends(require_auth)) -> UserRecord:
    """Calls require_auth then asserts role == admin. Raises 403 if not."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
