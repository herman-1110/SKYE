import uuid
from typing import Any, Dict, List, Optional

from firebase_admin import firestore

from models.building import BuildingRecord
from utils.timestamp_utils import utcnow_iso


class BuildingRepository:
    _COL = "buildings"

    def _db(self):
        return firestore.client()

    def create(self, user_id: str, name: str, description: str) -> BuildingRecord:
        record = BuildingRecord(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            user_id=user_id,
            created_at=utcnow_iso(),
        )
        self._db().collection(self._COL).document(record.id).set(record.__dict__)
        return record

    def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        docs = (
            self._db().collection(self._COL)
            .where("user_id", "==", user_id)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .stream()
        )
        return [doc.to_dict() for doc in docs]

    def get_by_id(self, building_id: str) -> Optional[Dict[str, Any]]:
        doc = self._db().collection(self._COL).document(building_id).get()
        return doc.to_dict() if doc.exists else None

    def update(self, building_id: str, fields: Dict[str, Any]) -> None:
        self._db().collection(self._COL).document(building_id).update(fields)

    def delete(self, building_id: str) -> None:
        self._db().collection(self._COL).document(building_id).delete()


building_repository = BuildingRepository()
