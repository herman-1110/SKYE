from typing import Dict, List, Optional, Tuple

from config.settings import settings
from models.position import PositionRecord
from models.telemetry import APRssiReading, OmadaTelemetryPayload
from repositories.position_repository import position_repository
from services.kalman_service import KalmanService
from utils.multilateration import least_squares_position
from utils.rssi_utils import rssi_to_distance
from utils.timestamp_utils import utcnow_iso
from utils.zone_utils import coordinate_to_zone


class PositioningService:
    """
    Orchestrates the full localisation pipeline:
    RSSI → LDPL distances → multilateration → Kalman smoothing → Firebase save.
    """

    def __init__(self) -> None:
        # One KalmanService instance per beacon MAC, persists across requests.
        self._filters: Dict[str, KalmanService] = {}

    def _get_filter(self, beacon_mac: str) -> KalmanService:
        if beacon_mac not in self._filters:
            self._filters[beacon_mac] = KalmanService()
        return self._filters[beacon_mac]

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

        record = PositionRecord(
            beacon_mac=payload.reporter_mac,
            person_id=payload.person_id,
            person_type=payload.person_type,
            x=sx,
            y=sy,
            zone=coordinate_to_zone(sx, sy),
            timestamp=payload.timestamp or utcnow_iso(),
            predicted_x=px,
            predicted_y=py,
        )
        position_repository.save(record)
        return record


positioning_service = PositioningService()
