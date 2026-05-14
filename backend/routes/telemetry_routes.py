from fastapi import APIRouter, Depends, Request

from middleware.auth_middleware import verify_omada_token
from models.telemetry import APRssiReading, OmadaTelemetryPayload
from schemas.telemetry_schema import TelemetryRequest
from services.positioning_service import positioning_service
from services.safety_service import safety_service
from utils.limiter import limiter

router = APIRouter(tags=["telemetry"])


@router.post("/telemetry", dependencies=[Depends(verify_omada_token)])
@limiter.limit("200/minute")
async def ingest_telemetry(request: Request, body: TelemetryRequest) -> dict:
    """Receive RSSI payload from Omada Controller, compute position, run safety checks."""
    readings = [
        APRssiReading(ap_mac=r.ap_mac, rssi=r.rssi, ap_x=r.ap_x, ap_y=r.ap_y)
        for r in body.readings
    ]
    payload = OmadaTelemetryPayload(
        reporter_mac=body.reporter_mac,
        timestamp=body.timestamp,
        readings=readings,
        person_id=body.person_id,
        person_type=body.person_type,
    )
    position = positioning_service.compute_position(payload)
    if position:
        safety_service.run_all_checks(position)
    return {"status": "ok"}
