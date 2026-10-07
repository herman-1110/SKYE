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
    cycle_id: str = ""  # groups checkpoint visits into one real-time patrol lap;
                        # "" for pre-existing/simulated logs that predate this field
    # True only for a checkpoint the time-boxed window closed before reaching
    # (Prompt 122) — distinct from a genuine skip (actual_arrival is None with
    # this False, unchanged meaning). Absent/False on every log written before
    # Prompt 122 — those keep rendering under the old wrap-model semantics,
    # by construction, since this field didn't exist yet.
    not_in_window: bool = False
