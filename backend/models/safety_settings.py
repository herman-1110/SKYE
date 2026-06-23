from dataclasses import dataclass


@dataclass
class SafetySettings:
    man_down_minutes: int = 5
    collision_distance_m: float = 2.0
    updated_at: str = ""
