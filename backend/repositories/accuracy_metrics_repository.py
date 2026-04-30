from typing import Any, Dict, List, Optional

from firebase_admin import firestore

from models.accuracy_metrics import AccuracyMetricsRecord


class AccuracyMetricsRepository:
    """Firestore repository for accuracy_metrics collection — never imports firebase_admin.db."""

    _COL = "accuracy_metrics"

    def _db(self):
        return firestore.client()

    def save(self, record: AccuracyMetricsRecord) -> None:
        """Write an AccuracyMetricsRecord as a Firestore document keyed by metrics_id."""
        self._db().collection(self._COL).document(record.metrics_id).set(record.__dict__)

    def get(self, metrics_id: str) -> Optional[Dict[str, Any]]:
        """Read a single metrics record by document ID; returns None if not found."""
        doc = self._db().collection(self._COL).document(metrics_id).get()
        return doc.to_dict() if doc.exists else None

    def get_by_run(self, run_id: str) -> List[Dict[str, Any]]:
        """Query accuracy metrics by run_id — used for simulation evaluation."""
        docs = self._db().collection(self._COL).where("run_id", "==", run_id).stream()
        return [doc.to_dict() for doc in docs]

    def get_by_shift(self, shift_id: str) -> List[Dict[str, Any]]:
        """Query accuracy metrics by shift_id."""
        docs = self._db().collection(self._COL).where("shift_id", "==", shift_id).stream()
        return [doc.to_dict() for doc in docs]


accuracy_metrics_repository = AccuracyMetricsRepository()
