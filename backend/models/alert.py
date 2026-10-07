from dataclasses import dataclass
from typing import Optional


@dataclass
class AlertRecord:
    alert_id: str
    alert_type: str    # "man_down" | "collision" | "ghost_patrol" | "patrol_violation"
    person_id: str
    zone: str
    timestamp: str     # ISO 8601
    resolved: bool = False
    other_person_id: Optional[str] = None   # collision only: the other party
    approximate: bool = False               # man_down: raised from a single/dual-AP proximity fix (low-confidence)
    # man_down: "stillness" (not moving) | "signal_loss" (beacon went dark)
    # patrol_violation: "missed_checkpoint" | "short_dwell" (Prompt 123) | "no_patrol" (Prompt 125)
    # collision / ghost_patrol: no cause taxonomy — always None.
    # None default on purpose (Prompt 125): a str default that happens to
    # equal a real value ("stillness") let every write site that forgot to
    # pass cause silently mislabel itself as a stillness man_down instead of
    # visibly carrying nothing. Every site must now pass cause explicitly.
    cause: Optional[str] = None
