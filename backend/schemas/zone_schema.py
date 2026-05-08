from typing import Optional
from pydantic import BaseModel


class ZoneCreateRequest(BaseModel):
    name: str
    color: str = "#3b82f633"
    is_high_risk: bool = False
    x_min: float
    x_max: float
    y_min: float
    y_max: float


class ZoneUpdateRequest(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    is_high_risk: Optional[bool] = None
    x_min: Optional[float] = None
    x_max: Optional[float] = None
    y_min: Optional[float] = None
    y_max: Optional[float] = None
