import re
import uuid
from typing import List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from middleware.auth_middleware import require_admin, require_admin_strict, require_auth, require_auth_strict
from models.ap import AccessPoint
from models.user import UserRecord
from repositories.ap_repository import ap_repository
from repositories.cctv_repository import cctv_repository
from repositories.floor_repository import floor_repository
from schemas.floor_schema import FloorCreateRequest, FloorScaleRequest, FloorUpdateRequest
from services import live_view_service
from services.camera_detection_buffer import WINDOW_S as DETECTION_WINDOW_S, detection_buffer
from services.camera_health_service import camera_health_service
from services.cctv_service import CameraError, cctv_service
from services.floor_service import floor_service
from services.live_view_service import LiveViewError
from utils.limiter import limiter
from utils.timestamp_utils import utcnow_iso


_MAC_RE = re.compile(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$')


class APCreateRequest(BaseModel):
    name: str
    mac: str
    x_pct: float
    y_pct: float
    # x_m/y_m intentionally NOT accepted here — server-derived in create_ap()
    # from x_pct/y_pct + the floor's calibrated scale. Trusting the client's
    # own copy was the root cause of every pre-calibration AP landing at
    # (0, 0); a client that still sends these fields has them silently
    # ignored (Pydantic drops undeclared fields), not merged or fallen back to.

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
    # Prompt 131: MAC (dashes, colons or none), IP and checkpoint are checked
    # in cctv_service so a bad value comes back as a 422 with a plain sentence
    # (a pydantic validator's 422 is a list the dashboard can't show as-is).
    mac: Optional[str] = None
    ip: Optional[str] = None
    checkpoint_ap_id: Optional[str] = None
    channel: Optional[int] = None        # hidden in the UI; 1 for a direct camera
    source_type: Optional[str] = None    # hidden in the UI; "ipc"


class CCTVUpdateRequest(BaseModel):
    """Only the fields sent are changed; send null to clear ip or checkpoint_ap_id."""
    name: Optional[str] = None
    mac: Optional[str] = None
    ip: Optional[str] = None
    checkpoint_ap_id: Optional[str] = None
    channel: Optional[int] = None


class PositionUpdateRequest(BaseModel):
    x_pct: float
    y_pct: float
    # x_m/y_m intentionally NOT accepted — see APCreateRequest. CCTV has no
    # metre coordinates at all, so this only matters for the AP variant of
    # this endpoint, which re-derives them server-side same as create_ap.

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
    patrol_interval_minutes: int = 10


@router.patch("/{floor_id}/patrol")
def update_patrol_config(
    building_id: str,
    floor_id: str,
    body: PatrolConfigRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    """Save patrol enabled flag, ordered AP route, and the time-boxed cycle
    interval (Prompt 122) for this floor. Admin only."""
    floor_repository.update_patrol_config(
        building_id, floor_id, body.patrol_enabled, body.patrol_route,
        body.patrol_interval_minutes,
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
    global_matches = ap_repository.get_by_mac_global(body.mac)
    if global_matches:
        match = global_matches[0]
        if match.floor_id == floor_id:
            raise HTTPException(
                status_code=409,
                detail=f"AP with MAC {body.mac} already exists on this floor"
            )
        else:
            raise HTTPException(
                status_code=409,
                detail=f"AP with MAC {body.mac} is already registered on another floor (floor_id: {match.floor_id}). Each AP MAC must be globally unique."
            )
    try:
        x_m, y_m = floor_service.derive_ap_metres(building_id, floor_id, body.x_pct, body.y_pct)
    except ValueError as e:
        # 409, not 400: the request itself is well-formed — the floor is just
        # in the wrong state (uncalibrated) to place an AP on right now.
        raise HTTPException(status_code=409, detail=str(e))

    ap = AccessPoint(
        id=str(uuid.uuid4()),
        floor_id=floor_id,
        building_id=building_id,
        name=body.name,
        mac=body.mac,
        x_pct=body.x_pct,
        y_pct=body.y_pct,
        created_at=utcnow_iso(),
        x_m=x_m,
        y_m=y_m,
    )
    ap_repository.save(building_id, floor_id, ap)
    return ap.__dict__


@router.patch("/{floor_id}/aps/{ap_id}/position")
def update_ap_position(
    building_id: str,
    floor_id: str,
    ap_id: str,
    body: PositionUpdateRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    """Marker was dragged on the map. x_m/y_m are re-derived server-side from
    the floor's current scale — same as create_ap, and for the same reason:
    an already-placed AP requires calibration to exist, but re-deriving here
    too (rather than trusting whatever the client last computed) means this
    endpoint can't reintroduce a zeroed-coordinate AP either."""
    try:
        x_m, y_m = floor_service.derive_ap_metres(building_id, floor_id, body.x_pct, body.y_pct)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    ap_repository.update_position(building_id, floor_id, ap_id, body.x_pct, body.y_pct, x_m, y_m)
    return {"status": "ok"}


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
    return [c.to_dict() for c in cctvs]


@router.post("/{floor_id}/cctvs")
def create_cctv(
    building_id: str,
    floor_id: str,
    body: CCTVCreateRequest,
    background_tasks: BackgroundTasks,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    try:
        cctv = cctv_service.create(
            building_id, floor_id,
            name=body.name, x_pct=body.x_pct, y_pct=body.y_pct, mac=body.mac, ip=body.ip,
            checkpoint_ap_id=body.checkpoint_ap_id, channel=body.channel, source_type=body.source_type,
        )
    except CameraError as e:
        raise HTTPException(status_code=e.status, detail=e.message)
    # First health check right away rather than at the next OpenAPI sweep.
    background_tasks.add_task(camera_health_service.check_now, cctv)
    return cctv.to_dict()


@router.patch("/{floor_id}/cctvs/{cctv_id}")
def update_cctv(
    building_id: str,
    floor_id: str,
    cctv_id: str,
    body: CCTVUpdateRequest,
    background_tasks: BackgroundTasks,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    """Edit name, mac, ip, checkpoint_ap_id or channel (Prompt 131 T2). Changing
    ip re-reads the camera's time zone once."""
    changes = body.model_dump(exclude_unset=True)
    try:
        cctv = cctv_service.update(building_id, floor_id, cctv_id, changes)
    except CameraError as e:
        raise HTTPException(status_code=e.status, detail=e.message)
    if "ip" in changes or "mac" in changes or "channel" in changes:
        background_tasks.add_task(camera_health_service.check_now, cctv)
    return cctv.to_dict()


@router.get("/{floor_id}/cctvs/{cctv_id}/detections")
def list_cctv_detections(
    building_id: str,
    floor_id: str,
    cctv_id: str,
    caller: UserRecord = Depends(require_auth_strict),
) -> dict:
    """The camera's alarm events from the last 15 minutes, newest first
    (Prompt 131 T7). In memory only: process_started_at tells the reader
    whether a restart may have emptied the window."""
    cctv = cctv_repository.get_by_id(building_id, floor_id, cctv_id)
    if cctv is None:
        raise HTTPException(status_code=404, detail="Camera not found.")
    return {
        "camera_key": cctv.camera_key,
        "process_started_at": detection_buffer.process_started_at,
        "window_s": DETECTION_WINDOW_S,
        "detections": detection_buffer.recent(cctv.camera_key),
    }


class WebRTCOfferRequest(BaseModel):
    sdp: str                                # the browser's offer: video only, receive only
    quality: Literal["sub", "main"] = "sub"  # sub = stream2 848x480; main = stream1, the HD option


@router.post("/{floor_id}/cctvs/{cctv_id}/webrtc")
@limiter.limit("30/minute")
def open_cctv_live_view(
    request: Request,
    building_id: str,
    floor_id: str,
    cctv_id: str,
    body: WebRTCOfferRequest,
    admin: UserRecord = Depends(require_admin_strict),
) -> dict:
    """Live view (Prompt 132, Herman's decision 6): WebRTC signaling through
    the backend. The offer goes to go2rtc on this machine, which answers and
    then sends the camera's video straight to the browser. Admins only; the
    reply is the SDP answer and nothing else - never a stream address.
    404 unknown camera, 409 camera offline (or no MAC/IP, or an NVR camera),
    422 not a video-only offer, 503 go2rtc not running or not yet reloaded,
    502/504 the camera's stream couldn't be started."""
    try:
        return live_view_service.open_stream(building_id, floor_id, cctv_id, body.sdp, body.quality,
                                             user_id=admin.uid)
    except LiveViewError as e:
        raise HTTPException(status_code=e.status, detail=e.message)


@router.patch("/{floor_id}/cctvs/{cctv_id}/position")
def update_cctv_position(
    building_id: str,
    floor_id: str,
    cctv_id: str,
    body: PositionUpdateRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    cctv_repository.update_position(building_id, floor_id, cctv_id, body.x_pct, body.y_pct)
    return {"status": "ok"}


@router.delete("/{floor_id}/cctvs/{cctv_id}")
def delete_cctv(
    building_id: str,
    floor_id: str,
    cctv_id: str,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    # Also removes the camera's /cctv_heartbeats node (Prompt 131 T2).
    cctv_service.delete(building_id, floor_id, cctv_id)
    return {"status": "ok"}
