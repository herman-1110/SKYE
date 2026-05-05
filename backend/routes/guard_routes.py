from fastapi import APIRouter, Depends, HTTPException

from middleware.auth_middleware import require_auth
from models.user import UserRecord
from services.guard_service import guard_service

router = APIRouter(prefix="/guard", tags=["guard"])


@router.get("/position")
def get_my_position(caller: UserRecord = Depends(require_auth)) -> dict:
    """Return the live position for the calling guard's person_id only."""
    if not caller.person_id:
        raise HTTPException(status_code=404, detail="No person_id linked to this account")
    position = guard_service.get_position(caller.person_id)
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found")
    return position


@router.get("/patrol")
def get_my_patrol(caller: UserRecord = Depends(require_auth)) -> list:
    """Return patrol log entries for the calling guard's shift only."""
    if not caller.person_id:
        return []
    return guard_service.get_patrol(caller.person_id)


@router.get("/alerts")
def get_my_alerts(caller: UserRecord = Depends(require_auth)) -> list:
    """Return alerts where person_id matches the calling guard. Never returns other guards' data."""
    if not caller.person_id:
        return []
    return guard_service.get_alerts(caller.person_id)
