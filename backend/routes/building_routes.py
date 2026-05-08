from fastapi import APIRouter, Depends, HTTPException

from middleware.auth_middleware import require_admin, require_auth
from models.user import UserRecord
from schemas.building_schema import BuildingCreateRequest, BuildingUpdateRequest
from services.building_service import building_service

router = APIRouter(prefix="/buildings", tags=["buildings"])


@router.get("")
def get_buildings(user_id: str, caller: UserRecord = Depends(require_auth)) -> list:
    return building_service.get_all(user_id)


@router.post("")
def create_building(body: BuildingCreateRequest, admin: UserRecord = Depends(require_admin)) -> dict:
    record = building_service.create(admin.uid, body.name, body.description)
    return record.__dict__


@router.patch("/{building_id}")
def rename_building(
    building_id: str,
    body: BuildingUpdateRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    building_service.rename(building_id, body.name)
    return {"status": "ok"}


@router.delete("/{building_id}")
def delete_building(building_id: str, admin: UserRecord = Depends(require_admin)) -> dict:
    building_service.delete(building_id)
    return {"status": "ok"}
