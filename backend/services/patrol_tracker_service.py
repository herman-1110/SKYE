"""
Real-time patrol tracker — converts live guard positions into PatrolLogRecords
and produces the project's first genuine patrol_violation alerts.

Design constraints (Prompt 110 / 110a recon):

  Only guards, only exact (non-approximate) positions. An approximate position's
  x/y ARE the anchor AP's own coordinates (single/dual-AP proximity fallback) —
  measuring dwell against that would fabricate perfect, permanent compliance at
  exactly one checkpoint and unreachability at every other. When only one real
  AP is placed, every real-hardware position is approximate and this service is
  silent on real hardware — correct, not a bug, the alternative is a demo full
  of fake compliance. CONFIRMED 2026-09-10, re-verified directly against RTDB
  /ap_heartbeats + Firestore access_points + /positions: 3 real APs are now
  placed and online on "Level 2" (EAP660 HD x2, EAP770), and live guard-001 /
  worker-001 positions are is_approximate=False. This service is no longer
  silent on real hardware — treat that assumption as gone, not just stale.
  Confirm freshly again if this matters (AP counts/coverage can change).
  Cross-checked against RTDB /alerts (the real store — see AlertRepository,
  not Firestore): real guard-001 short_dwell/no_patrol patrol_violation
  alerts already exist from 2026-09-09 real-hardware data, timestamps lining
  up with the corresponding patrol_logs windows, so window-close alerting is
  confirmed working end-to-end on real hardware at least once.

  No schedule exists (no Shift model, no route assignment, no timing primitive)
  and this service does not invent one. Missed checkpoints are detected by
  ORDER: patrol_route is ordered, so arriving at index N while some index before
  it was never logged this cycle means that index was skipped. expected_arrival
  is therefore derived — the moment the guard departed the previous checkpoint
  in this cycle (or cycle start, for the first checkpoint closed in the cycle)
  — not scheduled against a clock.

  Reuses safety_service.check_patrol_compliance() rather than writing a sibling
  — it already evaluates exactly the condition this service needs and persists
  the alert itself; this service's only job is producing a correctly-shaped
  PatrolLogRecord and handing it over.

Threading: check_patrol_progress() is only ever called from
safety_service.run_all_checks(), which itself only ever runs inside
positioning_service.pipeline_lock (held for the full compute+check pipeline by
both /telemetry and /telemetry/omada). That external serialization is what
makes the plain dicts below safe without their own lock — the same assumption
safety_service's own _man_down_tracker/_last_man_down/_last_collision rely on.

Multi-worker note (same shape as _man_down_stale_loop's in main.py): all state
below is per-process, in-memory. Under --reload (single worker, the documented
startup) this is fine. Under gunicorn/uvicorn with >1 worker, a guard's visits
would be split across processes — fragmented or duplicate checkpoint logs. Not
an issue today, but worth revisiting the moment this is productionised behind
more than one worker.
"""
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from config.settings import settings
from models.ap import AccessPoint
from models.patrol_log import PatrolLogRecord
from models.position import PositionRecord
from repositories.ap_repository import ap_repository
from repositories.floor_repository import floor_repository
from repositories.patrol_log_repository import patrol_log_repository
from utils.timestamp_utils import seconds_between, utcnow_iso

# Same convention as OmadaIngestService._AP_CACHE_TTL_S — a position tick must
# never hit Firestore directly for route/AP resolution.
_FLOOR_CACHE_TTL_S = 30.0

# Soft-close cap (Prompt 122): once the window has expired AND this many extra
# seconds have passed, close the cycle even if the guard is still standing
# inside a checkpoint zone. Without this, a guard stopped at the last
# checkpoint for a long break could hold one window open indefinitely.
_SOFT_CLOSE_CAP_S = 120.0


@dataclass
class _FloorPatrolContext:
    loaded_at: float
    patrol_enabled: bool
    route_aps: List[AccessPoint]  # resolved, in patrol_route order; unresolvable ids dropped
    interval_minutes: int         # per-floor cycle window (Prompt 122), FloorRecord.patrol_interval_minutes


@dataclass
class _GuardCycleState:
    person_id: str
    cycle_id: str
    cycle_started_at: str                       # ISO 8601 — cycle start / index-0 fallback
    current_index: Optional[int] = None         # route index the guard is currently inside
    current_entered_at: Optional[str] = None
    last_departed_at: Optional[str] = None       # feeds the next checkpoint's expected_arrival
    # Stamped on every exact-position tick this cycle, regardless of
    # candidate — including ticks that never touch a checkpoint at all
    # (Prompt 125). None means no exact tick has landed this cycle yet:
    # the only signal that distinguishes a guard genuinely absent all
    # window from one who was on the floor but never patrolled. Approximate
    # positions never reach here (skipped at the top of
    # check_patrol_progress), so this is "seen" in the same exact-only
    # sense the rest of this service already requires.
    last_seen_at: Optional[str] = None
    logged_indices: Set[int] = field(default_factory=set)
    # route index -> every closed PatrolLogRecord for that checkpoint this
    # window (Prompt 123) — 122 made revisiting a checkpoint within a window
    # normal, so a checkpoint can accumulate several real visits before the
    # window closes. Evaluated once, at window close, to decide whether that
    # checkpoint's BEST visit still counts as a violation — see
    # safety_service.check_patrol_window_compliance().
    visits: Dict[int, List[PatrolLogRecord]] = field(default_factory=dict)


class PatrolTrackerService:

    def __init__(self) -> None:
        # (person_id, floor_id) -> in-progress cycle state. See module docstring
        # re: threading and the multi-worker caveat.
        self._states: Dict[Tuple[str, str], _GuardCycleState] = {}
        # (building_id, floor_id) -> resolved patrol context, TTL-cached.
        self._floor_cache: Dict[Tuple[str, str], _FloorPatrolContext] = {}

    # ------------------------------------------------------------------
    # Floor / route-AP resolution
    # ------------------------------------------------------------------
    def _get_floor_context(self, building_id: str, floor_id: str) -> Optional[_FloorPatrolContext]:
        key = (building_id, floor_id)
        cached = self._floor_cache.get(key)
        if cached is not None and (time.monotonic() - cached.loaded_at) < _FLOOR_CACHE_TTL_S:
            return cached

        floor = floor_repository.get_by_id(building_id, floor_id)
        if floor is None:
            return None

        # Same resolution pattern every simulation file already uses for
        # patrol_route (a list of AP ids): load the floor's APs once, index by
        # id, drop any route entry that no longer resolves (deleted AP).
        aps_by_id = {ap.id: ap for ap in ap_repository.get_all(building_id, floor_id)}
        route_aps = [aps_by_id[ap_id] for ap_id in floor.patrol_route if ap_id in aps_by_id]

        ctx = _FloorPatrolContext(
            loaded_at=time.monotonic(),
            patrol_enabled=floor.patrol_enabled,
            route_aps=route_aps,
            interval_minutes=floor.patrol_interval_minutes,
        )
        self._floor_cache[key] = ctx
        return ctx

    @staticmethod
    def _nearest_checkpoint_index(
        x: float, y: float, route_aps: List[AccessPoint], current_index: Optional[int] = None,
    ) -> Optional[int]:
        """Enter a checkpoint's zone at PATROL_PROXIMITY_RADIUS_M; once inside,
        require exceeding radius + PATROL_PROXIMITY_EXIT_MARGIN_M before
        registering a departure (Prompt 117) — even if some other checkpoint is
        nominally nearer by raw distance. Without this, solve noise landing a
        hair outside the zone (a None candidate, since nothing else is within
        radius either) immediately closes the visit; re-entry a moment later
        mints a brand-new cycle instead of resuming — confirmed as the cause of
        59/69 single-log phantom cycles in the 117a capture.
        """
        if current_index is not None and 0 <= current_index < len(route_aps):
            cur_ap = route_aps[current_index]
            cur_dist = math.hypot(x - cur_ap.x_m, y - cur_ap.y_m)
            if cur_dist <= settings.PATROL_PROXIMITY_RADIUS_M + settings.PATROL_PROXIMITY_EXIT_MARGIN_M:
                return current_index

        best_idx: Optional[int] = None
        best_dist = float("inf")
        for idx, ap in enumerate(route_aps):
            dist = math.hypot(x - ap.x_m, y - ap.y_m)
            if dist < best_dist:
                best_dist = dist
                best_idx = idx
        if best_idx is not None and best_dist <= settings.PATROL_PROXIMITY_RADIUS_M:
            return best_idx
        return None

    # ------------------------------------------------------------------
    # Entry point — called from safety_service.run_all_checks()
    # ------------------------------------------------------------------
    def check_patrol_progress(self, position: PositionRecord) -> None:
        if position.person_type != "guard":
            return
        # An approximate position's x/y are the anchor AP's own coordinates —
        # see module docstring. Skipped unconditionally, no override.
        if position.is_approximate:
            return

        ctx = self._get_floor_context(position.building_id, position.floor_id)
        if ctx is None or not ctx.patrol_enabled or not ctx.route_aps:
            return

        key = (position.person_id, position.floor_id)
        state = self._states.get(key)
        is_fresh = state is None
        if state is None:
            state = _GuardCycleState(
                person_id=position.person_id,
                cycle_id=str(uuid.uuid4()),
                cycle_started_at=utcnow_iso(),
            )
            self._states[key] = state

        candidate = self._nearest_checkpoint_index(position.x, position.y, ctx.route_aps, state.current_index)

        # TEMP-MEASURE-119: emitted unconditionally, before the suppress-return
        # below, so suppressed evaluations stay visible same as MEASURE-112.
        # old_candidate is the bare pre-117 check (radius only, no hysteresis,
        # no current_index awareness) computed here for comparison only -
        # never acted on. ASCII only, no box-drawing/em-dash/arrow characters.
        prev_index_119 = state.current_index
        dists_119 = [math.hypot(position.x - ap.x_m, position.y - ap.y_m) for ap in ctx.route_aps]
        old_best_idx_119 = None
        old_best_dist_119 = float("inf")
        for idx_119, d_119 in enumerate(dists_119):
            if d_119 < old_best_dist_119:
                old_best_dist_119 = d_119
                old_best_idx_119 = idx_119
        old_candidate_119 = (
            old_best_idx_119
            if old_best_idx_119 is not None and old_best_dist_119 <= settings.PATROL_PROXIMITY_RADIUS_M
            else None
        )
        suppressed_119 = (candidate == prev_index_119) and (old_candidate_119 != prev_index_119)
        diverged_119 = candidate != old_candidate_119
        dist_str_119 = " ".join(f"cp{i}={d:.3f}" for i, d in enumerate(dists_119))
        print(
            f"[MEASURE-119] ts={utcnow_iso()} person_id={position.person_id} "
            f"floor_id={position.floor_id} x={position.x:.4f} y={position.y:.4f} "
            f"is_approximate={position.is_approximate} dists=[{dist_str_119}] "
            f"current_index={prev_index_119} new_candidate={candidate} "
            f"old_candidate={old_candidate_119} suppressed_transition={suppressed_119}"
            + (" DIVERGED" if diverged_119 else "")
        )  # TEMP-MEASURE-119

        now = utcnow_iso()

        # Time-boxed cycle close (Prompt 122) — replaces the old index-based
        # wrap trigger entirely. Revisiting a checkpoint within one window is
        # now normal and must never itself start a new cycle; only the clock
        # does. Soft close: don't cut a live visit short just because the
        # window expired — wait until the guard is between checkpoints,
        # unless the hard cap has also elapsed (a stationary guard must not
        # hold a window open forever). is_fresh guard is a cheap skip, not a
        # correctness requirement: a just-created state's elapsed time is
        # ~0s and could never be expired anyway.
        if not is_fresh:
            elapsed_s = seconds_between(state.cycle_started_at, now)
            window_s = ctx.interval_minutes * 60
            window_expired = elapsed_s >= window_s
            hard_capped = elapsed_s >= window_s + _SOFT_CLOSE_CAP_S
            if window_expired and (candidate is None or hard_capped):
                if state.current_index is not None:
                    self._close_visit(
                        state, ctx.route_aps, state.current_index,
                        actual_arrival=state.current_entered_at, departed_at=now,
                    )
                # Every route index never reached this window is not_in_window
                # (Prompt 122 §3) — the window ran out, not a demonstrated
                # skip. logged_indices only ever grows via _close_visit, so
                # every index below the highest one reached is already in it;
                # this loop only ever backfills genuinely never-reached ones.
                for idx in range(len(ctx.route_aps)):
                    if idx not in state.logged_indices:
                        self._close_visit(
                            state, ctx.route_aps, idx,
                            actual_arrival=None, departed_at=now, not_in_window=True,
                        )

                # Window-scope alerting (Prompt 123) — replaces the old
                # once-per-visit discipline. Every route index has at least
                # one entry in state.visits by this point (either a real/skip
                # close above or in an earlier iteration of this same window,
                # or the not_in_window backfill just above), so this covers
                # every checkpoint exactly once per window. Local import:
                # same decoupling reason as _close_visit()'s.
                from services.safety_service import safety_service
                for idx, visits in state.visits.items():
                    ap = ctx.route_aps[idx]
                    safety_service.check_patrol_window_compliance(
                        state.person_id, ap.name, visits,
                    )

                # Window-scope presence check (Prompt 125) — a question the
                # per-checkpoint loop above structurally can't ask, since it
                # only ever sees one checkpoint's visits at a time. Fires at
                # most once per window, using the OLD (about-to-be-replaced)
                # state's visits and presence stamp — see
                # check_patrol_window_no_patrol()'s docstring for the
                # firing condition.
                safety_service.check_patrol_window_no_patrol(
                    state.person_id, position.zone, len(ctx.route_aps),
                    window_s, state.visits, state.last_seen_at,
                )

                state = _GuardCycleState(
                    person_id=position.person_id,
                    cycle_id=str(uuid.uuid4()),
                    cycle_started_at=now,
                )
                self._states[key] = state
                is_fresh = True
                # candidate itself doesn't depend on cycle timing, only on
                # current_index for hysteresis — the fresh state's
                # current_index is None, which is exactly what was already
                # passed into _nearest_checkpoint_index's hysteresis branch
                # further up whenever state.current_index was already None,
                # so re-resolving would return the same value. Safe to reuse.

        # Presence stamp (Prompt 125) — every exact tick that reaches this
        # point, unconditionally, before the no-op early return just below.
        # Deliberately after the window-close block above: a tick that
        # closes one window and opens the next belongs to the NEW cycle
        # going forward, not the one that just ended (mirrors this
        # function's existing "window anchoring is cycle_started_at, not
        # floor wall-clock" treatment of late/cold-started guards).
        state.last_seen_at = now

        if candidate == state.current_index:
            return  # still inside the same checkpoint zone — dwell keeps accruing

        if state.current_index is not None:
            # Close out the checkpoint the guard is leaving, using the OLD
            # last_departed_at (this checkpoint's own expected_arrival) before
            # it gets overwritten below for the NEXT checkpoint's benefit.
            self._close_visit(
                state, ctx.route_aps, state.current_index,
                actual_arrival=state.current_entered_at, departed_at=now,
            )
            state.current_index = None
            state.current_entered_at = None
            state.last_departed_at = now

        if candidate is None:
            return  # departed a checkpoint, not yet arrived at another

        if not is_fresh:
            # Cold start (is_fresh) never fabricates skips for checkpoints that
            # may have been visited before this process started observing this
            # guard on this floor — mirrors check_man_down()'s cold-start
            # seed-and-start behaviour, no retroactive penalty for unknown
            # prior state. Also true immediately after a time-box close just
            # above: a brand new window must not fabricate skips for whatever
            # the previous window left unreached (Prompt 122).
            for idx in range(0, candidate):
                if idx not in state.logged_indices:
                    self._close_visit(
                        state, ctx.route_aps, idx,
                        actual_arrival=None, departed_at=now, not_in_window=False,
                    )

        state.current_index = candidate
        state.current_entered_at = now

    # ------------------------------------------------------------------
    # Closing out one checkpoint visit (real or skipped) — Prompt 110 §3.
    # Ordering matters: compliant must reflect check_patrol_compliance()'s
    # actual verdict, which needs the record built (with a placeholder) first.
    # ------------------------------------------------------------------
    def _close_visit(
        self,
        state: _GuardCycleState,
        route_aps: List[AccessPoint],
        index: int,
        actual_arrival: Optional[str],
        departed_at: str,
        not_in_window: bool = False,
    ) -> None:
        # local import: keeps safety_service<->patrol_tracker_service decoupled
        # at module-load time, same pattern zone_service uses for
        # positioning_service. safety_service is the core, hot-path module;
        # this service is the one reaching out to it, not the other way round.
        from services.safety_service import safety_service

        ap = route_aps[index]
        # None only for the first checkpoint closed in a cycle — the "for
        # index 0" case in the spec falls out naturally here, since
        # last_departed_at hasn't been set yet at that point regardless of
        # which index happens to close first.
        expected_arrival = state.last_departed_at or state.cycle_started_at
        dwell_time_seconds = (
            int(seconds_between(actual_arrival, departed_at))
            if actual_arrival is not None else 0
        )

        record = PatrolLogRecord(
            log_id=str(uuid.uuid4()),
            guard_id=state.person_id,
            checkpoint_id=ap.mac,
            checkpoint_name=ap.name,
            expected_arrival=expected_arrival,
            actual_arrival=actual_arrival,
            dwell_time_seconds=dwell_time_seconds,
            min_dwell_required=settings.MIN_DWELL_SECONDS,
            ble_detected=True,
            vigi_detected=False,
            compliant=False,  # placeholder, corrected below
            shift_id="",       # no Shift model exists — see module docstring
            cycle_id=state.cycle_id,
            not_in_window=not_in_window,
        )

        # Per-visit compliant is still computed here, once per completed
        # visit, unchanged (Prompt 123) — this is the raw record. Whether an
        # alert fires is decided separately, once per checkpoint at window
        # close: see check_patrol_progress()'s window-close block and
        # safety_service.check_patrol_window_compliance().
        record.compliant = not safety_service.is_patrol_violation(record)
        patrol_log_repository.save(record)
        state.logged_indices.add(index)
        state.visits.setdefault(index, []).append(record)


patrol_tracker_service = PatrolTrackerService()
