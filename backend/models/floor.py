from dataclasses import dataclass
from typing import Optional


@dataclass
class FloorRecord:
    id: str
    building_id: str
    name: str
    floor_number: int
    url: str
    storage_path: str
    is_active: bool
    uploaded_at: str
    scale_pixels_per_meter: Optional[float] = None
