from typing import List
from pydantic import BaseModel


class APRssiSchema(BaseModel):
    ap_mac: str
    rssi: float
    ap_x: float
    ap_y: float


class TelemetryRequest(BaseModel):
    reporter_mac: str
    timestamp: str
    readings: List[APRssiSchema]
    person_id: str = ""
    person_type: str = "worker"
