from fastapi import APIRouter, Depends, HTTPException

from middleware.auth_middleware import require_admin, require_auth
from models.user import UserRecord
from schemas.floor_schema import FloorCreateRequest, FloorScaleRequest, FloorUpdateRequest
from services.floor_service import floor_service

router = APIRouter(prefix="/buildings/{building_id}/floors", tags=["floors"])


@router.get("")
def get_floors(building_id: str, caller: UserRecord = Depends(require_auth)) -> list:
    floors = floor_service.get_all(building_id)
    return [f.__dict__ for f in floors]


@router.post("")
def create_floor(
    building_id: str,
    body: FloorCreateRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    floor = floor_service.create(building_id, body.name, body.floor_number, body.url, body.storage_path)
    return floor.__dict__


@router.patch("/{floor_id}")
def update_floor(
    building_id: str,
    floor_id: str,
    body: FloorUpdateRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    if body.name is not None:
        floor_service.rename(building_id, floor_id, body.name)
    return {"status": "ok"}


@router.patch("/{floor_id}/scale")
def update_scale(
    building_id: str,
    floor_id: str,
    body: FloorScaleRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    try:
        floor_service.update_scale(building_id, floor_id, body.scale_pixels_per_meter)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}


@router.patch("/{floor_id}/activate")
def activate_floor(
    building_id: str,
    floor_id: str,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    floor_service.set_active(building_id, floor_id)
    return {"status": "ok"}


@router.patch("/{floor_id}/deactivate")
def deactivate_floor(
    building_id: str,
    floor_id: str,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    floor_service.deactivate(building_id, floor_id)
    return {"status": "ok"}


@router.delete("/{floor_id}")
def delete_floor(
    building_id: str,
    floor_id: str,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    floor_service.delete(building_id, floor_id)
    return {"status": "ok"}
