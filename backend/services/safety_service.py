import math
import time
import uuid
from typing import Dict, List, Optional

from config.settings import settings
from models.alert import AlertRecord
from models.patrol_log import PatrolLogRecord
from models.position import PositionRecord
from models.safety_settings import SafetySettings
from repositories.alert_repository import alert_repository
from repositories.position_repository import position_repository
from repositories.safety_settings_repository import safety_settings_repository
from utils.timestamp_utils import utcnow_iso, seconds_between


_last_man_down: Dict[str, str] = {}    # person_id → ISO timestamp of last alert
_last_collision: Dict[str, str] = {}   # "worker_id|forklift_id" → ISO timestamp


class SafetyService:

    _SETTINGS_TTL_S = 30.0

    def __init__(self) -> None:
        self._settings_cache: Optional[SafetySettings] = None
        self._settings_cache_ts: float = 0.0

    def _get_settings(self) -> SafetySettings:
        now = time.monotonic()
        if self._settings_cache is not None and (now - self._settings_cache_ts) < self._SETTINGS_TTL_S:
            return self._settings_cache
        try:
            s = safety_settings_repository.get()
        except Exception:
            s = None
        if s is None:
            s = SafetySettings(
                man_down_minutes=settings.MAN_DOWN_MINUTES,
                collision_distance_m=settings.COLLISION_DISTANCE_M,
            )
        self._settings_cache = s
        self._settings_cache_ts = now
        return s

    def invalidate_settings_cache(self) -> None:
        self._settings_cache = None
        self._settings_cache_ts = 0.0

    # ------------------------------------------------------------------
    # FR3 / UC4 — Man-down detection
    # ------------------------------------------------------------------
    def check_man_down(self, current: PositionRecord) -> Optional[AlertRecord]:
        """Alert if a worker or guard has not moved for > MAN_DOWN_MINUTES.
        Forklifts are exempt. Fires regardless of zone."""
        if current.person_type == "forklift":
            return None

        elapsed = seconds_between(current.timestamp, utcnow_iso())
        cfg = self._get_settings()
        if elapsed < cfg.man_down_minutes * 60:
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
        """Alert when a worker's Kalman-predicted position converges with a forklift's
        within COLLISION_ALERT_SECONDS. Suppresses repeat alerts for the same pair
        within 30 seconds."""
        workers   = [p for p in all_positions if p.person_type == "worker"   and p.predicted_x is not None]
        forklifts = [p for p in all_positions if p.person_type == "forklift" and p.predicted_x is not None]
        alerts: List[AlertRecord] = []

        cfg = self._get_settings()
        collision_distance = cfg.collision_distance_m

        for w in workers:
            for f in forklifts:
                dist = math.hypot(
                    w.predicted_x - f.predicted_x,  # type: ignore[operator]
                    w.predicted_y - f.predicted_y,  # type: ignore[operator]
                )
                if dist >= collision_distance:
                    continue

                pair_key = f"{w.person_id}|{f.person_id}"
                last_ts = _last_collision.get(pair_key)
                if last_ts and seconds_between(last_ts, utcnow_iso()) < 10:
                    continue

                record = AlertRecord(
                    alert_id=str(uuid.uuid4()),
                    alert_type="collision",
                    person_id=w.person_id,
                    zone=w.zone,
                    timestamp=utcnow_iso(),
                    other_person_id=f.person_id,
                )
                alert_repository.save(record)
                _last_collision[pair_key] = record.timestamp
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
