from typing import Any, Dict, List
from pydantic import BaseModel


class ReportRequest(BaseModel):
    shift_id: str
    patrol_summaries: List[Dict[str, Any]] = []
    alert_summaries: List[Dict[str, Any]] = []
