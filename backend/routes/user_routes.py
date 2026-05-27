from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from middleware.auth_middleware import require_admin
from models.user import UserRecord
from schemas.user_schema import UpdateRoleRequest, UpdateStatusRequest
from services.user_service import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
def get_users(admin: UserRecord = Depends(require_admin)) -> list:
    """Return all users ordered by created_at descending. Admin only.
    Pending users are hidden until they verify their email.
    """
    return [asdict(u) for u in user_service.get_all() if u.email_verified or u.status != "pending"]


@router.get("/pending")
def get_pending(admin: UserRecord = Depends(require_admin)) -> list:
    """Return all users with status=pending. Admin only."""
    return [asdict(u) for u in user_service.get_pending()]


@router.patch("/{uid}/role")
def update_role(uid: str, body: UpdateRoleRequest, admin: UserRecord = Depends(require_admin)) -> dict:
    """Change a user's role. Admin only."""
    try:
        user_service.update_role(uid, body.role, admin.uid)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}


@router.patch("/{uid}/status")
# Disabled from UI — kept for manual use only (suspend/unsuspend removed from user management table)
def update_status(uid: str, body: UpdateStatusRequest, admin: UserRecord = Depends(require_admin)) -> dict:
    """Approve or suspend a user. Admin only."""
    try:
        user_service.update_status(uid, body.status, admin.uid)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}


@router.delete("/{uid}")
def delete_user(uid: str, admin: UserRecord = Depends(require_admin)) -> dict:
    """Delete a user's Firebase Auth account and Firestore doc. Admin only."""
    if admin.uid == uid:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    try:
        user_service.delete(uid)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}
