import uuid
from typing import Any, Dict, List, Optional

from models.floor import FloorRecord
from repositories.floor_repository import floor_repository
from repositories.zone_repository import zone_repository
from services.positioning_service import positioning_service
from firebase_admin import storage
from utils.timestamp_utils import utcnow_iso


class FloorService:

    def get_all(self, building_id: str) -> List[FloorRecord]:
        return floor_repository.get_all(building_id)

    def create(
        self,
        building_id: str,
        name: Optional[str],
        floor_number: int,
        url: str,
        storage_path: str,
    ) -> FloorRecord:
        if not name or not name.strip():
            existing = floor_repository.get_all(building_id)
            name = f"Level {len(existing) + 1}"
        floor = FloorRecord(
            id=str(uuid.uuid4()),
            building_id=building_id,
            name=name,
            floor_number=floor_number,
            url=url,
            storage_path=storage_path,
            is_active=False,
            uploaded_at=utcnow_iso(),
        )
        return floor_repository.save(floor)

    def update_scale(self, building_id: str, floor_id: str, scale: float) -> None:
        if scale <= 0:
            raise ValueError("scale_pixels_per_meter must be positive")
        floor_repository.update_scale(building_id, floor_id, scale)
        positioning_service.invalidate_scale_cache()

    def set_active(self, building_id: str, floor_id: str) -> None:
        floor_repository.set_active(building_id, floor_id)
        positioning_service.invalidate_scale_cache()

    def deactivate(self, building_id: str, floor_id: str) -> None:
        floor_repository.deactivate(building_id, floor_id)
        positioning_service.invalidate_scale_cache()

    def rename(self, building_id: str, floor_id: str, name: str) -> None:
        floor_repository.update(building_id, floor_id, {"name": name})

    def delete(self, building_id: str, floor_id: str) -> None:
        floor = floor_repository.get_by_id(building_id, floor_id)
        if not floor:
            return
            
        # 1. Delete all zones in this floor
        zones = zone_repository.get_all(building_id, floor_id)
        for zone in zones:
            zone_repository.delete(building_id, floor_id, zone.id)
            
        # 2. Delete floorplan image from Firebase Storage
        if floor.storage_path:
            try:
                bucket = storage.bucket("skye-3fa05.firebasestorage.app")
                blob = bucket.blob(floor.storage_path)
                if blob.exists():
                    blob.delete()
            except Exception as e:
                print(f"Failed to delete storage file {floor.storage_path}: {e}")
                
        # 3. Delete floor document
        floor_repository.delete(building_id, floor_id)


floor_service = FloorService()
