from fastapi import APIRouter, Depends, HTTPException

from middleware.auth_middleware import require_admin
from models.user import UserRecord
from schemas.report_schema import ReportRequest, SafetyReportRequest
from services.llm_service import llm_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/shifts")
def list_reportable_shifts(admin: UserRecord = Depends(require_admin)) -> dict:
    """List patrol_log documents that have checkpoint data — valid for report generation."""
    shifts = llm_service.get_reportable_shifts()
    return {"shifts": shifts}


@router.post("/generate")
def generate_report(body: ReportRequest, admin: UserRecord = Depends(require_admin)) -> dict:
    """Generate a Gemini audit report from a completed patrol_log document. Admin only."""
    try:
        report = llm_service.generate_report(body.log_id, body.guard_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "report_id": report.report_id,
        "shift_id": report.shift_id,
        "guard_id": report.guard_id,
        "generated_at": report.generated_at,
        "report_text": report.report_text,
        "model_used": report.model_used,
        "report_type": report.report_type,
    }


@router.get("/safety-groups")
def list_safety_event_groups(admin: UserRecord = Depends(require_admin)) -> dict:
    """List distinct (person_id, date) pairs that have alerts in RTDB."""
    groups = llm_service.get_safety_event_groups()
    return {"groups": groups}


@router.post("/generate-safety")
def generate_safety_report(
    body: SafetyReportRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    """Generate a safety incident LLM report for a person+date. Admin only."""
    try:
        report = llm_service.generate_safety_report(body.person_id, body.date_str)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "report_id": report.report_id,
        "shift_id": report.shift_id,
        "guard_id": report.guard_id,
        "generated_at": report.generated_at,
        "report_text": report.report_text,
        "model_used": report.model_used,
        "report_type": report.report_type,
    }
