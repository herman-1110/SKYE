from fastapi import APIRouter

from schemas.floor_plan_schema import ActivateRequest, FloorPlanCreateRequest, ScaleUpdateRequest
from services.floor_plan_service import floor_plan_service

router = APIRouter(prefix="/floor-plans", tags=["floor-plans"])


@router.get("")
def get_floor_plans(user_id: str) -> list:
    """Return all floor plans for a user ordered by upload date."""
    return floor_plan_service.get_all(user_id)


@router.post("")
def create_floor_plan(body: FloorPlanCreateRequest) -> dict:
    """Persist floor plan metadata after the frontend uploads the image to Firebase Storage."""
    record = floor_plan_service.create(body.user_id, body.name, body.url)
    return record.__dict__


@router.patch("/{floor_plan_id}/scale")
def update_scale(floor_plan_id: str, body: ScaleUpdateRequest) -> dict:
    """Update scale_pixels_per_meter after the user calibrates the floor plan."""
    floor_plan_service.update_scale(floor_plan_id, body.scale_pixels_per_meter)
    return {"status": "ok"}


@router.patch("/{floor_plan_id}/activate")
def activate_floor_plan(floor_plan_id: str, body: ActivateRequest) -> dict:
    """Set this floor plan as active and deactivate all others for the user."""
    floor_plan_service.set_active(floor_plan_id, body.user_id)
    return {"status": "ok"}
