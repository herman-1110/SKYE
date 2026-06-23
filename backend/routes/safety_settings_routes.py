from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from middleware.auth_middleware import require_auth, require_admin
from models.user import UserRecord

from services.safety_settings_service import safety_settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


class SafetySettingsUpdate(BaseModel):
    man_down_minutes: int = Field(ge=1, le=60)
    collision_distance_m: float = Field(ge=0.5, le=10.0)


@router.get("/safety")
def get_safety_settings(caller: UserRecord = Depends(require_auth)) -> dict:
    return safety_settings_service.get().__dict__


@router.put("/safety")
def update_safety_settings(
    body: SafetySettingsUpdate,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    updated = safety_settings_service.update(
        man_down_minutes=body.man_down_minutes,
        collision_distance_m=body.collision_distance_m,
    )
    return updated.__dict__
