import math
import uuid
from typing import Dict, List, Optional

from config.settings import settings
from models.alert import AlertRecord
from models.patrol_log import PatrolLogRecord
from models.position import PositionRecord
from repositories.alert_repository import alert_repository
from repositories.floor_repository import floor_repository
from repositories.position_repository import position_repository
from utils.timestamp_utils import utcnow_iso, seconds_between
from utils.zone_utils import is_high_risk


_last_man_down: Dict[str, str] = {}  # person_id → ISO timestamp of last alert


class SafetyService:

    # ------------------------------------------------------------------
    # FR3 / UC4 — Man-down detection
    # ------------------------------------------------------------------
    def check_man_down(self, current: PositionRecord) -> Optional[AlertRecord]:
        """Alert if a worker has not moved in a high-risk zone for > MAN_DOWN_MINUTES."""
        if current.person_type != "worker":
            return None

        floor = floor_repository.get_any_active()
        building_id: str = floor.building_id if floor else ""
        floor_id: str = floor.id if floor else ""
        if not is_high_risk(current.x, current.y, building_id, floor_id):
            return None

        previous = position_repository.get(current.beacon_mac)
        if previous is None:
            return None

        elapsed = seconds_between(previous["timestamp"], current.timestamp)
        if elapsed < settings.MAN_DOWN_MINUTES * 60:
            return None

        dx = current.x - float(previous.get("x", current.x))
        dy = current.y - float(previous.get("y", current.y))
        if math.hypot(dx, dy) >= settings.MAN_DOWN_MOVEMENT_THRESHOLD:
            return None

        last_ts = _last_man_down.get(current.person_id)
        if last_ts and seconds_between(last_ts, utcnow_iso()) < 30:
            return None

        record = AlertRecord(
            alert_id=str(uuid.uuid4()),
            alert_type="man_down",
            person_id=current.person_id,
            zone=current.zone,
            timestamp=utcnow_iso(),
        )
        alert_repository.save(record)
        _last_man_down[current.person_id] = record.timestamp
        return record

    # ------------------------------------------------------------------
    # FR4 / NFR2 / UC5 — Collision prediction
    # ------------------------------------------------------------------
    def check_collision(self, all_positions: List[PositionRecord]) -> List[AlertRecord]:
        """Alert when a worker's and a forklift's predicted positions converge within COLLISION_ALERT_SECONDS."""
        workers = [p for p in all_positions if p.person_type == "worker" and p.predicted_x is not None]
        forklifts = [p for p in all_positions if p.person_type == "forklift" and p.predicted_x is not None]
        alerts: List[AlertRecord] = []

        for w in workers:
            for f in forklifts:
                dist = math.hypot(
                    w.predicted_x - f.predicted_x,  # type: ignore[operator]
                    w.predicted_y - f.predicted_y,  # type: ignore[operator]
                )
                if dist < settings.MAN_DOWN_MOVEMENT_THRESHOLD * 2:
                    record = AlertRecord(
                        alert_id=str(uuid.uuid4()),
                        alert_type="collision",
                        person_id=w.person_id,
                        zone=w.zone,
                        timestamp=utcnow_iso(),
                    )
                    alert_repository.save(record)
                    alerts.append(record)
        return alerts

    # ------------------------------------------------------------------
    # FR5 / UC3 — Patrol compliance
    # ------------------------------------------------------------------
    def check_patrol_compliance(self, patrol_log: PatrolLogRecord) -> Optional[AlertRecord]:
        """Alert if guard missed a checkpoint or dwell time is below the required minimum."""
        violation = (
            patrol_log.actual_arrival is None
            or patrol_log.dwell_time_seconds < patrol_log.min_dwell_required
        )
        if not violation:
            return None

        record = AlertRecord(
            alert_id=str(uuid.uuid4()),
            alert_type="patrol_violation",
            person_id=patrol_log.guard_id,
            zone=patrol_log.checkpoint_name,
            timestamp=utcnow_iso(),
        )
        alert_repository.save(record)
        return record

    # ------------------------------------------------------------------
    # UC2 — Ghost patrol multi-modal verification
    # ------------------------------------------------------------------
    def verify_multimodal(
        self,
        patrol_log: PatrolLogRecord,
        ble_detected: bool,
        vigi_detected: bool,
    ) -> Optional[AlertRecord]:
        """Ghost Patrol fires ONLY when BLE tag IS present but VIGI does NOT confirm human presence."""
        if not ble_detected or vigi_detected:
            return None

        record = AlertRecord(
            alert_id=str(uuid.uuid4()),
            alert_type="ghost_patrol",
            person_id=patrol_log.guard_id,
            zone=patrol_log.checkpoint_name,
            timestamp=utcnow_iso(),
        )
        alert_repository.save(record)
        return record

    # ------------------------------------------------------------------
    # Convenience entry point called from telemetry route
    # ------------------------------------------------------------------
    def run_all_checks(self, current: PositionRecord) -> None:
        """Run man-down and collision checks for a freshly computed position."""
        self.check_man_down(current)
        raw_all = position_repository.get_all()
        all_positions = [
            PositionRecord(**v) for v in raw_all.values() if isinstance(v, dict)
        ]
        self.check_collision(all_positions)


safety_service = SafetyService()
