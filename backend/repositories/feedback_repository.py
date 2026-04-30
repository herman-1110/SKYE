from typing import List, Dict, Any
from firebase_admin import db


class FeedbackRepository:
    _PATH = "/alerts"

    def get_resolved_with_feedback(self) -> List[Dict[str, Any]]:
        """Return all alert records that have a non-null feedback value, for RAG retrieval."""
        all_alerts: Dict[str, Any] = db.reference(self._PATH).get() or {}
        return [v for v in all_alerts.values() if v.get("feedback") is not None]


feedback_repository = FeedbackRepository()
