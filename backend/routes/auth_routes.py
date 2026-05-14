import firebase_admin.auth
from fastapi import APIRouter, HTTPException, Request

from schemas.user_schema import GoogleAuthRequest, RegisterRequest
from services.user_service import user_service
from utils.limiter import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
@limiter.limit("5/15minutes")
async def register(request: Request, body: RegisterRequest) -> dict:
    """Verify Firebase ID token (created client-side) and create Firestore user doc."""
    try:
        decoded = firebase_admin.auth.verify_id_token(body.id_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Firebase ID token")

    uid = decoded["uid"]
    email = decoded.get("email", "")

    try:
        record = user_service.create_user_doc(uid, email, body.display_name, body.person_id or "")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"uid": record.uid, "role": record.role, "status": record.status}


@router.post("/google")
@limiter.limit("5/15minutes")
async def google_auth(request: Request, body: GoogleAuthRequest) -> dict:
    """Public endpoint — verify Firebase Google ID token, upsert user doc, return role+status."""
    try:
        decoded = firebase_admin.auth.verify_id_token(body.id_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google ID token")

    uid = decoded["uid"]
    email = decoded.get("email", "")
    display_name = decoded.get("name", "") or email

    record = user_service.register_google(uid, email, display_name)
    return {"uid": record.uid, "role": record.role, "status": record.status}
