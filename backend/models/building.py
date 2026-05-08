from dataclasses import dataclass


@dataclass
class BuildingRecord:
    id: str
    name: str
    description: str
    user_id: str
    created_at: str
