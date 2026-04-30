from typing import Any, Dict, List

from firebase_admin import firestore

from models.feedback import FeedbackRecord


class FeedbackRepository:
    """Firestore repository for feedback collection — never imports firebase_admin.db."""

    _COL = "feedback"

    def _db(self):
        return firestore.client()

    def save(self, record: FeedbackRecord) -> None:
        """Write a FeedbackRecord as a Firestore document keyed by feedback_id."""
        self._db().collection(self._COL).document(record.feedback_id).set(record.__dict__)

    def get_resolved_with_feedback(self) -> List[Dict[str, Any]]:
        """Return all feedback documents — used by RAG pipeline for context retrieval."""
        return [doc.to_dict() for doc in self._db().collection(self._COL).stream()]

    def get_by_alert_type(self, alert_type: str) -> List[Dict[str, Any]]:
        """Filter feedback by alert_type — used by RAG rule-based pre-filter."""
        docs = self._db().collection(self._COL).where("alert_type", "==", alert_type).stream()
        return [doc.to_dict() for doc in docs]

    def get_by_zone(self, zone: str) -> List[Dict[str, Any]]:
        """Filter feedback by zone — used by RAG rule-based pre-filter."""
        docs = self._db().collection(self._COL).where("zone", "==", zone).stream()
        return [doc.to_dict() for doc in docs]


feedback_repository = FeedbackRepository()
