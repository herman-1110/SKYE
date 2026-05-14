from typing import Literal, Optional
from pydantic import BaseModel


class RegisterRequest(BaseModel):
    id_token: str
    display_name: str
    person_id: Optional[str] = ""


class UpdateRoleRequest(BaseModel):
    role: Literal["admin", "user"]


class UpdateStatusRequest(BaseModel):
    status: Literal["pending", "approved", "suspended"]


class GoogleAuthRequest(BaseModel):
    id_token: str
