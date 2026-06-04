from pydantic import BaseModel


class ReportRequest(BaseModel):
    log_id: str
    guard_id: str


class SafetyReportRequest(BaseModel):
    person_id: str
    date_str: str          # "YYYY-MM-DD"
