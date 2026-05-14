import re
from typing import List, Literal

from pydantic import BaseModel, Field, field_validator

_MAC_RE = re.compile(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$')


def _validate_mac(v: str) -> str:
    if not _MAC_RE.match(v):
        raise ValueError("Invalid MAC address format (expected XX:XX:XX:XX:XX:XX)")
    return v.upper()


class APRssiSchema(BaseModel):
    ap_mac: str = Field(..., min_length=17, max_length=17)
    rssi: float = Field(..., ge=-120, le=0)
    ap_x: float = Field(..., ge=0, le=10_000)
    ap_y: float = Field(..., ge=0, le=10_000)

    @field_validator("ap_mac")
    @classmethod
    def validate_ap_mac(cls, v: str) -> str:
        return _validate_mac(v)


class TelemetryRequest(BaseModel):
    reporter_mac: str = Field(..., min_length=17, max_length=17)
    timestamp: str = Field(..., min_length=1, max_length=64)
    readings: List[APRssiSchema] = Field(..., max_length=50)
    person_id: str = Field(default="", max_length=64)
    person_type: Literal["guard", "worker", "forklift"] = "worker"

    @field_validator("reporter_mac")
    @classmethod
    def validate_reporter_mac(cls, v: str) -> str:
        return _validate_mac(v)
