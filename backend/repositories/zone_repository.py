from typing import Any, Dict, List, Optional

from firebase_admin import firestore

from models.zone import ZoneRecord


class ZoneRepository:
    _BUILDINGS = "buildings"
    _FLOORS = "floors"
    _ZONES = "zones"

    def _db(self):
        return firestore.client()

    def _col(self, building_id: str, floor_id: str):
        return (
            self._db()
            .collection(self._BUILDINGS)
            .document(building_id)
            .collection(self._FLOORS)
            .document(floor_id)
            .collection(self._ZONES)
        )

    def save(self, building_id: str, floor_id: str, zone: ZoneRecord) -> ZoneRecord:
        self._col(building_id, floor_id).document(zone.id).set(zone.__dict__)
        return zone

    def get_all(self, building_id: str, floor_id: str) -> List[ZoneRecord]:
        docs = self._col(building_id, floor_id).stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            try:
                results.append(ZoneRecord(**data))
            except TypeError:
                pass
        return results

    def update(
        self,
        building_id: str,
        floor_id: str,
        zone_id: str,
        fields: Dict[str, Any],
    ) -> Optional[ZoneRecord]:
        ref = self._col(building_id, floor_id).document(zone_id)
        ref.update(fields)
        doc = ref.get()
        return ZoneRecord(**doc.to_dict()) if doc.exists else None

    def delete(self, building_id: str, floor_id: str, zone_id: str) -> None:
        self._col(building_id, floor_id).document(zone_id).delete()


zone_repository = ZoneRepository()
