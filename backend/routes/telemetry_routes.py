import time

from fastapi import APIRouter, Depends, Request
from firebase_admin import db
from starlette.concurrency import run_in_threadpool

from middleware.auth_middleware import verify_omada_token
from models.telemetry import APRssiReading, OmadaTelemetryPayload
from schemas.telemetry_schema import TelemetryRequest
from services.positioning_service import positioning_service
from services.safety_service import safety_service
from utils.limiter import limiter

router = APIRouter(tags=["telemetry"])


def _write_ap_heartbeats(readings: list[APRssiReading]) -> None:
    """Write last-seen unix timestamp for every AP that reported in this payload."""
    now = int(time.time())
    for r in readings:
        key = r.ap_mac.replace(":", "_")
        db.reference(f"/ap_heartbeats/{key}").set({
            "mac":       r.ap_mac,
            "last_seen": now,
        })


def _process_telemetry(payload: OmadaTelemetryPayload, readings: list[APRssiReading]) -> dict:
    """Blocking body of ingest_telemetry — run off the event loop (see caller).

    Holds positioning_service.pipeline_lock around compute_position() +
    run_all_checks() so this (simulation) path and the real-AP /telemetry/omada
    path — which shares positioning_service/safety_service's in-memory state —
    can never run those two calls concurrently with each other.
    """
    _write_ap_heartbeats(readings)
    with positioning_service.pipeline_lock:
        position = positioning_service.compute_position(payload)
        if position:
            safety_service.run_all_checks(position)
    return {"status": "ok"}


@router.post("/telemetry", dependencies=[Depends(verify_omada_token)])
@limiter.limit("200/minute")
async def ingest_telemetry(request: Request, body: TelemetryRequest) -> dict:
    """Receive RSSI payload from Omada Controller, compute position, run safety checks.

    Firebase calls inside _process_telemetry are blocking; offloaded via
    run_in_threadpool so a burst of simulation ticks can't freeze the event
    loop for unrelated requests (same fix as /telemetry/omada).
    """
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
    return await run_in_threadpool(_process_telemetry, payload, readings)
