from typing import Dict, Any, Optional
from firebase_admin import db
from models.position import PositionRecord


class PositionRepository:
    _PATH = "/positions"

    def save(self, record: PositionRecord) -> None:
        key = record.beacon_mac.replace(":", "_")
        db.reference(f"{self._PATH}/{key}").set(record.__dict__)

    def get(self, beacon_mac: str) -> Optional[Dict[str, Any]]:
        key = beacon_mac.replace(":", "_")
        return db.reference(f"{self._PATH}/{key}").get()

    def get_all(self) -> Dict[str, Any]:
        """Read all current positions from Firebase."""
        return db.reference(self._PATH).get() or {}

    def delete(self, beacon_mac: str) -> None:
        key = beacon_mac.replace(":", "_")
        db.reference(f"{self._PATH}/{key}").delete()

    def delete_ap_heartbeat(self, mac: str) -> None:
        """Remove /ap_heartbeats/{mac_underscores} from RTDB."""
        key = mac.replace(":", "_")
        db.reference(f"/ap_heartbeats/{key}").delete()


position_repository = PositionRepository()
