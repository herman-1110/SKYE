from dataclasses import dataclass, field
from typing import List, Optional


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
    image_width_px: Optional[int] = None
    image_height_px: Optional[int] = None
    patrol_enabled: bool = False
    patrol_route: List[str] = field(default_factory=list)
