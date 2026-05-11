import uuid
from typing import Any, Dict, List

from models.zone import ZoneRecord
from repositories.floor_repository import floor_repository
from repositories.zone_repository import zone_repository
from utils.gemini_zone_detector import detect_zones_from_image
from utils.timestamp_utils import utcnow_iso


class ZoneService:

    def get_zones(self, building_id: str, floor_id: str) -> List[ZoneRecord]:
        return zone_repository.get_all(building_id, floor_id)

    def create_zone(
        self,
        building_id: str,
        floor_id: str,
        data: Dict[str, Any],
        user_id: str,
    ) -> ZoneRecord:
        zone = ZoneRecord(
            id=str(uuid.uuid4()),
            floor_id=floor_id,
            name=data["name"],
            color=data.get("color", "#3b82f633"),
            is_high_risk=bool(data.get("is_high_risk", False)),
            x_min=float(data["x_min"]),
            x_max=float(data["x_max"]),
            y_min=float(data["y_min"]),
            y_max=float(data["y_max"]),
            created_at=utcnow_iso(),
            created_by=user_id,
        )
        return zone_repository.save(building_id, floor_id, zone)

    def update_zone(
        self,
        building_id: str,
        floor_id: str,
        zone_id: str,
        data: Dict[str, Any],
        user_id: str,
    ) -> ZoneRecord:
        fields = {k: v for k, v in data.items() if v is not None}
        result = zone_repository.update(building_id, floor_id, zone_id, fields)
        if result is None:
            raise ValueError(f"Zone {zone_id} not found")
        return result

    def delete_zone(
        self,
        building_id: str,
        floor_id: str,
        zone_id: str,
        user_id: str,
    ) -> None:
        zone_repository.delete(building_id, floor_id, zone_id)

    def ai_detect_zones(self, building_id: str, floor_id: str) -> List[dict]:
        floor = floor_repository.get_by_id(building_id, floor_id)
        if not floor:
            raise ValueError("Floor not found")
        scale = floor.scale_pixels_per_meter
        if not scale:
            raise ValueError("Floor must be calibrated before AI detection")
        return detect_zones_from_image(floor.url, float(scale))


zone_service = ZoneService()
