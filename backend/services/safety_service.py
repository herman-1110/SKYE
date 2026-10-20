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
from repositories.ap_repository import ap_repository
from repositories.position_repository import position_repository
from repositories.safety_settings_repository import safety_settings_repository
from utils.mac_utils import ap_mac_colons
from utils.timestamp_utils import parse_iso, utcnow_iso, seconds_between


_last_man_down: Dict[str, str] = {}    # person_id → ISO timestamp of last alert
_last_collision: Dict[str, str] = {}   # "worker_id|forklift_id" → ISO timestamp
# person_id → (anchor_x, anchor_y, since_iso, anchor_is_approximate): where the
# person was last seen genuinely moving, and when. Man-down fires if they stay
# within MAN_DOWN_MOVEMENT_EPSILON_M of the anchor past the threshold.
# Only exact solves move this anchor or its clock. An approximate anchor is
# only ever a cold-start placeholder: the first exact solve replaces it
# (Prompt 113). Approximate readings are timed separately, in _approx_runs
# (Prompt 136, COR-03).
_man_down_tracker: Dict[str, tuple[float, float, str, bool]] = {}
# person_ids that have already fired a signal-loss man-down and haven't been
# seen again since. Prevents the stale sweep from re-alerting every tick for
# a beacon that's simply staying dead. Cleared in check_man_down() the moment
# a fresh position for that person arrives.
_stale_alerted: Set[str] = set()
# person_ids that have already fired a stillness man-down for the current
# stillness episode, i.e. since their anchor was last (re)seeded. One alert per
# episode, the same latch _stale_alerted gives signal-loss; without it a
# motionless beacon re-alerted every 30 s for as long as it stayed still.
# Cleared only where the anchor is (re)seeded in check_man_down(), so a beacon
# that goes dark and comes back still within epsilon of the same anchor is the
# same episode and doesn't alert again. Per-process, in-memory, like the rest.
_still_alerted: Set[str] = set()
# person_id (or /positions key) -> monotonic time its unreadable timestamp was
# last logged by check_man_down_stale() (Prompt 135, COR-01): once an hour each.
_bad_timestamp_logged: Dict[str, float] = {}
_BAD_TIMESTAMP_LOG_EVERY_S = 3600.0
# The same once-an-hour log for check_collision() (Prompt 136, COR-04), kept
# apart so the sweep's log and this one don't silence each other.
_collision_bad_timestamp_logged: Dict[str, float] = {}


@dataclass
class _ApproxRun:
    """One person's current approximate run (Prompt 136, COR-03): consecutive
    approximate (one- or two-AP) readings. Its anchor is the run's first
    reading; a reading MAN_DOWN_MOVEMENT_EPSILON_M or more from it (in
    practice, a different strongest AP) starts a new run. An exact fix ends a
    run that hasn't alerted, and confirms or cancels one that has."""
    x: float
    y: float
    started_at: str                          # ISO 8601: the run's own clock
    alerted: bool = False                    # its one possible_man_down has fired
    confirming_since: Optional[str] = None   # first exact fix after that alert


_approx_runs: Dict[str, _ApproxRun] = {}
# person_id -> time.monotonic() of their latest fresh position, recorded by
# check_man_down() under pipeline_lock (Prompt 136, CON-03). The signal-loss
# sweep reads /positions outside the lock, so it skips anyone seen after its
# snapshot: their record was already out of date when it decided.
_last_fresh_mono: Dict[str, float] = {}
# person_ids whose signal-loss alert the last sweep held because none of their
# APs was alive (Prompt 136, REL-01): logged once per person per outage.
_held_logged: Set[str] = set()


@dataclass
class _SweepRead:
    """What one signal-loss sweep read, outside pipeline_lock (Prompt 136,
    CON-03). taken_at is noted before the first read."""
    taken_at: float                     # time.monotonic()
    now: str                            # ISO 8601
    candidates: List[PositionRecord]    # non-forklifts whose record is stale but not dead
    # /ap_heartbeats by "AA:BB:..." MAC; None if it couldn't be read (REL-01)
    heartbeats: Optional[Dict[str, dict]] = None
    # placed APs' MACs by (building_id, floor_id); None if they couldn't be read
    placed: Optional[Dict[tuple, List[str]]] = None


def _unix(iso: str) -> float:
    return parse_iso(iso).timestamp()


def _ap_reporting(hb: Optional[dict], now_unix: float) -> bool:
    """The AP's last report is no older than AP_SILENT_AFTER_S."""
    last = (hb or {}).get("last_seen")
    return isinstance(last, (int, float)) and now_unix - last <= settings.AP_SILENT_AFTER_S


def _ap_alive(hb: Optional[dict], now_unix: float) -> bool:
    """Reporting, and its current run of reports is at least AP_ALIVE_GRACE_S
    old (Prompt 136, REL-01). No up_since (every writer but the Omada ingest)
    counts as alive while it's reporting."""
    if not _ap_reporting(hb, now_unix):
        return False
    up = hb.get("up_since")
    return not isinstance(up, (int, float)) or now_unix - up >= settings.AP_ALIVE_GRACE_S


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
        # One positioning_offline per outage: set when it's raised, cleared
        # when a placed AP reports again (Prompt 136, REL-01).
        self._positioning_offline_latched = False

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

        Forklifts are exempt. Fires regardless of zone.

        Exact (three-AP) solves raise a red man_down. Approximate positions
        (one or two APs; x/y is the strongest AP's own coordinate) can't tell
        'still' from 'small movement', so they never move the exact anchor or
        its clock. They are timed on their own approximate run instead, and
        raise an amber possible_man_down (Prompt 136, COR-03; Herman's decision
        (b), 16 Oct). An exact fix after that alert can upgrade it to a red
        man_down: see _check_upgrade().
        """
        # A fresh position means this beacon is transmitting again — let it
        # fire a signal-loss alert a second time if it goes dark again later.
        # Before the forklift early-return so it applies regardless of type.
        _stale_alerted.discard(current.person_id)
        _last_fresh_mono[current.person_id] = time.monotonic()

        if current.person_type == "forklift":
            return None

        cfg = self._get_settings()
        now = utcnow_iso()
        pid = current.person_id

        if current.is_approximate:
            # Cold start: seed a placeholder anchor, replaced by the first
            # exact solve (Prompt 113, below). Otherwise the anchor and its
            # clock stay as they are.
            if pid not in _man_down_tracker:
                _man_down_tracker[pid] = (current.x, current.y, now, True)
                _still_alerted.discard(pid)
            return self._check_approximate(current, cfg, now)

        run = _approx_runs.get(pid)
        if run is not None and run.alerted:
            return self._check_upgrade(current, cfg, now, run)
        # An exact fix ends an approximate run that hasn't alerted.
        _approx_runs.pop(pid, None)

        prev = _man_down_tracker.get(pid)

        # First time we see this person: seed the tracker and start the clock.
        # (Cold-start case — including a beacon that appears in a dead zone and
        # never moves — begins counting from first sighting.)
        if prev is None:
            _man_down_tracker[pid] = (current.x, current.y, now, False)
            _still_alerted.discard(pid)
            return None

        anchor_x, anchor_y, since_iso, anchor_is_approximate = prev

        # The anchor must be allowed to UPGRADE from approximate to exact
        # (Prompt 113, fixing a regression from Prompt 111). An approximate
        # position's x/y is the anchor AP's own coordinate, not a fix
        # comparable to an exact solve's, so it is never measured against one.
        # On real hardware the first-ever flush after process start almost
        # always seeds approximate (only one AP has posted yet); without this
        # re-seed that anchor would block man-down forever.
        if anchor_is_approximate:
            # Upgrade. Re-seed from here, not from since_iso — the clock
            # deliberately restarts. Before this exact solve there was no
            # real position to measure stillness against; preserving the old
            # since_iso would let a moving person accumulate stillness they
            # never earned. A person already motionless at startup simply
            # waits man_down_minutes from their first exact solve rather than
            # from first sighting — an accepted, correct cost. (The exception
            # is an exact fix after a possible_man_down: _check_upgrade().)
            _man_down_tracker[pid] = (current.x, current.y, now, False)
            _still_alerted.discard(pid)
            return None

        moved = math.hypot(current.x - anchor_x, current.y - anchor_y)

        # Genuine movement: re-anchor to the new spot and reset the clock.
        # Do NOT re-anchor on every call — only when epsilon is broken — or the
        # anchor chases position jitter and the person never appears still.
        if moved >= settings.MAN_DOWN_MOVEMENT_EPSILON_M:
            _man_down_tracker[pid] = (current.x, current.y, now, False)
            _still_alerted.discard(pid)
            return None

        return self._stillness_alert(current, cfg, now, since_iso)

    def _check_approximate(self, current: PositionRecord, cfg: SafetySettings, now: str) -> Optional[AlertRecord]:
        """An approximate reading: extend or restart the person's approximate
        run, and raise its one possible_man_down once it has lasted
        man_down_minutes (Prompt 136, COR-03). Neither reads nor writes
        _last_man_down: the amber alert is a separate signal from the red one."""
        pid = current.person_id
        run = _approx_runs.get(pid)
        if run is not None and math.hypot(current.x - run.x, current.y - run.y) >= settings.MAN_DOWN_MOVEMENT_EPSILON_M:
            # A different strongest AP, in practice. This also ends an
            # upgrade's confirmation (_check_upgrade).
            run = None
        if run is None:
            _approx_runs[pid] = _ApproxRun(current.x, current.y, now)
            return None
        if run.confirming_since is not None:
            # Confirming an upgrade: an approximate reading at the run's
            # anchor changes nothing.
            return None
        if run.alerted or seconds_between(run.started_at, now) < cfg.man_down_minutes * 60:
            return None

        record = AlertRecord(
            alert_id=str(uuid.uuid4()),
            alert_type="possible_man_down",
            person_id=pid,
            zone=current.zone,
            timestamp=now,
            approximate=True,
            cause="stillness",
        )
        alert_repository.save(record)
        run.alerted = True
        return record

    def _check_upgrade(
        self, current: PositionRecord, cfg: SafetySettings, now: str, run: _ApproxRun,
    ) -> Optional[AlertRecord]:
        """An exact fix after this run's possible_man_down (Prompt 136, COR-03).

        The first one becomes the exact anchor, with its clock at the run's
        start, so the stillness behind the amber alert counts. Exact fixes
        that stay within epsilon of it for MAN_DOWN_UPGRADE_CONFIRM_S raise an
        ordinary stillness man_down, and the run ends. One that moved past
        epsilon is ordinary movement: the anchor moves, its clock restarts,
        and the run ends."""
        pid = current.person_id
        if run.confirming_since is None:
            _man_down_tracker[pid] = (current.x, current.y, run.started_at, False)
            _still_alerted.discard(pid)
            run.confirming_since = now
            return None

        anchor_x, anchor_y, since_iso, _ = _man_down_tracker[pid]
        if math.hypot(current.x - anchor_x, current.y - anchor_y) >= settings.MAN_DOWN_MOVEMENT_EPSILON_M:
            _man_down_tracker[pid] = (current.x, current.y, now, False)
            _still_alerted.discard(pid)
            del _approx_runs[pid]
            return None
        if seconds_between(run.confirming_since, now) < settings.MAN_DOWN_UPGRADE_CONFIRM_S:
            return None

        record = self._stillness_alert(current, cfg, now, since_iso)
        if record is not None:
            del _approx_runs[pid]
        return record

    def _stillness_alert(
        self, current: PositionRecord, cfg: SafetySettings, now: str, since_iso: str,
    ) -> Optional[AlertRecord]:
        """The red stillness man_down for an exact fix within epsilon of the
        exact anchor, if its clock has run past man_down_minutes."""
        pid = current.person_id
        # Within epsilon: still. Has the clock run past the threshold?
        if seconds_between(since_iso, now) < cfg.man_down_minutes * 60:
            return None

        # One stillness alert per episode (see _still_alerted).
        if pid in _still_alerted:
            return None

        # Plus the shared 30 s per-person suppression, which also spaces this
        # alert from a signal-loss one fired by check_man_down_stale().
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
        _still_alerted.add(pid)
        return record

    def check_man_down_stale(self) -> List[AlertRecord]:
        """Fire a signal-loss man-down for any beacon whose last known /positions
        record has gone stale, independent of the telemetry path. Catches battery
        death, a guard leaving AP coverage, or a beacon destroyed in the incident
        itself — none of which ever produce a fresh position, so check_man_down()
        (which only runs after a position is successfully computed) never sees them.

        A stale record is only evidence when the APs could have heard the
        person (Prompt 136, REL-01): the alert is held while none of the APs
        in the record's heard_by (or, for an older record, none placed on its
        floor) is alive. When no placed AP is reporting at all, the sweep
        raises one positioning_offline instead.

        Called from a background sweep, not per-telemetry-packet, in a worker
        thread. The reads happen outside positioning_service.pipeline_lock;
        the decision and the save inside it (Prompt 136, CON-03), so the sweep
        never holds up ingest across a read, and can't alert for someone whose
        fresh position arrived after it read their old one.
        """
        return self._decide_sweep(self._read_for_sweep())

    def _read_for_sweep(self) -> _SweepRead:
        """The sweep's reads, outside pipeline_lock. The latch checks here
        only save work; the locked step repeats them."""
        taken_at = time.monotonic()
        now = utcnow_iso()
        raw_all = position_repository.get_all()
        candidates: List[PositionRecord] = []

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

            # One unreadable timestamp (not ISO 8601, no time zone, not a
            # string) must not abort the sweep for everyone (Prompt 135,
            # COR-01): skip that record, and say so at most once an hour.
            try:
                age = seconds_between(record.timestamp, now)
            except Exception:
                who = pid or key
                t = time.monotonic()
                last = _bad_timestamp_logged.get(who)
                if last is None or t - last >= _BAD_TIMESTAMP_LOG_EVERY_S:
                    _bad_timestamp_logged[who] = t
                    print(f"[SAFETY] WARNING: skipping /positions/{key} in the signal-loss sweep: "
                          f"its timestamp isn't an ISO 8601 date-time with a time zone")
                continue
            if age < settings.MAN_DOWN_STALE_SECONDS:
                continue
            if age > settings.MAN_DOWN_STALE_MAX_AGE_S:
                # Dead record, not an active incident — see MAN_DOWN_STALE_MAX_AGE_S.
                continue
            candidates.append(record)

        # Which APs are reporting, and which are placed (REL-01). If either
        # can't be read, the sweep alerts as it did before 136 rather than
        # holding alerts on missing information.
        heartbeats: Optional[Dict[str, dict]] = None
        try:
            heartbeats = {}
            for key, hb in position_repository.get_ap_heartbeats().items():
                if isinstance(hb, dict):
                    heartbeats[ap_mac_colons(hb.get("mac") or key)] = hb
        except Exception as e:
            heartbeats = None
            print(f"[SAFETY] WARNING: signal-loss sweep couldn't read /ap_heartbeats: {e}")
        placed: Optional[Dict[tuple, List[str]]] = None
        try:
            placed = {}
            for a in ap_repository.get_all_placed():
                placed.setdefault((a.building_id, a.floor_id), []).append(ap_mac_colons(a.mac))
        except Exception as e:
            placed = None
            print(f"[SAFETY] WARNING: signal-loss sweep couldn't read the placed APs: {e}")

        return _SweepRead(taken_at=taken_at, now=now, candidates=candidates,
                          heartbeats=heartbeats, placed=placed)

    def _aps_for(self, record: PositionRecord, read: _SweepRead) -> List[str]:
        """The APs whose silence would explain this record going stale: its
        heard_by, or for a record written before 136, every AP placed on its
        floor. Empty (don't hold the alert) when neither is known."""
        if record.heard_by:
            return [ap_mac_colons(m) for m in record.heard_by]
        if read.placed is None or not record.floor_id:
            return []
        return read.placed.get((record.building_id, record.floor_id), [])

    def _check_positioning_offline(self, read: _SweepRead, now_unix: float) -> Optional[AlertRecord]:
        """One positioning_offline while no placed AP is reporting, if at least
        one placed AP ever has (REL-01). The latch clears when one reports
        again. Never resolved automatically."""
        if read.heartbeats is None or read.placed is None:
            return None
        placed_hbs = [read.heartbeats[m] for macs in read.placed.values() for m in macs if m in read.heartbeats]
        if any(_ap_reporting(hb, now_unix) for hb in placed_hbs):
            self._positioning_offline_latched = False
            return None
        if not placed_hbs or self._positioning_offline_latched:
            return None
        alert = AlertRecord(
            alert_id=str(uuid.uuid4()),
            alert_type="positioning_offline",
            person_id="",
            zone="",
            timestamp=read.now,
            cause=None,
        )
        alert_repository.save(alert)
        self._positioning_offline_latched = True
        return alert

    def _decide_sweep(self, read: _SweepRead) -> List[AlertRecord]:
        """The sweep's decisions and saves, under pipeline_lock: no fresh
        position can be processed in between, and none may have been since
        the read (_last_fresh_mono)."""
        # local import, as for the patrol tracker in run_all_checks()
        from services.positioning_service import positioning_service

        now = read.now
        now_unix = _unix(now)
        fired: List[AlertRecord] = []
        held: Set[str] = set()
        with positioning_service.pipeline_lock:
            offline = self._check_positioning_offline(read, now_unix)
            if offline is not None:
                fired.append(offline)

            for record in read.candidates:
                pid = record.person_id
                if pid in _stale_alerted:
                    continue
                seen = _last_fresh_mono.get(pid)
                if seen is not None and seen > read.taken_at:
                    continue

                # Hold the alert while none of the person's APs is alive: the
                # record went stale because nothing could hear anyone, not
                # because this beacon went dark. Not latched, so the next
                # sweep looks again (REL-01).
                aps = self._aps_for(record, read) if read.heartbeats is not None else []
                if aps and not any(_ap_alive(read.heartbeats.get(m), now_unix) for m in aps):
                    held.add(pid)
                    if pid not in _held_logged:
                        print(f"[SAFETY] holding the signal-loss alert for {pid}: none of the APs that "
                              f"last heard them is alive ({', '.join(aps)})")
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

            # Anyone not held this sweep has left the outage: log again next time.
            _held_logged.intersection_update(held)
            _held_logged.update(held)

        return fired

    # ------------------------------------------------------------------
    # FR4 / NFR2 / UC5 — Collision prediction
    # ------------------------------------------------------------------
    def _fresh_for_collision(self, p: PositionRecord, now: str) -> bool:
        """True if this record is recent enough to take part in the collision
        check (Prompt 136, COR-04). An unreadable timestamp counts as not
        fresh, logged at most once an hour per record, as the sweep does."""
        try:
            return seconds_between(p.timestamp, now) <= settings.COLLISION_MAX_AGE_S
        except Exception:
            who = p.person_id or p.beacon_mac
            t = time.monotonic()
            last = _collision_bad_timestamp_logged.get(who)
            if last is None or t - last >= _BAD_TIMESTAMP_LOG_EVERY_S:
                _collision_bad_timestamp_logged[who] = t
                print(f"[SAFETY] WARNING: skipping {who} in the collision check: its timestamp "
                      f"isn't an ISO 8601 date-time with a time zone")
            return False

    def check_collision(self, all_positions: List[PositionRecord]) -> List[AlertRecord]:
        """Alert when a worker's Kalman-predicted position converges with a forklift's
        within COLLISION_ALERT_SECONDS. Suppresses repeat alerts for the same pair
        within 10 seconds.

        Only records younger than COLLISION_MAX_AGE_S take part, and a pair must
        be on the same floor of the same building (Prompt 136, COR-04)."""
        now = utcnow_iso()
        fresh = [p for p in all_positions
                 if p.person_type in ("worker", "forklift") and p.predicted_x is not None
                 and self._fresh_for_collision(p, now)]
        workers   = [p for p in fresh if p.person_type == "worker"]
        forklifts = [p for p in fresh if p.person_type == "forklift"]
        alerts: List[AlertRecord] = []

        cfg = self._get_settings()
        collision_distance = cfg.collision_distance_m

        for w in workers:
            if not w.building_id or not w.floor_id:
                continue
            for f in forklifts:
                if (f.building_id, f.floor_id) != (w.building_id, w.floor_id):
                    continue
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
