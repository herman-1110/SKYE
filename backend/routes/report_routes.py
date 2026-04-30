from flask import Blueprint, Response, jsonify, request

from services.llm_service import llm_service

report_bp = Blueprint("reports", __name__)


@report_bp.route("/reports/generate", methods=["POST"])
def generate_report() -> Response:
    """Trigger Gemini audit report generation for a completed shift."""
    body = request.get_json(force=True)
    shift_id: str = body.get("shift_id", "")
    patrol_summaries: list = body.get("patrol_summaries", [])
    alert_summaries: list = body.get("alert_summaries", [])

    report = llm_service.generate_report(shift_id, patrol_summaries, alert_summaries)

    return jsonify({
        "report_id": report.report_id,
        "shift_id": report.shift_id,
        "generated_at": report.generated_at,
        "report_text": report.report_text,
        "model_used": report.model_used,
    })
