import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from config.settings import settings
from models.position import PositionRecord
from models.telemetry import APRssiReading, OmadaTelemetryPayload
from models.zone import ZoneRecord
from repositories.ap_repository import ap_repository
from repositories.floor_repository import floor_repository
from repositories.position_repository import position_repository
from repositories.zone_repository import zone_repository
from services.kalman_service import KalmanService
from utils.multilateration import least_squares_position
from utils.rssi_utils import rssi_to_distance
from utils.timestamp_utils import utcnow_iso

# If a beacon has not sent telemetry for this many seconds,
# reset its Kalman filter on the next arrival so it re-initialises
# from the new position rather than extrapolating from stale state.
KALMAN_RESET_AFTER_S = 10.0

# Below this spread, every AP in the reading set is "the same point" for
# multilateration purposes — most commonly all APs sitting at (0, 0) because
# they were placed on an uncalibrated floor before the create-time guard
# existed (see floor_routes.create_ap). Solving against that produces a
# confident, wrong answer clamped into whatever corner those coordinates sit
# in, rather than an honest "can't compute this."
DEGENERATE_AP_EPSILON = 1e-6

# Both warnings below fire on the hot path (every telemetry packet); cap how
# often the same person can re-trigger one so a persistently bad floor logs
# once a minute instead of drowning [OMADA]'s output.
_WARNING_RATE_LIMIT_S = 60.0


@dataclass
class _FloorContext:
    """Everything compute_position() needs about one specific floor — scale,
    zones, and Kalman-clamping bounds. Cached per floor_id so two active floors
    in two different buildings never share (or clobber) each other's geometry."""
    scale: Optional[float] = None
    building_id: Optional[str] = None
    floor_id: Optional[str] = None
    zones: List[ZoneRecord] = field(default_factory=list)
    x_min: float = 0.0
    x_max: float = 100.0
    y_min: float = 0.0
    y_max: float = 100.0


class PositioningService:
    """
    Orchestrates the full localisation pipeline:
    RSSI → LDPL distances → multilateration → Kalman smoothing → pixel conversion → Firebase save.
    """

    def __init__(self) -> None:
        self._filters: Dict[str, KalmanService] = {}
        self._last_seen: Dict[str, float] = {}   # beacon_mac → unix timestamp of last telemetry
        # floor_id -> context; the "" key holds the legacy global-active-floor
        # fallback, used only when a caller doesn't know its floor_id yet
        # (the simulation /telemetry path).
        self._contexts: Dict[str, _FloorContext] = {}
        # Both /telemetry and /telemetry/omada now run compute_position() +
        # run_all_checks() off the event loop (via run_in_threadpool), so
        # concurrent AP/simulation POSTs can genuinely overlap on separate
        # threads. Every caller of that pair must hold this lock — it's what
        # used to be free single-threaded serialization when both ran
        # directly on the event loop. Guards this service's own _filters/
        # _last_seen/_contexts, safety_service's tracker dicts, and
        # omada_ingest_service's beacon buffers (see its ingest()).
        self.pipeline_lock: threading.Lock = threading.Lock()
        # person_id -> monotonic ts of the last degenerate-geometry warning
        self._last_degenerate_warning: Dict[str, float] = {}
        # person_id -> monotonic ts of the last successful EXACT solve here.
        # Read by omada_ingest_service to decide whether a fresh approximate
        # (proximity-fallback) estimate should be suppressed in favour of a
        # still-recent exact position (POSITION_EXACT_HOLD_SECONDS, Prompt 111).
        self._last_exact_solve: Dict[str, float] = {}

    def _get_filter(self, beacon_mac: str) -> KalmanService:
        if beacon_mac not in self._filters:
            self._filters[beacon_mac] = KalmanService()
        return self._filters[beacon_mac]

    def _build_context(self, floor) -> _FloorContext:
        """Build a _FloorContext from a resolved FloorRecord (or None). Bounds
        logic is unchanged from the pre-per-floor-cache version: image
        dimensions when available, else AP-spread ± 3.0 m pad, else 0..100."""
        ctx = _FloorContext()
        if not floor:
            return ctx

        ctx.scale = floor.scale_pixels_per_meter
        ctx.building_id = floor.building_id
        ctx.floor_id = floor.id

        if ctx.building_id and ctx.floor_id:
            ctx.zones = zone_repository.get_all(ctx.building_id, ctx.floor_id)
            _scale = ctx.scale
            if (
                floor.image_width_px and floor.image_height_px
                and _scale and _scale > 0
            ):
                ctx.x_min = 0.0
                ctx.x_max = floor.image_width_px / _scale
                ctx.y_min = 0.0
                ctx.y_max = floor.image_height_px / _scale
            else:
                aps = ap_repository.get_all(ctx.building_id, ctx.floor_id)
                if aps:
                    xs = [ap.x_m for ap in aps]
                    ys = [ap.y_m for ap in aps]
                    pad = 3.0
                    ctx.x_min = max(0.0, min(xs) - pad)
                    ctx.x_max = max(xs) + pad
                    ctx.y_min = max(0.0, min(ys) - pad)
                    ctx.y_max = max(ys) + pad
                # else: keep the dataclass defaults (0, 100, 0, 100)
        # else: keep zones=[] and the dataclass default bounds (0, 100, 0, 100)

        return ctx

    def _refresh_cache(self, floor_id: str = "", building_id: str = "") -> _FloorContext:
        """Load (and cache) the context for a specific floor. When floor_id is
        empty, falls back to the global "any active floor" lookup — the legacy
        behaviour, kept for callers that don't resolve their own floor."""
        if floor_id:
            floor = floor_repository.get_by_id(building_id, floor_id)
        else:
            floor = floor_repository.get_any_active()
        ctx = self._build_context(floor)
        self._contexts[floor_id or ""] = ctx
        return ctx

    def _get_context(self, floor_id: str = "", building_id: str = "") -> _FloorContext:
        cache_key = floor_id or ""
        ctx = self._contexts.get(cache_key)
        # No TTL by design (matches the pre-per-floor-cache behaviour) — once a
        # real floor is resolved it stays cached until invalidate_scale_cache()
        # is called. Only retry automatically if we've never resolved anything
        # for this key yet (scale and building_id both still None).
        if ctx is None or (ctx.scale is None and ctx.building_id is None):
            ctx = self._refresh_cache(floor_id, building_id)
        return ctx

    def _lookup_zone(self, ctx: _FloorContext, x: float, y: float) -> str:
        for zone in ctx.zones:
            if zone.x_min <= x <= zone.x_max and zone.y_min <= y <= zone.y_max:
                return zone.name
        return "unknown"

    def invalidate_scale_cache(self) -> None:
        """Call this after a floor scale, activation, or zone change."""
        self._contexts.clear()
        self._last_seen.clear()

    def had_recent_exact_solve(self, person_id: str, within_seconds: float) -> bool:
        """True if this person's last successful exact solve happened within
        the given window. Used to suppress a strictly-worse approximate
        estimate that would otherwise overwrite it (Prompt 111 §1)."""
        ts = self._last_exact_solve.get(person_id)
        return ts is not None and (time.monotonic() - ts) < within_seconds

    def compute_position(
        self,
        payload: OmadaTelemetryPayload,
        floor_id: str = "",
        building_id: str = "",
    ) -> Optional[PositionRecord]:
        """Full pipeline: returns smoothed PositionRecord, or None if < 3 AP readings.

        floor_id/building_id identify the floor these readings were resolved
        against (the AP-driven resolution in omada_ingest_service). When left
        empty — the simulation /telemetry path — falls back to whichever floor
        is globally active, exactly as before this became floor-aware.
        """
        readings: List[APRssiReading] = payload.readings
        if len(readings) < 3:
            return None

        ap_positions: List[Tuple[float, float]] = [(r.ap_x, r.ap_y) for r in readings]

        # Degenerate AP geometry: all readings anchored to (effectively) the
        # same point. Solving would clamp into a corner with false confidence
        # instead of failing honestly — refuse instead.
        xs = [p[0] for p in ap_positions]
        ys = [p[1] for p in ap_positions]
        if (max(xs) - min(xs)) < DEGENERATE_AP_EPSILON and (max(ys) - min(ys)) < DEGENERATE_AP_EPSILON:
            now_mono = time.monotonic()
            last_warn = self._last_degenerate_warning.get(payload.person_id, 0.0)
            if now_mono - last_warn >= _WARNING_RATE_LIMIT_S:
                self._last_degenerate_warning[payload.person_id] = now_mono
                print(
                    f"[POSITIONING] WARNING: degenerate AP geometry for {payload.person_id} "
                    f"— all APs at ({xs[0]}, {ys[0]}); floor likely uncalibrated"
                )
            return None

        tx_power = payload.tx_power if payload.tx_power else settings.TX_POWER_DEFAULT
        distances: List[float] = [
            rssi_to_distance(r.rssi, tx_power, settings.PATH_LOSS_EXPONENT)
            for r in readings
        ]

        # Populate floor bounds and scale before the solve so bounds are real on first packet
        ctx = self._get_context(floor_id, building_id)

        raw = least_squares_position(
            ap_positions,
            distances,
            bounds=(ctx.x_min, ctx.x_max, ctx.y_min, ctx.y_max),
        )
        if raw is None:
            return None

        # Stale beacon detection — drop filter if beacon was absent too long
        now_unix = time.time()
        mac = payload.reporter_mac
        last = self._last_seen.get(mac)
        if last is not None and (now_unix - last) > KALMAN_RESET_AFTER_S:
            self._filters.pop(mac, None)
        self._last_seen[mac] = now_unix

        # Clamp raw multilateration to floor bounds before feeding Kalman
        raw_x = float(np.clip(raw[0], ctx.x_min, ctx.x_max))
        raw_y = float(np.clip(raw[1], ctx.y_min, ctx.y_max))

        kf = self._get_filter(payload.reporter_mac)
        sx, sy = kf.update(raw_x, raw_y)

        # Clamp Kalman internal state so bad measurements cannot corrupt future predictions
        kf.clamp_state(ctx.x_min, ctx.x_max, ctx.y_min, ctx.y_max)
        sx = float(np.clip(sx, ctx.x_min, ctx.x_max))
        sy = float(np.clip(sy, ctx.y_min, ctx.y_max))

        px, py = kf.predict_ahead(seconds=float(settings.COLLISION_ALERT_SECONDS))

        pixel_x = sx * ctx.scale if ctx.scale is not None else None
        pixel_y = sy * ctx.scale if ctx.scale is not None else None

        record = PositionRecord(
            beacon_mac=payload.reporter_mac,
            person_id=payload.person_id,
            person_type=payload.person_type,
            x=sx,
            y=sy,
            zone=self._lookup_zone(ctx, sx, sy),
            timestamp=payload.timestamp or utcnow_iso(),
            predicted_x=px,
            predicted_y=py,
            pixel_x=pixel_x,
            pixel_y=pixel_y,
            floor_id=ctx.floor_id or "",
            building_id=ctx.building_id or "",
            label=payload.label,
            # Explicit, not the dataclass default — this flag is now load-bearing
            # for man-down (Prompt 111) and a silent default is the wrong
            # mechanism to carry it.
            is_approximate=False,
        )
        self._last_exact_solve[payload.person_id] = time.monotonic()
        position_repository.save(record)
        return record


positioning_service = PositioningService()
