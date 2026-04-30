from typing import Any, Dict, List, Optional

from firebase_admin import firestore

from models.audit_report import AuditReportRecord


class AuditReportRepository:
    """Firestore repository for audit_reports collection — never imports firebase_admin.db."""

    _COL = "audit_reports"

    def _db(self):
        return firestore.client()

    def save(self, record: AuditReportRecord) -> None:
        """Write an AuditReportRecord as a Firestore document keyed by report_id."""
        self._db().collection(self._COL).document(record.report_id).set(record.__dict__)

    def get(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Read a single audit report by document ID; returns None if not found."""
        doc = self._db().collection(self._COL).document(report_id).get()
        return doc.to_dict() if doc.exists else None

    def get_all(self) -> List[Dict[str, Any]]:
        """Read all audit reports from Firestore."""
        return [doc.to_dict() for doc in self._db().collection(self._COL).stream()]

    def get_by_shift(self, shift_id: str) -> List[Dict[str, Any]]:
        """Query audit reports by shift_id."""
        docs = self._db().collection(self._COL).where("shift_id", "==", shift_id).stream()
        return [doc.to_dict() for doc in docs]


audit_report_repository = AuditReportRepository()
