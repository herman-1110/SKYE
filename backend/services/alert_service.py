import uuid
from typing import Any, Dict, Optional

from models.feedback import FeedbackRecord
from models.user import UserRecord
from repositories.alert_repository import alert_repository
from repositories.feedback_repository import feedback_repository
from utils.timestamp_utils import utcnow_iso

_VALID_FEEDBACK = frozenset({"confirmed", "fixed", "false_alarm"})
_ACK_FIELDS = ("acknowledged_at", "acknowledged_by", "acknowledged_by_uid")


class AlertService:
    """
    Alert retrieval and feedback submission.
    submit_feedback() writes to two databases — no sync layer, no bridge function:
      1. RTDB /alerts  → mark_resolved() (for live dashboard display)
      2. Firestore /feedback → save() (for RAG pipeline queries)
    """

    def get_all(self) -> Dict[str, Any]:
        """Return all alerts from Realtime Database."""
        return alert_repository.get_all()

    def submit_feedback(
        self, alert_id: str, feedback: str, reason: Optional[str]
    ) -> None:
        """Validate feedback, resolve alert in RTDB, persist feedback doc in Firestore."""
        if feedback not in _VALID_FEEDBACK:
            raise ValueError(f"feedback must be one of {_VALID_FEEDBACK}")

        existing = alert_repository.get(alert_id)
        if existing is None:
            raise ValueError(f"Alert {alert_id} not found")

        # RTDB write — update resolved flag for live dashboard
        alert_repository.mark_resolved(alert_id)

        # Firestore write — persist for RAG pipeline
        record = FeedbackRecord(
            feedback_id=str(uuid.uuid4()),
            alert_id=alert_id,
            alert_type=existing.get("alert_type", ""),
            zone=existing.get("zone", ""),
            feedback=feedback,
            timestamp=utcnow_iso(),
            feedback_reason=reason,
        )
        feedback_repository.save(record)

    def acknowledge(self, alert_id: str, caller: UserRecord) -> Optional[Dict[str, Any]]:
        """Acknowledge an alert for everyone (Prompt 145, D1): its pop-up closes
        on every dashboard. Writes only the three acknowledgement fields; the
        alert stays unresolved. Returns the acknowledgement: the first one's
        if the alert was already acknowledged, None if there's no such alert."""
        existing = alert_repository.get(alert_id)
        if not isinstance(existing, dict):
            return None
        if existing.get("acknowledged_at"):
            return {k: existing.get(k) for k in _ACK_FIELDS}
        ack = {
            "acknowledged_at": utcnow_iso(),
            "acknowledged_by": (caller.display_name or "").strip() or "admin",
            "acknowledged_by_uid": caller.uid,
        }
        alert_repository.acknowledge(alert_id, **ack)
        return ack

    def delete(self, alert_id: str) -> None:
        """Permanently remove an alert from RTDB /alerts."""
        alert_repository.delete(alert_id)


alert_service = AlertService()
