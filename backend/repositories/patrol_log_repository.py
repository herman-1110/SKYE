from typing import Any, Dict, List, Optional

from firebase_admin import firestore

from models.patrol_log import PatrolLogRecord


class PatrolLogRepository:
    """Firestore repository for patrol_logs collection — never imports firebase_admin.db."""

    _COL = "patrol_logs"

    def _db(self):
        return firestore.client()

    def save(self, record: PatrolLogRecord) -> None:
        """Write a PatrolLogRecord as a Firestore document keyed by log_id."""
        self._db().collection(self._COL).document(record.log_id).set(record.__dict__)

    def get(self, log_id: str) -> Optional[Dict[str, Any]]:
        """Read a single patrol log document by ID; returns None if not found."""
        doc = self._db().collection(self._COL).document(log_id).get()
        return doc.to_dict() if doc.exists else None

    def get_by_shift(self, shift_id: str) -> List[Dict[str, Any]]:
        """Query patrol logs where shift_id matches — used by LLM engine at end of shift."""
        docs = self._db().collection(self._COL).where("shift_id", "==", shift_id).stream()
        return [doc.to_dict() for doc in docs]

    def get_by_guard(self, guard_id: str) -> List[Dict[str, Any]]:
        """Query patrol logs where guard_id matches."""
        docs = self._db().collection(self._COL).where("guard_id", "==", guard_id).stream()
        return [doc.to_dict() for doc in docs]


patrol_log_repository = PatrolLogRepository()
