from typing import Optional

from firebase_admin import db as rtdb

from config.beacon_registry import make_ibeacon_key
from models.beacon import Beacon
from repositories.beacon_repository import beacon_repository
from utils.timestamp_utils import utcnow_iso


class BeaconService:
    def list(self) -> list[Beacon]:
        return beacon_repository.get_all()

    def create(
        self,
        uuid_str: str, major: str, minor: str,
        person_id: str, person_type: str, label: str,
        building_id: Optional[str] = None,
        tx_power: float = -59.0,
    ) -> Beacon:
        key = make_ibeacon_key(uuid_str, major, minor)   # lowercases uuid
        if beacon_repository.exists(key):
            raise ValueError("DUPLICATE")                 # route → 409
        now = utcnow_iso()
        beacon = Beacon(
            id=key,
            uuid=uuid_str.lower(),
            major=major, minor=minor,
            person_id=person_id, person_type=person_type, label=label,
            building_id=building_id,
            tx_power=tx_power,
            created_at=now, updated_at=now,
        )
        beacon_repository.save(beacon)
        self._invalidate_cache()
        return beacon

    def update(self, beacon_id: str, patch: dict) -> Optional[Beacon]:
        if beacon_repository.get_by_id(beacon_id) is None:
            return None
        patch = {**patch, "updated_at": utcnow_iso()}
        beacon_repository.update_fields(beacon_id, patch)
        self._invalidate_cache()

        updated = beacon_repository.get_by_id(beacon_id)
        if updated is None:
            return None

        # If the label changed, immediately patch the live RTDB position node so
        # the Sidebar reflects the new name without waiting for the next solve.
        if "label" in patch and updated.person_id:
            try:
                ref = rtdb.reference(f"/positions/{updated.person_id}")
                # Only patch an existing record — never create one. person_id only
                # matches the /positions key for real Omada devices (reporter_mac ==
                # person_id there); for simulated beacons the key is a MAC instead,
                # so blindly updating here would create an orphaned partial node.
                if ref.get() is not None:
                    ref.update({"label": patch["label"]})
            except Exception as e:
                print(f"[BEACON] WARNING: RTDB label patch failed for {updated.person_id}: {e}")

        return updated

    def delete(self, beacon_id: str) -> bool:
        ok = beacon_repository.delete(beacon_id)
        if ok:
            self._invalidate_cache()
        return ok

    def _invalidate_cache(self) -> None:
        # local import: keeps service<->ingest decoupled at module-load time
        from services.omada_ingest_service import omada_ingest_service
        omada_ingest_service.invalidate_beacon_cache()


beacon_service = BeaconService()
