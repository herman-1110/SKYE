from flask import Blueprint, Response, jsonify, request

from services.alert_service import alert_service

alert_bp = Blueprint("alerts", __name__)


@alert_bp.route("/alerts", methods=["GET"])
def get_alerts() -> Response:
    """Return all alerts."""
    return jsonify(alert_service.get_all())


@alert_bp.route("/alerts/<alert_id>/feedback", methods=["POST"])
def post_feedback(alert_id: str) -> Response:
    """Record operator feedback for an alert."""
    body = request.get_json(force=True)
    feedback = body.get("feedback", "")
    reason = body.get("reason")

    try:
        alert_service.submit_feedback(alert_id, feedback, reason)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"status": "ok"})
