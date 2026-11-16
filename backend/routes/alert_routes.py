from fastapi import APIRouter, Depends, HTTPException

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
    caller: UserRecord = Depends(require_auth),
) -> dict:
    """Record operator feedback for an alert. All authenticated users."""
    alert_service.submit_feedback(alert_id, body.feedback, body.reason)
    return {"status": "ok"}


@router.post("/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: str,
    caller: UserRecord = Depends(require_admin),
) -> dict:
    """Close an alert's pop-up for everyone (Prompt 145, D1). Admins and the
    owner. A second call changes nothing and returns the first one's values.
    The alert stays unresolved until someone gives feedback."""
    ack = alert_service.acknowledge(alert_id, caller)
    if ack is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"alert_id": alert_id, **ack}


@router.delete("/{alert_id}")
def delete_alert(
    alert_id: str,
    caller: UserRecord = Depends(require_admin),
) -> dict:
    """Permanently delete an alert. Admin only — removes safety-incident evidence."""
    alert_service.delete(alert_id)
    return {"status": "deleted"}
