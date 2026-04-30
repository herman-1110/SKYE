from dataclasses import dataclass, field
from typing import List


@dataclass
class AuditReportRecord:
    report_id: str
    shift_id: str
    generated_at: str         # ISO 8601
    patrol_summary: str
    alert_summary: str
    rag_examples_used: List[str] = field(default_factory=list)
    report_text: str = ""
    model_used: str = "gemini-2.5-flash"
