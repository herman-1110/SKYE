from pydantic import BaseModel
from typing import Optional


class FloorCreateRequest(BaseModel):
    name: Optional[str] = None
    floor_number: int = 1
    url: str
    storage_path: str


class FloorUpdateRequest(BaseModel):
    name: Optional[str] = None
    floor_number: Optional[int] = None


class FloorScaleRequest(BaseModel):
    scale_pixels_per_meter: float
