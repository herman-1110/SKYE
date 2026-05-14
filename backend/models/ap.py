from dataclasses import dataclass


@dataclass
class AccessPoint:
    id: str
    floor_id: str
    building_id: str
    name: str
    mac: str
    x_pct: float    # 0.0–1.0 fraction of image width
    y_pct: float    # 0.0–1.0 fraction of image height
    created_at: str
