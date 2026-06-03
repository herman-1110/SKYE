from typing import Any, Dict, List, Optional

from firebase_admin import firestore

from models.floor import FloorRecord


class FloorRepository:
    _BUILDINGS = "buildings"
    _FLOORS = "floors"

    def _db(self):
        return firestore.client()

    def _col(self, building_id: str):
        return self._db().collection(self._BUILDINGS).document(building_id).collection(self._FLOORS)

    def _to_record(self, data: Dict[str, Any]) -> FloorRecord:
        return FloorRecord(
            id=data["id"],
            building_id=data["building_id"],
            name=data["name"],
            floor_number=int(data.get("floor_number", 1)),
            url=data["url"],
            storage_path=data["storage_path"],
            is_active=bool(data.get("is_active", False)),
            uploaded_at=data["uploaded_at"],
            scale_pixels_per_meter=data.get("scale_pixels_per_meter"),
            image_width_px=int(data["image_width_px"]) if data.get("image_width_px") else None,
            image_height_px=int(data["image_height_px"]) if data.get("image_height_px") else None,
            patrol_enabled=bool(data.get("patrol_enabled", False)),
            patrol_route=list(data.get("patrol_route", [])),
        )

    def save(self, floor: FloorRecord) -> FloorRecord:
        self._col(floor.building_id).document(floor.id).set(floor.__dict__)
        return floor

    def get_all(self, building_id: str) -> List[FloorRecord]:
        docs = self._col(building_id).order_by("floor_number").stream()
        results = []
        for doc in docs:
            try:
                results.append(self._to_record(doc.to_dict()))
            except (KeyError, TypeError):
                pass
        return results

    def get_by_id(self, building_id: str, floor_id: str) -> Optional[FloorRecord]:
        doc = self._col(building_id).document(floor_id).get()
        if not doc.exists:
            return None
        return self._to_record(doc.to_dict())

    def get_active(self, building_id: str) -> Optional[FloorRecord]:
        docs = list(self._col(building_id).where("is_active", "==", True).limit(1).stream())
        if not docs:
            return None
        return self._to_record(docs[0].to_dict())

    def get_any_active(self) -> Optional[FloorRecord]:
        """Return any active floor across all buildings (used by the telemetry pipeline)."""
        db = self._db()
        docs = list(
            db.collection_group(self._FLOORS)
            .where("is_active", "==", True)
            .limit(1)
            .stream()
        )
        if not docs:
            return None
        return self._to_record(docs[0].to_dict())

    def update_scale(self, building_id: str, floor_id: str, scale: float) -> None:
        self._col(building_id).document(floor_id).update({"scale_pixels_per_meter": scale})

    def set_active(self, building_id: str, floor_id: str) -> None:
        db = self._db()
        batch = db.batch()
        for doc in self._col(building_id).stream():
            batch.update(doc.reference, {"is_active": False})
        batch.update(self._col(building_id).document(floor_id), {"is_active": True})
        batch.commit()

    def deactivate(self, building_id: str, floor_id: str) -> None:
        self._col(building_id).document(floor_id).update({"is_active": False})

    def update(self, building_id: str, floor_id: str, fields: Dict[str, Any]) -> None:
        self._col(building_id).document(floor_id).update(fields)

    def delete(self, building_id: str, floor_id: str) -> None:
        self._col(building_id).document(floor_id).delete()

    def update_patrol_config(
        self,
        building_id: str,
        floor_id: str,
        patrol_enabled: bool,
        patrol_route: List[str],
    ) -> None:
        self._col(building_id).document(floor_id).update({
            "patrol_enabled": patrol_enabled,
            "patrol_route": patrol_route,
        })


floor_repository = FloorRepository()
