import time
from typing import Dict, List, Optional, Tuple

from config.settings import settings
from models.position import PositionRecord
from models.telemetry import APRssiReading, OmadaTelemetryPayload
from models.zone import ZoneRecord
from repositories.floor_repository import floor_repository
from repositories.position_repository import position_repository
from repositories.zone_repository import zone_repository
from services.kalman_service import KalmanService
from utils.multilateration import least_squares_position
from utils.rssi_utils import rssi_to_distance
from utils.timestamp_utils import utcnow_iso

_BUFFER_TTL_S = 10  # drop readings older than this before multilateration


class PositioningService:
    """
    Orchestrates the full localisation pipeline:
    RSSI → LDPL distances → multilateration → Kalman smoothing → pixel conversion → Firebase save.

    Supports both the Omada per-AP push format (process_ap_reading) and the legacy
    all-at-once format (compute_position) used by tests.
    """

    def __init__(self) -> None:
        self._filters: Dict[str, KalmanService] = {}
        self._cached_scale: Optional[float] = None
        self._cached_building_id: Optional[str] = None
        self._cached_floor_id: Optional[str] = None
        self._cached_zones: List[ZoneRecord] = []

        # AP MAC → (x_m, y_m) physical position registry
        self._ap_registry: Dict[str, Tuple[float, float]] = {}

        # Beacon MAC → {ap_mac: (rssi, received_at)}  — rolling latest reading per AP
        self._beacon_buffer: Dict[str, Dict[str, Tuple[int, float]]] = {}

    # ------------------------------------------------------------------
    # AP position registry
    # ------------------------------------------------------------------

    def register_ap(self, mac: str, x_m: float, y_m: float) -> None:
        """Record the physical position of an AP so it can be used for multilateration."""
        self._ap_registry[mac] = (x_m, y_m)

    # ------------------------------------------------------------------
    # Omada per-AP ingest (main path)
    # ------------------------------------------------------------------

    def process_ap_reading(
        self,
        ap_mac: str,
        beacon_mac: str,
        rssi: int,
    ) -> Optional[PositionRecord]:
        """
        Accept one AP's RSSI reading for a beacon.  Buffer it, and once ≥3 APs have
        fresh readings for the same beacon run multilateration and return the result.
        """
        now = time.time()

        if beacon_mac not in self._beacon_buffer:
            self._beacon_buffer[beacon_mac] = {}
        self._beacon_buffer[beacon_mac][ap_mac] = (rssi, now)

        # Drop stale entries
        self._beacon_buffer[beacon_mac] = {
            mac: (r, t)
            for mac, (r, t) in self._beacon_buffer[beacon_mac].items()
            if now - t <= _BUFFER_TTL_S
        }

        fresh = self._beacon_buffer[beacon_mac]
        if len(fresh) < 3:
            return None

        # Build APRssiReading list — skip APs whose position is unknown
        readings: List[APRssiReading] = []
        for a_mac, (a_rssi, _) in fresh.items():
            if a_mac not in self._ap_registry:
                continue
            ax, ay = self._ap_registry[a_mac]
            readings.append(APRssiReading(ap_mac=a_mac, rssi=float(a_rssi), ap_x=ax, ap_y=ay))

        if len(readings) < 3:
            return None

        payload = OmadaTelemetryPayload(
            reporter_mac=beacon_mac,
            timestamp=utcnow_iso(),
            readings=readings,
        )
        return self.compute_position(payload)

    # ------------------------------------------------------------------
    # Core multilateration pipeline (shared by both paths)
    # ------------------------------------------------------------------

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
            else:
                self._cached_zones = []
        else:
            self._cached_scale = None
            self._cached_building_id = None
            self._cached_floor_id = None
            self._cached_zones = []

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

        kf = self._get_filter(payload.reporter_mac)
        sx, sy = kf.update(raw[0], raw[1])
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
        )
        position_repository.save(record)
        return record


positioning_service = PositioningService()
