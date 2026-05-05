import uuid
from typing import Any, Dict, List, Optional

from models.floor_plan import FloorPlanRecord
from repositories.floor_plan_repository import floor_plan_repository
from utils.timestamp_utils import utcnow_iso


class FloorPlanService:

    def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        """Return all floor plans for a user ordered by upload date."""
        return floor_plan_repository.get_all(user_id)

    def get_active(self, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return the currently active floor plan, optionally scoped to a user."""
        return floor_plan_repository.get_active(user_id)

    def create(self, user_id: str, name: str, url: str) -> FloorPlanRecord:
        """Create and persist a new floor plan record after the image is in Storage."""
        record = FloorPlanRecord(
            floor_plan_id=str(uuid.uuid4()),
            user_id=user_id,
            name=name,
            url=url,
            uploaded_at=utcnow_iso(),
            is_active=False,
        )
        floor_plan_repository.save(record)
        return record

    def update_scale(self, floor_plan_id: str, scale_pixels_per_meter: float) -> None:
        """Persist calibrated scale after the user marks two reference points on the map."""
        if scale_pixels_per_meter <= 0:
            raise ValueError("scale_pixels_per_meter must be positive")
        floor_plan_repository.update_scale(floor_plan_id, scale_pixels_per_meter)

    def set_active(self, floor_plan_id: str, user_id: str) -> None:
        """Activate a floor plan — deactivates all others for the same user."""
        floor_plan_repository.set_active(floor_plan_id, user_id)


floor_plan_service = FloorPlanService()
