from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

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

    ingest() is synchronous and does several blocking Firebase round-trips
    (RTDB writes, Firestore cache-refresh reads, a full /positions read via
    safety checks). Run it off the event loop — otherwise every telemetry
    POST freezes the entire server for its full duration, since this route
    is declared async and nothing else yields control while it runs.
    """
    raw = await request.json()
    return await run_in_threadpool(omada_ingest_service.ingest, raw)
