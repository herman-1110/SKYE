import logging

import firebase_admin.auth
from fastapi import APIRouter, Header, HTTPException, Request

from schemas.user_schema import GoogleAuthRequest, RegisterRequest
from services.user_service import user_service
from utils.limiter import limiter

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
@limiter.limit("5/15minutes")
async def register(request: Request, body: RegisterRequest) -> dict:
    """Verify Firebase ID token (created client-side) and create Firestore user doc."""
    try:
        decoded = firebase_admin.auth.verify_id_token(body.id_token, clock_skew_seconds=60)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Firebase ID token")

    uid = decoded["uid"]
    email = decoded.get("email", "")

    try:
        record = user_service.create_user_doc(
            uid, email, body.display_name, body.person_id or "",
            email_verified=decoded.get("email_verified", False),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"uid": record.uid, "role": record.role, "status": record.status}


@router.post("/verify-email")
@limiter.limit("10/minute")
async def sync_email_verified(
    request: Request,
    authorization: str = Header(..., alias="Authorization"),
) -> dict:
    """Called by the frontend after Firebase confirms emailVerified=True.
    Double-checks with Firebase Admin SDK, then sets email_verified=True in Firestore.
    """
    try:
        token = authorization.removeprefix("Bearer ").strip()
        log.info("[verify-email] Verifying token len=%d preview=%s...", len(token), token[:20])
        decoded = firebase_admin.auth.verify_id_token(token, clock_skew_seconds=60)
    except Exception as exc:
        log.error("[verify-email] verify_id_token FAILED %s: %s", type(exc).__name__, exc)
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    uid = decoded["uid"]
    email_verified_claim = decoded.get("email_verified", False)
    log.info("[verify-email] uid=%s email_verified_claim=%s", uid, email_verified_claim)

    # Trust the signed JWT claim — no secondary Admin SDK call needed
    if not email_verified_claim:
        raise HTTPException(status_code=400, detail="Email not yet verified")

    try:
        log.info("[verify-email] Firestore update called for uid=%s", uid)
        user_service.sync_email_verified(uid)
        log.info("[verify-email] Update complete for uid=%s", uid)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"status": "email_verified"}


@router.post("/google")
@limiter.limit("5/15minutes")
async def google_auth(request: Request, body: GoogleAuthRequest) -> dict:
    """Public endpoint — verify Firebase Google ID token, upsert user doc, return role+status."""
    try:
        decoded = firebase_admin.auth.verify_id_token(body.id_token, clock_skew_seconds=60)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google ID token")

    uid = decoded["uid"]
    email = decoded.get("email", "")
    display_name = decoded.get("name", "") or email

    record = user_service.register_google(uid, email, display_name)
    return {"uid": record.uid, "role": record.role, "status": record.status}
