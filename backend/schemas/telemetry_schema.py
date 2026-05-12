from typing import List
from pydantic import BaseModel


class OmadaMetaSchema(BaseModel):
    access_token: str
    clientId: str = ""
    nbTopic: str = ""


class OmadaReporterSchema(BaseModel):
    name: str = ""
    mac: str
    hwType: str = ""
    swVersion: str = ""
    swBuild: str = ""
    ipv4: str = ""
    time: str = ""


class OmadaBeaconEntrySchema(BaseModel):
    mac: str
    rssi: int
    timestamp: int


class OmadaTelemetryRequest(BaseModel):
    meta: OmadaMetaSchema
    reporter: OmadaReporterSchema
    reported: List[OmadaBeaconEntrySchema]
