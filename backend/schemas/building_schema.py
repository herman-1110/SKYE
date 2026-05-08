from pydantic import BaseModel


class BuildingCreateRequest(BaseModel):
    name: str
    description: str = ""


class BuildingUpdateRequest(BaseModel):
    name: str
