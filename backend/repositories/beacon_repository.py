from dataclasses import asdict
from typing import Optional

from firebase_admin import firestore

from models.beacon import Beacon
from utils.timestamp_utils import utcnow_iso


class BeaconRepository:
    def _col(self):
        return firestore.client().collection("beacons")

    def get_all(self) -> list[Beacon]:
        docs = self._col().stream()
        return [Beacon(**d.to_dict()) for d in docs]

    def get_by_id(self, beacon_id: str) -> Optional[Beacon]:
        doc = self._col().document(beacon_id).get()
        if not doc.exists:
            return None
        return Beacon(**doc.to_dict())

    def exists(self, beacon_id: str) -> bool:
        return self._col().document(beacon_id).get().exists

    def save(self, beacon: Beacon) -> Beacon:
        self._col().document(beacon.id).set(asdict(beacon))
        return beacon

    def update_fields(self, beacon_id: str, fields: dict) -> None:
        self._col().document(beacon_id).update(fields)

    def delete(self, beacon_id: str) -> bool:
        doc_ref = self._col().document(beacon_id)
        if not doc_ref.get().exists:
            return False
        doc_ref.delete()
        return True

    def seed_from_legacy(self) -> int:
        """Idempotently migrate SEED_BEACONS into Firestore. Returns count created."""
        from config.beacon_registry import SEED_BEACONS  # local import avoids any cycle
        created = 0
        for key, ident in SEED_BEACONS.items():
            if self._col().document(key).get().exists:
                continue
            uuid, major, minor = key.split(":")
            now = utcnow_iso()
            self.save(Beacon(
                id=key,
                uuid=uuid,
                major=major,
                minor=minor,
                person_id=ident["person_id"],
                person_type=ident["person_type"],
                label=ident["label"],
                created_at=now,
                updated_at=now,
            ))
            created += 1
        return created


beacon_repository = BeaconRepository()
