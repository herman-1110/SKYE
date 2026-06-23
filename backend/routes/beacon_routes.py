from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from middleware.auth_middleware import require_auth, require_admin
from models.user import UserRecord

from services.beacon_service import beacon_service

router = APIRouter(prefix="/beacons", tags=["beacons"])

PersonType = Literal["guard", "worker", "forklift"]


class BeaconCreateRequest(BaseModel):
    uuid: str
    major: str
    minor: str
    person_id: str
    person_type: PersonType
    label: str
    building_id: Optional[str] = None


class BeaconUpdateRequest(BaseModel):
    person_id: Optional[str] = None
    person_type: Optional[PersonType] = None
    label: Optional[str] = None
    building_id: Optional[str] = None


@router.get("")
def list_beacons(caller: UserRecord = Depends(require_auth)) -> list:
    return [b.__dict__ for b in beacon_service.list()]


@router.post("")
def create_beacon(
    body: BeaconCreateRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    try:
        beacon = beacon_service.create(
            uuid_str=body.uuid, major=body.major, minor=body.minor,
            person_id=body.person_id, person_type=body.person_type,
            label=body.label, building_id=body.building_id,
        )
    except ValueError:
        raise HTTPException(
            status_code=409,
            detail="A beacon with this UUID/major/minor already exists",
        )
    return beacon.__dict__


@router.patch("/{beacon_id}")
def update_beacon(
    beacon_id: str,
    body: BeaconUpdateRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    patch = {
        k: v for k, v in {
            "person_id": body.person_id,
            "person_type": body.person_type,
            "label": body.label,
            "building_id": body.building_id,
        }.items() if v is not None
    }
    updated = beacon_service.update(beacon_id, patch)
    if updated is None:
        raise HTTPException(status_code=404, detail="Beacon not found")
    return updated.__dict__


@router.delete("/{beacon_id}")
def delete_beacon(
    beacon_id: str,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    if not beacon_service.delete(beacon_id):
        raise HTTPException(status_code=404, detail="Beacon not found")
    return {"status": "ok"}
