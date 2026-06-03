from dataclasses import dataclass, field
from typing import List


@dataclass
class APRssiReading:
    ap_mac: str
    rssi: float
    ap_x: float
    ap_y: float


@dataclass
class OmadaTelemetryPayload:
    reporter_mac: str     # BLE beacon MAC address
    timestamp: str        # ISO 8601
    readings: List[APRssiReading] = field(default_factory=list)
    person_id: str = ""
    person_type: str = "worker"   # "guard" | "worker" | "forklift"
    label: str = ""
