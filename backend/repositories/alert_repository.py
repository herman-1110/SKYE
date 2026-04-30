from typing import Dict, Any, Optional
from firebase_admin import db
from models.alert import AlertRecord


class AlertRepository:
    _PATH = "/alerts"

    def save(self, record: AlertRecord) -> None:
        """Write an AlertRecord to /alerts/{alert_id}."""
        db.reference(f"{self._PATH}/{record.alert_id}").set(record.__dict__)

    def get(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Read a single alert by ID; returns None if not found."""
        return db.reference(f"{self._PATH}/{alert_id}").get()

    def get_all(self) -> Dict[str, Any]:
        """Read all alerts from Firebase."""
        return db.reference(self._PATH).get() or {}

    def write_feedback(
        self,
        alert_id: str,
        feedback: str,
        reason: Optional[str],
        timestamp: str,
    ) -> None:
        """Patch feedback fields onto an existing alert without overwriting other fields."""
        db.reference(f"{self._PATH}/{alert_id}").update({
            "feedback": feedback,
            "feedback_reason": reason,
            "feedback_timestamp": timestamp,
        })


alert_repository = AlertRepository()
