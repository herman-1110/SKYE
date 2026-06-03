import time
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


class PositioningService:
    """
    Orchestrates the full localisation pipeline:
    RSSI → LDPL distances → multilateration → Kalman smoothing → pixel conversion → Firebase save.
    """

    def __init__(self) -> None:
        self._filters: Dict[str, KalmanService] = {}
        self._last_seen: Dict[str, float] = {}   # beacon_mac → unix timestamp of last telemetry
        self._cached_scale: Optional[float] = None
        self._cached_building_id: Optional[str] = None
        self._cached_floor_id: Optional[str] = None
        self._cached_zones: List[ZoneRecord] = []
        # Floor bounds for Kalman clamping — populated by _refresh_cache
        self._cached_x_min: float = 0.0
        self._cached_x_max: float = 100.0
        self._cached_y_min: float = 0.0
        self._cached_y_max: float = 100.0

    def _get_filter(self, beacon_mac: str) -> KalmanService:
        if beacon_mac not in self._filters:
            self._filters[beacon_mac] = KalmanService()
        return self._filters[beacon_mac]

    def _refresh_cache(self) -> None:
        """Load scale, building_id, floor_id, and zones from the active floor."""
        floor = floor_repository.get_any_active()
        if floor:
            self._cached_scale = floor.scale_pixels_per_meter
            self._cached_building_id = floor.building_id
            self._cached_floor_id = floor.id
            if self._cached_building_id and self._cached_floor_id:
                self._cached_zones = zone_repository.get_all(
                    self._cached_building_id, self._cached_floor_id
                )
                # Load AP positions to derive floor bounds for Kalman clamping
                aps = ap_repository.get_all(
                    self._cached_building_id, self._cached_floor_id
                )
                if aps:
                    xs = [ap.x_m for ap in aps]
                    ys = [ap.y_m for ap in aps]
                    pad = 3.0
                    self._cached_x_min = max(0.0, min(xs) - pad)
                    self._cached_x_max = max(xs) + pad
                    self._cached_y_min = max(0.0, min(ys) - pad)
                    self._cached_y_max = max(ys) + pad
                else:
                    self._cached_x_min = 0.0
                    self._cached_x_max = 100.0
                    self._cached_y_min = 0.0
                    self._cached_y_max = 100.0
            else:
                self._cached_zones = []
                self._cached_x_min = 0.0
                self._cached_x_max = 100.0
                self._cached_y_min = 0.0
                self._cached_y_max = 100.0
        else:
            self._cached_scale = None
            self._cached_building_id = None
            self._cached_floor_id = None
            self._cached_zones = []
            self._cached_x_min = 0.0
            self._cached_x_max = 100.0
            self._cached_y_min = 0.0
            self._cached_y_max = 100.0

    def _get_scale(self) -> Optional[float]:
        if self._cached_scale is None and self._cached_building_id is None:
            self._refresh_cache()
        return self._cached_scale

    def _lookup_zone(self, x: float, y: float) -> str:
        for zone in self._cached_zones:
            if zone.x_min <= x <= zone.x_max and zone.y_min <= y <= zone.y_max:
                return zone.name
        return "unknown"

    def invalidate_scale_cache(self) -> None:
        """Call this after a floor scale, activation, or zone change."""
        self._cached_scale = None
        self._cached_building_id = None
        self._cached_floor_id = None
        self._cached_zones = []
        self._cached_x_min = 0.0
        self._cached_x_max = 100.0
        self._cached_y_min = 0.0
        self._cached_y_max = 100.0
        self._last_seen.clear()

    def compute_position(self, payload: OmadaTelemetryPayload) -> Optional[PositionRecord]:
        """Full pipeline: returns smoothed PositionRecord, or None if < 3 AP readings."""
        readings: List[APRssiReading] = payload.readings
        if len(readings) < 3:
            return None

        ap_positions: List[Tuple[float, float]] = [(r.ap_x, r.ap_y) for r in readings]
        distances: List[float] = [
            rssi_to_distance(r.rssi, settings.TX_POWER_DEFAULT, settings.PATH_LOSS_EXPONENT)
            for r in readings
        ]

        raw = least_squares_position(ap_positions, distances)
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
        raw_x = float(np.clip(raw[0], self._cached_x_min, self._cached_x_max))
        raw_y = float(np.clip(raw[1], self._cached_y_min, self._cached_y_max))

        kf = self._get_filter(payload.reporter_mac)
        sx, sy = kf.update(raw_x, raw_y)

        # Clamp Kalman internal state so bad measurements cannot corrupt future predictions
        kf.clamp_state(
            self._cached_x_min, self._cached_x_max,
            self._cached_y_min, self._cached_y_max,
        )
        sx = float(np.clip(sx, self._cached_x_min, self._cached_x_max))
        sy = float(np.clip(sy, self._cached_y_min, self._cached_y_max))

        px, py = kf.predict_ahead(seconds=float(settings.COLLISION_ALERT_SECONDS))

        scale = self._get_scale()
        pixel_x = sx * scale if scale is not None else None
        pixel_y = sy * scale if scale is not None else None

        record = PositionRecord(
            beacon_mac=payload.reporter_mac,
            person_id=payload.person_id,
            person_type=payload.person_type,
            x=sx,
            y=sy,
            zone=self._lookup_zone(sx, sy),
            timestamp=payload.timestamp or utcnow_iso(),
            predicted_x=px,
            predicted_y=py,
            pixel_x=pixel_x,
            pixel_y=pixel_y,
            floor_id=self._cached_floor_id or "",
            building_id=self._cached_building_id or "",
            label=payload.label,
        )
        position_repository.save(record)
        return record


positioning_service = PositioningService()
