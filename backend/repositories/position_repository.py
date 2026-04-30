from typing import Dict, Any, Optional
from firebase_admin import db
from models.position import PositionRecord


class PositionRepository:
    _PATH = "/positions"

    def save(self, record: PositionRecord) -> None:
        """Write a PositionRecord to /positions/{beacon_mac}."""
        db.reference(f"{self._PATH}/{record.beacon_mac}").set(record.__dict__)

    def get(self, beacon_mac: str) -> Optional[Dict[str, Any]]:
        """Read the latest stored position for a beacon MAC; returns None if not found."""
        return db.reference(f"{self._PATH}/{beacon_mac}").get()

    def get_all(self) -> Dict[str, Any]:
        """Read all current positions from Firebase."""
        return db.reference(self._PATH).get() or {}

    def delete(self, beacon_mac: str) -> None:
        """Remove a position entry by beacon MAC."""
        db.reference(f"{self._PATH}/{beacon_mac}").delete()


position_repository = PositionRepository()
