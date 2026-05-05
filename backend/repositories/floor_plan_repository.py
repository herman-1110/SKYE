from typing import Any, Dict, List, Optional

from firebase_admin import firestore

from models.floor_plan import FloorPlanRecord


class FloorPlanRepository:
    """Firestore repository for floor_plans collection — never imports firebase_admin.db."""

    _COL = "floor_plans"

    def _db(self):
        return firestore.client()

    def save(self, record: FloorPlanRecord) -> None:
        """Write a FloorPlanRecord as a Firestore document keyed by floor_plan_id."""
        self._db().collection(self._COL).document(record.floor_plan_id).set(record.__dict__)

    def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        """Return all floor plans for a user, ordered by uploaded_at descending."""
        docs = (
            self._db().collection(self._COL)
            .where("user_id", "==", user_id)
            .order_by("uploaded_at", direction=firestore.Query.DESCENDING)
            .stream()
        )
        return [doc.to_dict() for doc in docs]

    def get_active(self, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return the active floor plan; scoped to user_id if provided, else any active plan."""
        query = self._db().collection(self._COL).where("is_active", "==", True)
        if user_id:
            query = query.where("user_id", "==", user_id)
        docs = list(query.limit(1).stream())
        return docs[0].to_dict() if docs else None

    def update_scale(self, floor_plan_id: str, scale_pixels_per_meter: float) -> None:
        """Update the scale_pixels_per_meter field on an existing floor plan."""
        self._db().collection(self._COL).document(floor_plan_id).update(
            {"scale_pixels_per_meter": scale_pixels_per_meter}
        )

    def set_active(self, floor_plan_id: str, user_id: str) -> None:
        """Set is_active=True on this plan and is_active=False on all others for the user."""
        db = self._db()
        batch = db.batch()
        for doc in db.collection(self._COL).where("user_id", "==", user_id).stream():
            batch.update(doc.reference, {"is_active": False})
        batch.update(db.collection(self._COL).document(floor_plan_id), {"is_active": True})
        batch.commit()


floor_plan_repository = FloorPlanRepository()
