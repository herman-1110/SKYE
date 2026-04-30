from typing import Literal, Optional
from pydantic import BaseModel


class FeedbackRequest(BaseModel):
    feedback: Literal["confirmed", "fixed", "false_alarm"]
    reason: Optional[str] = None
