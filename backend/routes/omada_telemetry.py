from fastapi import APIRouter, Depends, Request

from middleware.auth_middleware import verify_omada_body_token
from services.omada_ingest_service import omada_ingest_service
from utils.limiter import limiter

router = APIRouter(tags=["omada-telemetry"])


@router.post("/telemetry/omada", dependencies=[Depends(verify_omada_body_token)])
@limiter.limit("600/minute")
async def ingest_omada_telemetry(request: Request) -> dict:
    """
    Receive raw AP-centric BLE scan payload from the Omada IoT Transport Stream.
    Inverts to beacon-centric format and feeds the positioning pipeline.

    Rate limit is higher than /telemetry because each AP posts independently
    (~3 APs × 1/s = ~180/min baseline, with headroom for more APs or faster intervals).
    """
    raw = await request.json()
    return omada_ingest_service.ingest(raw)
