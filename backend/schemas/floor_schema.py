from pydantic import BaseModel
from typing import Optional


class FloorCreateRequest(BaseModel):
    name: Optional[str] = None
    floor_number: int = 1
    url: str
    storage_path: str
    image_width_px: Optional[int] = None
    image_height_px: Optional[int] = None


class FloorUpdateRequest(BaseModel):
    name: Optional[str] = None
    floor_number: Optional[int] = None


class CalibrationPointRequest(BaseModel):
    x_pct: Optional[float] = None
    y_pct: Optional[float] = None


class CalibrationRequest(BaseModel):
    """The two points (image fractions) and the real distance between them
    (Prompt 142, D3). Every field is optional here so that a missing one gets
    floor_service's one-sentence 422 rather than pydantic's list."""
    a: Optional[CalibrationPointRequest] = None
    b: Optional[CalibrationPointRequest] = None
    distance_m: Optional[float] = None


class FloorScaleRequest(BaseModel):
    scale_pixels_per_meter: float
    # Without it, the floor's stored calibration is cleared.
    calibration: Optional[CalibrationRequest] = None
