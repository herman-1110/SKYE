from fastapi import APIRouter

from schemas.alert_schema import FeedbackRequest
from services.alert_service import alert_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def get_alerts() -> dict:
    """Return all alerts."""
    return alert_service.get_all()


@router.post("/{alert_id}/feedback")
def post_feedback(alert_id: str, body: FeedbackRequest) -> dict:
    """Record operator feedback for an alert."""
    alert_service.submit_feedback(alert_id, body.feedback, body.reason)
    return {"status": "ok"}
