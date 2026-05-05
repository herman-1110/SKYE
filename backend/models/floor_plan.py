from dataclasses import dataclass
from typing import Optional


@dataclass
class FloorPlanRecord:
    floor_plan_id: str               # Firestore document ID
    user_id: str                     # owning Security Manager UID
    name: str                        # e.g. "Level 1 — Warehouse A"
    url: str                         # Firebase Storage download URL
    uploaded_at: str                 # ISO 8601
    is_active: bool                  # only one plan active per user at a time
    scale_pixels_per_meter: Optional[float] = None  # set after calibration, None until calibrated
