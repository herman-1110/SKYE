"""
Single-AP proximity positioning.

Fallback used by omada_ingest_service when a beacon is heard by fewer than
MIN_APS_FOR_POSITION APs within the buffer window — too few for a full
multilateration solve. Instead of dropping the reading, the beacon is
anchored to whichever AP currently hears it strongest ("closest"), with a
radius derived from RSSI via the same LDPL model the main pipeline uses.

There is no Kalman smoothing here: as the beacon moves and a different AP
becomes the strongest, the anchor hops to that AP on the very next call.
This is an intentionally coarse approximation, not a replacement for the
multilateration path.
"""
from typing import List, Optional

from config.settings import settings
from models.position import PositionRecord
from models.telemetry import APRssiReading
from repositories.position_repository import position_repository
from utils.rssi_utils import rssi_to_distance
from utils.timestamp_utils import utcnow_iso


class ProximityService:
    """Anchors a beacon to its strongest-RSSI AP instead of solving an exact position."""

    def compute_position(
        self,
        person_id: str,
        person_type: str,
        label: str,
        readings: List[APRssiReading],
        tx_power: float,
        floor_id: str = "",
        building_id: str = "",
    ) -> Optional[PositionRecord]:
        """readings must be non-empty. The AP with the strongest (least negative)
        RSSI is treated as closest and becomes the position anchor."""
        if not readings:
            return None

        nearest = max(readings, key=lambda r: r.rssi)

        # "Beacon has left" gate: if even the strongest AP is fainter than the
        # floor, this reading is too weak to be a useful proximity anchor. Emit
        # nothing — no write means the last record's timestamp goes stale and the
        # frontend staleness filter drops the marker, instead of a giant radius
        # lingering at the last AP forever.
        if nearest.rssi < settings.PROXIMITY_RSSI_FLOOR:
            return None

        radius_m = rssi_to_distance(nearest.rssi, tx_power, settings.PATH_LOSS_EXPONENT)

        record = PositionRecord(
            beacon_mac=person_id,
            person_id=person_id,
            person_type=person_type,
            x=nearest.ap_x,
            y=nearest.ap_y,
            zone="unknown",
            timestamp=utcnow_iso(),
            floor_id=floor_id,
            building_id=building_id,
            label=label,
            radius_m=radius_m,
            is_approximate=True,
            anchor_ap_mac=nearest.ap_mac,
        )
        position_repository.save(record)
        return record


proximity_service = ProximityService()
