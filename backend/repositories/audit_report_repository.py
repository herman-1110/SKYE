from typing import Dict, Any, Optional
from firebase_admin import db
from models.audit_report import AuditReportRecord


class AuditReportRepository:
    _PATH = "/audit_reports"

    def save(self, record: AuditReportRecord) -> None:
        """Write an AuditReportRecord to /audit_reports/{report_id}."""
        db.reference(f"{self._PATH}/{record.report_id}").set(record.__dict__)

    def get(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Read a single audit report by ID; returns None if not found."""
        return db.reference(f"{self._PATH}/{report_id}").get()

    def get_all(self) -> Dict[str, Any]:
        """Read all audit reports from Firebase."""
        return db.reference(self._PATH).get() or {}


audit_report_repository = AuditReportRepository()
