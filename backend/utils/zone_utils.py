from typing import Optional

from models.zone import ZoneRecord
from repositories.zone_repository import zone_repository


def coordinate_to_zone(
    x: float,
    y: float,
    building_id: Optional[str] = None,
    floor_id: Optional[str] = None,
) -> str:
    """Map (x, y) metres to a named zone. Returns 'unknown' if ids absent or no match."""
    if not building_id or not floor_id:
        return "unknown"

    zones: list[ZoneRecord] = zone_repository.get_all(building_id, floor_id)
    for zone in zones:
        if zone.x_min <= x <= zone.x_max and zone.y_min <= y <= zone.y_max:
            return zone.name

    return "unknown"


def is_high_risk_zone(
    x: float,
    y: float,
    building_id: Optional[str] = None,
    floor_id: Optional[str] = None,
) -> bool:
    """Return True if the coordinate falls inside a high-risk zone."""
    if not building_id or not floor_id:
        return False

    zones: list[ZoneRecord] = zone_repository.get_all(building_id, floor_id)
    for zone in zones:
        if zone.x_min <= x <= zone.x_max and zone.y_min <= y <= zone.y_max:
            return zone.is_high_risk

    return False


def is_high_risk(
    x: float,
    y: float,
    building_id: str,
    floor_id: str,
) -> bool:
    """Public alias — returns True if (x, y) falls in a high-risk zone."""
    return is_high_risk_zone(x, y, building_id, floor_id)
