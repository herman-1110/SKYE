from typing import Optional

from repositories.alert_repository import alert_repository
from repositories.patrol_log_repository import patrol_log_repository
from repositories.position_repository import position_repository


class GuardService:
    def get_position(self, person_id: str) -> Optional[dict]:
        """Return the live position entry matching person_id, or None."""
        all_positions = position_repository.get_all()
        for entry in all_positions.values():
            if isinstance(entry, dict) and entry.get("person_id") == person_id:
                return entry
        return None

    def get_patrol(self, guard_id: str) -> list:
        """Return patrol log entries for this guard only."""
        return patrol_log_repository.get_by_guard(guard_id)

    def get_alerts(self, person_id: str) -> list:
        """Return alerts where person_id matches the calling guard only."""
        all_alerts = alert_repository.get_all()
        if isinstance(all_alerts, dict):
            return [a for a in all_alerts.values() if isinstance(a, dict) and a.get("person_id") == person_id]
        return []


guard_service = GuardService()
