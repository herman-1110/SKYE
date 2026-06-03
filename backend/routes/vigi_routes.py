from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from middleware.auth_middleware import verify_omada_token
from services.vigi_service import vigi_service
from utils.limiter import limiter

router = APIRouter(tags=["vigi"])


@router.post("/vigi/detection", dependencies=[Depends(verify_omada_token)])
@limiter.limit("200/minute")
async def vigi_detection(request: Request, body: Dict[str, Any]) -> dict:
    """Receive VIGI camera detection event. Writes CCTV heartbeat to RTDB."""
    mac = body.get("MAC") or body.get("mac")
    if mac:
        device_name = body.get("device_name") or body.get("DeviceName", "Unknown CCTV")
        vigi_service.write_cctv_heartbeat(mac, device_name)
    return {"status": "ok"}
