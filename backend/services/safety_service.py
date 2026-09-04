import math
import time
import uuid
from typing import Dict, List, Optional, Set

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
# person_id → (anchor_x, anchor_y, since_iso): where the person was last seen
# genuinely moving, and when. Man-down fires if they stay within
# MAN_DOWN_MOVEMENT_EPSILON_M of the anchor past the threshold.
_man_down_tracker: Dict[str, tuple[float, float, str]] = {}
# person_ids that have already fired a signal-loss man-down and haven't been
# seen again since. Prevents the stale sweep from re-alerting every tick for
# a beacon that's simply staying dead. Cleared in check_man_down() the moment
# a fresh position for that person arrives.
_stale_alerted: Set[str] = set()


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
        """Alert if a worker or guard has stayed within MAN_DOWN_MOVEMENT_EPSILON_M
        of their last-moved position for longer than MAN_DOWN_MINUTES.

        Forklifts are exempt. Fires regardless of zone. Alerts raised from an
        approximate (proximity-fallback) position are flagged approximate=True:
        single/dual-AP coverage cannot reliably tell 'still' from 'small movement',
        so the alert is treated as a low-confidence welfare check, not a precise fix.
        """
        # A fresh position means this beacon is transmitting again — let it
        # fire a signal-loss alert a second time if it goes dark again later.
        # Before the forklift early-return so it applies regardless of type.
        _stale_alerted.discard(current.person_id)

        if current.person_type == "forklift":
            return None

        cfg = self._get_settings()
        now = utcnow_iso()
        pid = current.person_id

        prev = _man_down_tracker.get(pid)

        # First time we see this person: seed the tracker and start the clock.
        # (Cold-start case — including a beacon that appears in a dead zone and
        # never moves — begins counting from first sighting.)
        if prev is None:
            _man_down_tracker[pid] = (current.x, current.y, now)
            return None

        anchor_x, anchor_y, since_iso = prev
        moved = math.hypot(current.x - anchor_x, current.y - anchor_y)

        # Genuine movement: re-anchor to the new spot and reset the clock.
        # Do NOT re-anchor on every call — only when epsilon is broken — or the
        # anchor chases position jitter and the person never appears still.
        if moved >= settings.MAN_DOWN_MOVEMENT_EPSILON_M:
            _man_down_tracker[pid] = (current.x, current.y, now)
            return None

        # Within epsilon: still. Has the clock run past the threshold?
        if seconds_between(since_iso, now) < cfg.man_down_minutes * 60:
            return None

        # Repeat-alert suppression (unchanged): one man-down per person per 30s.
        last_ts = _last_man_down.get(pid)
        if last_ts and seconds_between(last_ts, now) < 30:
            return None

        record = AlertRecord(
            alert_id=str(uuid.uuid4()),
            alert_type="man_down",
            person_id=pid,
            zone=current.zone,
            timestamp=now,
            approximate=current.is_approximate,
        )
        alert_repository.save(record)
        _last_man_down[pid] = record.timestamp
        return record

    def check_man_down_stale(self) -> List[AlertRecord]:
        """Fire a signal-loss man-down for any beacon whose last known /positions
        record has gone stale, independent of the telemetry path. Catches battery
        death, a guard leaving AP coverage, or a beacon destroyed in the incident
        itself — none of which ever produce a fresh position, so check_man_down()
        (which only runs after a position is successfully computed) never sees them.

        Called from a background sweep, not per-telemetry-packet.
        """
        now = utcnow_iso()
        raw_all = position_repository.get_all()
        fired: List[AlertRecord] = []

        for key, v in raw_all.items():
            if not isinstance(v, dict):
                continue
            try:
                record = PositionRecord(**v)
            except TypeError as e:
                print(f"[SAFETY] WARNING: skipping malformed /positions/{key}: {e}")
                continue

            if record.person_type == "forklift":
                continue

            pid = record.person_id
            if pid in _stale_alerted:
                continue

            age = seconds_between(record.timestamp, now)
            if age < settings.MAN_DOWN_STALE_SECONDS:
                continue
            if age > settings.MAN_DOWN_STALE_MAX_AGE_S:
                # Dead record, not an active incident — see MAN_DOWN_STALE_MAX_AGE_S.
                continue

            # Second dedup layer, same suppressor check_man_down() uses.
            last_ts = _last_man_down.get(pid)
            if last_ts and seconds_between(last_ts, now) < 30:
                continue

            alert = AlertRecord(
                alert_id=str(uuid.uuid4()),
                alert_type="man_down",
                person_id=pid,
                zone=record.zone,
                timestamp=now,
                approximate=record.is_approximate,
                cause="signal_loss",
            )
            alert_repository.save(alert)
            _last_man_down[pid] = alert.timestamp
            _stale_alerted.add(pid)
            fired.append(alert)

        return fired

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
        all_positions: List[PositionRecord] = []
        for key, v in raw_all.items():
            if not isinstance(v, dict):
                continue
            try:
                all_positions.append(PositionRecord(**v))
            except TypeError as e:
                # A stray/partial RTDB node (e.g. a label patch that landed before
                # any full position record existed at this key) shouldn't take down
                # every telemetry request — skip it and keep going.
                print(f"[SAFETY] WARNING: skipping malformed /positions/{key}: {e}")
        self.check_collision(all_positions)


safety_service = SafetyService()
