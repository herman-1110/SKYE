from dataclasses import dataclass, field


@dataclass
class ZoneRecord:
    id: str
    floor_id: str
    name: str
    color: str            # hex with alpha e.g. "#ef444433"
    is_high_risk: bool
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    created_at: str
    created_by: str
    risk_level: str = field(default="moderate")   # "high" | "moderate" | "low"
