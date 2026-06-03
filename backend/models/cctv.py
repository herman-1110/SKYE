from dataclasses import dataclass
from typing import Optional


@dataclass
class CCTV:
    id: str
    floor_id: str
    building_id: str
    name: str
    x_pct: float    # 0.0–1.0 fraction of image width
    y_pct: float    # 0.0–1.0 fraction of image height
    created_at: str
    mac: Optional[str] = None
