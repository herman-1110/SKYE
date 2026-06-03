from pydantic import BaseModel


class ReportRequest(BaseModel):
    log_id: str
