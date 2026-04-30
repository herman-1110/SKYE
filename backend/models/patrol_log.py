from dataclasses import dataclass
from typing import Optional


@dataclass
class PatrolLogRecord:
    log_id: str
    guard_id: str
    checkpoint_id: str
    checkpoint_name: str
    expected_arrival: str     # ISO 8601
    actual_arrival: Optional[str]  # ISO 8601; None if guard missed the checkpoint
    dwell_time_seconds: int
    min_dwell_required: int
    ble_detected: bool
    vigi_detected: bool
    compliant: bool
    shift_id: str
