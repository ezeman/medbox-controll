from datetime import datetime

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    qr_raw: str = Field(min_length=3)


class ScanResult(BaseModel):
    item_id: str
    patient_name: str | None
    drug_code: str
    strength: str | None
    qty: int
    rate: float | None
    diluent: str | None
    administration: str | None
    order_date: str | None
    hn: str
    station_code: str
    bed_no: str | None


class SlotView(BaseModel):
    id: int
    status: str
    station_code: str | None
    item_count: int


class SlotSelectResponse(BaseModel):
    slot_id: int
    batch_id: int
    status: str


class MissionResponse(BaseModel):
    mission_id: int
    batch_id: int
    slot_id: int
    station_code: str
    status: str
    robot_mission_id: str | None
    created_at: datetime


class MessageResponse(BaseModel):
    message: str


class RelayOpenResponse(BaseModel):
    slot_id: int
    status: str
    relay_result: str


class RobotConfig(BaseModel):
    robot_ip: str | None = None
    robot_api_url: str | None = None
