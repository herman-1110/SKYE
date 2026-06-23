from dataclasses import asdict
from typing import Optional

from firebase_admin import firestore

from config.settings import settings
from models.safety_settings import SafetySettings
from utils.timestamp_utils import utcnow_iso


class SafetySettingsRepository:
    def _doc_ref(self):
        return firestore.client().collection("settings").document("safety")

    def get(self) -> Optional[SafetySettings]:
        doc = self._doc_ref().get()
        if not doc.exists:
            return None
        return SafetySettings(**doc.to_dict())

    def exists(self) -> bool:
        return self._doc_ref().get().exists

    def save(self, s: SafetySettings) -> None:
        self._doc_ref().set(asdict(s))

    def seed_defaults(self) -> None:
        """Idempotently create the settings/safety doc from settings.py defaults."""
        if self.exists():
            return
        self.save(SafetySettings(
            man_down_minutes=settings.MAN_DOWN_MINUTES,
            collision_distance_m=settings.COLLISION_DISTANCE_M,
            updated_at=utcnow_iso(),
        ))


safety_settings_repository = SafetySettingsRepository()
