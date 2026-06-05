import uuid
from typing import Any, Dict, List, Optional

from models.floor import FloorRecord
from repositories.ap_repository import ap_repository
from repositories.cctv_repository import cctv_repository
from repositories.floor_repository import floor_repository
from repositories.position_repository import position_repository
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
        image_width_px: Optional[int] = None,
        image_height_px: Optional[int] = None,
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
            image_width_px=image_width_px,
            image_height_px=image_height_px,
        )
        return floor_repository.save(floor)

    def update_scale(self, building_id: str, floor_id: str, scale: float) -> None:
        if scale <= 0:
            raise ValueError("scale_pixels_per_meter must be positive")
        floor_repository.update_scale(building_id, floor_id, scale)
        positioning_service.invalidate_scale_cache()
        self._recalculate_ap_coordinates(building_id, floor_id, scale)

    def _recalculate_ap_coordinates(self, building_id: str, floor_id: str, scale: float) -> None:
        floor = floor_repository.get_by_id(building_id, floor_id)
        if not floor or not floor.image_width_px or not floor.image_height_px:
            print(f"[CALIBRATION] Floor {floor_id} missing image dimensions — AP coordinates not recalculated")
            return
        aps = ap_repository.get_all(building_id, floor_id)
        for ap in aps:
            new_x_m = ap.x_pct * floor.image_width_px  / scale
            new_y_m = ap.y_pct * floor.image_height_px / scale
            ap_repository.update_coordinates(building_id, floor_id, ap.id, new_x_m, new_y_m)
        print(f"[CALIBRATION] Recalculated coordinates for {len(aps)} AP(s) on floor '{floor.name}' → {scale} px/m")

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

        # 2. Delete all APs — Firestore docs + RTDB heartbeats
        aps = ap_repository.get_all(building_id, floor_id)
        for ap in aps:
            ap_repository.delete(building_id, floor_id, ap.id)
            if ap.mac:
                position_repository.delete_ap_heartbeat(ap.mac)

        # 3. Delete all CCTVs — Firestore docs + RTDB heartbeats
        cctvs = cctv_repository.get_all(building_id, floor_id)
        for cctv in cctvs:
            cctv_repository.delete(building_id, floor_id, cctv.id)
            if cctv.mac:
                cctv_repository.delete_cctv_heartbeat(cctv.mac)

        # 4. Delete floorplan image from Firebase Storage
        if floor.storage_path:
            try:
                bucket = storage.bucket("skye-3fa05.firebasestorage.app")
                blob = bucket.blob(floor.storage_path)
                if blob.exists():
                    blob.delete()
            except Exception as e:
                print(f"Failed to delete storage file {floor.storage_path}: {e}")

        # 5. Delete floor document
        floor_repository.delete(building_id, floor_id)

    def delete_ap(self, building_id: str, floor_id: str, ap_id: str) -> None:
        mac = ap_repository.delete(building_id, floor_id, ap_id)
        if mac:
            position_repository.delete_ap_heartbeat(mac)
            from services.simulation_patrol import remove_ap as patrol_remove_ap
            from services.simulation_events import remove_ap as events_remove_ap
            patrol_remove_ap(mac)
            events_remove_ap(mac)

        floor = floor_repository.get_by_id(building_id, floor_id)
        if floor and floor.patrol_route:
            cleaned_route = [pid for pid in floor.patrol_route if pid != ap_id]
            if len(cleaned_route) != len(floor.patrol_route):
                floor_repository.update_patrol_config(
                    building_id, floor_id, floor.patrol_enabled or False, cleaned_route
                )


floor_service = FloorService()
