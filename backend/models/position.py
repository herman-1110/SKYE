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
    pixel_x: Optional[float] = None   # metres × scale_pixels_per_meter from active floor plan
    pixel_y: Optional[float] = None
    is_stationary: bool = False
    floor_id: str = ""
    building_id: str = ""
    label: str = ""
