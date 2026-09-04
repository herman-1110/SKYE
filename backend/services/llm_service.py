import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from models.audit_report import AuditReportRecord
from providers.llm_factory import get_llm_provider
from repositories.audit_report_repository import audit_report_repository
from repositories.patrol_log_repository import patrol_log_repository
from services.rag_service import rag_service
from utils.timestamp_utils import utcnow_iso

provider = get_llm_provider()

_FORMAT_INSTRUCTIONS = (
    "Format your response using ONLY the following markdown:\n"
    "- **bold** for section headings and emphasis (use ## prefix for major sections)\n"
    "- Bullet points starting with '- ' for lists\n"
    "- Plain numbered lines '1. ' for ordered steps\n"
    "Do NOT use: #### or any heading level beyond ##, *italic*, "
    "`backticks`, or any HTML.\n"
    "Do NOT wrap person IDs or AP names in backticks.\n"
)


class LLMService:

    def _build_prompt(
        self,
        shift_id: str,
        patrol_summaries: List[Dict[str, Any]],
        alert_summaries: List[Dict[str, Any]],
        rag_context: str,
    ) -> str:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

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
            f"Today's date is {today}. Use this exact date as the Audit Date in your report.\n"
            f"Generate a structured audit report for shift {shift_id}.\n\n"
            f"## Patrol Log\n{patrol_lines}\n\n"
            f"## Safety Alerts\n{alert_lines}\n\n"
            f"## Historical Context\n{rag_context}\n\n"
            "Industrial Safety Audit Report"
            "Provide: (1) overall safety rating 1-10, "
            "(2) key risk findings, (3) recommended corrective actions.\n\n"
            + _FORMAT_INSTRUCTIONS
        )

    def _build_safety_prompt(
        self,
        person_id: str,
        date_str: str,
        alert_summaries: List[Dict[str, Any]],
    ) -> str:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        alert_lines = "\n".join(
            f"- [{a.get('alert_type')}] zone={a.get('zone_id', 'unknown')} "
            f"timestamp={a.get('timestamp')} "
            f"person_type={a.get('person_type', 'unknown')}"
            for a in alert_summaries
        ) or "No alerts recorded."

        return (
            "You are an industrial safety audit AI.\n"
            f"Today's date is {today}. Use this as the Audit Date.\n"
            f"Generate a safety incident report for person '{person_id}' on {date_str}.\n\n"
            f"## Safety Alerts ({len(alert_summaries)} incidents)\n{alert_lines}\n\n"
            "Provide:\n"
            "(1) Incident summary — what happened, when, in which zones\n"
            "(2) Risk assessment — severity of each alert type, zones repeatedly triggered\n"
            "(3) Behavioural pattern analysis — recurring times, locations, or sequences\n"
            "(4) Corrective actions — concrete recommendations (retraining, CCTV repositioning, "
            "zone reassignment, etc.)\n"
            "(5) Safety rating 1–10 based on incident severity and frequency\n\n"
            + _FORMAT_INSTRUCTIONS
        )

    def get_reportable_shifts(self) -> List[Dict[str, Any]]:
        return patrol_log_repository.get_reportable_shifts()

    def get_safety_event_groups(self) -> List[Dict[str, Any]]:
        from firebase_admin import db as rtdb

        alerts_ref = rtdb.reference("/alerts").get() or {}
        seen: Dict[str, Dict[str, Any]] = {}

        for v in alerts_ref.values():
            if not isinstance(v, dict):
                continue
            person_id = v.get("person_id", "")
            timestamp = str(v.get("timestamp", ""))
            if not person_id or len(timestamp) < 10:
                continue
            date_str = timestamp[:10]
            key = f"{person_id}|{date_str}"
            if key not in seen:
                seen[key] = {
                    "person_id": person_id,
                    "date_str": date_str,
                    "person_type": v.get("person_type", "unknown"),
                    "alert_count": 0,
                }
            seen[key]["alert_count"] += 1

        return sorted(seen.values(), key=lambda x: x["date_str"], reverse=True)

    def generate_report(self, log_id: str, guard_id: str) -> AuditReportRecord:
        from firebase_admin import db as rtdb

        checkpoints = patrol_log_repository.get_by_shift_and_guard(log_id, guard_id)
        if not checkpoints:
            raise ValueError(f"No patrol data found for shift {log_id!r} guard {guard_id!r}")

        alerts_ref = rtdb.reference("/alerts").get() or {}
        alert_summaries = [
            v for v in alerts_ref.values()
            if isinstance(v, dict) and v.get("person_id") == guard_id
        ]

        shift_id = log_id
        rag_context, rag_feedback_ids = rag_service.get_context_with_sources(
            f"shift {shift_id} safety audit"
        )
        prompt = self._build_prompt(shift_id, checkpoints, alert_summaries, rag_context)

        report_text = provider.generate(prompt)

        record = AuditReportRecord(
            report_id=str(uuid.uuid4()),
            shift_id=shift_id,
            guard_id=guard_id,
            generated_at=utcnow_iso(),
            patrol_summary=str(checkpoints),
            alert_summary=str(alert_summaries),
            rag_examples_used=rag_feedback_ids,
            report_text=report_text,
            model_used=provider.get_model_name(),
            report_type="patrol",
        )

        audit_report_repository.save(record)
        return record

    def generate_safety_report(self, person_id: str, date_str: str) -> AuditReportRecord:
        from firebase_admin import db as rtdb

        alerts_ref = rtdb.reference("/alerts").get() or {}
        alert_summaries = [
            v for v in alerts_ref.values()
            if isinstance(v, dict)
            and v.get("person_id") == person_id
            and str(v.get("timestamp", "")).startswith(date_str)
        ]

        if not alert_summaries:
            raise ValueError(
                f"No alerts found for person {person_id!r} on {date_str!r}"
            )

        shift_id = f"safety-{person_id}-{date_str}"
        prompt = self._build_safety_prompt(person_id, date_str, alert_summaries)
        report_text = provider.generate(prompt)

        record = AuditReportRecord(
            report_id=str(uuid.uuid4()),
            shift_id=shift_id,
            guard_id=person_id,
            generated_at=utcnow_iso(),
            patrol_summary="",
            alert_summary=str(alert_summaries),
            rag_examples_used=[],
            report_text=report_text,
            model_used=provider.get_model_name(),
            report_type="safety_event",
        )

        audit_report_repository.save(record)
        return record


llm_service = LLMService()
