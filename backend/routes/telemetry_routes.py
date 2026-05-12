from fastapi import APIRouter, Depends

from middleware.auth_middleware import verify_omada_token
from schemas.telemetry_schema import OmadaTelemetryRequest
from services.positioning_service import positioning_service
from services.safety_service import safety_service

router = APIRouter(tags=["telemetry"])


@router.post("/telemetry", dependencies=[Depends(verify_omada_token)])
def ingest_telemetry(body: OmadaTelemetryRequest) -> dict:
    """Receive Omada BLE telemetry (one POST per AP), buffer per beacon, run positioning."""
    ap_mac = body.reporter.mac
    ap_name = body.reporter.name
    print(f"[TEL] Saved AP Info: {ap_name} ({ap_mac}), beacons={len(body.reported)}")

    for entry in body.reported:
        position = positioning_service.process_ap_reading(
            ap_mac=ap_mac,
            beacon_mac=entry.mac,
            rssi=entry.rssi,
        )
        if position:
            safety_service.run_all_checks(position)

    return {"status": "ok"}
