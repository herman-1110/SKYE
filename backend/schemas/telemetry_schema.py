import re
from datetime import datetime, timedelta, timezone
from typing import List, Literal

from pydantic import BaseModel, Field, field_validator

from utils.timestamp_utils import parse_iso

_MAC_RE = re.compile(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$')

# How far ahead of this server's clock a telemetry timestamp may be (Prompt 135, COR-01).
MAX_FUTURE_SKEW = timedelta(minutes=5)


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

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Prompt 135 (COR-01): the timestamp is stored on the position and
        later parsed by the signal-loss sweep with seconds_between(), so it has
        to be something that parser accepts - ISO 8601 with a time zone - and
        no more than MAX_FUTURE_SKEW ahead of this server. Anything else is a
        422 here rather than a record that breaks the sweep. Past timestamps
        are fine (the simulator's backdated man-down seed is six minutes old)."""
        v = v.strip()
        try:
            ts = parse_iso(v)
        except (TypeError, ValueError):
            raise ValueError("timestamp must be an ISO 8601 date-time with a time zone") from None
        if ts.tzinfo is None or ts.utcoffset() is None:
            raise ValueError("timestamp must include a time zone, e.g. +00:00")
        if ts > datetime.now(timezone.utc) + MAX_FUTURE_SKEW:
            raise ValueError("timestamp is more than 5 minutes ahead of the server's clock")
        return v
