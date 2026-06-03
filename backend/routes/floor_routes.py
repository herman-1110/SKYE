import re
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from middleware.auth_middleware import require_admin, require_auth
from models.ap import AccessPoint
from models.cctv import CCTV
from models.user import UserRecord
from repositories.ap_repository import ap_repository
from repositories.cctv_repository import cctv_repository
from repositories.floor_repository import floor_repository
from schemas.floor_schema import FloorCreateRequest, FloorScaleRequest, FloorUpdateRequest
from services.floor_service import floor_service
from utils.timestamp_utils import utcnow_iso


_MAC_RE = re.compile(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$')


class APCreateRequest(BaseModel):
    name: str
    mac: str
    x_pct: float
    y_pct: float
    x_m: float = 0.0
    y_m: float = 0.0

    @field_validator("mac")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        if not _MAC_RE.match(v.strip()):
            raise ValueError("MAC must be in format XX:XX:XX:XX:XX:XX")
        return v.strip().upper()


class CCTVCreateRequest(BaseModel):
    name: str
    x_pct: float
    y_pct: float
    mac: Optional[str] = None

    @field_validator("mac")
    @classmethod
    def validate_mac(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        if not _MAC_RE.match(v.strip()):
            raise ValueError("MAC must be in format XX:XX:XX:XX:XX:XX")
        return v.strip().upper()

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
    floor = floor_service.create(building_id, body.name, body.floor_number, body.url, body.storage_path, body.image_width_px, body.image_height_px)
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


class PatrolConfigRequest(BaseModel):
    patrol_enabled: bool
    patrol_route: List[str]


@router.patch("/{floor_id}/patrol")
def update_patrol_config(
    building_id: str,
    floor_id: str,
    body: PatrolConfigRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    """Save patrol enabled flag and ordered AP route for this floor. Admin only."""
    floor_repository.update_patrol_config(
        building_id, floor_id, body.patrol_enabled, body.patrol_route
    )
    return {"status": "ok"}


@router.delete("/{floor_id}")
def delete_floor(
    building_id: str,
    floor_id: str,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    floor_service.delete(building_id, floor_id)
    return {"status": "ok"}


# ── Access Points ──────────────────────────────────────────────────────────────

@router.get("/{floor_id}/aps")
def list_aps(
    building_id: str,
    floor_id: str,
    caller: UserRecord = Depends(require_auth),
) -> list:
    aps = ap_repository.get_all(building_id, floor_id)
    return [ap.__dict__ for ap in aps]


@router.post("/{floor_id}/aps")
def create_ap(
    building_id: str,
    floor_id: str,
    body: APCreateRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    existing = ap_repository.get_all(building_id, floor_id)
    if any(a.mac.upper() == body.mac for a in existing):
        raise HTTPException(status_code=409, detail=f"AP with MAC {body.mac} already exists on this floor")
    ap = AccessPoint(
        id=str(uuid.uuid4()),
        floor_id=floor_id,
        building_id=building_id,
        name=body.name,
        mac=body.mac,
        x_pct=body.x_pct,
        y_pct=body.y_pct,
        created_at=utcnow_iso(),
        x_m=body.x_m,
        y_m=body.y_m,
    )
    ap_repository.save(building_id, floor_id, ap)
    return ap.__dict__


@router.delete("/{floor_id}/aps/{ap_id}")
def delete_ap(
    building_id: str,
    floor_id: str,
    ap_id: str,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    floor_service.delete_ap(building_id, floor_id, ap_id)
    return {"status": "ok"}


# ── CCTVs ──────────────────────────────────────────────────────────────────────

@router.get("/{floor_id}/cctvs")
def list_cctvs(
    building_id: str,
    floor_id: str,
    caller: UserRecord = Depends(require_auth),
) -> list:
    cctvs = cctv_repository.get_all(building_id, floor_id)
    return [c.__dict__ for c in cctvs]


@router.post("/{floor_id}/cctvs")
def create_cctv(
    building_id: str,
    floor_id: str,
    body: CCTVCreateRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    cctv = CCTV(
        id=str(uuid.uuid4()),
        floor_id=floor_id,
        building_id=building_id,
        name=body.name,
        x_pct=body.x_pct,
        y_pct=body.y_pct,
        created_at=utcnow_iso(),
        mac=body.mac,
    )
    cctv_repository.save(building_id, floor_id, cctv)
    return cctv.__dict__


@router.delete("/{floor_id}/cctvs/{cctv_id}")
def delete_cctv(
    building_id: str,
    floor_id: str,
    cctv_id: str,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    cctv_repository.delete(building_id, floor_id, cctv_id)
    return {"status": "ok"}
