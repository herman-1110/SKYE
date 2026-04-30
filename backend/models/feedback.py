from dataclasses import dataclass
from typing import Optional


@dataclass
class FeedbackRecord:
    feedback_id: str
    alert_id: str
    alert_type: str    # mirrors the original alert's type — used for RAG filtering
    zone: str          # mirrors the original alert's zone — used for RAG filtering
    feedback: str      # "confirmed" | "fixed" | "false_alarm"
    timestamp: str     # ISO 8601
    feedback_reason: Optional[str] = None
    shift_id: Optional[str] = None
