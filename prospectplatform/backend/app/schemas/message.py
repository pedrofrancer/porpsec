from pydantic import BaseModel
from datetime import datetime


class MessageRead(BaseModel):
    id: int
    company_id: int
    opportunity_ids: str
    message_text: str
    status: str
    generated_at: datetime
    approved_at: datetime | None
    sent_at: datetime | None
    llm_model: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageCreateRequest(BaseModel):
    company_id: int


class MessageUpdateStatus(BaseModel):
    status: str
