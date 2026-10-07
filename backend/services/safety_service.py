import math
import time
import uuid
from dataclasses import asdict, dataclass
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
# person_id → (anchor_x, anchor_y, since_iso, anchor_is_approximate): where the
# person was last seen genuinely moving, and when. Man-down fires if they stay
# within MAN_DOWN_MOVEMENT_EPSILON_M of the anchor past the threshold.
# anchor_is_approximate records whether that anchor came from an exact solve or
# a proximity-fallback estimate, so a later reading of the OTHER kind can be
# recognised as incomparable rather than measured as movement (Prompt 111 §2).
_man_down_tracker: Dict[str, tuple[float, float, str, bool]] = {}
# person_ids that have already fired a signal-loss man-down and haven't been
# seen again since. Prevents the stale sweep from re-alerting every tick for
# a beacon that's simply staying dead. Cleared in check_man_down() the moment
# a fresh position for that person arrives.
_stale_alerted: Set[str] = set()


@dataclass
class _TrackerHealth:
    """Patrol-tracker invocation health (Prompt 126), observed here because
    run_all_checks() is the only place a tracker exception is ever caught —
    see its try/except below. consecutive_failures resets to 0 on any
    successful invocation; total_failures never resets. last_invocation_at
    is stamped at the very top of run_all_checks(), before check_man_down()
    or the tracker call — it advances on every call regardless of outcome,
    so it splits three states that would otherwise be indistinguishable:
    tracker throwing (failures climbing), something upstream in
    run_all_checks() dying before the tracker block runs (last_invocation_at
    fresh, last_success_at stale), and no ingest reaching it at all (both
    stale).

    Per-process, in-memory: lost on restart, not shared across uvicorn
    workers — same class of caveat as _stale_alerted above. Single-worker
    dev/capture runs are unaffected.
    """
    consecutive_failures: int = 0
    total_failures: int = 0
    last_error: Optional[str] = None
    last_error_at: Optional[str] = None
    last_success_at: Optional[str] = None
    last_invocation_at: Optional[str] = None


class SafetyService:

    _SETTINGS_TTL_S = 30.0

    def __init__(self) -> None:
        self._settings_cache: Optional[SafetySettings] = None
        self._settings_cache_ts: float = 0.0
        self._tracker_health = _TrackerHealth()

    def get_tracker_health(self) -> dict:
        """Read-only snapshot for the /health/tracker route."""
        return asdict(self._tracker_health)

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
            _man_down_tracker[pid] = (current.x, current.y, now, current.is_approximate)
            return None

        anchor_x, anchor_y, since_iso, anchor_is_approximate = prev

        # Asymmetric on purpose (Prompt 113 — fixes a real regression from
        # Prompt 111's symmetric version). An approximate position's x/y is
        # the anchor AP's own coordinate, not a comparable fix to an exact
        # solve's x/y — comparing them reads as a multi-metre teleport. But
        # the anchor must be allowed to UPGRADE from approximate to exact:
        # the only two write sites are cold-start (unreachable once an anchor
        # exists) and the movement-reset below (unreachable while types keep
        # mismatching), so a symmetric guard permanently locks the anchor to
        # whichever type happened to seed it first. On real hardware the
        # first-ever flush after process start almost always seeds
        # approximate (only one AP has posted yet) — that anchor would then
        # reject every future exact solve forever, and man-down could never
        # fire. Downgrading (exact anchor + approximate current) stays
        # rejected: an approximate reading is never better information than
        # an exact anchor already holds.
        if anchor_is_approximate and not current.is_approximate:
            # Upgrade. Re-seed from here, not from since_iso — the clock
            # deliberately restarts. Before this exact solve there was no
            # real position to measure stillness against; preserving the old
            # since_iso would let a moving person accumulate stillness they
            # never earned. A person already motionless at startup simply
            # waits man_down_minutes from their first exact solve rather than
            # from first sighting — an accepted, correct cost.
            _man_down_tracker[pid] = (current.x, current.y, now, current.is_approximate)
            return None
        if current.is_approximate != anchor_is_approximate:
            # Exact anchor + approximate current: never downgrade. Leave
            # anchor and clock untouched (Prompt 111 §2, unchanged).
            return None

        moved = math.hypot(current.x - anchor_x, current.y - anchor_y)

        # Genuine movement: re-anchor to the new spot and reset the clock.
        # Do NOT re-anchor on every call — only when epsilon is broken — or the
        # anchor chases position jitter and the person never appears still.
        if moved >= settings.MAN_DOWN_MOVEMENT_EPSILON_M:
            _man_down_tracker[pid] = (current.x, current.y, now, current.is_approximate)
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
            cause="stillness",
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
    def is_patrol_violation(self, patrol_log: PatrolLogRecord) -> bool:
        """Pure per-visit violation check, no alert side-effect (Prompt 123).
        Shared by check_patrol_compliance() (the older one-shot alerting path)
        and the real-time tracker, which uses it to set each individual log
        record's `compliant` flag — the raw per-visit record — without
        itself deciding whether to alert; see check_patrol_window_compliance().

        A not_in_window record (Prompt 122) means the checkpoint's time-boxed
        window closed before it was reached — never a violation regardless of
        actual_arrival/dwell (both are always their zero/None defaults on
        this kind of record anyway).
        """
        if patrol_log.not_in_window:
            return False
        return (
            patrol_log.actual_arrival is None
            or patrol_log.dwell_time_seconds < patrol_log.min_dwell_required
        )

    def check_patrol_compliance(self, patrol_log: PatrolLogRecord) -> Optional[AlertRecord]:
        """Alert immediately if guard missed a checkpoint or dwell time is
        below the required minimum. Used by the older one-shot simulation
        path (simulation_events.py) — one visit is the whole state there, no
        window/multi-lap concept exists. The real-time tracker (Prompt 123)
        no longer calls this per-visit; see check_patrol_window_compliance().
        """
        if not self.is_patrol_violation(patrol_log):
            return None
        cause = "missed_checkpoint" if patrol_log.actual_arrival is None else "short_dwell"
        record = AlertRecord(
            alert_id=str(uuid.uuid4()),
            alert_type="patrol_violation",
            person_id=patrol_log.guard_id,
            zone=patrol_log.checkpoint_name,
            timestamp=utcnow_iso(),
            cause=cause,
        )
        alert_repository.save(record)
        return record

    def check_patrol_window_compliance(
        self, guard_id: str, checkpoint_name: str, visits: List[PatrolLogRecord],
    ) -> Optional[AlertRecord]:
        """Fire at most one patrol_violation for one checkpoint across an
        entire time-boxed window (Prompt 123) — the replacement for the old
        once-per-visit discipline (v20 §10), which stopped bounding anything
        once 122 made looping within a window normal (hardware confirmed one
        window with 9 real visits across 3 checkpoints).

        REPLACEMENT INVARIANT for v20 §10's "check_patrol_compliance() runs
        exactly once per completed checkpoint visit": a patrol_violation
        alert fires at most once per checkpoint per window, decided at
        window close against that checkpoint's BEST visit — a compliant
        visit beats a non-compliant one; among non-compliant, the longest
        dwell wins; tie-broken by expected_arrival for determinism (mirrors
        the frontend's identical selection in patrolLogOrder.ts). Per-visit
        `compliant` on each individual PatrolLogRecord is unchanged — only
        the alert decision moved to window scope. `visits` must be every log
        closed for this checkpoint this window, including any not_in_window
        backfill — is_patrol_violation() already excludes those from ever
        winning "best" unless they're the only entry.
        """
        best = min(visits, key=lambda v: (0 if v.compliant else 1, -v.dwell_time_seconds, v.expected_arrival))
        if best.compliant:
            return None
        cause = "missed_checkpoint" if best.actual_arrival is None else "short_dwell"
        record = AlertRecord(
            alert_id=str(uuid.uuid4()),
            alert_type="patrol_violation",
            person_id=guard_id,
            zone=checkpoint_name,
            timestamp=utcnow_iso(),
            cause=cause,
        )
        alert_repository.save(record)
        return record

    def check_patrol_window_no_patrol(
        self,
        guard_id: str,
        zone: str,
        route_len: int,
        window_s: float,
        visits_by_checkpoint: Dict[int, List[PatrolLogRecord]],
        last_seen_at: Optional[str],
    ) -> Optional[AlertRecord]:
        """Fire patrol_violation/no_patrol once per window when a guard was
        demonstrably on the floor but never genuinely patrolled it (Prompt
        125 — v21 §6/§9.6/§11: the parked-at-CP0 guard produces one real,
        compliant, window-length visit and nothing else, which the
        per-checkpoint evaluation above correctly does not treat as a
        violation on its own).

        Absence must never fire this: last_seen_at is None means no exact
        position tick reached the tracker this window at all (genuinely
        absent, or under 3-AP coverage — see patrol_tracker_service.py's
        module docstring; this feature inherits that constraint, it doesn't
        introduce it) — indistinguishable from "not here", never a
        violation, same reasoning as a not_in_window checkpoint.

        Firing condition, agreed before implementation:
          - 0 checkpoints reached this window (despite presence): fires.
          - exactly 1 checkpoint reached, on a route of >=2: fires only if
            that checkpoint's best visit consumed >= PATROL_NO_PATROL_
            DWELL_RATIO of the window — corroborates "parked" against a
            legitimate late first arrival that a short window simply cut
            off before a second checkpoint was reachable.
          - a 1-checkpoint route reaching its sole checkpoint: never fires
            — that checkpoint IS the whole patrol there.
          - >=2 checkpoints reached: never fires, regardless of dwell. This
            is what protects the benign straddle (122's core guarantee) —
            categorically, not by tuning a threshold near it.
        """
        if last_seen_at is None:
            return None

        reached = {
            idx for idx, visits in visits_by_checkpoint.items()
            if any(not v.not_in_window for v in visits)
        }

        if len(reached) == 0:
            pass  # definite no_patrol — presence with zero real visits
        elif len(reached) == 1 and route_len >= 2:
            idx = next(iter(reached))
            best_dwell = max(
                v.dwell_time_seconds for v in visits_by_checkpoint[idx] if not v.not_in_window
            )
            if best_dwell < window_s * settings.PATROL_NO_PATROL_DWELL_RATIO:
                return None  # legitimate late first arrival, not parked
        else:
            return None  # >=2 reached, or the sole checkpoint on a 1-stop route

        record = AlertRecord(
            alert_id=str(uuid.uuid4()),
            alert_type="patrol_violation",
            person_id=guard_id,
            zone=zone,
            timestamp=utcnow_iso(),
            cause="no_patrol",
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
        """Run man-down, patrol-tracking, and collision checks for a freshly computed position."""
        # Stamped before anything else in this method runs, including
        # check_man_down() below — see _TrackerHealth's docstring for why
        # this specific ordering is what makes the three health states
        # distinguishable (Prompt 126).
        self._tracker_health.last_invocation_at = utcnow_iso()

        self.check_man_down(current)

        # local import: keeps safety_service<->patrol_tracker_service decoupled
        # at module-load time, same pattern zone_service uses for
        # positioning_service. Wrapped defensively — a tracker bug must never
        # take down position ingest or man-down detection, which both run in
        # this same call. Same posture as RAG's failure handling (Prompt 109).
        try:
            from services.patrol_tracker_service import patrol_tracker_service
            patrol_tracker_service.check_patrol_progress(current)
            self._tracker_health.last_success_at = utcnow_iso()
            self._tracker_health.consecutive_failures = 0
        except Exception as e:
            h = self._tracker_health
            h.consecutive_failures += 1
            h.total_failures += 1
            # Defensive against a custom __str__ that itself raises (Prompt
            # 126 VALIDATION A6) — this recording code must be trivially
            # incapable of throwing, since if it does, ingest breaks, which
            # is the exact outcome the outer except exists to prevent.
            try:
                detail = str(e)
            except Exception:
                detail = "<exception str() raised>"
            h.last_error = f"{type(e).__name__}: {detail}"[:500]
            h.last_error_at = utcnow_iso()
            print(
                f"[SAFETY] WARNING: patrol tracker failed for a position update "
                f"(consecutive_failures={h.consecutive_failures}): {h.last_error}"
            )

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
