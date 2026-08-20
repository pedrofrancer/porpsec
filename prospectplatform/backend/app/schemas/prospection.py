from pydantic import BaseModel
from datetime import datetime


class ProspectingQueueRead(BaseModel):
    id: int
    company_id: int
    status: str
    assigned_to: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime | None
    last_followup_at: datetime | None

    model_config = {"from_attributes": True}


class ProspectingQueueCreate(BaseModel):
    company_id: int
    notes: str | None = None


class ProspectingStatusUpdate(BaseModel):
    status: str


class OptOutCreate(BaseModel):
    contact_identifier: str
    reason: str | None = None
    source: str | None = None


class OptOutRead(BaseModel):
    id: int
    contact_identifier: str
    reason: str | None
    source: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ActionLogRead(BaseModel):
    id: int
    company_id: int | None
    contact_id: str | None
    action: str
    details: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class QueueStats(BaseModel):
    total: int
    by_status: dict[str, int]
    stale_count: int
