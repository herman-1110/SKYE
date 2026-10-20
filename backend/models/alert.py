from dataclasses import dataclass
from typing import Optional


@dataclass
class AlertRecord:
    alert_id: str
    # "man_down" | "possible_man_down" (Prompt 136: stillness seen by only one
    # or two APs) | "collision" | "ghost_patrol" | "patrol_violation"
    alert_type: str
    person_id: str
    zone: str
    timestamp: str     # ISO 8601
    resolved: bool = False
    other_person_id: Optional[str] = None   # collision only: the other party
    # True on possible_man_down (raised from single/dual-AP proximity fixes),
    # and on a signal-loss man_down whose last position was one
    approximate: bool = False
    # man_down: "stillness" (not moving) | "signal_loss" (beacon went dark)
    # possible_man_down: always "stillness"
    # patrol_violation: "missed_checkpoint" | "short_dwell" (Prompt 123) | "no_patrol" (Prompt 125)
    # collision / ghost_patrol: no cause taxonomy — always None.
    # None default on purpose (Prompt 125): a str default that happens to
    # equal a real value ("stillness") let every write site that forgot to
    # pass cause silently mislabel itself as a stillness man_down instead of
    # visibly carrying nothing. Every site must now pass cause explicitly.
    cause: Optional[str] = None
