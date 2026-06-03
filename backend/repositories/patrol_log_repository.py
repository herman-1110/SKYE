from datetime import datetime
from typing import Any, Dict, List, Optional

from firebase_admin import firestore

from models.patrol_log import PatrolLogRecord


def _iso_to_unix(iso_str: str) -> Optional[int]:
    """Convert ISO 8601 string to Unix timestamp (seconds). Returns None on failure."""
    try:
        return int(datetime.fromisoformat(iso_str).timestamp())
    except (ValueError, AttributeError):
        return None


class PatrolLogRepository:
    """Firestore repository for patrol_logs collection — never imports firebase_admin.db."""

    _COL = "patrol_logs"

    def _db(self):
        return firestore.client()

    def save(self, record: PatrolLogRecord) -> None:
        """Write a PatrolLogRecord as a Firestore document keyed by log_id."""
        self._db().collection(self._COL).document(record.log_id).set(record.__dict__)

    def get(self, log_id: str) -> Optional[Dict[str, Any]]:
        """Read a single patrol log document by ID; returns None if not found."""
        doc = self._db().collection(self._COL).document(log_id).get()
        return doc.to_dict() if doc.exists else None

    def get_by_shift(self, shift_id: str) -> List[Dict[str, Any]]:
        """Query patrol logs where shift_id matches — used by LLM engine at end of shift."""
        docs = self._db().collection(self._COL).where("shift_id", "==", shift_id).stream()
        return [doc.to_dict() for doc in docs]

    def get_by_guard(self, guard_id: str) -> List[Dict[str, Any]]:
        """Query patrol logs where guard_id matches."""
        docs = self._db().collection(self._COL).where("guard_id", "==", guard_id).stream()
        return [doc.to_dict() for doc in docs]

    def get_reportable_shifts(self) -> List[Dict[str, Any]]:
        """Aggregate individual checkpoint records by shift_id.
        Returns one entry per shift that has at least one checkpoint, newest first."""
        # Each PatrolLogRecord document is one checkpoint visit.
        # Group them by shift_id so the frontend sees one selectable entry per shift.
        buckets: Dict[str, Dict] = {}
        for doc in self._db().collection(self._COL).stream():
            data = doc.to_dict()
            sid = data.get("shift_id")
            if not sid:
                continue
            if sid not in buckets:
                buckets[sid] = {
                    "log_id": sid,
                    "guard_id": data.get("guard_id", "Unknown"),
                    "guard_label": data.get("guard_id", "Unknown Guard"),
                    "arrivals": [],
                }
            arr = data.get("actual_arrival")
            if arr:
                buckets[sid]["arrivals"].append(arr)

        result = []
        for info in buckets.values():
            arrivals = sorted(info.pop("arrivals"))
            if not arrivals:
                continue
            info["shift_start"] = _iso_to_unix(arrivals[0])
            info["shift_end"]   = _iso_to_unix(arrivals[-1])
            result.append(info)

        result.sort(key=lambda x: x.get("shift_start") or 0, reverse=True)
        return result[:50]


patrol_log_repository = PatrolLogRepository()
