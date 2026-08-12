from typing import Any, Dict, Optional

from firebase_admin import db

from models.alert import AlertRecord


class AlertRepository:
    """Realtime Database repository for /alerts — never imports firestore."""

    _PATH = "/alerts"

    def save(self, record: AlertRecord) -> None:
        """Write an AlertRecord to /alerts/{alert_id} in Realtime Database."""
        db.reference(f"{self._PATH}/{record.alert_id}").set(record.__dict__)

    def get(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Read a single alert by ID; returns None if not found."""
        return db.reference(f"{self._PATH}/{alert_id}").get()

    def get_all(self) -> Dict[str, Any]:
        """Read all active alerts from Realtime Database."""
        return db.reference(self._PATH).get() or {}

    def mark_resolved(self, alert_id: str) -> None:
        """Patch resolved=True on an existing alert without overwriting other fields."""
        db.reference(f"{self._PATH}/{alert_id}").update({"resolved": True})

    def delete(self, alert_id: str) -> None:
        """Permanently remove /alerts/{alert_id} from Realtime Database."""
        db.reference(f"{self._PATH}/{alert_id}").delete()


alert_repository = AlertRepository()
