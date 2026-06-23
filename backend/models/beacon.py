from dataclasses import dataclass
from typing import Optional


@dataclass
class Beacon:
    id: str            # composite key: "<uuid_lowercase>:<major>:<minor>"
    uuid: str
    major: str
    minor: str
    person_id: str
    person_type: str   # "guard" | "worker" | "forklift"
    label: str
    created_at: str
    updated_at: str
    building_id: Optional[str] = None   # org tag only — NEVER used to resolve
    tx_power: float = -59.0             # RSSI at 1 metre; calibrate per device with nRF Connect
