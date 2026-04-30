import uuid
from typing import Any, Dict, List

import google.generativeai as genai

from config.settings import settings
from models.audit_report import AuditReportRecord
from repositories.audit_report_repository import audit_report_repository
from services.rag_service import rag_service
from utils.timestamp_utils import utcnow_iso


class LLMService:
    MODEL = "gemini-2.5-flash"

    def __init__(self) -> None:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self._model = genai.GenerativeModel(self.MODEL)

    def _build_prompt(
        self,
        shift_id: str,
        patrol_summaries: List[Dict[str, Any]],
        alert_summaries: List[Dict[str, Any]],
        rag_context: str,
    ) -> str:
        patrol_lines = "\n".join(
            f"- Guard {p.get('guard_id')}: {p.get('checkpoint_name')} | "
            f"compliant={p.get('compliant')} | dwell={p.get('dwell_time_seconds')}s"
            for p in patrol_summaries
        ) or "No patrol data."

        alert_lines = "\n".join(
            f"- [{a.get('alert_type')}] zone={a.get('zone')} "
            f"person={a.get('person_id')} at {a.get('timestamp')}"
            for a in alert_summaries
        ) or "No alerts."

        return (
            "You are an industrial safety audit AI.\n"
            f"Generate a structured audit report for shift {shift_id}.\n\n"
            f"## Patrol Log\n{patrol_lines}\n\n"
            f"## Safety Alerts\n{alert_lines}\n\n"
            f"## Historical Context\n{rag_context}\n\n"
            "Provide: (1) overall safety rating 1-10, "
            "(2) key risk findings, (3) recommended corrective actions."
        )

    def generate_report(
        self,
        shift_id: str,
        patrol_summaries: List[Dict[str, Any]],
        alert_summaries: List[Dict[str, Any]],
    ) -> AuditReportRecord:
        """Build prompt, inject RAG context, call Gemini 2.5 Flash, persist and return report."""
        rag_context = rag_service.get_context(f"shift {shift_id} safety audit")
        prompt = self._build_prompt(shift_id, patrol_summaries, alert_summaries, rag_context)

        response = self._model.generate_content(prompt)

        record = AuditReportRecord(
            report_id=str(uuid.uuid4()),
            shift_id=shift_id,
            generated_at=utcnow_iso(),
            patrol_summary=str(patrol_summaries),
            alert_summary=str(alert_summaries),
            rag_examples_used=[rag_context],
            report_text=response.text,
            model_used=self.MODEL,
        )
        audit_report_repository.save(record)
        return record


llm_service = LLMService()
