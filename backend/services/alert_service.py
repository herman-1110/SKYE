from typing import Any, Dict, Optional

from repositories.alert_repository import alert_repository
from utils.timestamp_utils import utcnow_iso

_VALID_FEEDBACK = frozenset({"confirmed", "fixed", "false_alarm"})


class AlertService:
    """Thin service layer for alert retrieval and feedback — keeps routes free of repository calls."""

    def get_all(self) -> Dict[str, Any]:
        """Return all alerts stored in Firebase."""
        return alert_repository.get_all()

    def submit_feedback(
        self, alert_id: str, feedback: str, reason: Optional[str]
    ) -> None:
        """Validate and persist operator feedback for an alert."""
        if feedback not in _VALID_FEEDBACK:
            raise ValueError(f"feedback must be one of {_VALID_FEEDBACK}")
        alert_repository.write_feedback(alert_id, feedback, reason, utcnow_iso())


alert_service = AlertService()
