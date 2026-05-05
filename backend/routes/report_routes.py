from fastapi import APIRouter, Depends

from middleware.auth_middleware import require_admin
from models.user import UserRecord
from schemas.report_schema import ReportRequest
from services.llm_service import llm_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/generate")
def generate_report(body: ReportRequest, admin: UserRecord = Depends(require_admin)) -> dict:
    """Trigger Gemini audit report generation for a completed shift. Admin only."""
    report = llm_service.generate_report(
        body.shift_id, body.patrol_summaries, body.alert_summaries
    )
    return {
        "report_id": report.report_id,
        "shift_id": report.shift_id,
        "generated_at": report.generated_at,
        "report_text": report.report_text,
        "model_used": report.model_used,
    }
