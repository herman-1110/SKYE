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
    # Per-floor, not a settings.py global (Prompt 122) — "suit the size of the
    # space" is per-floor by definition. Real Firestore data, unlike
    # patrol_proximity_radius_m below. Default 10: observed lap time ~2 min,
    # straddle probability is roughly lap/window, so 10 min keeps splitting
    # rare (~25%) without delaying reports the way a much longer window would.
    patrol_interval_minutes: int = 10
    # Global backend setting (config/settings.py), not per-floor Firestore data —
    # riding along on this existing floor->frontend crossing (Prompt 117) instead
    # of a second hardcoded frontend copy or a dedicated settings endpoint.
    patrol_proximity_radius_m: float = 0.0
