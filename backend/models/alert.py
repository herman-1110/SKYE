from dataclasses import dataclass
from typing import Optional


@dataclass
class AlertRecord:
    alert_id: str
    alert_type: str    # "man_down" | "collision" | "ghost_patrol" | "patrol_violation"
    person_id: str
    zone: str
    timestamp: str     # ISO 8601
    resolved: bool = False
    other_person_id: Optional[str] = None   # collision only: the other party
