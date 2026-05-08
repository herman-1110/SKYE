import asyncio

from fastapi import APIRouter, Depends, HTTPException

from middleware.auth_middleware import require_admin, require_auth
from models.user import UserRecord
from schemas.zone_schema import ZoneCreateRequest, ZoneUpdateRequest
from services.zone_service import zone_service

router = APIRouter(
    prefix="/buildings/{building_id}/floors/{floor_id}/zones",
    tags=["zones"],
)


@router.get("")
def get_zones(
    building_id: str,
    floor_id: str,
    caller: UserRecord = Depends(require_auth),
) -> list:
    zones = zone_service.get_zones(building_id, floor_id)
    return [z.__dict__ for z in zones]


@router.post("")
def create_zone(
    building_id: str,
    floor_id: str,
    body: ZoneCreateRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    zone = zone_service.create_zone(building_id, floor_id, body.dict(), admin.uid)
    return zone.__dict__


@router.patch("/{zone_id}")
def update_zone(
    building_id: str,
    floor_id: str,
    zone_id: str,
    body: ZoneUpdateRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    try:
        zone = zone_service.update_zone(building_id, floor_id, zone_id, body.dict(), admin.uid)
        return zone.__dict__
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{zone_id}")
def delete_zone(
    building_id: str,
    floor_id: str,
    zone_id: str,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    zone_service.delete_zone(building_id, floor_id, zone_id, admin.uid)
    return {"status": "ok"}


@router.post("/ai-detect")
async def ai_detect_zones(
    building_id: str,
    floor_id: str,
    admin: UserRecord = Depends(require_admin),
) -> list:
    try:
        result = await asyncio.to_thread(zone_service.ai_detect_zones, building_id, floor_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
