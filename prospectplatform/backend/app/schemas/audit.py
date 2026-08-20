from pydantic import BaseModel
from datetime import datetime


class AuditRead(BaseModel):
    id: int
    company_id: int
    digital_score: int
    has_https: bool | None
    response_time_ms: int | None
    has_whatsapp: bool | None
    has_cta: bool | None
    has_form: bool | None
    has_scheduling: bool | None
    has_meta_title: bool | None
    has_meta_description: bool | None
    raw_data: str | None
    audited_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditCreate(BaseModel):
    company_id: int
