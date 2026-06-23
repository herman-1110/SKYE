from utils.timestamp_utils import utcnow_iso
from models.safety_settings import SafetySettings
from repositories.safety_settings_repository import safety_settings_repository
from config.settings import settings


class SafetySettingsService:
    def get(self) -> SafetySettings:
        s = safety_settings_repository.get()
        if s is None:
            s = SafetySettings(
                man_down_minutes=settings.MAN_DOWN_MINUTES,
                collision_distance_m=settings.COLLISION_DISTANCE_M,
            )
        return s

    def update(self, man_down_minutes: int, collision_distance_m: float) -> SafetySettings:
        s = SafetySettings(
            man_down_minutes=man_down_minutes,
            collision_distance_m=collision_distance_m,
            updated_at=utcnow_iso(),
        )
        safety_settings_repository.save(s)
        self._invalidate_cache()
        return s

    def _invalidate_cache(self) -> None:
        # local import: keeps service<->safety_service decoupled at module-load time
        from services.safety_service import safety_service
        safety_service.invalidate_settings_cache()


safety_settings_service = SafetySettingsService()
