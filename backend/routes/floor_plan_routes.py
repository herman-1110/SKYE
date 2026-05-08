from fastapi import APIRouter, Depends

from middleware.auth_middleware import require_admin, require_auth
from models.user import UserRecord
from schemas.floor_plan_schema import ActivateRequest, FloorPlanCreateRequest, ScaleUpdateRequest
from services.floor_plan_service import floor_plan_service

router = APIRouter(prefix="/floor-plans", tags=["floor-plans"])


@router.get("")
def get_floor_plans(user_id: str, caller: UserRecord = Depends(require_auth)) -> list:
    """Return all floor plans for a user ordered by upload date. All authenticated users."""
    return floor_plan_service.get_all(user_id)


@router.post("")
def create_floor_plan(body: FloorPlanCreateRequest, admin: UserRecord = Depends(require_admin)) -> dict:
    """Persist floor plan metadata after the frontend uploads the image to Firebase Storage. Admin only."""
    record = floor_plan_service.create(body.user_id, body.name, body.url, body.storage_path)
    return record.__dict__


@router.delete("/{floor_plan_id}")
def delete_floor_plan(floor_plan_id: str, admin: UserRecord = Depends(require_admin)) -> dict:
    """Delete a floor plan record. Admin only."""
    floor_plan_service.delete(floor_plan_id)
    return {"status": "ok"}


@router.patch("/{floor_plan_id}/scale")
def update_scale(
    floor_plan_id: str,
    body: ScaleUpdateRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    """Update scale_pixels_per_meter after the user calibrates the floor plan. Admin only."""
    floor_plan_service.update_scale(floor_plan_id, body.scale_pixels_per_meter)
    return {"status": "ok"}


@router.patch("/{floor_plan_id}/activate")
def activate_floor_plan(
    floor_plan_id: str,
    body: ActivateRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    """Set this floor plan as active and deactivate all others for the user. Admin only."""
    floor_plan_service.set_active(floor_plan_id, body.user_id)
    return {"status": "ok"}
