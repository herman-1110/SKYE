from fastapi import APIRouter, Depends

from middleware.auth_middleware import require_admin, require_auth
from models.user import UserRecord
from schemas.alert_schema import FeedbackRequest
from services.alert_service import alert_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def get_alerts(caller: UserRecord = Depends(require_auth)) -> dict:
    """Return all alerts. Both admin and guard roles can view."""
    return alert_service.get_all()


@router.post("/{alert_id}/feedback")
def post_feedback(
    alert_id: str,
    body: FeedbackRequest,
    admin: UserRecord = Depends(require_admin),
) -> dict:
    """Record operator feedback for an alert. Admin (Security Manager) only."""
    alert_service.submit_feedback(alert_id, body.feedback, body.reason)
    return {"status": "ok"}
