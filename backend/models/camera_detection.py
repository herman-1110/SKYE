from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class CameraDetection:
    """One event from a camera's Alarm Server push, normalized across payload
    formats (Prompt 131 T3, docs/vigi-integration-design.md §2)."""
    camera_key: str                   # "ipc:98BA5F8B1003:1"
    source_type: str                  # "ipc"
    device_mac: str                   # "98:BA:5F:8B:10:03"
    channel: int
    event_type: str                   # "PEOPLE" | "MOTION" | anything else, upper-cased
    is_human: bool                    # True only for PEOPLE
    obj_num: Optional[int]            # enhanced format only
    regions: Optional[List[int]]      # enhanced format only
    boxes: Optional[List[dict]]       # enhanced: {x, y, w, h}; 0-10000 scale looks likely, UNCONFIRMED
    camera_time_raw: Optional[str]    # dateTime exactly as sent (no time zone)
    camera_time_utc: Optional[str]    # ISO 8601, using the camera's time zone; None if unparseable
    received_at: datetime             # server UTC; what matching uses
    source_ip: str
    payload_format: str               # "legacy" | "enhanced"
