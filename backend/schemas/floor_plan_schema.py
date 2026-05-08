from pydantic import BaseModel


class FloorPlanCreateRequest(BaseModel):
    user_id: str
    name: str
    url: str                     # Firebase Storage download URL from frontend upload
    storage_path: str            # e.g. floor_plans/uid/timestamp_file.png — for atomic deletion


class ScaleUpdateRequest(BaseModel):
    scale_pixels_per_meter: float


class ActivateRequest(BaseModel):
    user_id: str
