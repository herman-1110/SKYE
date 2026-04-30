from dataclasses import dataclass
from typing import Optional


@dataclass
class PositionRecord:
    beacon_mac: str
    person_id: str
    person_type: str          # "guard" | "worker" | "forklift"
    x: float
    y: float
    zone: str
    timestamp: str            # ISO 8601
    predicted_x: Optional[float] = None
    predicted_y: Optional[float] = None
    is_stationary: bool = False
