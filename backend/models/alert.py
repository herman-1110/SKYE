from dataclasses import dataclass


@dataclass
class AlertRecord:
    alert_id: str
    alert_type: str    # "man_down" | "collision" | "ghost_patrol" | "patrol_violation"
    person_id: str
    zone: str
    timestamp: str     # ISO 8601
    resolved: bool = False
    # Feedback fields removed — feedback lives in Firestore /feedback collection
