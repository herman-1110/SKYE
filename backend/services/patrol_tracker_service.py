"""
Real-time patrol tracker — converts live guard positions into PatrolLogRecords
and produces the project's first genuine patrol_violation alerts.

Design constraints (Prompt 110 / 110a recon):

  Only guards, only exact (non-approximate) positions. An approximate position's
  x/y ARE the anchor AP's own coordinates (single/dual-AP proximity fallback) —
  measuring dwell against that would fabricate perfect, permanent compliance at
  exactly one checkpoint and unreachability at every other. Today, with only one
  real AP placed, every real-hardware position is approximate, so this service
  is silent on real hardware until a second and third AP exist. That silence is
  correct, not a bug — the alternative is a demo full of fake compliance.

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


@dataclass
class _FloorPatrolContext:
    loaded_at: float
    patrol_enabled: bool
    route_aps: List[AccessPoint]  # resolved, in patrol_route order; unresolvable ids dropped


@dataclass
class _GuardCycleState:
    person_id: str
    cycle_id: str
    cycle_started_at: str                       # ISO 8601 — cycle start / index-0 fallback
    current_index: Optional[int] = None         # route index the guard is currently inside
    current_entered_at: Optional[str] = None
    last_departed_at: Optional[str] = None       # feeds the next checkpoint's expected_arrival
    logged_indices: Set[int] = field(default_factory=set)


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

        if candidate == state.current_index:
            return  # still inside the same checkpoint zone — dwell keeps accruing

        now = utcnow_iso()

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

        highest_logged = max(state.logged_indices) if state.logged_indices else -1
        wrapped = candidate <= highest_logged

        if wrapped:
            # Full-loop completion (or an out-of-order return): start a fresh
            # cycle rather than treating this as a skip of everything after
            # the highest index.
            state = _GuardCycleState(
                person_id=position.person_id,
                cycle_id=str(uuid.uuid4()),
                cycle_started_at=now,
            )
            self._states[key] = state
        elif not is_fresh:
            # Cold start (is_fresh) never fabricates skips for checkpoints that
            # may have been visited before this process started observing this
            # guard on this floor — mirrors check_man_down()'s cold-start
            # seed-and-start behaviour, no retroactive penalty for unknown
            # prior state.
            for idx in range(0, candidate):
                if idx not in state.logged_indices:
                    self._close_visit(
                        state, ctx.route_aps, idx,
                        actual_arrival=None, departed_at=now,
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
        )

        alert = safety_service.check_patrol_compliance(record)
        record.compliant = alert is None
        patrol_log_repository.save(record)
        state.logged_indices.add(index)


patrol_tracker_service = PatrolTrackerService()
