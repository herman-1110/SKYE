from typing import Dict, Any, Optional
from firebase_admin import db
from models.patrol_log import PatrolLogRecord


class PatrolLogRepository:
    _PATH = "/patrol_logs"

    def save(self, record: PatrolLogRecord) -> None:
        """Write a PatrolLogRecord to /patrol_logs/{log_id}."""
        db.reference(f"{self._PATH}/{record.log_id}").set(record.__dict__)

    def get(self, log_id: str) -> Optional[Dict[str, Any]]:
        """Read a single patrol log entry by ID; returns None if not found."""
        return db.reference(f"{self._PATH}/{log_id}").get()

    def get_by_shift(self, shift_id: str) -> Dict[str, Any]:
        """Read all patrol log entries whose shift_id matches the given value."""
        all_logs: Dict[str, Any] = db.reference(self._PATH).get() or {}
        return {k: v for k, v in all_logs.items() if v.get("shift_id") == shift_id}


patrol_log_repository = PatrolLogRepository()
