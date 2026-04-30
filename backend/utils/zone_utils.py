from typing import Dict, List, Tuple

# Zone definitions: name → list of axis-aligned rectangles (x_min, y_min, x_max, y_max) in metres.
# Must stay in sync with the frontend ZoneOverlay component.
ZONES: Dict[str, List[Tuple[float, float, float, float]]] = {
    "loading_bay":        [(0.0,  0.0, 20.0, 10.0)],
    "forklift_corridor":  [(0.0, 10.0, 40.0, 15.0)],
    "assembly_floor":     [(20.0, 0.0, 60.0, 30.0)],
    "storage_rack_a":     [(60.0, 0.0, 80.0, 15.0)],
    "storage_rack_b":     [(60.0, 15.0, 80.0, 30.0)],
    "control_room":       [(0.0, 30.0, 15.0, 40.0)],
    "exit_corridor":      [(15.0, 30.0, 80.0, 40.0)],
}

HIGH_RISK_ZONES = frozenset({"loading_bay", "forklift_corridor", "storage_rack_a", "storage_rack_b"})


def coordinate_to_zone(x: float, y: float) -> str:
    """Map (x, y) metres to a named factory zone; returns 'unknown' if outside all zones."""
    for zone_name, rects in ZONES.items():
        for x_min, y_min, x_max, y_max in rects:
            if x_min <= x <= x_max and y_min <= y <= y_max:
                return zone_name
    return "unknown"


def is_high_risk(zone: str) -> bool:
    """Return True if the zone is classified as high-risk for man-down / collision detection."""
    return zone in HIGH_RISK_ZONES
