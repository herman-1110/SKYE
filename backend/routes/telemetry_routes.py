from flask import Blueprint, Response, jsonify, request

from middleware.auth_middleware import require_omada_token
from models.telemetry import APRssiReading, OmadaTelemetryPayload
from services.positioning_service import positioning_service
from services.safety_service import safety_service

telemetry_bp = Blueprint("telemetry", __name__)


@telemetry_bp.route("/telemetry", methods=["POST"])
@require_omada_token
def ingest_telemetry() -> Response:
    """Receive RSSI JSON from Omada Controller, compute position, run safety checks."""
    body = request.get_json(force=True)

    readings = [
        APRssiReading(
            ap_mac=r["ap_mac"],
            rssi=float(r["rssi"]),
            ap_x=float(r["ap_x"]),
            ap_y=float(r["ap_y"]),
        )
        for r in body.get("readings", [])
    ]

    payload = OmadaTelemetryPayload(
        reporter_mac=body["reporter_mac"],
        timestamp=body.get("timestamp", ""),
        readings=readings,
        person_id=body.get("person_id", ""),
        person_type=body.get("person_type", "worker"),
    )

    position = positioning_service.compute_position(payload)
    if position:
        safety_service.run_all_checks(position)

    return jsonify({"status": "ok"})
